"""CompanionBudgetAgent — pure budget calculation for companion travel."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import ClassVar

from app.services.flight_provider import flight_provider
from app.services.agents.base import TripAgent, AgentResponse
from app.services.agents.conversation_state import ConversationState

logger = logging.getLogger(__name__)


class CompanionBudgetAgent(TripAgent):
    """Calculates cabin budget options for companion travel.

    No LLM calls — this is a pure computation agent. The coordinator
    calls this only when companions.count is known and > 0.
    """

    requires: ClassVar[set[str]] = {"legs.anchor_price", "companions.count"}
    provides: ClassVar[set[str]] = {"companions.recommended_cabin", "companions.budget_calculated"}

    def check_preconditions(self, state) -> str | None:
        if not any(l.anchor_price for l in state.legs):
            return "No anchor prices available — flight search must run first"
        if state.companions.count <= 0:
            return "No companions to calculate budget for"
        return None

    async def process(
        self,
        user_message: str,
        state: ConversationState,
        conversation_history: list[dict],
    ) -> AgentResponse:
        total_travelers = 1 + state.companions.count
        budget_result = await self._calculate_cabin_budget(state, total_travelers)

        state.companions.budget_calculated = True
        state.companions.recommended_cabin = budget_result["recommended_cabin"]
        state.stage = "ready"
        state.trip_ready = True

        reply = f"Great, {total_travelers} travelers total!\n\n{budget_result['reason']}"
        blocks = [{"type": "budget_card", "data": budget_result}]

        return AgentResponse(
            content=reply,
            blocks=blocks,
            state=state,
            trip_ready=True,
        )

    async def _search_cabin_leg(
        self, cabin: str, leg_origin: str, leg_dest: str, leg_date, leg_seq: int,
    ) -> tuple[str, int, float]:
        """Search cheapest flight for a cabin x leg combo. Returns (cabin, seq, price)."""
        try:
            flights = await flight_provider.search_flights(
                origin=leg_origin,
                destination=leg_dest,
                departure_date=leg_date,
                cabin_class=cabin,
            )
        except Exception as e:
            logger.warning("Budget search failed for %s %s: %s", cabin, leg_origin, e)
            flights = []

        if flights:
            flights.sort(key=lambda f: f.get("price", float("inf")))
            return cabin, leg_seq, flights[0]["price"]
        return cabin, leg_seq, 0

    async def _calculate_cabin_budget(
        self,
        state: ConversationState,
        total_travelers: int,
    ) -> dict:
        """Standalone cabin budget calculator — no DB or trip_id needed."""
        # Compute anchor budget
        anchor_total = sum(leg.anchor_price for leg in state.legs if leg.anchor_price)
        tolerance = 0.15
        ceiling = anchor_total * (1 + tolerance)

        # Build all search tasks upfront (3 cabins x N legs = parallel)
        tasks = []
        for cabin in ["business", "premium_economy", "economy"]:
            for leg in state.legs:
                if not leg.preferred_date:
                    continue
                tasks.append(
                    self._search_cabin_leg(
                        cabin, leg.origin_airport, leg.destination_airport,
                        leg.preferred_date, leg.sequence,
                    )
                )

        search_start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        search_ms = (time.perf_counter() - search_start) * 1000

        logger.info(
            "budget_search.complete",
            extra={
                "searches": len(tasks),
                "duration_ms": round(search_ms),
            },
        )

        # Group results by cabin
        cabin_prices: dict[str, list[float]] = {
            "business": [], "premium_economy": [], "economy": [],
        }
        for cabin, _seq, price in results:
            cabin_prices[cabin].append(price)

        cabin_options: list[dict] = []
        for cabin in ["business", "premium_economy", "economy"]:
            total_per_person = sum(cabin_prices[cabin])
            total_all = total_per_person * total_travelers
            fits = total_all <= ceiling

            cabin_options.append({
                "cabin": cabin,
                "total_per_person": round(total_per_person),
                "total_all_travelers": round(total_all),
                "fits": fits,
                "delta": round(anchor_total - total_all),
            })

        # Pick highest cabin that fits
        recommended = "economy"
        for opt in cabin_options:
            if opt["fits"]:
                recommended = opt["cabin"]
                break

        rec_opt = next(o for o in cabin_options if o["cabin"] == recommended)
        delta = abs(rec_opt["delta"])
        delta_pct = round(delta / anchor_total * 100) if anchor_total else 0
        over_under = "under" if rec_opt["delta"] >= 0 else "over"

        reason = (
            f"All {total_travelers} travelers can fly {recommended.replace('_', ' ').title()} "
            f"for ${rec_opt['total_all_travelers']:,} — "
            f"${delta:,} {over_under} your ${anchor_total:,.0f} business class budget."
        )

        return {
            "anchor_total": round(anchor_total),
            "total_travelers": total_travelers,
            "recommended_cabin": recommended,
            "reason": reason,
            "cabin_options": cabin_options,
        }
