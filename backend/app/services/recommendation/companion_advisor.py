"""CompanionBudgetAdvisor — LLM-driven cabin recommendation for companion travel.

Follows the TravelAdvisor pattern: single LLM call → JSON response → validation → fallback.
"""

import json
import logging
from dataclasses import dataclass

from app.services.llm_client import llm_client
from app.services.recommendation.config import recommendation_config

logger = logging.getLogger(__name__)

cfg = recommendation_config.companion_budget


@dataclass
class CompanionAdvisorOutput:
    """Result of the companion budget advisor."""
    recommended_cabin: str
    reasoning: str
    near_miss_note: str | None = None
    savings_note: str | None = None
    justification_prompt: str | None = None
    source: str = "fallback"  # "llm" or "fallback"


# Short IDs for cabin classes — keeps LLM output reliable
_CABIN_SHORT_IDS = {
    "business": "BIZ",
    "premium_economy": "PE",
    "economy": "ECO",
    "first": "FIRST",
}


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


class CompanionBudgetAdvisor:
    """LLM-driven cabin budget recommendation for companion travel."""

    async def advise(
        self,
        cabin_options: list[dict],
        budget: float,
        total_travelers: int,
        employee_cabin: str,
        employee_airline: str,
        route_summary: str,
    ) -> CompanionAdvisorOutput:
        """Recommend cabin class using LLM reasoning.

        Args:
            cabin_options: List of dicts with keys:
                cabin, total_per_person, total_all_travelers, fits, delta
            budget: Employee's anchor total (the budget envelope)
            total_travelers: Employee + companions
            employee_cabin: Cabin the employee is flying
            employee_airline: Employee's preferred airline IATA code
            route_summary: e.g. "YYZ → LHR, LHR → YYZ"
        """
        # Always compute fallback first — it's the safety net
        fallback = self._fallback_recommend(
            cabin_options, budget, total_travelers,
        )

        try:
            return await self._llm_advise(
                cabin_options, budget, total_travelers,
                employee_cabin, employee_airline, route_summary,
                fallback,
            )
        except Exception as e:
            logger.warning("CompanionBudgetAdvisor LLM failed: %s", e)
            return fallback

    async def _llm_advise(
        self,
        cabin_options: list[dict],
        budget: float,
        total_travelers: int,
        employee_cabin: str,
        employee_airline: str,
        route_summary: str,
        fallback: CompanionAdvisorOutput,
    ) -> CompanionAdvisorOutput:
        system = self._build_system_prompt(total_travelers, budget)
        user = self._build_user_prompt(
            cabin_options, budget, total_travelers,
            employee_cabin, employee_airline, route_summary,
        )

        raw = await llm_client.complete(
            system=system,
            user=user,
            max_tokens=800,
            temperature=0.1,
            model="gpt-4o-mini",
        )

        # Extract JSON from response
        parsed = self._parse_response(raw)
        if not parsed:
            logger.warning("CompanionBudgetAdvisor: failed to parse LLM response")
            return fallback

        # Validate recommended cabin
        valid_cabins = {opt["cabin"] for opt in cabin_options}
        recommended = parsed.get("recommended_cabin", "").lower().replace(" ", "_")
        if recommended not in valid_cabins:
            logger.warning(
                "LLM returned invalid cabin %r, falling back", recommended,
            )
            return fallback

        return CompanionAdvisorOutput(
            recommended_cabin=recommended,
            reasoning=_truncate(
                parsed.get("reasoning", fallback.reasoning),
                cfg.max_narrative_chars,
            ),
            near_miss_note=parsed.get("near_miss_note"),
            savings_note=_truncate(
                parsed.get("savings_note", "") or "",
                cfg.max_narrative_chars,
            ) or None,
            justification_prompt=parsed.get("justification_prompt"),
            source="llm",
        )

    @staticmethod
    def _build_system_prompt(total_travelers: int, budget: float) -> str:
        companions = total_travelers - 1
        return (
            f"You are a corporate travel budget advisor. A business traveler is "
            f"bringing {companions} companion{'s' if companions != 1 else ''} "
            f"({total_travelers} travelers total). Their approved business class "
            f"budget is ${budget:,.0f}. You must recommend which cabin class "
            f"ALL {total_travelers} travelers should fly to stay within budget.\n\n"
            f"Consider:\n"
            f"- Budget fit (within {cfg.budget_tolerance:.0%} tolerance is acceptable)\n"
            f"- Comfort tradeoffs for long-haul vs short-haul routes\n"
            f"- Near-miss opportunities (if a premium option barely exceeds budget)\n"
            f"- Cost savings from lower cabins\n\n"
            f"Respond with a JSON object (no markdown fences):\n"
            f'{{"recommended_cabin": "economy|premium_economy|business", '
            f'"reasoning": "2-3 sentence recommendation", '
            f'"near_miss_note": "null or note if a better cabin barely misses budget", '
            f'"savings_note": "null or note about savings from a lower cabin", '
            f'"justification_prompt": "null or question if budget is tight"}}'
        )

    @staticmethod
    def _build_user_prompt(
        cabin_options: list[dict],
        budget: float,
        total_travelers: int,
        employee_cabin: str,
        employee_airline: str,
        route_summary: str,
    ) -> str:
        lines = [
            f"BUDGET: ${budget:,.0f} (employee's {employee_cabin} class total)",
            f"TRAVELERS: {total_travelers} (1 employee + {total_travelers - 1} companions)",
            f"ROUTE: {route_summary}",
            "",
            "CABIN OPTIONS:",
        ]

        for opt in cabin_options:
            cabin = opt["cabin"]
            sid = _CABIN_SHORT_IDS.get(cabin, cabin.upper())
            total = opt["total_all_travelers"]
            per_person = opt.get("total_per_person", total / total_travelers if total_travelers else 0)
            delta = opt.get("delta", budget - total)
            fits = opt.get("fits", total <= budget * (1 + cfg.budget_tolerance))

            if fits:
                budget_note = f"UNDER BUDGET by ${abs(delta):,.0f} ({abs(delta)/budget*100:.0f}%)" if delta >= 0 else f"WITHIN TOLERANCE (${abs(delta):,.0f} over, {abs(delta)/budget*100:.0f}%)"
            else:
                budget_note = f"OVER BUDGET by ${abs(delta):,.0f} ({abs(delta)/budget*100:.0f}%)"

            lines.append(
                f"[{sid}] {cabin.replace('_', ' ').title()} — "
                f"${total:,.0f} total (${per_person:,.0f}/person) — {budget_note}"
            )

        if employee_airline:
            lines.append(f"\nEmployee selected: {employee_airline} {employee_cabin} class")

        return "\n".join(lines)

    @staticmethod
    def _parse_response(raw: str) -> dict | None:
        """Extract JSON from LLM response (handles fenced or bare JSON)."""
        text = raw.strip()

        # Try fenced JSON first
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        # Find outermost braces
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start == -1 or brace_end == -1:
            return None

        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _fallback_recommend(
        cabin_options: list[dict],
        budget: float,
        total_travelers: int,
    ) -> CompanionAdvisorOutput:
        """Rule-based fallback: pick highest cabin that fits budget."""
        tolerance = cfg.budget_tolerance
        ceiling = budget * (1 + tolerance)

        recommended = "economy"
        for opt in cabin_options:
            if opt["total_all_travelers"] <= ceiling:
                recommended = opt["cabin"]
                break

        rec_opt = next(
            (o for o in cabin_options if o["cabin"] == recommended), None,
        )
        econ_opt = next(
            (o for o in cabin_options if o["cabin"] == "economy"), None,
        )

        # Build reason string
        if recommended == "business":
            reasoning = (
                f"All {total_travelers} travelers can fly business class "
                f"for ${rec_opt['total_all_travelers']:,.0f} — "
                f"within your ${budget:,.0f} budget."
            )
        elif recommended == "premium_economy":
            biz_opt = next(
                (o for o in cabin_options if o["cabin"] == "business"), None,
            )
            biz_total = biz_opt["total_all_travelers"] if biz_opt else 0
            reasoning = (
                f"All {total_travelers} travelers can fly Premium Economy "
                f"for ${rec_opt['total_all_travelers']:,.0f} — "
                f"${abs(rec_opt['delta']):,.0f} "
                f"{'under' if rec_opt['delta'] >= 0 else 'over'} "
                f"your ${budget:,.0f} business class budget."
            )
        else:
            reasoning = (
                f"All {total_travelers} travelers can fly Economy "
                f"for ${rec_opt['total_all_travelers']:,.0f}, "
                f"saving ${budget - rec_opt['total_all_travelers']:,.0f} "
                f"vs your business class budget."
            )

        # Check for near-miss (a better cabin barely exceeds budget)
        near_miss_note = None
        for opt in cabin_options:
            if opt["cabin"] == recommended:
                break
            overshoot = opt["total_all_travelers"] - ceiling
            if 0 < overshoot <= budget * cfg.near_miss_threshold:
                near_miss_note = (
                    f"{opt['cabin'].replace('_', ' ').title()} is only "
                    f"${overshoot:,.0f} over budget — worth requesting an exception?"
                )
                break

        # Savings note
        savings_note = None
        if econ_opt and recommended != "economy":
            savings = rec_opt["total_all_travelers"] - econ_opt["total_all_travelers"]
            if savings > 0:
                savings_note = (
                    f"Economy would save an additional ${savings:,.0f} "
                    f"for all {total_travelers} travelers."
                )

        return CompanionAdvisorOutput(
            recommended_cabin=recommended,
            reasoning=reasoning,
            near_miss_note=near_miss_note,
            savings_note=savings_note,
            source="fallback",
        )


# Singleton
companion_budget_advisor = CompanionBudgetAdvisor()
