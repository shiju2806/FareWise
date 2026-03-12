"""Typed conversation state for multi-agent trip planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

STATE_VERSION = 5


@dataclass
class LegState:
    """State for a single trip leg."""

    sequence: int = 1
    origin_city: str = ""
    origin_airport: str = ""
    destination_city: str = ""
    destination_airport: str = ""
    preferred_date: date | None = None
    flexibility_days: int = 3
    cabin_class: str = "economy"
    passengers: int = 1
    preferred_airline: str = ""  # IATA code, e.g. "AC"
    # Populated by FlightSearchAgent
    searched: bool = False
    anchor_flight: dict | None = None
    anchor_price: float | None = None


@dataclass
class CompanionState:
    """State for companion / family travel.

    count semantics:
      -1 = unknown (user hasn't mentioned companions)
       0 = solo (user explicitly said "just me" / "solo")
       1+ = number of companions
    """

    count: int = -1
    asked: bool = False
    recommended_cabin: str | None = None
    budget_calculated: bool = False
    # Phase H — companion date tracking
    same_dates: bool | None = None    # None=not asked, True=same dates, False=different
    dates_asked: bool = False         # whether we've asked the date question


@dataclass
class ConversationState:
    """Complete conversation state passed between agents."""

    legs: list[LegState] = field(default_factory=list)
    companions: CompanionState = field(default_factory=CompanionState)
    stage: Literal["planning", "searching", "budgeting", "ready"] = "planning"
    trip_ready: bool = False
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 0.0
    interpretation_notes: str = ""
    def to_llm_context(self) -> str:
        """Render state as concise text for the LLM system prompt."""
        if not self.legs:
            return "No trip data yet."

        parts = []
        for leg in self.legs:
            s = f"Leg {leg.sequence}: "
            s += f"{leg.origin_city} ({leg.origin_airport})" if leg.origin_airport else "? (?)"
            s += " -> "
            s += f"{leg.destination_city} ({leg.destination_airport})" if leg.destination_airport else "? (?)"
            if leg.preferred_date:
                s += f" on {leg.preferred_date.isoformat()}"
            s += f" ({leg.cabin_class})"
            if leg.preferred_airline:
                s += f" pref:{leg.preferred_airline}"
            if leg.searched:
                price_str = f"${leg.anchor_price:,.0f}" if leg.anchor_price else "no anchor"
                s += f" [SEARCHED, {price_str}]"
            parts.append(s)

        lines = "\n".join(parts)
        lines += f"\nCompanions: count={self.companions.count}"
        lines += " (-1=unknown, 0=solo confirmed, 1+=count)"
        lines += f", asked={self.companions.asked}"
        lines += f", dates_asked={self.companions.dates_asked}"
        lines += f", same_dates={self.companions.same_dates}"
        lines += f", budget_calculated={self.companions.budget_calculated}"
        lines += f"\nStage: {self.stage}"
        return lines

    # ------------------------------------------------------------------
    # Serialisation helpers (legacy partial_trip ↔ typed state)
    # ------------------------------------------------------------------

    def to_partial_trip(self) -> dict:
        """Convert to the dict format the frontend sends/receives."""
        return {
            "confidence": self.confidence,
            "legs": [
                {
                    "sequence": leg.sequence,
                    "origin_city": leg.origin_city,
                    "origin_airport": leg.origin_airport,
                    "destination_city": leg.destination_city,
                    "destination_airport": leg.destination_airport,
                    "preferred_date": leg.preferred_date.isoformat() if leg.preferred_date else None,
                    "flexibility_days": leg.flexibility_days,
                    "cabin_class": leg.cabin_class,
                    "passengers": leg.passengers,
                }
                for leg in self.legs
            ],
            "companions": max(0, self.companions.count),
            "companion_cabin_class": self.companions.recommended_cabin or "economy",
            "companions_same_dates": self.companions.same_dates,
            "interpretation_notes": self.interpretation_notes,
            # Agent-specific state that needs to survive round-trips
            "_agent_state": {
                "_version": STATE_VERSION,
                "stage": self.stage,
                "companions_count": self.companions.count,
                "companions_asked": self.companions.asked,
                "companions_same_dates": self.companions.same_dates,
                "companions_dates_asked": self.companions.dates_asked,
                "companions_budget_calculated": self.companions.budget_calculated,
                "legs_searched": [
                    {
                        "searched": leg.searched,
                        "anchor_price": leg.anchor_price,
                        "anchor_flight": leg.anchor_flight,
                        "preferred_airline": leg.preferred_airline,
                    }
                    for leg in self.legs
                ],
            },
        }

    @classmethod
    def from_partial_trip(cls, partial: dict | None) -> ConversationState:
        """Hydrate from the frontend's partial_trip dict."""
        if not partial:
            return cls()

        agent_state = partial.get("_agent_state", {})

        # Version mismatch → reset agent-internal state, keep legs
        if agent_state.get("_version", 0) < STATE_VERSION:
            agent_state = {}

        legs_searched = agent_state.get("legs_searched", [])

        legs: list[LegState] = []
        for i, leg_data in enumerate(partial.get("legs", [])):
            pdate = leg_data.get("preferred_date")
            search_info = legs_searched[i] if i < len(legs_searched) else {}
            legs.append(
                LegState(
                    sequence=leg_data.get("sequence", i + 1),
                    origin_city=leg_data.get("origin_city", ""),
                    origin_airport=leg_data.get("origin_airport", ""),
                    destination_city=leg_data.get("destination_city", ""),
                    destination_airport=leg_data.get("destination_airport", ""),
                    preferred_date=date.fromisoformat(pdate) if pdate else None,
                    flexibility_days=leg_data.get("flexibility_days", 3),
                    cabin_class=leg_data.get("cabin_class", "economy"),
                    passengers=leg_data.get("passengers", 1),
                    preferred_airline=search_info.get("preferred_airline", leg_data.get("preferred_airline", "")),
                    searched=search_info.get("searched", False),
                    anchor_price=search_info.get("anchor_price"),
                    anchor_flight=search_info.get("anchor_flight"),
                )
            )

        return cls(
            legs=legs,
            companions=CompanionState(
                count=agent_state.get("companions_count", partial.get("companions", -1)),
                asked=agent_state.get("companions_asked", False),
                recommended_cabin=partial.get("companion_cabin_class"),
                budget_calculated=agent_state.get("companions_budget_calculated", False),
                same_dates=agent_state.get("companions_same_dates"),
                dates_asked=agent_state.get("companions_dates_asked", False),
            ),
            stage=agent_state.get("stage", "planning"),
            confidence=partial.get("confidence", 0.0),
            interpretation_notes=partial.get("interpretation_notes", ""),
        )
