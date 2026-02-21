"""Trip Intelligence Service — LLM-powered trip-level cost analysis.

Provides:
- Trip-level cost analysis across all legs (vs cheapest, vs policy, vs stops/routing)
- Smart cost comparison summaries
"""

import json
import logging

from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)

# Policy budgets per cabin class (one-way, CAD)
POLICY_BUDGET = {
    "economy": 800,
    "premium_economy": 1500,
    "business": 3500,
    "first": 6000,
}

TRIP_ANALYSIS_SYSTEM_PROMPT = """You are a corporate travel cost optimization advisor. Analyze the entire trip (all legs) and produce a clear, actionable cost assessment.

Your response MUST be valid JSON with this exact structure:
{
    "summary": "1-2 sentence trip cost summary with total and key insight",
    "recommendation": "approve" | "review" | "optimize",
    "confidence": 0.0-1.0,
    "total_assessment": "under_budget" | "at_budget" | "over_budget",
    "key_insight": "The single most important cost optimization insight for this trip",
    "leg_insights": [
        {
            "leg_number": 1,
            "route": "YYZ → LHR",
            "assessment": "Brief assessment of this leg's selection",
            "optimization": "Specific suggestion if savings possible, or 'Good choice' if optimal"
        }
    ],
    "alternatives_summary": "Brief description of how much could be saved by switching airlines, adding stops, or adjusting dates",
    "justification_prompt": "If over budget: a professional 2-sentence prompt asking the traveler to justify their selections. If under/at budget: null"
}

Guidelines:
- Be specific with dollar amounts and routes
- Compare against policy budget per leg
- Highlight the biggest savings opportunity
- "approve" = within budget, reasonable choices
- "review" = over budget but not extreme, suggest optimizations
- "optimize" = significantly over budget, strong alternatives available
- Use CAD currency throughout
- Keep insights concise and actionable
- If it's a round trip, consider the total round-trip cost together

Respond with ONLY the JSON, no markdown, no preamble."""


