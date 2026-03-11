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
import re
from dataclasses import dataclass, field

from app.services.llm_client import llm_client
from app.services.recommendation.airline_tiers import get_tier, get_alliance
from app.services.recommendation.config import recommendation_config
from app.services.recommendation.context_assembler import TripContext
from app.services.recommendation.cost_driver_analyzer import CostDriverReport
from app.services.recommendation.trade_off_resolver import (
    ResolvedResult,
    ScoredAlternative,
    ScoredProposal,
)

logger = logging.getLogger(__name__)

cfg = recommendation_config


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
    manager_narrative: str = ""

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
            "manager_narrative": self.manager_narrative,
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
        """Make the single LLM call for selection + reasoning."""
        import copy

        system_prompt = self._build_system_prompt(context, trip_totals, cost_drivers)
        user_prompt = self._build_user_prompt(resolved, context)

        # Log user prompt for debugging (shows what the LLM sees)
        logger.debug(f"LLM user prompt:\n{user_prompt}")

        # Deep-copy before LLM filters — used for validation fallback
        original_resolved = copy.deepcopy(resolved)

        raw = await llm_client.complete(
            system=system_prompt,
            user=user_prompt,
            max_tokens=cfg.llm.max_tokens,
            temperature=cfg.llm.temperature,
            json_mode=cfg.llm.json_mode,
            model=cfg.llm.model_primary,
        )

        # Extract reasoning and JSON from free-form response
        text = raw.strip()
        logger.debug(f"LLM raw response ({len(text)} chars):\n{text[:1500]}")

        # Log the free-form reasoning (everything before the JSON block)
        json_start = text.find("```json")
        if json_start > 0:
            reasoning = text[:json_start].strip()
            reasoning_preview = reasoning[:300] + "..." if len(reasoning) > 300 else reasoning
            logger.info(f"LLM reasoning: {reasoning_preview}")
            logger.debug(f"LLM reasoning (full): {reasoning}")
        else:
            # No fenced block — check if response starts with { (direct JSON)
            brace_start = text.find("{")
            if brace_start > 0:
                reasoning = text[:brace_start].strip()
                if reasoning:
                    reasoning_preview = reasoning[:300] + "..." if len(reasoning) > 300 else reasoning
                    logger.info(f"LLM reasoning: {reasoning_preview}")

        # Extract and parse JSON block
        json_text = _extract_json_block(text)
        parsed = json.loads(json_text)

        # Log selection summary
        per_leg_data = parsed.get("per_leg", {})
        for lid, selections in per_leg_data.items():
            logger.debug(f"LLM leg {lid}: selected={list(selections.keys())}")

        # Apply LLM selections — filter alternatives to only those selected
        self._apply_selections(resolved, parsed, context)

        # Validate selections — enforce safety invariants
        self._validate_selections(resolved, original_resolved, context)

        # Truncate LLM narrative fields to prevent UI overflow
        trip_summary = _truncate(parsed.get("trip_summary", ""), cfg.llm.trip_summary_max_chars)
        key_insight = _truncate(parsed.get("key_insight", ""), cfg.llm.key_insight_max_chars)
        manager_narrative = _truncate(parsed.get("manager_narrative", ""), cfg.llm.manager_narrative_max_chars)
        justification_prompt = parsed.get("justification_prompt")
        if justification_prompt and justification_required:
            justification_prompt = _truncate(justification_prompt, cfg.llm.justification_prompt_max_chars)
        elif not justification_required:
            justification_prompt = None

        return AdvisorOutput(
            resolved=resolved,
            trip_summary=trip_summary,
            key_insight=key_insight,
            recommendation=self._validate_recommendation(parsed.get("recommendation", "review")),
            justification_prompt=justification_prompt,
            justification_required=justification_required,
            manager_narrative=manager_narrative,
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
        # Airline tier for context
        selected_codes = []
        for leg in context.legs:
            if leg.selected_flight:
                selected_codes.append(leg.selected_flight.airline_code)
        airline_tier = get_tier(selected_codes[0]) if selected_codes else "unknown"

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

        return f"""You are a corporate travel advisor. Analyze the alternatives below and select the best 3-5 per leg to show the traveler.

TRIP: {route_str}, {date_str} ({dur_str}), {cabin} class
TRAVELER: {traveler.name} ({traveler.role}), selected {airline_str} [{airline_tier.upper().replace('_', ' ')}]
COST: ${trip_totals['selected']:.0f} total, ${trip_totals['savings_amount']:.0f} ({trip_totals['savings_percent']:.0f}%) over cheapest
{drivers_str}{events_str}
THRESHOLDS: approve ≤${cfg.justification.min_savings_amount:.0f}/≤{cfg.justification.min_savings_percent:.0f}%, optimize ≥${cfg.justification.optimize_amount:.0f}/≥{cfg.justification.optimize_percent:.0f}%

INSTRUCTIONS:
1. Think through each alternative: savings, day/time, airline tier, disruption level.
2. Select 3-5 per leg with meaningfully different trade-offs.
3. Always keep: 1 cabin downgrade (if available), 1 user's airline option, 1 non-user airline for comparison.
4. Drop: work-hours departures (Mon-Thu 9am-5pm), near-zero savings, duplicates.
5. Trip-window/different-month: prefer user's airline, max 1 non-user for comparison.
6. TIER RULE: For business/first class, only select full-service alternatives. Lower-tier carriers have been pre-filtered; any remaining are tagged budget exceptions with significant savings.

Write a BRIEF analysis (5-8 bullet points max), then output a ```json block with EXACT short IDs from the prompt (L1-1, L2-1, TW-1, DM-1, etc.):
```json
{{
  "per_leg": {{"1": {{"L1-1": "reason under 20 words", "L1-3": "reason"}}, "2": {{"L2-1": "reason"}}}},
  "trip_window": {{"TW-1": "reason"}},
  "different_month": {{"DM-1": "reason"}},
  "trip_summary": "2-3 sentences: total cost, premium, cost driver, savings available",
  "key_insight": "Single most actionable optimization with airline, date, amount",
  "recommendation": "approve|review|optimize",
  "justification_prompt": "Question referencing best alternative with savings, or null",
  "manager_narrative": "3-4 factual sentences for manager: cost, carrier, routing, compliance"
}}
```"""

    def _build_user_prompt(
        self,
        resolved: ResolvedResult,
        context: TripContext,
    ) -> str:
        """Build the user prompt listing all alternatives for the LLM.

        Uses short IDs (L1-1, L1-2, L2-1, ...) instead of UUID-based IDs
        for reliable LLM copy-paste. The mapping from short IDs to actual
        flight_option_ids is stored on the resolved object for _apply_selections.
        """
        sections = []

        # Build short ID mapping: "L1-1" → (leg_id, flight_option_id)
        # Store on resolved for use by _apply_selections
        resolved._short_id_map = {}

        # Per-leg alternatives
        for leg_idx, leg in enumerate(resolved.per_leg):
            if not leg.alternatives:
                continue
            leg_num = leg_idx + 1
            sections.append(f"LEG {leg_num}: {leg.route}")
            if leg.selected:
                sel = leg.selected
                sections.append(
                    f"  Selected: {sel.get('airline', '?')} ${sel.get('price', 0):.0f} "
                    f"on {sel.get('date', '?')}"
                )
            for alt_idx, sa in enumerate(leg.alternatives):
                alt = sa.alternative
                short_id = f"L{leg_num}-{alt_idx + 1}"
                resolved._short_id_map[short_id] = (leg.leg_id, alt.flight_option_id)
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

                ua_tag = " [USER'S AIRLINE]" if alt.is_user_airline else ""
                tier = get_tier(alt.airline_code)
                tier_tag = {"full_service": " [FULL SERVICE]", "mid_tier": " [MID TIER]", "low_cost": " [LOW COST]"}.get(tier, "")
                # Show cabin class for cabin downgrade alternatives
                cabin_tag = ""
                if alt.alt_type == "cabin_downgrade" and hasattr(alt, "cabin_class") and alt.cabin_class:
                    cabin_tag = f" [CABIN: {alt.cabin_class.upper().replace('_', ' ')}]"
                sections.append(
                    f"  {short_id}: [{alt.disruption_level}] {alt.alt_type} — "
                    f"{alt.airline_name} ${alt.price:.0f} on {alt.date}{dep_str},{dur_str} "
                    f"{alt.stops}stop{stop_via}, "
                    f"save ${alt.savings_amount:.0f} ({alt.savings_percent:.0f}%), "
                    f"score={sa.score.total:.0f}"
                    f"{ua_tag}{tier_tag}{cabin_tag}{hotel_str}{net_str}"
                )
            sections.append("")

        # Trip-window proposals (use simple TW-1, TW-2 IDs for LLM reliability)
        if resolved.trip_window:
            sections.append(f"TRIP WINDOW — select up to {cfg.limits.layer2_max}:")
            for i, sp in enumerate(resolved.trip_window):
                p = sp.proposal
                tw_id = f"TW-{i + 1}"
                ua_tag = " [USER'S AIRLINE]" if p.is_user_airline else ""
                out_tier = get_tier(p.outbound_flight.airline_code)
                tier_tag = {"full_service": " [FULL SERVICE]", "mid_tier": " [MID TIER]", "low_cost": " [LOW COST]"}.get(out_tier, "")
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
                    f"score={sp.score.total:.0f}{ua_tag}{tier_tag}{net_str}"
                )
            sections.append("")

        if resolved.different_month:
            sections.append(f"DIFFERENT MONTH — select up to {cfg.limits.layer3_max}:")
            for i, sp in enumerate(resolved.different_month):
                p = sp.proposal
                dm_id = f"DM-{i + 1}"
                ua_tag = " [USER'S AIRLINE]" if p.is_user_airline else ""
                out_tier = get_tier(p.outbound_flight.airline_code)
                tier_tag = {"full_service": " [FULL SERVICE]", "mid_tier": " [MID TIER]", "low_cost": " [LOW COST]"}.get(out_tier, "")
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
                    f"score={sp.score.total:.0f}{ua_tag}{tier_tag}{net_str}"
                )
            sections.append("")

        return "\n".join(sections)

    def _apply_selections(
        self,
        resolved: ResolvedResult,
        parsed: dict,
        context: TripContext,
    ) -> None:
        """Filter alternatives to only those the LLM selected, apply reasons.

        Unlike _apply_reasons which filled gaps with fallback, this method DROPS
        alternatives the LLM didn't select. The LLM is the intelligent curator.

        Uses short IDs (L1-1, L1-2, ...) that map to per-leg alternatives via
        the _short_id_map built in _build_user_prompt.
        """
        per_leg_data = parsed.get("per_leg", {})
        total_pool = 0
        total_selected = 0

        # Build reverse mapping: (leg_id, flight_option_id) → short_id
        short_id_map = getattr(resolved, "_short_id_map", {})
        reverse_map = {v: k for k, v in short_id_map.items()}

        for leg_idx, leg in enumerate(resolved.per_leg):
            pool_size = len(leg.alternatives)
            total_pool += pool_size

            # Flat map: {"L1-1": "reason", "L1-3": "reason"}
            leg_num = str(leg_idx + 1)
            selected_map = per_leg_data.get(leg_num, per_leg_data.get(leg.leg_id, {}))

            if not selected_map:
                logger.warning(f"LLM returned no selections for leg {leg_num} ({leg.route})")
                continue

            # Filter alternatives to only selected ones
            kept = []
            for sa in leg.alternatives:
                short_id = reverse_map.get((leg.leg_id, sa.alternative.flight_option_id), "")
                if short_id in selected_map:
                    reason = selected_map[short_id]
                    if isinstance(reason, str) and len(reason) > cfg.llm.reason_max_chars:
                        reason = reason[:cfg.llm.reason_max_chars - 3] + "..."
                    sa.reason = reason
                    kept.append(sa)
                else:
                    logger.info(
                        f"LLM dropped {short_id} ({sa.alternative.airline_name} "
                        f"${sa.alternative.price:.0f})"
                    )

            total_selected += len(kept)
            leg.alternatives = kept

        # Trip-window — flat map
        tw_selected = parsed.get("trip_window", {})
        kept_tw = []
        for i, sp in enumerate(resolved.trip_window):
            tw_id = f"TW-{i + 1}"
            if tw_id in tw_selected:
                reason = tw_selected[tw_id]
                if isinstance(reason, str) and len(reason) > cfg.llm.reason_max_chars:
                    reason = reason[:cfg.llm.reason_max_chars - 3] + "..."
                sp.proposal.reason = reason
                kept_tw.append(sp)
            else:
                logger.debug(f"LLM dropped {tw_id}")
        total_pool += len(resolved.trip_window)
        total_selected += len(kept_tw)
        resolved.trip_window = kept_tw

        # Different-month — flat map
        dm_selected = parsed.get("different_month", {})
        kept_dm = []
        for i, sp in enumerate(resolved.different_month):
            dm_id = f"DM-{i + 1}"
            if dm_id in dm_selected:
                reason = dm_selected[dm_id]
                if isinstance(reason, str) and len(reason) > cfg.llm.reason_max_chars:
                    reason = reason[:cfg.llm.reason_max_chars - 3] + "..."
                sp.proposal.reason = reason
                kept_dm.append(sp)
            else:
                logger.debug(f"LLM dropped {dm_id}")
        total_pool += len(resolved.different_month)
        total_selected += len(kept_dm)
        resolved.different_month = kept_dm

        logger.info(
            f"LLM veto: {total_selected}/{total_pool} alternatives selected "
            f"({total_pool - total_selected} dropped)"
        )

    def _validate_selections(
        self,
        resolved: ResolvedResult,
        original_resolved: ResolvedResult,
        context: TripContext,
    ) -> None:
        """Validate LLM selections — enforce safety invariants.

        Rules:
        1. Max total_max (5) per leg
        2. At least 1 user-airline per leg (if any existed in pool)
        3. If LLM returned empty for a leg, fall back to top-3 by score
        4. Max layer2_max (4) trip-window, max layer3_max (4) different-month
        """
        for leg, orig_leg in zip(resolved.per_leg, original_resolved.per_leg):
            # Rule 1: cap per leg
            if len(leg.alternatives) > cfg.limits.total_max:
                leg.alternatives = leg.alternatives[:cfg.limits.total_max]

            # Rule 2: at least 1 user-airline
            has_user = any(sa.alternative.is_user_airline for sa in leg.alternatives)
            pool_had_user = any(sa.alternative.is_user_airline for sa in orig_leg.alternatives)
            if pool_had_user and not has_user:
                for sa in orig_leg.alternatives:
                    if sa.alternative.is_user_airline:
                        sa.reason = self._generate_alt_reason(sa, context)
                        leg.alternatives.append(sa)
                        logger.info(
                            f"Validation: added back user-airline {sa.alternative.airline_name} "
                            f"for leg {leg.leg_id}"
                        )
                        break

            # Rule 3: at least 1 non-user-airline for price comparison
            has_non_user = any(not sa.alternative.is_user_airline for sa in leg.alternatives)
            pool_had_non_user = any(not sa.alternative.is_user_airline for sa in orig_leg.alternatives)
            logger.debug(
                f"Validation check leg {leg.leg_id}: has_non_user={has_non_user}, "
                f"pool_had_non_user={pool_had_non_user}, "
                f"current_count={len(leg.alternatives)}, max={cfg.limits.total_max}"
            )
            if pool_had_non_user and not has_non_user and len(leg.alternatives) < cfg.limits.total_max:
                # Add back highest-savings non-user alternative from pool
                for sa in sorted(
                    orig_leg.alternatives,
                    key=lambda s: s.alternative.savings_amount,
                    reverse=True,
                ):
                    if not sa.alternative.is_user_airline:
                        sa.reason = self._generate_alt_reason(sa, context)
                        leg.alternatives.append(sa)
                        logger.info(
                            f"Validation: added back non-user-airline {sa.alternative.airline_name} "
                            f"(saves ${sa.alternative.savings_amount:.0f}) for leg {leg.leg_id}"
                        )
                        break

            # Rule 4: empty fallback
            if not leg.alternatives:
                leg.alternatives = orig_leg.alternatives[:3]
                for sa in leg.alternatives:
                    sa.reason = self._generate_alt_reason(sa, context)
                logger.warning(
                    f"Validation: LLM returned empty for leg {leg.leg_id}, "
                    f"falling back to top-3 by score"
                )

        # Rule 4: user-airline guarantee for trip-window
        tw_has_user = any(sp.proposal.is_user_airline for sp in resolved.trip_window)
        tw_pool_had_user = any(sp.proposal.is_user_airline for sp in original_resolved.trip_window)
        if tw_pool_had_user and not tw_has_user:
            for sp in original_resolved.trip_window:
                if sp.proposal.is_user_airline:
                    sp.proposal.reason = self._generate_tw_reason(sp, context)
                    resolved.trip_window.insert(0, sp)
                    logger.info(
                        f"Validation: added back user-airline trip-window proposal "
                        f"({sp.proposal.outbound_flight.airline_name})"
                    )
                    break

        # Rule 5: user-airline guarantee for different-month
        dm_has_user = any(sp.proposal.is_user_airline for sp in resolved.different_month)
        dm_pool_had_user = any(sp.proposal.is_user_airline for sp in original_resolved.different_month)
        if dm_pool_had_user and not dm_has_user:
            for sp in original_resolved.different_month:
                if sp.proposal.is_user_airline:
                    sp.proposal.reason = self._generate_tw_reason(sp, context)
                    resolved.different_month.insert(0, sp)
                    logger.info(
                        f"Validation: added back user-airline different-month proposal "
                        f"({sp.proposal.outbound_flight.airline_name})"
                    )
                    break

        # Rule 6: cap trip-window and different-month
        if len(resolved.trip_window) > cfg.limits.layer2_max:
            resolved.trip_window = resolved.trip_window[:cfg.limits.layer2_max]
        if len(resolved.different_month) > cfg.limits.layer3_max:
            resolved.different_month = resolved.different_month[:cfg.limits.layer3_max]

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
        manager_narrative = self._generate_manager_narrative(trip_totals, context)

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
            manager_narrative=manager_narrative,
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
            # Include work-hours and hotel context
            wh_note = ""
            if cfg.work_hours.is_work_hours(alt.departure_time):
                wh_note = ", mid-day departure"
            if alt.net_savings:
                net = alt.net_savings.get("net_amount")
                if net is not None and net != savings:
                    return f"{alt.airline_name} on {alt.date}, ${net:.0f} net after hotel{wh_note}"
            return f"{alt.airline_name} on {alt.date} saves ${savings:.0f}{wh_note}"

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

        if best_tw and best_tw.proposal.savings_amount >= cfg.alternatives.layer3_min_savings:
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

        if best_alt and best_alt.alternative.savings_amount >= cfg.alternatives.layer1_min_savings:
            alt = best_alt.alternative
            return f"{alt.label} saves ${alt.savings_amount:.0f}"

        return "Selection is cost-efficient — no significant savings available."

    def _compute_recommendation(self, trip_totals: dict) -> str:
        """Compute approve/review/optimize from trip totals."""
        pct = trip_totals["savings_percent"]
        amount = trip_totals["savings_amount"]

        if amount <= cfg.justification.min_savings_amount and pct <= cfg.justification.min_savings_percent:
            return "approve"
        if pct >= cfg.justification.optimize_percent or amount >= cfg.justification.optimize_amount:
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

    def _generate_manager_narrative(
        self,
        trip_totals: dict,
        context: TripContext,
    ) -> str:
        """Generate a 3-4 sentence factual narrative for manager approval (fallback)."""
        selected = trip_totals["selected"]
        cheapest = trip_totals["cheapest"]
        savings = trip_totals["savings_amount"]
        pct = trip_totals["savings_percent"]
        num_legs = len(context.legs)

        traveler = context.traveler
        route_parts = [f"{leg.origin_airport} → {leg.destination_airport}" for leg in context.legs]
        route_str = " / ".join(route_parts)

        # Sentence 1: total cost positioning
        parts = [
            f"{traveler.name} selected a {num_legs}-leg itinerary ({route_str}) "
            f"totaling ${selected:.0f} CAD."
        ]

        # Sentence 2: cheapest comparison
        if savings > 0:
            parts.append(
                f"This is ${savings:.0f} ({pct:.0f}%) above the lowest-fare combination "
                f"of ${cheapest:.0f} CAD."
            )
        else:
            parts.append(
                "The selected flights match or beat the lowest available fares."
            )

        # Sentence 3: notable choices (airlines, nonstop)
        airlines = set()
        nonstop_count = 0
        for leg in context.legs:
            if leg.selected_flight:
                airlines.add(leg.selected_flight.airline_name)
                if leg.selected_flight.stops == 0:
                    nonstop_count += 1
        if airlines:
            airline_str = ", ".join(sorted(airlines))
            nonstop_str = f" ({nonstop_count} nonstop)" if nonstop_count > 0 else ""
            parts.append(f"Selected carrier(s): {airline_str}{nonstop_str}.")

        # Sentence 4: policy
        policy_status = trip_totals.get("policy_status", "")
        if "over" in str(policy_status):
            parts.append("Trip exceeds policy budget.")
        elif "under" in str(policy_status) or "at" in str(policy_status):
            parts.append("All selections are within policy.")

        return " ".join(parts)

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
    """Extract day-of-week + HH:MM from ISO datetime, with work-hours tag.

    Examples:
        '2025-04-12T14:30:00' → 'Sat 14:30'
        '2025-04-16T12:35:00' → 'Wed 12:35 [WORK HRS]'
    """
    if not departure_time or len(departure_time) < 16:
        return ""
    try:
        from datetime import datetime as _dt
        dt = _dt.fromisoformat(departure_time[:19])
        result = dt.strftime("%a %H:%M")
        if cfg.work_hours.is_work_hours(departure_time):
            result += " [WORK HRS]"
        return result
    except (ValueError, TypeError):
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


def _extract_json_block(text: str) -> str:
    """Extract JSON from free-form LLM response.

    Looks for ```json ... ``` fenced block first,
    falls back to finding the outermost { ... } pair.
    """
    m = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]

    raise ValueError("No JSON block found in LLM response")


# Singleton
travel_advisor = TravelAdvisor()
