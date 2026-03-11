"""Tests for CompanionBudgetAgent — pure budget calculation with mocks."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agents.conversation_state import ConversationState, LegState, CompanionState
from app.services.agents.companion_budget_agent import CompanionBudgetAgent


@pytest.fixture
def agent():
    return CompanionBudgetAgent()


@pytest.fixture
def searched_state_with_companion():
    """Business trip with anchor prices and companions set."""
    return ConversationState(
        legs=[
            LegState(
                sequence=1, origin_city="Toronto", origin_airport="YYZ",
                destination_city="London", destination_airport="LHR",
                preferred_date=date(2026, 4, 12), cabin_class="business",
                searched=True, anchor_price=4882.0,
            ),
            LegState(
                sequence=2, origin_city="London", origin_airport="LHR",
                destination_city="Toronto", destination_airport="YYZ",
                preferred_date=date(2026, 4, 18), cabin_class="business",
                searched=True, anchor_price=4470.0,
            ),
        ],
        companions=CompanionState(count=3, asked=True),
        stage="budgeting",
    )


class TestBudgetCalculation:
    """Budget calculation for different companion counts."""

    @pytest.mark.anyio
    async def test_family_of_4_budget(self, agent, searched_state_with_companion):
        """Wife + 2 kids = 3 companions, 4 travelers total."""
        async def _mock_search(origin, destination, departure_date, cabin_class):
            prices = {
                "business": [{"price": 4800}],
                "premium_economy": [{"price": 1500}],
                "economy": [{"price": 800}],
            }
            return prices.get(cabin_class, [{"price": 999}])

        with patch("app.services.agents.companion_budget_agent.flight_provider") as mock_fp:
            mock_fp.search_flights = AsyncMock(side_effect=_mock_search)
            response = await agent.process("", searched_state_with_companion, [])

        assert response.trip_ready is True
        assert response.state.companions.budget_calculated is True
        assert len(response.blocks) == 1
        assert response.blocks[0]["type"] == "budget_card"

        budget = response.blocks[0]["data"]
        assert budget["total_travelers"] == 4
        assert budget["recommended_cabin"] in ("business", "premium_economy", "economy")

    @pytest.mark.anyio
    async def test_partner_only_budget(self, agent):
        """1 companion → 2 travelers total."""
        state = ConversationState(
            legs=[
                LegState(
                    sequence=1, origin_airport="YYZ", destination_airport="LHR",
                    preferred_date=date(2026, 4, 12), cabin_class="business",
                    searched=True, anchor_price=4882.0,
                ),
            ],
            companions=CompanionState(count=1, asked=True),
            stage="budgeting",
        )

        async def _mock_search(origin, destination, departure_date, cabin_class):
            prices = {
                "business": [{"price": 4800}],
                "premium_economy": [{"price": 1500}],
                "economy": [{"price": 800}],
            }
            return prices.get(cabin_class, [{"price": 999}])

        with patch("app.services.agents.companion_budget_agent.flight_provider") as mock_fp:
            mock_fp.search_flights = AsyncMock(side_effect=_mock_search)
            response = await agent.process("", state, [])

        assert response.trip_ready is True
        budget = response.blocks[0]["data"]
        assert budget["total_travelers"] == 2
        assert "2 travelers" in response.content


class TestPreconditions:
    """CompanionBudgetAgent contract validation."""

    def test_no_anchor_fails(self, agent):
        state = ConversationState(
            legs=[LegState(searched=False, anchor_price=None)],
            companions=CompanionState(count=2, asked=True),
        )
        err = agent.check_preconditions(state)
        assert err is not None
        assert "anchor prices" in err.lower()

    def test_no_companions_fails(self, agent):
        state = ConversationState(
            legs=[LegState(searched=True, anchor_price=5000)],
            companions=CompanionState(count=0, asked=True),
        )
        err = agent.check_preconditions(state)
        assert err is not None
        assert "no companions" in err.lower()

    def test_with_anchors_and_companions_passes(self, agent):
        state = ConversationState(
            legs=[LegState(searched=True, anchor_price=5000)],
            companions=CompanionState(count=2, asked=True),
        )
        assert agent.check_preconditions(state) is None
