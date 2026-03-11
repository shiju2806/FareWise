"""Tests for FlightSearchAgent — flight search with mocked provider."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agents.conversation_state import ConversationState, LegState
from app.services.agents.flight_search_agent import FlightSearchAgent


MOCK_FLIGHTS = [
    {"airline_name": "British Airways", "airline_code": "BA", "price": 4882,
     "stops": 0, "departure_time": "2026-04-12T08:30:00", "duration_minutes": 420,
     "flight_number": "BA092"},
    {"airline_name": "Air Canada", "airline_code": "AC", "price": 5200,
     "stops": 0, "departure_time": "2026-04-12T10:00:00", "duration_minutes": 435},
    {"airline_name": "United", "airline_code": "UA", "price": 3900,
     "stops": 1, "departure_time": "2026-04-12T06:00:00", "duration_minutes": 600},
]


@pytest.fixture
def agent():
    return FlightSearchAgent()


@pytest.fixture
def two_leg_state():
    return ConversationState(
        legs=[
            LegState(
                sequence=1, origin_city="Toronto", origin_airport="YYZ",
                destination_city="London", destination_airport="LHR",
                preferred_date=date(2026, 4, 12), cabin_class="business",
            ),
            LegState(
                sequence=2, origin_city="London", origin_airport="LHR",
                destination_city="Toronto", destination_airport="YYZ",
                preferred_date=date(2026, 4, 18), cabin_class="business",
            ),
        ],
        stage="searching",
    )


class TestFlightSearch:
    """Search produces flight_card blocks and updates state."""

    @pytest.mark.anyio
    async def test_two_legs_produces_two_blocks(self, agent, two_leg_state):
        with patch("app.services.agents.flight_search_agent.flight_provider") as mock_fp, \
             patch("app.services.agents.flight_search_agent.select_anchor_flight") as mock_anchor:
            mock_fp.search_flights = AsyncMock(return_value=MOCK_FLIGHTS)
            mock_anchor.return_value = MOCK_FLIGHTS[0]  # BA at $4882

            response = await agent.process("", two_leg_state, [])

        assert len(response.blocks) == 2
        assert response.blocks[0]["type"] == "flight_card"
        assert response.blocks[1]["type"] == "flight_card"
        assert response.state.legs[0].searched is True
        assert response.state.legs[1].searched is True
        assert response.state.legs[0].anchor_price == 4882

    @pytest.mark.anyio
    async def test_empty_flights_no_anchor(self, agent, two_leg_state):
        with patch("app.services.agents.flight_search_agent.flight_provider") as mock_fp, \
             patch("app.services.agents.flight_search_agent.select_anchor_flight") as mock_anchor:
            mock_fp.search_flights = AsyncMock(return_value=[])
            mock_anchor.return_value = None

            response = await agent.process("", two_leg_state, [])

        assert len(response.blocks) == 2
        assert response.state.legs[0].anchor_price is None

    @pytest.mark.anyio
    async def test_partial_failure(self, agent, two_leg_state):
        """One leg fails, the other succeeds — should return partial results."""
        call_count = 0

        async def _search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MOCK_FLIGHTS
            raise RuntimeError("Connection error")

        with patch("app.services.agents.flight_search_agent.flight_provider") as mock_fp, \
             patch("app.services.agents.flight_search_agent.select_anchor_flight") as mock_anchor:
            mock_fp.search_flights = _search
            mock_anchor.return_value = MOCK_FLIGHTS[0]

            response = await agent.process("", two_leg_state, [])

        # Should still return 2 blocks (one with anchor, one without)
        assert len(response.blocks) == 2
        assert response.state.legs[0].searched is True


class TestPreconditions:
    """FlightSearchAgent contract validation."""

    def test_no_legs_fails(self, agent):
        state = ConversationState()
        assert agent.check_preconditions(state) == "No trip legs defined"

    def test_missing_airport_fails(self, agent):
        state = ConversationState(
            legs=[LegState(
                sequence=1, origin_city="Toronto", origin_airport="",
                destination_city="London", destination_airport="LHR",
                preferred_date=date(2026, 4, 12),
            )]
        )
        err = agent.check_preconditions(state)
        assert err is not None
        assert "missing airport codes" in err.lower()

    def test_missing_date_fails(self, agent):
        state = ConversationState(
            legs=[LegState(
                sequence=1, origin_airport="YYZ", destination_airport="LHR",
            )]
        )
        err = agent.check_preconditions(state)
        assert "missing preferred date" in err.lower()

    def test_valid_state_passes(self, agent):
        state = ConversationState(
            legs=[LegState(
                origin_airport="YYZ", destination_airport="LHR",
                preferred_date=date(2026, 4, 12),
            )]
        )
        assert agent.check_preconditions(state) is None