class TripIntelligenceService:
    """LLM-powered trip-level cost analysis and optimization."""

    async def analyze_trip(
        self,
        legs: list[dict],
        selected_flights: list[dict],
        all_options_per_leg: list[list[dict]],
    ) -> dict:
        """Analyze entire trip cost vs alternatives, policy, and routing options."""
        prompt = self._build_trip_analysis_prompt(
            legs, selected_flights, all_options_per_leg
        )

        try:
            raw_text = await llm_client.complete(
                system=TRIP_ANALYSIS_SYSTEM_PROMPT,
                user=prompt,
                max_tokens=1000,
                temperature=0.2,
                json_mode=True,
            )
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

            analysis = json.loads(raw_text)

            # Validate required fields
            required = ["summary", "recommendation", "total_assessment", "key_insight"]
            if not all(k in analysis for k in required):
                raise ValueError(f"Missing fields: {[k for k in required if k not in analysis]}")

            if analysis["recommendation"] not in ("approve", "review", "optimize"):
                analysis["recommendation"] = "review"

            analysis["source"] = "llm"
            return analysis

        except Exception as e:
            logger.error(f"Trip analysis LLM failed: {e}")
            return self._fallback_trip_analysis(legs, selected_flights, all_options_per_leg)

    def get_cost_summary(
        self,
        legs: list[dict],
        selected_flights: list[dict] | None,
        all_options_per_leg: list[list[dict]],
    ) -> dict:
        """Compute cost summary with policy comparison (no LLM needed).

        Returns structured cost breakdown for the Trip Cost Bar.
        """
        leg_summaries = []
        total_selected = 0
        total_cheapest = 0
        total_cheapest_direct = 0
        total_cheapest_with_stops = 0
        total_policy = 0

        for i, leg in enumerate(legs):
            options = all_options_per_leg[i] if i < len(all_options_per_leg) else []
            selected = selected_flights[i] if selected_flights and i < len(selected_flights) else None
            cabin = leg.get("cabin_class", "economy")
            policy_budget = POLICY_BUDGET.get(cabin, POLICY_BUDGET["economy"])

            cheapest = min((f["price"] for f in options), default=0)
            cheapest_direct = min(
                (f["price"] for f in options if f.get("stops", 1) == 0),
                default=None,
            )
            cheapest_with_stops = min(
                (f["price"] for f in options if f.get("stops", 0) > 0),
                default=None,
            )

            # Find cheapest flight details
            cheapest_flight = min(options, key=lambda f: f["price"]) if options else None

            sel_price = selected["price"] if selected else 0
            total_selected += sel_price
            total_cheapest += cheapest
            total_cheapest_direct += cheapest_direct or cheapest
            total_cheapest_with_stops += cheapest_with_stops or cheapest
            total_policy += policy_budget

            leg_summaries.append({
                "leg_number": i + 1,
                "route": f"{leg.get('origin_airport', '?')} → {leg.get('destination_airport', '?')}",
                "cabin_class": cabin,
                "policy_budget": policy_budget,
                "selected_price": sel_price,
                "selected_airline": selected.get("airline_name") if selected else None,
                "cheapest_price": cheapest,
                "cheapest_airline": cheapest_flight.get("airline_name") if cheapest_flight else None,
                "cheapest_direct_price": cheapest_direct,
                "cheapest_with_stops_price": cheapest_with_stops,
                "option_count": len(options),
                "savings_vs_cheapest": round(sel_price - cheapest, 2) if selected else 0,
                "vs_policy": round(sel_price - policy_budget, 2) if selected else 0,
            })

        all_selected = selected_flights and all(f is not None for f in selected_flights)

        return {
            "legs": leg_summaries,
            "totals": {
                "selected": round(total_selected, 2),
                "cheapest": round(total_cheapest, 2),
                "cheapest_direct": round(total_cheapest_direct, 2),
                "cheapest_with_stops": round(total_cheapest_with_stops, 2),
                "policy_budget": round(total_policy, 2),
                "savings_vs_cheapest": round(total_selected - total_cheapest, 2),
                "savings_vs_stops": round(total_selected - total_cheapest_with_stops, 2),
                "vs_policy": round(total_selected - total_policy, 2),
            },
            "all_legs_selected": bool(all_selected),
            "policy_status": (
                "under" if total_selected <= total_policy
                else "over" if total_selected > total_policy * 1.1
                else "at"
            ) if all_selected else "incomplete",
        }

    def _build_trip_analysis_prompt(
        self,
        legs: list[dict],
        selected_flights: list[dict],
        all_options_per_leg: list[list[dict]],
    ) -> str:
        sections = ["=== TRIP OVERVIEW ==="]
        total_selected = 0
        total_cheapest = 0
        total_policy = 0

        for i, leg in enumerate(legs):
            selected = selected_flights[i] if i < len(selected_flights) else None
            options = all_options_per_leg[i] if i < len(all_options_per_leg) else []
            cabin = leg.get("cabin_class", "economy")
            policy = POLICY_BUDGET.get(cabin, 800)

            sections.append(f"\n--- Leg {i + 1}: {leg.get('origin_airport', '?')} → {leg.get('destination_airport', '?')} ---")
            sections.append(f"Date: {leg.get('preferred_date', '?')}")
            sections.append(f"Cabin: {cabin}")
            sections.append(f"Policy budget: ${policy} CAD")

            if selected:
                sections.append(f"Selected: {selected.get('airline_name', '?')} at ${selected.get('price', 0):.0f} CAD")
                sections.append(f"  Stops: {selected.get('stops', 0)}, Duration: {selected.get('duration_minutes', 0)} min")
                total_selected += selected.get("price", 0)
            else:
                sections.append("Selected: None yet")

            total_policy += policy

            if options:
                prices = [f["price"] for f in options if f.get("price", 0) > 0]
                if prices:
                    cheapest = min(prices)
                    total_cheapest += cheapest
                    cheapest_flight = min(options, key=lambda f: f["price"])
                    sections.append(f"Cheapest available: {cheapest_flight.get('airline_name', '?')} at ${cheapest:.0f} CAD "
                                    f"({cheapest_flight.get('stops', '?')} stops)")

                    direct = [f for f in options if f.get("stops", 1) == 0]
                    if direct:
                        cheapest_direct = min(direct, key=lambda f: f["price"])
                        sections.append(f"Cheapest nonstop: {cheapest_direct.get('airline_name', '?')} at ${cheapest_direct['price']:.0f} CAD")

                    with_stops = [f for f in options if f.get("stops", 0) > 0]
                    if with_stops:
                        cheapest_stops = min(with_stops, key=lambda f: f["price"])
                        sections.append(f"Cheapest with stops: {cheapest_stops.get('airline_name', '?')} at ${cheapest_stops['price']:.0f} CAD "
                                        f"({cheapest_stops.get('stops', 1)} stop{'s' if cheapest_stops.get('stops', 1) > 1 else ''})")

                    # Top 3 alternative airlines
                    by_airline: dict[str, float] = {}
                    for f in options:
                        name = f.get("airline_name", "Unknown")
                        if name not in by_airline or f["price"] < by_airline[name]:
                            by_airline[name] = f["price"]
                    top_airlines = sorted(by_airline.items(), key=lambda x: x[1])[:5]
                    sections.append(f"Airlines (cheapest): {', '.join(f'{a} ${p:.0f}' for a, p in top_airlines)}")

                    sections.append(f"Total options: {len(options)}")

        sections.extend([
            "",
            "=== TRIP TOTALS ===",
            f"Total selected: ${total_selected:.0f} CAD",
            f"Total cheapest: ${total_cheapest:.0f} CAD",
            f"Total policy budget: ${total_policy:.0f} CAD",
            f"Savings opportunity: ${total_selected - total_cheapest:.0f} CAD",
            f"Policy variance: ${total_selected - total_policy:.0f} CAD {'over' if total_selected > total_policy else 'under'} budget",
        ])

        return "\n".join(sections)

    def _fallback_trip_analysis(
        self,
        legs: list[dict],
        selected_flights: list[dict],
        all_options_per_leg: list[list[dict]],
    ) -> dict:
        """Rule-based fallback when LLM is unavailable."""
        total_selected = sum(f.get("price", 0) for f in selected_flights if f)
        total_cheapest = 0
        total_policy = 0
        leg_insights = []

        for i, leg in enumerate(legs):
            options = all_options_per_leg[i] if i < len(all_options_per_leg) else []
            selected = selected_flights[i] if i < len(selected_flights) else None
            cabin = leg.get("cabin_class", "economy")
            policy = POLICY_BUDGET.get(cabin, 800)
            total_policy += policy

            cheapest = min((f["price"] for f in options), default=0) if options else 0
            total_cheapest += cheapest

            savings = (selected.get("price", 0) - cheapest) if selected else 0

            leg_insights.append({
                "leg_number": i + 1,
                "route": f"{leg.get('origin_airport', '?')} → {leg.get('destination_airport', '?')}",
                "assessment": f"{'Good choice' if savings < 50 else f'${savings:.0f} over cheapest'}" if selected else "No flight selected",
                "optimization": "Good choice" if savings < 50 else f"Consider switching to save ${savings:.0f} CAD",
            })

        savings = total_selected - total_cheapest
        policy_diff = total_selected - total_policy

        if policy_diff > total_policy * 0.1:
            recommendation = "optimize"
        elif savings > 200:
            recommendation = "review"
        else:
            recommendation = "approve"

        return {
            "summary": f"Trip total: ${total_selected:.0f} CAD across {len(legs)} legs. "
                       f"{'Within budget.' if policy_diff <= 0 else f'${policy_diff:.0f} over policy budget.'}",
            "recommendation": recommendation,
            "confidence": 0.5,
            "total_assessment": "under_budget" if policy_diff <= 0 else "over_budget",
            "key_insight": f"${savings:.0f} CAD in potential savings by switching to cheapest options" if savings > 50 else "Selections are close to optimal pricing",
            "leg_insights": leg_insights,
            "alternatives_summary": f"Cheapest combination across all legs: ${total_cheapest:.0f} CAD (saves ${savings:.0f})" if savings > 50 else "Current selections are near-optimal",
            "justification_prompt": f"Your trip total of ${total_selected:.0f} CAD is ${policy_diff:.0f} over the ${total_policy:.0f} policy budget. Could you briefly explain your flight choices?" if policy_diff > 0 else None,
            "source": "fallback",
        }


trip_intelligence = TripIntelligenceService()
