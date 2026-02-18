"""Trip Intelligence Service — LLM-powered trip-level cost analysis and optimization.

Provides:
- Trip-level cost analysis across all legs (vs cheapest, vs policy, vs stops/routing)
- Round-trip date optimization (cross-reference outbound × return prices)
- LLM-generated trip-level justification prompts
- Smart cost comparison summaries
"""

import json
import logging
from datetime import date

import anthropic

from app.config import settings

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


DATE_OPTIMIZER_SYSTEM_PROMPT = """You are a corporate travel date optimization advisor. Given outbound and return flight prices across multiple dates, identify the best date combinations and explain why.

Your response MUST be valid JSON with this exact structure:
{
    "best_combo": {
        "outbound_date": "YYYY-MM-DD",
        "return_date": "YYYY-MM-DD",
        "total_price": 0,
        "savings_vs_preferred": 0,
        "reason": "Why this combo is best (1 sentence)"
    },
    "top_combos": [
        {
            "outbound_date": "YYYY-MM-DD",
            "return_date": "YYYY-MM-DD",
            "total_price": 0,
            "outbound_airline": "Airline",
            "return_airline": "Airline",
            "outbound_stops": 0,
            "return_stops": 0,
            "trip_days": 0,
            "reason": "Brief reason"
        }
    ],
    "date_insight": "1-2 sentence insight about date patterns (e.g., midweek is cheaper, avoid weekends)",
    "flexibility_advice": "Specific advice about date flexibility and potential savings"
}

Guidelines:
- Rank combos by total round-trip price (cheapest first)
- Provide up to 5 combos
- Consider trip duration (don't suggest 1-day or 30-day trips for typical business travel)
- Note if midweek vs weekend makes a difference
- Identify if nonstop options are available at competitive prices
- Use CAD currency throughout

Respond with ONLY the JSON, no markdown, no preamble."""


