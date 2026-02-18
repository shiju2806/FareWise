"""Justification service — generates contextual prompts for non-optimal flight selections."""

import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

JUSTIFICATION_SYSTEM_PROMPT = """You are a friendly corporate travel booking assistant. A traveler has chosen their preferred flight. Your job is to help them add context for their approver.

Write a SHORT note (2 sentences max) that:

1. Factually states the price difference from the lowest available fare
2. Invites them to add a quick note — suggest common valid reasons (schedule, loyalty program, nonstop, red-eye avoidance)

Tone: warm and helpful, like a travel agent on their side. You are NOT auditing them.
NEVER use the words: justify, explain, expensive, violation, policy, why.
Use CAD currency. Keep it under 60 words.

Example: "Your flight is $320 more than the lowest available fare. A quick note about your preference (schedule, loyalty status, nonstop routing) will help your approver."

Respond with ONLY the note text, no JSON, no preamble."""


TRIP_JUSTIFICATION_SYSTEM_PROMPT = """You are a friendly corporate travel booking assistant. A traveler has chosen their preferred flights for a multi-leg trip. Your job is to help them add context for their approver.

Write a SHORT note (2 sentences max) that:

1. States the trip total and the difference from the lowest-fare combination
2. Invites them to add a quick note about their preferences

Tone: warm and helpful, like a travel agent on their side. You are NOT auditing them.
NEVER use the words: justify, explain, expensive, violation, policy, why.
Use CAD currency. Keep it under 80 words.

Respond with ONLY the note text, no JSON, no preamble."""


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
            f"Traveler's choice: {selected['airline']} on {selected['date']} "
            f"at ${selected['price']:.0f} CAD "
            f"({selected.get('stops', 0)} stop{'s' if selected.get('stops', 0) != 1 else ''}, "
            f"{selected.get('duration_minutes', 0)} min)",
            "",
            "Lower-fare alternatives on this route:",
        ]
        if same_date:
            lines.append(
                f"- Same date, different airline: {same_date['airline']} "
                f"at ${same_date['price']:.0f} (${same_date['savings']:.0f} less)"
            )
        if any_date and any_date != same_date:
            lines.append(
                f"- Different date: {any_date['airline']} on {any_date['date']} "
                f"at ${any_date['price']:.0f} (${any_date['savings']:.0f} less)"
            )
        if same_airline:
            lines.append(
                f"- Same airline, different date: {same_airline['date']} "
                f"at ${same_airline['price']:.0f} (${same_airline['savings']:.0f} less)"
            )
        lines.append("")
        lines.append(f"Difference from lowest fare: ${savings:.0f} CAD ({pct:.0f}%)")
        return "\n".join(lines)

    @staticmethod
    def _fallback_prompt(selected, overall, savings):
        return (
            f"Your {selected['airline']} flight is ${savings:.0f} more than the "
            f"lowest available fare ({overall['airline']} on {overall['date']} "
            f"at ${overall['price']:.0f} CAD). A quick note about your preference "
            f"will help your approver."
        )

    # ---- Trip-level justification ----

    async def generate_trip_prompt(
        self,
        legs: list[dict],
        trip_total_selected: float,
        trip_total_cheapest: float,
        trip_savings_amount: float,
        trip_savings_percent: float,
    ) -> str:
        """Generate a trip-level justification prompt using Claude."""
        user_prompt = self._build_trip_prompt(
            legs, trip_total_selected, trip_total_cheapest,
            trip_savings_amount, trip_savings_percent,
        )

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=250,
                temperature=0.3,
                system=TRIP_JUSTIFICATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.error(f"Trip justification prompt generation failed: {e}")
            return self._fallback_trip_prompt(
                trip_total_selected, trip_total_cheapest, trip_savings_amount,
            )

    def _build_trip_prompt(
        self, legs, total_selected, total_cheapest,
        savings_amount, savings_percent,
    ) -> str:
        lines = [
            f"Trip total: ${total_selected:.0f} CAD (lowest-fare combination: ${total_cheapest:.0f} CAD)",
            f"Difference: ${savings_amount:.0f} CAD ({savings_percent:.0f}%)",
            "",
        ]
        for leg in legs:
            if not leg.get("selected"):
                continue
            sel = leg["selected"]
            lines.append(
                f"Leg {leg['sequence']}: {leg['route']} — {sel['airline']} "
                f"at ${sel['price']:.0f} CAD on {sel['date']}"
            )
            if leg.get("alternatives"):
                best_alt = leg["alternatives"][0]
                lines.append(
                    f"  Lower-fare option: {best_alt['airline']} at ${best_alt['price']:.0f} "
                    f"(${best_alt['savings']:.0f} less)"
                )
        return "\n".join(lines)

    @staticmethod
    def _fallback_trip_prompt(total_selected, total_cheapest, savings):
        return (
            f"Your trip total is ${total_selected:.0f} CAD, which is "
            f"${savings:.0f} more than the lowest-fare combination "
            f"(${total_cheapest:.0f} CAD). A quick note about your preferences "
            f"will help your approver."
        )


justification_service = JustificationService()
