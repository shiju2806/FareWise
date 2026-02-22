"""Travel advisor — single LLM call for reasoning and narrative.

Replaces 4 separate LLM calls:
- trip_intelligence_service.analyze_trip()
- trip_intelligence_service.optimize_dates()
- trip_intelligence_service.curate_all_alternatives()
- justification_service.generate_trip_prompt()

Takes ResolvedResult (scored, ranked from Phase 3) + TripContext and produces:
- reason (under 15 words) for every alternative and proposal
- trip_summary (1-2 sentences)
- key_insight (single most important cost optimization insight)
- recommendation ("approve" | "review" | "optimize")
- justification_prompt (professional question for the traveler, or null)

Falls back to rule-based reasoning when LLM is unavailable.
"""

import json
import logging
import math
from dataclasses import dataclass, field

from app.services.llm_client import llm_client
from app.services.recommendation.config import recommendation_config
from app.services.recommendation.context_assembler import TripContext
from app.services.recommendation.prompts import load_prompt
from app.services.recommendation.cost_driver_analyzer import CostDriverReport
from app.services.recommendation.trade_off_resolver import (
    ResolvedResult,
    ScoredAlternative,
    ScoredProposal,
)

logger = logging.getLogger(__name__)

cfg = recommendation_config

# Load reasoning guide once at module level
_ADVISOR_GUIDE = load_prompt("travel_advisor_guide.md")


# ---------- Data structures ----------


@dataclass
class AdvisorOutput:
    """Complete advisor output — enriched result + narrative."""

    # The resolved result with reasons added in-place
    resolved: ResolvedResult

    # Trip-level narrative
    trip_summary: str = ""
    key_insight: str = ""
    recommendation: str = "review"  # "approve" | "review" | "optimize"
    justification_prompt: str | None = None
    justification_required: bool = False

    # Trip totals for frontend
    trip_totals: dict = field(default_factory=dict)

    # Source tracking
    source: str = "fallback"  # "llm" or "fallback"

    def to_dict(self) -> dict:
        """Produces the final frontend-compatible output.

        Matches the shape expected by analyze-selections endpoint.
        """
        resolved_dict = self.resolved.to_dict()

        return {
            "justification_required": self.justification_required,
            "legs": resolved_dict["legs"],
            "trip_totals": self.trip_totals,
            "trip_window_alternatives": resolved_dict.get("trip_window_alternatives"),
            "justification_prompt": self.justification_prompt,
            "trip_summary": self.trip_summary,
            "key_insight": self.key_insight,
            "recommendation": self.recommendation,
            "source": self.source,
        }


# ---------- Advisor ----------