class TripIntelligenceService:
    """LLM-powered trip-level cost analysis and optimization."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def analyze_trip(
        self,
        legs: list[dict],
        selected_flights: list[dict],
        all_options_per_leg: list[list[dict]],
    ) -> dict:
        """Analyze entire trip cost vs alternatives, policy, and routing options.

        Args:
            legs: List of leg info dicts (origin, destination, cabin_class, preferred_date)
            selected_flights: List of selected flight dicts per leg
            all_options_per_leg: List of all flight option lists per leg

        Returns:
            LLM-generated trip analysis with recommendations
        """
        prompt = self._build_trip_analysis_prompt(
            legs, selected_flights, all_options_per_leg
        )

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                temperature=0.2,
                system=TRIP_ANALYSIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = message.content[0].text.strip()
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

    async def optimize_dates(
        self,
        outbound_leg: dict,
        return_leg: dict,
        outbound_options: list[dict],
        return_options: list[dict],
        preferred_outbound: str,
        preferred_return: str,
    ) -> dict:
        """Cross-reference outbound × return prices for optimal date combinations.

        Args:
            outbound_leg: Outbound leg info
            return_leg: Return leg info
            outbound_options: All outbound flight options
            return_options: All return flight options
            preferred_outbound: Preferred outbound date
            preferred_return: Preferred return date

        Returns:
            LLM-generated date optimization with top combos
        """
        prompt = self._build_date_optimizer_prompt(
            outbound_leg, return_leg, outbound_options, return_options,
            preferred_outbound, preferred_return,
        )

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                temperature=0.2,
                system=DATE_OPTIMIZER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = message.content[0].text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

            result = json.loads(raw_text)
            result["source"] = "llm"
            return result

        except Exception as e:
            logger.error(f"Date optimizer LLM failed: {e}")
            return self._fallback_date_optimization(
                outbound_options, return_options,
                preferred_outbound, preferred_return,
            )

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

    def _build_date_optimizer_prompt(
        self,
        outbound_leg: dict,
        return_leg: dict,
        outbound_options: list[dict],
        return_options: list[dict],
        preferred_outbound: str,
        preferred_return: str,
    ) -> str:
        sections = [
            f"Route: {outbound_leg.get('origin_airport', '?')} → {outbound_leg.get('destination_airport', '?')} (round trip)",
            f"Preferred outbound: {preferred_outbound}",
            f"Preferred return: {preferred_return}",
            f"Cabin: {outbound_leg.get('cabin_class', 'economy')}",
            "",
            "=== OUTBOUND CHEAPEST BY DATE ===",
        ]

        # Group outbound by date
        out_by_date: dict[str, dict] = {}
        for f in outbound_options:
            d = f.get("departure_time", "")[:10]
            if not d:
                continue
            if d not in out_by_date or f["price"] < out_by_date[d]["price"]:
                out_by_date[d] = {
                    "date": d,
                    "price": f["price"],
                    "airline": f.get("airline_name", "?"),
                    "stops": f.get("stops", 0),
                }

        for d in sorted(out_by_date.keys()):
            info = out_by_date[d]
            marker = " ← preferred" if d == preferred_outbound else ""
            sections.append(f"  {d}: ${info['price']:.0f} ({info['airline']}, {info['stops']} stops){marker}")

        sections.append("")
        sections.append("=== RETURN CHEAPEST BY DATE ===")

        ret_by_date: dict[str, dict] = {}
        for f in return_options:
            d = f.get("departure_time", "")[:10]
            if not d:
                continue
            if d not in ret_by_date or f["price"] < ret_by_date[d]["price"]:
                ret_by_date[d] = {
                    "date": d,
                    "price": f["price"],
                    "airline": f.get("airline_name", "?"),
                    "stops": f.get("stops", 0),
                }

        for d in sorted(ret_by_date.keys()):
            info = ret_by_date[d]
            marker = " ← preferred" if d == preferred_return else ""
            sections.append(f"  {d}: ${info['price']:.0f} ({info['airline']}, {info['stops']} stops){marker}")

        # Cross-reference top combos
        sections.extend(["", "=== TOP DATE COMBINATIONS (by total round-trip price) ==="])
        combos = []
        for od, oi in out_by_date.items():
            for rd, ri in ret_by_date.items():
                if rd > od:
                    combos.append({
                        "out": od,
                        "ret": rd,
                        "total": oi["price"] + ri["price"],
                        "out_airline": oi["airline"],
                        "ret_airline": ri["airline"],
                        "out_stops": oi["stops"],
                        "ret_stops": ri["stops"],
                    })

        combos.sort(key=lambda c: c["total"])
        for c in combos[:10]:
            days = (date.fromisoformat(c["ret"]) - date.fromisoformat(c["out"])).days
            sections.append(
                f"  {c['out']} → {c['ret']} ({days}d): "
                f"${c['total']:.0f} = ${combos[0]['total'] + c['total'] - combos[0]['total']:.0f} "
                f"(out: {c['out_airline']} {c['out_stops']}stop, ret: {c['ret_airline']} {c['ret_stops']}stop)"
            )

        # Preferred combo price
        pref_out = out_by_date.get(preferred_outbound)
        pref_ret = ret_by_date.get(preferred_return)
        if pref_out and pref_ret:
            pref_total = pref_out["price"] + pref_ret["price"]
            best_total = combos[0]["total"] if combos else pref_total
            sections.extend([
                "",
                f"Preferred dates total: ${pref_total:.0f} CAD",
                f"Cheapest combo total: ${best_total:.0f} CAD",
                f"Potential savings: ${pref_total - best_total:.0f} CAD",
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

    def _fallback_date_optimization(
        self,
        outbound_options: list[dict],
        return_options: list[dict],
        preferred_outbound: str,
        preferred_return: str,
    ) -> dict:
        """Rule-based date optimization fallback."""
        out_by_date: dict[str, dict] = {}
        for f in outbound_options:
            d = f.get("departure_time", "")[:10]
            if d and (d not in out_by_date or f["price"] < out_by_date[d]["price"]):
                out_by_date[d] = f

        ret_by_date: dict[str, dict] = {}
        for f in return_options:
            d = f.get("departure_time", "")[:10]
            if d and (d not in ret_by_date or f["price"] < ret_by_date[d]["price"]):
                ret_by_date[d] = f

        combos = []
        for od, of in out_by_date.items():
            for rd, rf in ret_by_date.items():
                if rd > od:
                    days = (date.fromisoformat(rd) - date.fromisoformat(od)).days
                    if 1 <= days <= 21:
                        combos.append({
                            "outbound_date": od,
                            "return_date": rd,
                            "total_price": round(of["price"] + rf["price"], 2),
                            "outbound_airline": of.get("airline_name", "?"),
                            "return_airline": rf.get("airline_name", "?"),
                            "outbound_stops": of.get("stops", 0),
                            "return_stops": rf.get("stops", 0),
                            "trip_days": days,
                            "reason": "",
                        })

        combos.sort(key=lambda c: c["total_price"])
        top = combos[:5]

        pref_out = out_by_date.get(preferred_outbound)
        pref_ret = ret_by_date.get(preferred_return)
        pref_total = (pref_out["price"] + pref_ret["price"]) if pref_out and pref_ret else 0

        best = top[0] if top else None

        return {
            "best_combo": {
                "outbound_date": best["outbound_date"] if best else preferred_outbound,
                "return_date": best["return_date"] if best else preferred_return,
                "total_price": best["total_price"] if best else 0,
                "savings_vs_preferred": round(pref_total - best["total_price"], 2) if best and pref_total else 0,
                "reason": "Cheapest date combination found",
            } if best else None,
            "top_combos": top,
            "date_insight": "Prices vary by date. Midweek departures are often cheaper.",
            "flexibility_advice": f"Flexible dates could save up to ${round(pref_total - top[0]['total_price'], 2)} CAD" if top and pref_total > top[0]["total_price"] else "Your preferred dates are already well-priced",
            "source": "fallback",
        }


    def compute_trip_window_alternatives(
        self,
        outbound_options: list[dict],
        return_options: list[dict],
        preferred_outbound: str,
        preferred_return: str,
        max_proposals: int = 5,
        selected_airline_codes: list[str] | None = None,
    ) -> dict:
        """Compute trip-window alternatives that preserve trip duration.

        For each candidate outbound date, pairs with (outbound + trip_duration)
        for return. Scores PAIRS by total cost. Pure computation — no LLM call.

        If selected_airline_codes is provided, ensures at least one proposal
        uses the traveler's selected airline(s).
        """
        if not preferred_outbound or not preferred_return:
            return {"original_trip_duration": 0, "original_total_price": 0, "proposals": []}

        pref_out = date.fromisoformat(preferred_outbound)
        pref_ret = date.fromisoformat(preferred_return)
        trip_duration = (pref_ret - pref_out).days

        if trip_duration <= 0:
            return {"original_trip_duration": 0, "original_total_price": 0, "proposals": []}

        # Build cheapest flight per date for each leg
        out_by_date: dict[str, dict] = {}
        for f in outbound_options:
            d = f.get("departure_time", "")[:10]
            if d and (d not in out_by_date or f["price"] < out_by_date[d]["price"]):
                out_by_date[d] = f

        ret_by_date: dict[str, dict] = {}
        for f in return_options:
            d = f.get("departure_time", "")[:10]
            if d and (d not in ret_by_date or f["price"] < ret_by_date[d]["price"]):
                ret_by_date[d] = f

        # Build top-N cheapest per date from DIFFERENT airlines for diversity
        from collections import defaultdict
        out_top_by_date: dict[str, list[dict]] = defaultdict(list)
        for f in sorted(outbound_options, key=lambda x: x.get("price", 0)):
            d = f.get("departure_time", "")[:10]
            if not d:
                continue
            existing_airlines = {x.get("airline_code") for x in out_top_by_date[d]}
            if f.get("airline_code") not in existing_airlines and len(out_top_by_date[d]) < 3:
                out_top_by_date[d].append(f)

        ret_top_by_date: dict[str, list[dict]] = defaultdict(list)
        for f in sorted(return_options, key=lambda x: x.get("price", 0)):
            d = f.get("departure_time", "")[:10]
            if not d:
                continue
            existing_airlines = {x.get("airline_code") for x in ret_top_by_date[d]}
            if f.get("airline_code") not in existing_airlines and len(ret_top_by_date[d]) < 3:
                ret_top_by_date[d].append(f)

        # Build per-airline cheapest by date for same-airline matching
        out_by_airline_date: dict[tuple[str, str], dict] = {}
        for f in outbound_options:
            d = f.get("departure_time", "")[:10]
            airline = f.get("airline_code", "")
            key = (airline, d)
            if d and (key not in out_by_airline_date or f["price"] < out_by_airline_date[key]["price"]):
                out_by_airline_date[key] = f

        ret_by_airline_date: dict[tuple[str, str], dict] = {}
        for f in return_options:
            d = f.get("departure_time", "")[:10]
            airline = f.get("airline_code", "")
            key = (airline, d)
            if d and (key not in ret_by_airline_date or f["price"] < ret_by_airline_date[key]["price"]):
                ret_by_airline_date[key] = f

        # Original trip cost
        orig_out_price = out_by_date.get(preferred_outbound, {}).get("price", 0)
        orig_ret_price = ret_by_date.get(preferred_return, {}).get("price", 0)
        original_total = orig_out_price + orig_ret_price

        proposals = []
        seen_pairs: set[tuple] = set()

        # Generic proposals: cheapest per date, paired by trip duration
        from datetime import timedelta as td
        for out_date_str, out_flight in out_by_date.items():
            out_date = date.fromisoformat(out_date_str)
            ret_date = out_date + td(days=trip_duration)
            ret_date_str = ret_date.isoformat()

            pair_key = (out_date_str, ret_date_str)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            if out_date_str == preferred_outbound and ret_date_str == preferred_return:
                continue

            ret_flight = ret_by_date.get(ret_date_str)
            if not ret_flight:
                continue

            total = out_flight["price"] + ret_flight["price"]
            savings = original_total - total
            if savings <= 0:
                continue

            proposals.append({
                "outbound_date": out_date_str,
                "return_date": ret_date_str,
                "trip_duration": trip_duration,
                "outbound_flight": {
                    "airline_name": out_flight.get("airline_name", ""),
                    "airline_code": out_flight.get("airline_code", ""),
                    "price": out_flight["price"],
                    "stops": out_flight.get("stops", 0),
                },
                "return_flight": {
                    "airline_name": ret_flight.get("airline_name", ""),
                    "airline_code": ret_flight.get("airline_code", ""),
                    "price": ret_flight["price"],
                    "stops": ret_flight.get("stops", 0),
                },
                "total_price": round(total, 2),
                "savings": round(savings, 2),
                "savings_percent": round((savings / original_total) * 100, 1) if original_total > 0 else 0,
                "same_airline": out_flight.get("airline_code") == ret_flight.get("airline_code"),
                "airline_name": out_flight.get("airline_name") if out_flight.get("airline_code") == ret_flight.get("airline_code") else None,
            })

        # Diverse proposals: pair top-N airlines per date to get airline variety
        for out_date_str, out_flights in out_top_by_date.items():
            out_date = date.fromisoformat(out_date_str)
            ret_date = out_date + td(days=trip_duration)
            ret_date_str = ret_date.isoformat()

            if out_date_str == preferred_outbound and ret_date_str == preferred_return:
                continue

            ret_flights = ret_top_by_date.get(ret_date_str, [])
            for out_flight in out_flights:
                for ret_flight in ret_flights:
                    pair_key = (out_date_str, ret_date_str)
                    total = out_flight["price"] + ret_flight["price"]
                    savings = original_total - total
                    if savings <= 0:
                        continue
                    proposals.append({
                        "outbound_date": out_date_str,
                        "return_date": ret_date_str,
                        "trip_duration": trip_duration,
                        "outbound_flight": {
                            "airline_name": out_flight.get("airline_name", ""),
                            "airline_code": out_flight.get("airline_code", ""),
                            "price": out_flight["price"],
                            "stops": out_flight.get("stops", 0),
                        },
                        "return_flight": {
                            "airline_name": ret_flight.get("airline_name", ""),
                            "airline_code": ret_flight.get("airline_code", ""),
                            "price": ret_flight["price"],
                            "stops": ret_flight.get("stops", 0),
                        },
                        "total_price": round(total, 2),
                        "savings": round(savings, 2),
                        "savings_percent": round((savings / original_total) * 100, 1) if original_total > 0 else 0,
                        "same_airline": out_flight.get("airline_code") == ret_flight.get("airline_code"),
                        "airline_name": out_flight.get("airline_name") if out_flight.get("airline_code") == ret_flight.get("airline_code") else None,
                    })

        # Same-airline proposals
        airlines_seen: set[tuple] = set()
        for (airline, out_date_str), out_flight in out_by_airline_date.items():
            out_date = date.fromisoformat(out_date_str)
            ret_date = out_date + td(days=trip_duration)
            ret_date_str = ret_date.isoformat()

            ret_flight = ret_by_airline_date.get((airline, ret_date_str))
            if not ret_flight:
                continue

            pair_key = (out_date_str, ret_date_str, airline)
            if pair_key in airlines_seen:
                continue
            airlines_seen.add(pair_key)

            if out_date_str == preferred_outbound and ret_date_str == preferred_return:
                continue

            total = out_flight["price"] + ret_flight["price"]
            savings = original_total - total
            if savings <= 0:
                continue

            proposals.append({
                "outbound_date": out_date_str,
                "return_date": ret_date_str,
                "trip_duration": trip_duration,
                "outbound_flight": {
                    "airline_name": out_flight.get("airline_name", ""),
                    "airline_code": out_flight.get("airline_code", ""),
                    "price": out_flight["price"],
                    "stops": out_flight.get("stops", 0),
                },
                "return_flight": {
                    "airline_name": ret_flight.get("airline_name", ""),
                    "airline_code": ret_flight.get("airline_code", ""),
                    "price": ret_flight["price"],
                    "stops": ret_flight.get("stops", 0),
                },
                "total_price": round(total, 2),
                "savings": round(savings, 2),
                "savings_percent": round((savings / original_total) * 100, 1) if original_total > 0 else 0,
                "same_airline": True,
                "airline_name": out_flight.get("airline_name"),
            })

        # Deduplicate: keep best savings per (outDate, retDate, airline)
        unique: dict[tuple, dict] = {}
        for p in proposals:
            key = (p["outbound_date"], p["return_date"], p.get("airline_name", ""))
            if key not in unique or p["savings"] > unique[key]["savings"]:
                unique[key] = p

        all_sorted = sorted(unique.values(), key=lambda p: p["savings"], reverse=True)

        # Diversity pass: pick best proposal from each distinct airline pair first,
        # then fill remaining slots with highest savings regardless of airline
        def _airline_pair(p: dict) -> tuple[str, str]:
            return (p["outbound_flight"]["airline_code"], p["return_flight"]["airline_code"])

        best_per_airline: dict[tuple[str, str], dict] = {}
        for p in all_sorted:
            pair = _airline_pair(p)
            if pair not in best_per_airline:
                best_per_airline[pair] = p

        # Start with the best from each airline pair (up to max_proposals)
        diverse_picks = list(best_per_airline.values())[:max_proposals]
        diverse_set = set(id(p) for p in diverse_picks)

        # Fill remaining slots with highest savings (any airline)
        for p in all_sorted:
            if len(diverse_picks) >= max_proposals:
                break
            if id(p) not in diverse_set:
                diverse_picks.append(p)
                diverse_set.add(id(p))

        # Ensure at least one proposal matches the user's selected airline
        selected_codes = set(selected_airline_codes or [])
        if selected_codes:
            has_selected = any(
                p["outbound_flight"]["airline_code"] in selected_codes
                or p["return_flight"]["airline_code"] in selected_codes
                for p in diverse_picks
            )
            if not has_selected:
                # Find the best selected-airline proposal and swap it in
                for p in all_sorted:
                    if (p["outbound_flight"]["airline_code"] in selected_codes
                            or p["return_flight"]["airline_code"] in selected_codes):
                        if len(diverse_picks) >= max_proposals:
                            diverse_picks[-1] = p  # replace worst
                        else:
                            diverse_picks.append(p)
                        break

        sorted_proposals = sorted(diverse_picks, key=lambda p: p["savings"], reverse=True)

        return {
            "original_trip_duration": trip_duration,
            "original_total_price": round(original_total, 2),
            "proposals": sorted_proposals[:max_proposals],
        }


trip_intelligence = TripIntelligenceService()
