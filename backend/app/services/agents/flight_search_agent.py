"""FlightSearchAgent — searches flights for each leg, selects anchor prices."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date as date_cls
from typing import ClassVar

from app.services.flight_provider import flight_provider
from app.services.anchor_selector import select_anchor_flight, build_anchor_alternatives
from app.services.agents.base import TripAgent, AgentResponse
from app.services.agents.conversation_state import ConversationState

logger = logging.getLogger(__name__)


class FlightSearchAgent(TripAgent):
    """Searches flights for all legs and selects anchor prices."""

    requires: ClassVar[set[str]] = {"legs.origin_airport", "legs.preferred_date"}
    provides: ClassVar[set[str]] = {"legs.searched", "legs.anchor_price", "legs.anchor_flight"}

    def check_preconditions(self, state) -> str | None:
        if not state.legs:
            return "No trip legs defined"
        for leg in state.legs:
            if not leg.origin_airport or not leg.destination_airport:
                return f"Leg {leg.sequence}: missing airport codes"
            if not leg.preferred_date:
                return f"Leg {leg.sequence}: missing preferred date"
        return None

    async def _search_single_leg(
        self, info: dict
    ) -> tuple[list[dict], Exception | None]:
        """Search flights for a single leg. Returns (flights, error)."""
        try:
            flights = await flight_provider.search_flights(
                origin=info["origin"],
                destination=info["destination"],
                departure_date=date_cls.fromisoformat(info["date"]),
                cabin_class=info["cabin_class"],
            )
            return flights, None
        except Exception as e:
            logger.error("Flight search failed for %s: %s", info["route_label"], e)
            return [], e

    async def process(
        self,
        user_message: str,
        state: ConversationState,
        conversation_history: list[dict],
    ) -> AgentResponse:
        # Build search info from state legs
        legs_info = []
        for leg in state.legs:
            if not leg.preferred_date:
                continue
            legs_info.append({
                "origin": leg.origin_airport,
                "destination": leg.destination_airport,
                "date": leg.preferred_date.isoformat(),
                "cabin_class": leg.cabin_class,
                "preferred_airline": leg.preferred_airline,
                "route_label": f"{leg.origin_city} ({leg.origin_airport}) → {leg.destination_city} ({leg.destination_airport})",
            })

        if not legs_info:
            return AgentResponse(
                content="I need route and date information before I can search flights.",
                state=state,
            )

        # Parallel flight search across all legs
        search_start = time.perf_counter()
        results = await asyncio.gather(
            *[self._search_single_leg(info) for info in legs_info]
        )
        search_ms = (time.perf_counter() - search_start) * 1000

        logger.info(
            "flight_search.complete",
            extra={
                "legs_searched": len(legs_info),
                "duration_ms": round(search_ms),
                "total_flights": sum(len(r[0]) for r in results),
            },
        )

        blocks: list[dict] = []
        anchor_total = 0.0
        reply_parts: list[str] = []

        for i, (flights, err) in enumerate(results):
            info = legs_info[i]
            preferred = info.get("preferred_airline") or None
            anchor = select_anchor_flight(flights, info["cabin_class"], preferred) if flights else None

            # Update state
            if i < len(state.legs):
                state.legs[i].searched = True
                state.legs[i].anchor_flight = anchor
                state.legs[i].anchor_price = anchor["price"] if anchor else None

            # Price range
            prices = [f.get("price", 0) for f in flights if f.get("price")]
            price_min = min(prices) if prices else 0
            price_max = max(prices) if prices else 0

            # Build structured block
            block_data: dict = {
                "route": info["route_label"],
                "date": info["date"],
                "cabin_class": info["cabin_class"],
                "alternatives_count": len(flights),
                "price_range": {"min": round(price_min), "max": round(price_max)},
            }

            if anchor:
                anchor_total += anchor["price"]
                block_data["anchor"] = {
                    "airline": anchor.get("airline_name", anchor.get("airline_code", "")),
                    "airline_code": anchor.get("airline_code", ""),
                    "flight_number": anchor.get("flight_number", ""),
                    "price": round(anchor["price"]),
                    "stops": anchor.get("stops", 0),
                    "departure": anchor.get("departure_time", ""),
                    "duration_minutes": anchor.get("duration_minutes"),
                    "reason": anchor.get("anchor_reason", ""),
                }
                # Build alternatives for the card
                alternatives = build_anchor_alternatives(
                    flights, anchor, info["cabin_class"], preferred,
                )
                if alternatives:
                    block_data["alternatives"] = alternatives
                stops_label = "direct" if anchor.get("stops", 0) == 0 else f"{anchor['stops']} stop"
                reply_parts.append(
                    f"{info['route_label']} on {info['date']}: "
                    f"{anchor.get('airline_name', '')} ${anchor['price']:,.0f} ({stops_label})"
                )
            else:
                reply_parts.append(
                    f"{info['route_label']} on {info['date']}: "
                    f"{len(flights)} options from ${price_min:,.0f}" if flights
                    else f"{info['route_label']}: no flights found"
                )

            blocks.append({"type": "flight_card", "data": block_data})

        # Build reply text
        if len(legs_info) > 1 and anchor_total > 0:
            reply = "Here are the smart defaults I've picked for your trip:\n\n"
            reply += "\n".join(f"  {p}" for p in reply_parts)
            reply += f"\n\nRound-trip anchor total: ${anchor_total:,.0f}"
        elif reply_parts:
            reply = reply_parts[0]
        else:
            reply = "I couldn't find flights for your route."

        state.stage = "budgeting"

        return AgentResponse(
            content=reply,
            blocks=blocks,
            state=state,
            trip_ready=False,
        )