class TravelAdvisor:
    """Single LLM call for all reasoning and narrative.

    Input: ResolvedResult (scored alternatives) + TripContext + CostDriverReport
    Output: AdvisorOutput with reasons on every alternative + trip narrative
    """

    async def advise(
        self,
        resolved: ResolvedResult,
        context: TripContext,
        cost_drivers: CostDriverReport | None = None,
    ) -> AdvisorOutput:
        """Generate reasoning for all alternatives and trip narrative.

        Makes ONE LLM call. Falls back to rule-based reasoning on failure.
        """
        # Compute trip totals
        trip_totals = self._compute_trip_totals(resolved, context)

        # Guard: if no selections yet, skip LLM and return minimal response
        if trip_totals["selected"] <= 0:
            return AdvisorOutput(
                resolved=resolved,
                trip_summary="No flights selected yet. Select flights to see cost analysis.",
                key_insight="Select flights for all legs to enable optimization analysis.",
                recommendation="review",
                justification_required=False,
                trip_totals=trip_totals,
                source="fallback",
            )

        justification_required = (
            trip_totals["savings_amount"] >= cfg.justification.min_savings_amount
            or trip_totals["savings_percent"] >= cfg.justification.min_savings_percent
        )

        # Try LLM
        try:
            output = await self._llm_advise(
                resolved, context, cost_drivers, trip_totals, justification_required,
            )
            return output
        except Exception as e:
            logger.warning(f"LLM advisor failed, using fallback: {e}")

        # Fallback: rule-based reasoning
        return self._fallback_advise(
            resolved, context, cost_drivers, trip_totals, justification_required,
        )

    # ---- LLM path ----

    async def _llm_advise(
        self,
        resolved: ResolvedResult,
        context: TripContext,
        cost_drivers: CostDriverReport | None,
        trip_totals: dict,
        justification_required: bool,
    ) -> AdvisorOutput:
        """Make the single LLM call for reasoning."""
        system_prompt = self._build_system_prompt(context, trip_totals, cost_drivers)
        user_prompt = self._build_user_prompt(resolved, context)

        raw = await llm_client.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=cfg.llm.max_tokens,
            temperature=cfg.llm.temperature,
            json_mode=cfg.llm.json_mode,
        )

        # Clean markdown fencing if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        parsed = json.loads(text)

        # Apply reasons to alternatives (fill gaps with fallback)
        reasons = parsed.get("reasons", {})
        # Truncate individual reasons to prevent UI overflow
        for key in list(reasons):
            if isinstance(reasons[key], str) and len(reasons[key]) > 80:
                reasons[key] = reasons[key][:77] + "..."
        self._apply_reasons(resolved, reasons, context)

        # Truncate LLM narrative fields to prevent UI overflow
        trip_summary = _truncate(parsed.get("trip_summary", ""), 300)
        key_insight = _truncate(parsed.get("key_insight", ""), 150)
        justification_prompt = parsed.get("justification_prompt")
        if justification_prompt and justification_required:
            justification_prompt = _truncate(justification_prompt, 300)
        elif not justification_required:
            justification_prompt = None

        return AdvisorOutput(
            resolved=resolved,
            trip_summary=trip_summary,
            key_insight=key_insight,
            recommendation=self._validate_recommendation(parsed.get("recommendation", "review")),
            justification_prompt=justification_prompt,
            justification_required=justification_required,
            trip_totals=trip_totals,
            source="llm",
        )

    def _build_system_prompt(
        self,
        context: TripContext,
        trip_totals: dict,
        cost_drivers: CostDriverReport | None,
    ) -> str:
        """Build the system prompt for the single LLM call."""
        # Traveler context
        traveler = context.traveler
        selected_airlines = []
        for leg in context.legs:
            if leg.selected_flight:
                selected_airlines.append(leg.selected_flight.airline_name)
        airline_str = selected_airlines[0] if selected_airlines else "unknown"

        # Route summary
        legs_desc = []
        for leg in context.legs:
            legs_desc.append(f"{leg.origin_airport} → {leg.destination_airport}")
        route_str = " / ".join(legs_desc)

        # Dates
        dates = []
        for leg in context.legs:
            if leg.preferred_date:
                dates.append(leg.preferred_date)
        date_str = " → ".join(dates)

        # Duration
        dur_str = f"{context.trip_duration_days}d" if context.trip_duration_days else "one-way"

        # Cost drivers
        drivers_str = ""
        if cost_drivers and cost_drivers.drivers:
            drivers_str = "\nCost drivers (why the selection costs what it does):\n"
            for d in cost_drivers.drivers[:3]:
                drivers_str += f"- {d.description} (${d.impact_amount:.0f}, {d.impact_percent:.0f}%)\n"

        # Events
        events_str = ""
        if context.events_context:
            events_str = "\nEvents at destination: " + "; ".join(context.events_context[:2])

        cabin = context.legs[0].cabin_class if context.legs else "economy"

        return f"""{_ADVISOR_GUIDE}

---

TRIP CONTEXT:
- Traveler: {traveler.name} ({traveler.role}, {traveler.department or 'N/A'})
- Route: {route_str}
- Dates: {date_str} ({dur_str})
- Cabin: {cabin}
- Selected airline: {airline_str}
- Selected total: ${trip_totals['selected']:.0f} CAD
- Cheapest available: ${trip_totals['cheapest']:.0f} CAD
- Premium over cheapest: ${trip_totals['savings_amount']:.0f} ({trip_totals['savings_percent']:.0f}%)
- Thresholds: "approve" if premium ≤ ${cfg.justification.min_savings_amount:.0f} AND ≤ {cfg.justification.min_savings_percent:.0f}%. "optimize" if ≥ $500 OR ≥ 30%.
{drivers_str}{events_str}

YOUR TASK:
For each alternative/proposal listed below, write a REASON (under 15 words) explaining why a corporate traveler should consider it. Be specific with dollar amounts and trade-offs. Follow the reasoning steps in the guide above.

Respond ONLY with valid JSON:
{{
  "reasons": {{"ALT-ID": "reason text", ...}},
  "trip_summary": "...",
  "key_insight": "...",
  "recommendation": "approve|review|optimize",
  "justification_prompt": "..." or null
}}"""

    def _build_user_prompt(
        self,
        resolved: ResolvedResult,
        context: TripContext,
    ) -> str:
        """Build the user prompt listing all alternatives for the LLM."""
        sections = []

        # Per-leg alternatives
        for leg in resolved.per_leg:
            if not leg.alternatives:
                continue
            sections.append(f"LEG: {leg.route}")
            if leg.selected:
                sel = leg.selected
                sections.append(
                    f"  Selected: {sel.get('airline', '?')} ${sel.get('price', 0):.0f} "
                    f"on {sel.get('date', '?')}"
                )
            for sa in leg.alternatives:
                alt = sa.alternative
                alt_id = f"L-{leg.leg_id}-{alt.flight_option_id}"
                net_str = ""
                if alt.net_savings:
                    net_amt = alt.net_savings.get("net_amount")
                    if net_amt is not None:
                        net_str = f" (net ${net_amt:.0f} after hotel)"
                hotel_str = ""
                if alt.hotel_impact:
                    nights = alt.hotel_impact.get("nights_added", 0)
                    if nights != 0:
                        hotel_str = f" [{nights:+d} hotel nights]"

                # Extract HH:MM from ISO departure time
                dep_short = _extract_time(alt.departure_time)
                dep_str = f" dep {dep_short}" if dep_short else ""
                dur_str = f" {alt.duration_minutes}min" if alt.duration_minutes else ""
                stop_via = ""
                if alt.stop_airports:
                    stop_via = f" via {alt.stop_airports}"

                sections.append(
                    f"  {alt_id}: [{alt.disruption_level}] {alt.alt_type} — "
                    f"{alt.airline_name} ${alt.price:.0f} on {alt.date}{dep_str},{dur_str} "
                    f"{alt.stops}stop{stop_via}, "
                    f"save ${alt.savings_amount:.0f} ({alt.savings_percent:.0f}%), "
                    f"score={sa.score.total:.0f}"
                    f"{hotel_str}{net_str}"
                )
            sections.append("")

        # Trip-window proposals (use simple TW-1, TW-2 IDs for LLM reliability)
        if resolved.trip_window:
            sections.append("TRIP WINDOW (date shifts ≤3 weeks):")
            for i, sp in enumerate(resolved.trip_window):
                p = sp.proposal
                tw_id = f"TW-{i + 1}"
                ua_tag = " [USER'S AIRLINE]" if p.is_user_airline else ""
                net_str = ""
                if p.net_savings:
                    net_amt = p.net_savings.get("net_amount")
                    if net_amt is not None:
                        net_str = f" (net ${net_amt:.0f} after hotel)"
                out_dep = _extract_time(p.outbound_flight.departure_time)
                ret_dep = _extract_time(p.return_flight.departure_time)
                out_time = f" dep {out_dep}" if out_dep else ""
                ret_time = f" dep {ret_dep}" if ret_dep else ""
                sections.append(
                    f"  {tw_id}: {p.outbound_date} → {p.return_date} ({p.trip_duration}d) | "
                    f"{p.outbound_flight.airline_name} ${p.outbound_flight.price:.0f}{out_time} + "
                    f"{p.return_flight.airline_name} ${p.return_flight.price:.0f}{ret_time} = "
                    f"${p.total_price:.0f}, save ${p.savings_amount:.0f}, "
                    f"score={sp.score.total:.0f}{ua_tag}{net_str}"
                )
            sections.append("")

        if resolved.different_month:
            sections.append("DIFFERENT MONTH (date shifts >3 weeks):")
            for i, sp in enumerate(resolved.different_month):
                p = sp.proposal
                dm_id = f"DM-{i + 1}"
                ua_tag = " [USER'S AIRLINE]" if p.is_user_airline else ""
                net_str = ""
                if p.net_savings:
                    net_amt = p.net_savings.get("net_amount")
                    if net_amt is not None:
                        net_str = f" (net ${net_amt:.0f} after hotel)"
                out_dep = _extract_time(p.outbound_flight.departure_time)
                ret_dep = _extract_time(p.return_flight.departure_time)
                out_time = f" dep {out_dep}" if out_dep else ""
                ret_time = f" dep {ret_dep}" if ret_dep else ""
                sections.append(
                    f"  {dm_id}: {p.outbound_date} → {p.return_date} ({p.trip_duration}d) | "
                    f"{p.outbound_flight.airline_name} ${p.outbound_flight.price:.0f}{out_time} + "
                    f"{p.return_flight.airline_name} ${p.return_flight.price:.0f}{ret_time} = "
                    f"${p.total_price:.0f}, save ${p.savings_amount:.0f}, "
                    f"score={sp.score.total:.0f}{ua_tag}{net_str}"
                )
            sections.append("")

        return "\n".join(sections)

    def _apply_reasons(
        self,
        resolved: ResolvedResult,
        reasons: dict,
        context: TripContext,
    ) -> None:
        """Apply LLM-generated reasons, fill gaps with rule-based fallback."""
        total_expected = 0
        total_matched = 0

        # Per-leg alternatives
        for leg in resolved.per_leg:
            for sa in leg.alternatives:
                total_expected += 1
                alt = sa.alternative
                alt_id = f"L-{leg.leg_id}-{alt.flight_option_id}"
                if alt_id in reasons:
                    sa.reason = reasons[alt_id]
                    total_matched += 1
                else:
                    sa.reason = self._generate_alt_reason(sa, context)
                    logger.warning(
                        f"LLM reason missing for {alt_id} ({alt.alt_type}, "
                        f"{alt.airline_name}), using fallback: {sa.reason!r}"
                    )

        # Trip-window proposals (simple TW-1, TW-2 IDs)
        for i, sp in enumerate(resolved.trip_window):
            total_expected += 1
            tw_id = f"TW-{i + 1}"
            if tw_id in reasons:
                sp.proposal.reason = reasons[tw_id]
                total_matched += 1
            elif not sp.proposal.reason:
                sp.proposal.reason = self._generate_tw_reason(sp, context)
                logger.warning(
                    f"LLM reason missing for {tw_id} ({sp.proposal.outbound_date} → "
                    f"{sp.proposal.return_date}), using fallback: {sp.proposal.reason!r}"
                )

        # Different-month proposals (simple DM-1, DM-2 IDs)
        for i, sp in enumerate(resolved.different_month):
            total_expected += 1
            dm_id = f"DM-{i + 1}"
            if dm_id in reasons:
                sp.proposal.reason = reasons[dm_id]
                total_matched += 1
            elif not sp.proposal.reason:
                sp.proposal.reason = self._generate_tw_reason(sp, context)
                logger.warning(
                    f"LLM reason missing for {dm_id} ({sp.proposal.outbound_date} → "
                    f"{sp.proposal.return_date}), using fallback: {sp.proposal.reason!r}"
                )

        if total_expected > 0:
            hit_rate = total_matched / total_expected * 100
            if hit_rate < 50:
                logger.warning(
                    f"LLM reason hit rate low: {total_matched}/{total_expected} "
                    f"({hit_rate:.0f}%). LLM returned keys: {list(reasons.keys())[:5]}"
                )
            else:
                logger.info(f"LLM reasons: {total_matched}/{total_expected} matched ({hit_rate:.0f}%)")

    # ---- Fallback path ----

    def _fallback_advise(
        self,
        resolved: ResolvedResult,
        context: TripContext,
        cost_drivers: CostDriverReport | None,
        trip_totals: dict,
        justification_required: bool,
    ) -> AdvisorOutput:
        """Rule-based reasoning when LLM is unavailable."""
        # Generate reasons for each alternative
        for leg in resolved.per_leg:
            for sa in leg.alternatives:
                sa.reason = self._generate_alt_reason(sa, context)

        for sp in resolved.trip_window:
            sp.proposal.reason = self._generate_tw_reason(sp, context)

        for sp in resolved.different_month:
            sp.proposal.reason = self._generate_tw_reason(sp, context)

        # Generate narrative
        trip_summary = self._generate_trip_summary(trip_totals, context, cost_drivers)
        key_insight = self._generate_key_insight(resolved, trip_totals, cost_drivers)
        recommendation = self._compute_recommendation(trip_totals)

        justification_prompt = None
        if justification_required:
            justification_prompt = self._generate_justification_prompt(trip_totals, context)

        return AdvisorOutput(
            resolved=resolved,
            trip_summary=trip_summary,
            key_insight=key_insight,
            recommendation=recommendation,
            justification_prompt=justification_prompt,
            justification_required=justification_required,
            trip_totals=trip_totals,
            source="fallback",
        )

    def _generate_alt_reason(
        self,
        sa: ScoredAlternative,
        context: TripContext,
    ) -> str:
        """Generate a rule-based reason for a per-leg alternative."""
        alt = sa.alternative
        savings = alt.savings_amount

        if alt.alt_type == "same_date":
            return f"Save ${savings:.0f} with {alt.airline_name}, same date and route"

        if alt.alt_type == "nearby_airport":
            return f"Save ${savings:.0f} via {alt.origin_airport}, same date"

        if alt.alt_type == "same_airline_routing":
            stop_label = f"{alt.stops} stop" if alt.stops == 1 else f"{alt.stops} stops"
            return f"Save ${savings:.0f} on {alt.airline_name} with {stop_label}"

        if alt.alt_type == "same_airline_date_shift":
            # Include hotel impact if available
            if alt.net_savings:
                net = alt.net_savings.get("net_amount")
                if net is not None and net != savings:
                    return f"{alt.airline_name} on {alt.date}, ${net:.0f} net savings after hotel"
            return f"{alt.airline_name} on {alt.date} saves ${savings:.0f}"

        if alt.alt_type == "cabin_downgrade":
            cabin_name = alt.cabin_class.replace("_", " ").title()
            return f"{cabin_name} saves ${savings:.0f}, same flight and schedule"

        return f"Save ${savings:.0f} — {alt.label or alt.airline_name or 'alternative option'}"

    def _generate_tw_reason(
        self,
        sp: ScoredProposal,
        context: TripContext,
    ) -> str:
        """Generate a rule-based reason for a trip-window proposal."""
        p = sp.proposal

        airline_desc = p.airline_name if p.same_airline else (
            f"{p.outbound_flight.airline_name}/{p.return_flight.airline_name}"
        )

        # Net savings
        net_str = ""
        if p.net_savings:
            net = p.net_savings.get("net_amount")
            if net is not None and abs(net - p.savings_amount) > 50:
                net_str = f" (${net:.0f} net after hotel)"

        if p.is_user_airline:
            return f"Your airline on {p.outbound_date}, save ${p.savings_amount:.0f}{net_str}"

        if p.duration_change != 0:
            dur_str = f"{p.duration_change:+d}d"
            return f"{airline_desc} {dur_str} trip, save ${p.savings_amount:.0f}{net_str}"

        return f"{airline_desc} shifted dates, save ${p.savings_amount:.0f}{net_str}"

    def _generate_trip_summary(
        self,
        trip_totals: dict,
        context: TripContext,
        cost_drivers: CostDriverReport | None,
    ) -> str:
        """Generate a 1-2 sentence trip cost summary."""
        selected = trip_totals["selected"]
        cheapest = trip_totals["cheapest"]
        savings = trip_totals["savings_amount"]
        pct = trip_totals["savings_percent"]

        if savings <= 0:
            return (
                f"Trip total ${selected:.0f} CAD is at or below the cheapest available. "
                f"Good selection."
            )

        # Get primary cost driver
        driver_str = ""
        if cost_drivers and cost_drivers.primary_driver:
            d = cost_drivers.primary_driver
            driver_str = f" Primary driver: {d.description.lower()}."

        if pct >= 20:
            return (
                f"Trip total ${selected:.0f} CAD is ${savings:.0f} ({pct:.0f}%) above "
                f"the cheapest option at ${cheapest:.0f}.{driver_str}"
            )
        if pct >= 10:
            return (
                f"Trip total ${selected:.0f} CAD has moderate savings potential of "
                f"${savings:.0f} ({pct:.0f}%).{driver_str}"
            )
        return (
            f"Trip total ${selected:.0f} CAD is close to optimal, "
            f"${savings:.0f} ({pct:.0f}%) above cheapest.{driver_str}"
        )

    def _generate_key_insight(
        self,
        resolved: ResolvedResult,
        trip_totals: dict,
        cost_drivers: CostDriverReport | None,
    ) -> str:
        """Generate the single most actionable insight."""
        # Priority: cost driver > best trip-window > best per-leg alternative
        if cost_drivers and cost_drivers.primary_driver:
            d = cost_drivers.primary_driver
            return d.description

        # Best trip-window proposal
        best_tw = None
        for sp in resolved.trip_window + resolved.different_month:
            if best_tw is None or sp.proposal.savings_amount > best_tw.proposal.savings_amount:
                best_tw = sp

        if best_tw and best_tw.proposal.savings_amount >= 200:
            p = best_tw.proposal
            return (
                f"Shifting to {p.outbound_date} → {p.return_date} saves "
                f"${p.savings_amount:.0f} ({p.savings_percent:.0f}%)"
            )

        # Best per-leg alternative
        best_alt = None
        for leg in resolved.per_leg:
            for sa in leg.alternatives:
                if best_alt is None or sa.alternative.savings_amount > best_alt.alternative.savings_amount:
                    best_alt = sa

        if best_alt and best_alt.alternative.savings_amount >= 50:
            alt = best_alt.alternative
            return f"{alt.label} saves ${alt.savings_amount:.0f}"

        return "Selection is cost-efficient — no significant savings available."

    def _compute_recommendation(self, trip_totals: dict) -> str:
        """Compute approve/review/optimize from trip totals."""
        pct = trip_totals["savings_percent"]
        amount = trip_totals["savings_amount"]

        if amount <= cfg.justification.min_savings_amount and pct <= cfg.justification.min_savings_percent:
            return "approve"
        if pct >= 30 or amount >= 500:
            return "optimize"
        return "review"

    def _generate_justification_prompt(
        self,
        trip_totals: dict,
        context: TripContext,
    ) -> str:
        """Generate a professional justification prompt for the traveler."""
        selected = trip_totals["selected"]
        savings = trip_totals["savings_amount"]
        pct = trip_totals["savings_percent"]

        return (
            f"Your trip total of ${selected:.0f} CAD is ${savings:.0f} ({pct:.0f}%) "
            f"above the cheapest available options. Could you briefly explain your "
            f"flight selections — for example, airline preference, schedule requirements, "
            f"or meeting constraints?"
        )

    # ---- Shared helpers ----

    def _compute_trip_totals(
        self,
        resolved: ResolvedResult,
        context: TripContext,
    ) -> dict:
        """Compute trip totals matching frontend's trip_totals shape."""
        total_selected = context.selected_total
        total_cheapest = context.cheapest_total

        # Guard against NaN propagation from bad price data
        if not math.isfinite(total_selected):
            total_selected = 0.0
        if not math.isfinite(total_cheapest):
            total_cheapest = 0.0

        savings_amount = round(total_selected - total_cheapest, 2)
        savings_percent = (
            round((savings_amount / total_selected) * 100, 1)
            if total_selected > 0 else 0.0
        )

        return {
            "selected": round(total_selected, 2),
            "cheapest": round(total_cheapest, 2),
            "savings_amount": savings_amount,
            "savings_percent": savings_percent,
        }

    @staticmethod
    def _validate_recommendation(rec: str) -> str:
        """Ensure recommendation is a valid value."""
        if rec in ("approve", "review", "optimize"):
            return rec
        return "review"


def _extract_time(departure_time: str) -> str:
    """Extract HH:MM from ISO datetime string (e.g. '2025-04-12T14:30:00' → '14:30')."""
    if not departure_time or len(departure_time) < 16:
        return ""
    return departure_time[11:16]


def _truncate(text, max_len: int) -> str:
    """Truncate text to max_len, appending '...' if truncated."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


# Singleton
travel_advisor = TravelAdvisor()
