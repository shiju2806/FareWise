"""Narrative generator — uses Claude API to produce human-readable savings justification."""

import json
import logging
from decimal import Decimal

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a corporate travel cost analyst. Generate a brief, factual summary
(max 4 sentences) of a traveler's flight selections.

Include:
- Total cost and comparison to cheapest/most expensive options
- Dollar savings achieved
- Key tradeoffs (e.g., chose a different date or airline)
- Policy compliance status

Rules:
- Be factual and neutral. State numbers and facts only.
- Do NOT use superlatives (e.g., "excellent", "impressive", "great").
- Do NOT use exclamation marks or judgment language.
- Do NOT praise or criticize the traveler's choices.
- Use actual dollar amounts with currency codes.
- Do not use markdown formatting.

Respond with ONLY the narrative text, no JSON, no preamble."""


class NarrativeGenerator:
    """Generates human-readable savings narratives using Claude API."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(
        self,
        traveler_name: str,
        trip_title: str,
        selected_total: Decimal,
        cheapest_total: Decimal,
        most_expensive_total: Decimal,
        policy_status: str,
        per_leg_details: list[dict],
        hotel_total: Decimal | None = None,
        hotel_cheapest: Decimal | None = None,
        events_context: list[str] | None = None,
        currency: str = "USD",
    ) -> str:
        prompt = self._build_prompt(
            traveler_name, trip_title, selected_total,
            cheapest_total, most_expensive_total, policy_status, per_leg_details,
            hotel_total, hotel_cheapest, events_context, currency,
        )

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=500,
                temperature=0.3,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude API failed for narrative generation: {e}")
            return self._fallback_narrative(
                traveler_name, trip_title, selected_total,
                cheapest_total, most_expensive_total, policy_status, currency,
            )

    def _build_prompt(
        self, traveler_name, trip_title, selected_total,
        cheapest_total, most_expensive_total, policy_status, per_leg_details,
        hotel_total=None, hotel_cheapest=None, events_context=None, currency="USD",
    ) -> str:
        savings = most_expensive_total - selected_total
        premium = selected_total - cheapest_total

        legs_text = ""
        for leg in per_leg_details:
            legs_text += (
                f"\n- {leg['route']}: Selected ${leg['selected_price']:.0f} "
                f"(cheapest: ${leg['cheapest_price']:.0f}, "
                f"most expensive: ${leg.get('most_expensive_price', leg['selected_price']):.0f})"
            )
            if leg.get("savings_note"):
                legs_text += f" — {leg['savings_note']}"

        hotel_text = ""
        if hotel_total is not None:
            hotel_text = f"\nHotel total: {currency} {hotel_total:.2f}"
            if hotel_cheapest is not None:
                hotel_text += f" (cheapest available: {currency} {hotel_cheapest:.2f})"

        events_text = ""
        if events_context:
            events_text = "\nRelevant events: " + "; ".join(events_context)

        return f"""Traveler: {traveler_name}
Trip: {trip_title}
Currency: {currency}
Flight total selected: {currency} {selected_total:.2f}
Cheapest available: {currency} {cheapest_total:.2f}
Most expensive: {currency} {most_expensive_total:.2f}
Savings vs expensive: {currency} {savings:.2f}
Premium over cheapest: {currency} {premium:.2f}
Policy status: {policy_status}{hotel_text}{events_text}

Per-leg breakdown:{legs_text}"""

    def _fallback_narrative(
        self, traveler_name, trip_title, selected_total,
        cheapest_total, most_expensive_total, policy_status,
        currency="USD",
    ) -> str:
        savings = most_expensive_total - selected_total
        return (
            f"{traveler_name} selected a {trip_title} itinerary totaling "
            f"{currency} {selected_total:.0f} — {currency} {savings:.0f} less than the most expensive "
            f"option. Policy status: {policy_status}."
        )


narrative_generator = NarrativeGenerator()
