"""Tests for TripCoordinator — LLM-driven tool-calling architecture."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agents.base import AgentResponse
from app.services.agents.conversation_state import ConversationState, LegState, CompanionState
from app.services.agents.trip_coordinator import TripCoordinator


@pytest.fixture
def coordinator():
    return TripCoordinator()


@pytest.fixture
def empty_state():
    return ConversationState()


def _llm_result(content: str = "", tool_calls: list | None = None) -> dict:
    """Build a mock complete_with_tools response."""
    return {
        "content": content,
        "tool_calls": tool_calls or [],
        "stop_reason": "end_turn" if not tool_calls else "tool_use",
    }


class TestToolCallingFlow:
    """LLM decides what tools to call, coordinator just executes them."""

    @pytest.mark.anyio
    async def test_update_and_search(self, coordinator, empty_state):
        """LLM calls update_trip + search_flights → flight cards appear."""
        llm_response = _llm_result(
            content="Toronto to London, business, Air Canada.",
            tool_calls=[
                {
                    "name": "update_trip",
                    "arguments": {
                        "legs": [{
                            "sequence": 1,
                            "origin_city": "Toronto",
                            "origin_airport": "YYZ",
                            "destination_city": "London",
                            "destination_airport": "LHR",
                            "preferred_date": "2026-04-12",
                            "flexibility_days": 5,
                            "cabin_class": "business",
                            "passengers": 1,
                            "preferred_airline": "AC",
                        }],
                        "confidence": 0.95,
                    },
                },
                {"name": "search_flights", "arguments": {}},
            ],
        )

        search_state = ConversationState(
            legs=[LegState(
                sequence=1, origin_city="Toronto", origin_airport="YYZ",
                destination_city="London", destination_airport="LHR",
                preferred_date=date(2026, 4, 12), cabin_class="business",
                preferred_airline="AC", searched=True, anchor_price=3694.0,
            )],
            stage="budgeting",
        )
        search_resp = AgentResponse(
            content="AC $3,694 direct",
            blocks=[{"type": "flight_card", "data": {"route": "YYZ→LHR"}}],
            state=search_state,
        )

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm, \
             patch("app.services.agents.flight_search_agent.FlightSearchAgent.process",
                   new_callable=AsyncMock, return_value=search_resp), \
             patch("app.services.agents.flight_search_agent.FlightSearchAgent.check_preconditions",
                   return_value=None):
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process(
                "Toronto to London mid April business Air Canada",
                empty_state, [],
            )

        assert "Toronto to London" in response.content
        assert "3,694" in response.content
        assert any(b["type"] == "flight_card" for b in response.blocks)

    @pytest.mark.anyio
    async def test_update_and_ask_user(self, coordinator, empty_state):
        """LLM calls update_trip + ask_user → question appended, no search."""
        llm_response = _llm_result(
            content="Toronto to London, business class.",
            tool_calls=[
                {
                    "name": "update_trip",
                    "arguments": {
                        "legs": [{
                            "sequence": 1,
                            "origin_city": "Toronto",
                            "origin_airport": "YYZ",
                            "destination_city": "London",
                            "destination_airport": "LHR",
                            "preferred_date": "2026-04-12",
                            "cabin_class": "business",
                        }],
                        "confidence": 0.9,
                    },
                },
                {
                    "name": "ask_user",
                    "arguments": {
                        "question": "Do you have a preferred airline?",
                        "block_type": "text",
                    },
                },
            ],
        )

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm:
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process(
                "Toronto to London mid April business", empty_state, [],
            )

        assert "preferred airline" in response.content.lower()
        assert len(response.blocks) == 0  # No flight cards
        assert response.trip_ready is False

    @pytest.mark.anyio
    async def test_update_and_mark_complete(self, coordinator, empty_state):
        """LLM calls update_trip + mark_complete → trip_ready=True."""
        llm_response = _llm_result(
            content="NYC to Chicago, economy. All set!",
            tool_calls=[
                {
                    "name": "update_trip",
                    "arguments": {
                        "legs": [{
                            "sequence": 1,
                            "origin_city": "New York",
                            "origin_airport": "JFK",
                            "destination_city": "Chicago",
                            "destination_airport": "ORD",
                            "preferred_date": "2026-03-07",
                            "cabin_class": "economy",
                        }],
                        "confidence": 0.95,
                    },
                },
                {"name": "mark_complete", "arguments": {}},
            ],
        )

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm:
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process(
                "NYC to Chicago this Friday economy", empty_state, [],
            )

        assert response.trip_ready is True
        assert response.state.stage == "ready"

    @pytest.mark.anyio
    async def test_content_only_no_tools(self, coordinator, empty_state):
        """LLM returns only content, no tool_calls → reply returned as-is."""
        llm_response = _llm_result(content="Where are you flying from?")

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm:
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process("hello", empty_state, [])

        assert "flying from" in response.content.lower()
        assert response.trip_ready is False
        assert len(response.blocks) == 0

    @pytest.mark.anyio
    async def test_full_oneshot_flow(self, coordinator, empty_state):
        """Full info in one message → update + search + budget in one pass."""
        llm_response = _llm_result(
            content="Toronto to London, business, Air Canada, with your wife and 2 kids.",
            tool_calls=[
                {
                    "name": "update_trip",
                    "arguments": {
                        "legs": [{
                            "sequence": 1,
                            "origin_city": "Toronto",
                            "origin_airport": "YYZ",
                            "destination_city": "London",
                            "destination_airport": "LHR",
                            "preferred_date": "2026-04-12",
                            "flexibility_days": 5,
                            "cabin_class": "business",
                            "preferred_airline": "AC",
                        }],
                        "companions_count": 3,
                        "confidence": 0.95,
                    },
                },
                {"name": "search_flights", "arguments": {}},
                {"name": "calculate_budget", "arguments": {}},
            ],
        )

        search_resp = AgentResponse(
            content="AC $3,694 direct",
            blocks=[{"type": "flight_card", "data": {"route": "YYZ→LHR"}}],
            state=ConversationState(
                legs=[LegState(
                    sequence=1, origin_city="Toronto", origin_airport="YYZ",
                    destination_city="London", destination_airport="LHR",
                    preferred_date=date(2026, 4, 12), cabin_class="business",
                    preferred_airline="AC", searched=True, anchor_price=3694.0,
                )],
                companions=CompanionState(count=3, asked=True),
                stage="budgeting",
            ),
        )

        budget_resp = AgentResponse(
            content="4 travelers in premium economy!",
            blocks=[{"type": "budget_card", "data": {"total": 3158}}],
            state=ConversationState(
                legs=[LegState(
                    sequence=1, origin_city="Toronto", origin_airport="YYZ",
                    destination_city="London", destination_airport="LHR",
                    preferred_date=date(2026, 4, 12), cabin_class="business",
                    preferred_airline="AC", searched=True, anchor_price=3694.0,
                )],
                companions=CompanionState(count=3, asked=True, budget_calculated=True,
                                          recommended_cabin="premium_economy"),
                stage="ready",
                trip_ready=True,
            ),
            trip_ready=True,
        )

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm, \
             patch("app.services.agents.flight_search_agent.FlightSearchAgent.process",
                   new_callable=AsyncMock, return_value=search_resp), \
             patch("app.services.agents.flight_search_agent.FlightSearchAgent.check_preconditions",
                   return_value=None), \
             patch("app.services.agents.companion_budget_agent.CompanionBudgetAgent.process",
                   new_callable=AsyncMock, return_value=budget_resp), \
             patch("app.services.agents.companion_budget_agent.CompanionBudgetAgent.check_preconditions",
                   return_value=None):
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process(
                "Toronto to London mid April business Air Canada with my wife and 2 kids",
                empty_state, [],
            )

        assert "Toronto to London" in response.content
        assert "3,694" in response.content
        assert any(b["type"] == "flight_card" for b in response.blocks)
        assert any(b["type"] == "budget_card" for b in response.blocks)

    @pytest.mark.anyio
    async def test_companion_prompt_block(self, coordinator, empty_state):
        """ask_user with companion_prompt → companion_prompt block added."""
        llm_response = _llm_result(
            content="Flights found!",
            tool_calls=[
                {
                    "name": "ask_user",
                    "arguments": {
                        "question": "Will anyone be joining you on this trip?",
                        "block_type": "companion_prompt",
                    },
                },
            ],
        )

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm:
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process("test", empty_state, [])

        assert any(b["type"] == "companion_prompt" for b in response.blocks)
        assert response.state.companions.asked is True


class TestSearchPreconditionGuard:
    """Precondition guards are safety nets, not flow control."""

    @pytest.mark.anyio
    async def test_search_without_legs_blocked(self, coordinator, empty_state):
        """LLM calls search_flights without legs → precondition blocks, no crash."""
        llm_response = _llm_result(
            content="Let me search for flights.",
            tool_calls=[{"name": "search_flights", "arguments": {}}],
        )

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm, \
             patch("app.services.agents.flight_search_agent.FlightSearchAgent.check_preconditions",
                   return_value="No legs configured"):
            mock_llm.complete_with_tools = AsyncMock(return_value=llm_response)
            response = await coordinator.process("search", empty_state, [])

        # Should still return content, just no flight cards
        assert "search" in response.content.lower()
        assert len(response.blocks) == 0


class TestStateUpdate:
    """_apply_state_update preserves search results and merges correctly."""

    def test_preserves_search_results(self, coordinator):
        """When LLM sends updated legs, search results from prior turns are preserved."""
        state = ConversationState(
            legs=[LegState(
                sequence=1, origin_city="Toronto", origin_airport="YYZ",
                destination_city="London", destination_airport="LHR",
                preferred_date=date(2026, 4, 12), cabin_class="business",
                searched=True, anchor_price=3694.0,
                anchor_flight={"airline_code": "AC", "price": 3694},
            )],
        )

        args = {
            "legs": [{
                "sequence": 1,
                "origin_city": "Toronto",
                "origin_airport": "YYZ",
                "destination_city": "London",
                "destination_airport": "LHR",
                "preferred_date": "2026-04-12",
                "cabin_class": "business",
                "preferred_airline": "AC",
            }],
        }

        updated = coordinator._apply_state_update(state, args)
        assert updated.legs[0].searched is True
        assert updated.legs[0].anchor_price == 3694.0
        assert updated.legs[0].preferred_airline == "AC"

    def test_companions_count_update(self, coordinator):
        """companions_count=0 (solo) updates count and marks asked."""
        state = ConversationState()
        args = {"companions_count": 0}
        updated = coordinator._apply_state_update(state, args)
        assert updated.companions.count == 0
        assert updated.companions.asked is True

    def test_companions_negative_one_ignored(self, coordinator):
        """companions_count=-1 (unknown) does NOT update the state."""
        state = ConversationState()
        args = {"companions_count": -1}
        updated = coordinator._apply_state_update(state, args)
        assert updated.companions.count == -1
        assert updated.companions.asked is False


class TestErrorRecovery:
    """Coordinator handles failures gracefully."""

    @pytest.mark.anyio
    async def test_llm_timeout(self, coordinator, empty_state):
        async def slow_llm(*args, **kwargs):
            await asyncio.sleep(100)

        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm:
            mock_llm.complete_with_tools = slow_llm
            with patch("app.services.agents.trip_coordinator._AGENT_TIMEOUT", 0.01):
                response = await coordinator.process("hello", empty_state, [])

        assert "taking longer" in response.content.lower()
        assert response.trip_ready is False

    @pytest.mark.anyio
    async def test_llm_exception(self, coordinator, empty_state):
        with patch("app.services.agents.trip_coordinator.llm_client") as mock_llm:
            mock_llm.complete_with_tools = AsyncMock(side_effect=RuntimeError("LLM exploded"))
            response = await coordinator.process("hello", empty_state, [])

        assert "something went wrong" in response.content.lower()
        assert response.trip_ready is False
