"""Base classes for trip planning agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from app.services.agents.conversation_state import ConversationState


class AgentName(str, Enum):
    """Canonical names for all trip planning agents."""

    FLIGHT_SEARCH = "flight_search_agent"
    COMPANION_BUDGET = "companion_budget_agent"


@dataclass
class AgentResponse:
    """Standard response returned by every trip agent."""

    content: str                                    # Text reply shown to user
    blocks: list[dict] = field(default_factory=list)  # Structured UI blocks [{type, data}]
    state: ConversationState | None = None          # Updated conversation state
    trip_ready: bool = False


class TripAgent(ABC):
    """Abstract base for all trip planning agents.

    Subclasses declare typed contracts:
      requires — set of state fields the agent needs before it can run
      provides — set of state fields it guarantees after running
    """

    requires: ClassVar[set[str]] = set()
    provides: ClassVar[set[str]] = set()

    def check_preconditions(self, state: ConversationState) -> str | None:
        """Validate required state before processing.

        Returns an error message if preconditions are not met, or None if OK.
        Override in subclasses for domain-specific validation.
        """
        return None

    @abstractmethod
    async def process(
        self,
        user_message: str,
        state: ConversationState,
        conversation_history: list[dict],
    ) -> AgentResponse:
        """Process a user message given current state and history."""
        ...
