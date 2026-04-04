"""CompanionBudgetAgent — cabin budget calculation with LLM advisor for companion travel."""

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

    Gathers pricing data via parallel flight searches, then delegates the
    recommendation decision to CompanionBudgetAdvisor (LLM-driven with
    rule-based fallback).
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
        employee_airline: str = "",
    ) -> tuple[str, int, float, str]:
        """Search cheapest flight for a cabin x leg combo.

        Returns (cabin, seq, price, airline_code).
        Prefers the same airline as the employee's anchor selection.
        """
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
            # Prefer same airline as employee's selection
            if employee_airline:
                same_airline = [f for f in flights if f.get("airline_code") == employee_airline]
                if same_airline:
                    best = same_airline[0]
                    return cabin, leg_seq, best["price"], best.get("airline_code", "")
            best = flights[0]
            return cabin, leg_seq, best["price"], best.get("airline_code", "")
        return cabin, leg_seq, 0, ""

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
                # Extract employee's airline from anchor flight for same-airline preference
                emp_airline = (leg.anchor_flight or {}).get("airline_code", "")
                tasks.append(
                    self._search_cabin_leg(
                        cabin, leg.origin_airport, leg.destination_airport,
                        leg.preferred_date, leg.sequence, emp_airline,
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
        cabin_airlines: dict[str, list[str]] = {
            "business": [], "premium_economy": [], "economy": [],
        }
        for cabin, _seq, price, airline_code in results:
            cabin_prices[cabin].append(price)
            cabin_airlines[cabin].append(airline_code)

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
                "airline_codes": cabin_airlines[cabin],
            })

        # Build route summary for the advisor
        route_parts = []
        for leg in state.legs:
            if leg.origin_airport and leg.destination_airport:
                route_parts.append(f"{leg.origin_airport} \u2192 {leg.destination_airport}")
        route_summary = ", ".join(route_parts)

        # LLM advisor for recommendation (with rule-based fallback)
        from app.services.recommendation.companion_advisor import companion_budget_advisor

        advisor_output = await companion_budget_advisor.advise(
            cabin_options=cabin_options,
            budget=anchor_total,
            total_travelers=total_travelers,
            employee_cabin=state.legs[0].cabin_class if state.legs else "business",
            employee_airline=state.legs[0].preferred_airline if state.legs else "",
            route_summary=route_summary,
        )

        return {
            "anchor_total": round(anchor_total),
            "total_travelers": total_travelers,
            "recommended_cabin": advisor_output.recommended_cabin,
            "reason": advisor_output.reasoning,
            "near_miss_note": advisor_output.near_miss_note,
            "savings_note": advisor_output.savings_note,
            "cabin_options": cabin_options,
            "source": advisor_output.source,
        }
