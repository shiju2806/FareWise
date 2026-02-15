"""Justification service — generates contextual prompts for non-optimal flight selections."""

import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

JUSTIFICATION_SYSTEM_PROMPT = """You are a corporate travel cost advisor. A traveler has selected a flight that is NOT the cheapest option available. Write a SHORT, professional prompt (2-3 sentences) that:

1. Acknowledges which flight they selected
2. States the specific cheaper alternative(s) and the dollar savings
3. Asks them to briefly explain why they chose this flight

Tone: helpful, not judgmental. Like a colleague reminding them of the alternatives.
Do NOT lecture. Do NOT use words like "policy" or "violation".
Use CAD currency. Keep it under 80 words.

Respond with ONLY the prompt text, no JSON, no preamble."""


class JustificationService:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate_prompt(
        self,
        selected_flight: dict,
        cheapest_same_date: dict | None,
        cheapest_any_date: dict | None,
        cheapest_same_airline: dict | None,
        overall_cheapest: dict,
        savings_amount: float,
        savings_percent: float,
        route: str,
    ) -> str:
        """Generate a contextual justification prompt using Claude."""
        user_prompt = self._build_prompt(
            selected_flight, cheapest_same_date, cheapest_any_date,
            cheapest_same_airline, overall_cheapest, savings_amount,
            savings_percent, route,
        )

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=200,
                temperature=0.3,
                system=JUSTIFICATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.error(f"Justification prompt generation failed: {e}")
            return self._fallback_prompt(
                selected_flight, overall_cheapest, savings_amount
            )

    def _build_prompt(
        self, selected, same_date, any_date, same_airline,
        overall, savings, pct, route,
    ):
        lines = [
            f"Route: {route}",
            f"Selected: {selected['airline']} on {selected['date']} "
            f"at ${selected['price']:.0f} CAD "
            f"({selected.get('stops', 0)} stop{'s' if selected.get('stops', 0) != 1 else ''}, "
            f"{selected.get('duration_minutes', 0)} min)",
            "",
            "Cheaper alternatives:",
        ]
        if same_date:
            lines.append(
                f"- Same date, different airline: {same_date['airline']} "
                f"at ${same_date['price']:.0f} (save ${same_date['savings']:.0f})"
            )
        if any_date and any_date != same_date:
            lines.append(
                f"- Different date: {any_date['airline']} on {any_date['date']} "
                f"at ${any_date['price']:.0f} (save ${any_date['savings']:.0f})"
            )
        if same_airline:
            lines.append(
                f"- Same airline, different date: {same_airline['date']} "
                f"at ${same_airline['price']:.0f} (save ${same_airline['savings']:.0f})"
            )
        lines.append("")
        lines.append(f"Maximum potential savings: ${savings:.0f} CAD ({pct:.0f}%)")
        return "\n".join(lines)

    @staticmethod
    def _fallback_prompt(selected, overall, savings):
        return (
            f"You selected {selected['airline']} at ${selected['price']:.0f} CAD, "
            f"but {overall['airline']} on {overall['date']} is available for "
            f"${overall['price']:.0f} CAD (${savings:.0f} less). "
            f"Could you briefly note why you prefer this flight?"
        )


justification_service = JustificationService()
