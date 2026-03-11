"""Tests for ConversationState serialization, versioning, and LLM context."""

import pytest
from datetime import date

from app.services.agents.conversation_state import (
    ConversationState,
    CompanionState,
    LegState,
    STATE_VERSION,
)


class TestRoundTrip:
    """State -> dict -> state round-trip preserves all fields."""

    def test_empty_state_round_trip(self):
        state = ConversationState()
        d = state.to_partial_trip()
        restored = ConversationState.from_partial_trip(d)

        assert restored.legs == []
        assert restored.companions.count == -1  # Unknown by default
        assert restored.stage == "planning"
        assert restored.trip_ready is False

    def test_full_state_round_trip(self):
        state = ConversationState(
            legs=[
                LegState(
                    sequence=1,
                    origin_city="Toronto",
                    origin_airport="YYZ",
                    destination_city="London",
                    destination_airport="LHR",
                    preferred_date=date(2026, 4, 12),
                    flexibility_days=5,
                    cabin_class="business",
                    passengers=1,
                    searched=True,
                    anchor_price=4882.0,
                    anchor_flight={"airline": "BA", "price": 4882},
                ),
                LegState(
                    sequence=2,
                    origin_city="London",
                    origin_airport="LHR",
                    destination_city="Toronto",
                    destination_airport="YYZ",
                    preferred_date=date(2026, 4, 18),
                    cabin_class="business",
                    searched=True,
                    anchor_price=4470.0,
                ),
            ],
            companions=CompanionState(count=3, asked=True, recommended_cabin="premium_economy", budget_calculated=True),
            stage="ready",
            trip_ready=True,
            confidence=0.95,
            interpretation_notes="Shifted to Sunday",
        )
        d = state.to_partial_trip()
        restored = ConversationState.from_partial_trip(d)

        assert len(restored.legs) == 2
        assert restored.legs[0].origin_airport == "YYZ"
        assert restored.legs[0].preferred_date == date(2026, 4, 12)
        assert restored.legs[0].searched is True
        assert restored.legs[0].anchor_price == 4882.0
        assert restored.legs[1].anchor_price == 4470.0
        assert restored.companions.count == 3
        assert restored.companions.asked is True
        assert restored.companions.budget_calculated is True
        assert restored.stage == "ready"
        assert restored.confidence == 0.95


class TestFromPartialTrip:
    """Edge cases for from_partial_trip."""

    def test_none_returns_empty(self):
        state = ConversationState.from_partial_trip(None)
        assert state.legs == []
        assert state.stage == "planning"

    def test_empty_dict_returns_empty(self):
        state = ConversationState.from_partial_trip({})
        assert state.legs == []

    def test_missing_agent_state(self):
        partial = {
            "legs": [
                {
                    "sequence": 1,
                    "origin_city": "NYC",
                    "origin_airport": "JFK",
                    "destination_city": "Chicago",
                    "destination_airport": "ORD",
                    "preferred_date": "2026-03-15",
                    "cabin_class": "economy",
                }
            ],
            "confidence": 0.9,
        }
        state = ConversationState.from_partial_trip(partial)
        assert len(state.legs) == 1
        assert state.legs[0].origin_airport == "JFK"
        assert state.legs[0].searched is False  # No _agent_state
        assert state.stage == "planning"


class TestVersioning:
    """State versioning resets agent-internal state on mismatch."""

    def test_current_version_is_4(self):
        assert STATE_VERSION == 4

    def test_current_version_preserved(self):
        state = ConversationState(
            legs=[LegState(searched=True, anchor_price=100)],
            companions=CompanionState(asked=True),
            stage="budgeting",
        )
        d = state.to_partial_trip()
        assert d["_agent_state"]["_version"] == STATE_VERSION

        restored = ConversationState.from_partial_trip(d)
        assert restored.legs[0].searched is True
        assert restored.companions.asked is True
        assert restored.stage == "budgeting"

    def test_old_version_resets_agent_state(self):
        partial = {
            "legs": [
                {
                    "sequence": 1,
                    "origin_city": "NYC",
                    "origin_airport": "JFK",
                    "destination_city": "London",
                    "destination_airport": "LHR",
                    "preferred_date": "2026-04-15",
                    "cabin_class": "business",
                }
            ],
            "_agent_state": {
                "_version": 3,  # Old version (< 4)
                "stage": "budgeting",
                "companions_asked": True,
                "legs_searched": [{"searched": True, "anchor_price": 5000}],
            },
        }
        state = ConversationState.from_partial_trip(partial)
        # Legs preserved but agent state reset
        assert state.legs[0].origin_airport == "JFK"
        assert state.legs[0].searched is False  # Reset
        assert state.companions.asked is False  # Reset
        assert state.stage == "planning"  # Reset


class TestToLlmContext:
    """to_llm_context() renders state as concise text for LLM."""

    def test_empty_state(self):
        state = ConversationState()
        assert state.to_llm_context() == "No trip data yet."

    def test_single_leg_unsearched(self):
        state = ConversationState(
            legs=[LegState(
                sequence=1,
                origin_city="Toronto",
                origin_airport="YYZ",
                destination_city="London",
                destination_airport="LHR",
                preferred_date=date(2026, 4, 12),
                cabin_class="business",
            )],
        )
        ctx = state.to_llm_context()
        assert "Toronto (YYZ)" in ctx
        assert "London (LHR)" in ctx
        assert "2026-04-12" in ctx
        assert "(business)" in ctx
        assert "[SEARCHED" not in ctx

    def test_searched_leg_shows_marker(self):
        state = ConversationState(
            legs=[LegState(
                sequence=1,
                origin_city="Toronto",
                origin_airport="YYZ",
                destination_city="London",
                destination_airport="LHR",
                preferred_date=date(2026, 4, 12),
                cabin_class="business",
                preferred_airline="AC",
                searched=True,
                anchor_price=3694.0,
            )],
        )
        ctx = state.to_llm_context()
        assert "[SEARCHED, $3,694]" in ctx
        assert "pref:AC" in ctx

    def test_companions_context(self):
        state = ConversationState(
            legs=[LegState(sequence=1, origin_airport="YYZ", destination_airport="LHR")],
            companions=CompanionState(count=3, asked=True, budget_calculated=True),
        )
        ctx = state.to_llm_context()
        assert "count=3" in ctx
        assert "asked=True" in ctx
        assert "budget_calculated=True" in ctx

    def test_stage_shown(self):
        state = ConversationState(
            legs=[LegState(sequence=1, origin_airport="YYZ", destination_airport="LHR")],
            stage="budgeting",
        )
        ctx = state.to_llm_context()
        assert "Stage: budgeting" in ctx
