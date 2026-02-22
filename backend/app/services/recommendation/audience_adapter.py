"""Audience adapter — formats recommendation output for three audiences.

Takes AdvisorOutput (Phase 4) + TripContext (Phase 1) and produces:
    for_traveler    ReviewAnalysis-shaped output for TripSearch/JustificationModal/TripReview
    for_manager     SavingsReport-compatible fields for ApprovalDetailPage
    for_audit       Full data dump with scores and policy flags for compliance

Input shapes (from previous phases):
    AdvisorOutput.resolved → ResolvedResult (scored, ranked, curated)
    AdvisorOutput.trip_totals, trip_summary, key_insight, recommendation, etc.

Output shapes (matching frontend TypeScript interfaces):
    Traveler → ReviewAnalysis + extension fields
    Manager  → alternatives_snapshot + trip_window_snapshot + per_leg_summary + narrative
    Audit    → Full scoring, policy flags, timestamps
"""

from datetime import datetime, timezone

from app.services.recommendation.advisor import AdvisorOutput
from app.services.recommendation.config import CABIN_DOWNGRADE_MAP
from app.services.recommendation.context_assembler import TripContext
from app.services.recommendation.cost_driver_analyzer import CostDriverReport
from app.services.recommendation.trade_off_resolver import (
    ResolvedLeg,
    ScoredAlternative,
    ScoredProposal,
)


class AudienceAdapter:
    """Formats AdvisorOutput for three audiences: traveler, manager, audit."""

    # ------------------------------------------------------------------ #
    #  Traveler view — analyze-selections endpoint response               #
    # ------------------------------------------------------------------ #

    def for_traveler(
        self,
        output: AdvisorOutput,
        context: TripContext,
    ) -> dict:
        """Format for the traveler's analyze-selections endpoint.

        Returns the shape consumed by:
          TripSearch → JustificationModal → TripReview → InlineReviewPanel

        Matches ReviewAnalysis TS interface (evaluation.ts) with extension
        fields (disruption, reason, hotel_impact) for enhanced UI.
        """
        seq_map = {leg.leg_id: leg.sequence for leg in context.legs}

        legs = [
            self._format_traveler_leg(leg, seq_map.get(leg.leg_id, 0))
            for leg in output.resolved.per_leg
        ]

        return {
            "justification_required": output.justification_required,
            "legs": legs,
            "trip_totals": output.trip_totals,
            "trip_window_alternatives": self._format_trip_window(output),
            "justification_prompt": output.justification_prompt,
            "trip_summary": output.trip_summary,
            "key_insight": output.key_insight,
            "recommendation": output.recommendation,
            "source": output.source,
            "cabin_downgrade_suggestion": self._compute_cabin_downgrade_suggestion(
                output, context,
            ),
        }

    # ------------------------------------------------------------------ #
    #  Manager view — SavingsReport JSONB fields at submit time           #
    # ------------------------------------------------------------------ #

    def for_manager(
        self,
        output: AdvisorOutput,
        context: TripContext,
        cost_drivers: CostDriverReport | None = None,
    ) -> dict:
        """Format for the SavingsReport JSONB fields populated at submit time.

        Returns fields that map to SavingsReport columns:
          alternatives_snapshot  → JSONB (ReviewLeg[] shape)
          trip_window_snapshot   → JSONB (TripWindowAlternatives shape)
          per_leg_summary        → JSONB (LegSummary[] shape)
          narrative              → text  (trip_summary string)

        Used by ApprovalDetailPage to show what the traveler was presented.
        """
        seq_map = {leg.leg_id: leg.sequence for leg in context.legs}

        return {
            "alternatives_snapshot": [
                self._format_traveler_leg(leg, seq_map.get(leg.leg_id, 0))
                for leg in output.resolved.per_leg
            ],
            "trip_window_snapshot": self._format_trip_window(output),
            "per_leg_summary": self._format_per_leg_summary(output, context),
            "narrative": output.trip_summary,
            "cost_drivers": cost_drivers.to_dict() if cost_drivers else None,
        }

    # ------------------------------------------------------------------ #
    #  Audit view — full dump for compliance                              #
    # ------------------------------------------------------------------ #

    def for_audit(
        self,
        output: AdvisorOutput,
        context: TripContext,
        cost_drivers: CostDriverReport | None = None,
    ) -> dict:
        """Full data dump for compliance audit and debugging.

        Includes all scores, policy flags, reasons, and metadata.
        Stored as JSONB on SavingsReport or exported for audit reporting.
        """
        resolved = output.resolved

        legs = [
            {
                "leg_id": leg.leg_id,
                "route": leg.route,
                "selected": leg.selected,
                "cheapest_price": leg.cheapest_price,
                "savings_vs_cheapest": round(leg.savings_vs_cheapest, 2),
                "savings_percent": round(leg.savings_percent, 1),
                "alternatives": [
                    self._format_audit_alternative(sa) for sa in leg.alternatives
                ],
            }
            for leg in resolved.per_leg
        ]

        return {
            "legs": legs,
            "trip_window": [
                self._format_audit_proposal(sp) for sp in resolved.trip_window
            ],
            "different_month": [
                self._format_audit_proposal(sp) for sp in resolved.different_month
            ],
            "trip_totals": output.trip_totals,
            "trip_summary": output.trip_summary,
            "key_insight": output.key_insight,
            "recommendation": output.recommendation,
            "justification_required": output.justification_required,
            "justification_prompt": output.justification_prompt,
            "cost_drivers": cost_drivers.to_dict() if cost_drivers else None,
            "source": output.source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    #  Shared formatting helpers                                          #
    # ------------------------------------------------------------------ #

    def _format_traveler_leg(self, leg: ResolvedLeg, sequence: int) -> dict:
        """Format a leg for the ReviewLeg TS interface.

        ReviewLeg: { leg_id, sequence, route, selected, savings, alternatives }
        """
        return {
            "leg_id": leg.leg_id,
            "sequence": sequence,
            "route": leg.route,
            "selected": leg.selected,
            "savings": {
                "amount": round(leg.savings_vs_cheapest, 2),
                "percent": round(leg.savings_percent, 1),
            },
            "alternatives": [
                self._format_traveler_alternative(sa) for sa in leg.alternatives
            ],
        }

    @staticmethod
    def _format_traveler_alternative(sa: ScoredAlternative) -> dict:
        """Format an alternative for the ReviewAlternative TS interface.

        Core fields (type, label, airline, date, price, savings, stops,
        flight_option_id) match ReviewAlternative exactly.

        Extended fields (disruption_level, reason, hotel_impact, etc.) are
        included for the enhanced recommendation UI but safely ignored by
        components that only read ReviewAlternative fields.
        """
        alt = sa.alternative
        d = {
            # Core ReviewAlternative fields
            "type": alt.alt_type,
            "label": alt.label,
            "airline": alt.airline_name,
            "date": alt.date,
            "price": alt.price,
            "savings": alt.savings_amount,
            "stops": alt.stops,
            "flight_option_id": alt.flight_option_id,
            # Extended fields for enhanced UI
            "disruption_level": alt.disruption_level,
            "what_changes": alt.what_changes,
            "is_user_airline": alt.is_user_airline,
            "cabin_class": alt.cabin_class,
            "savings_percent": alt.savings_percent,
            "departure_time": alt.departure_time,
            "duration_minutes": alt.duration_minutes,
        }
        if sa.reason:
            d["reason"] = sa.reason
        if alt.hotel_impact:
            d["hotel_impact"] = alt.hotel_impact
        if alt.net_savings:
            d["net_savings"] = alt.net_savings
        return d

    def _format_trip_window(self, output: AdvisorOutput) -> dict | None:
        """Format trip-window data for the TripWindowAlternatives TS interface.

        TripWindowAlternatives: { original_trip_duration, original_total_price,
                                   proposals, different_month }
        """
        resolved = output.resolved
        if not resolved.trip_window and not resolved.different_month:
            return None

        return {
            "original_trip_duration": resolved.original_trip_duration,
            "original_total_price": round(resolved.original_total_price, 2),
            "proposals": [
                self._format_proposal(sp) for sp in resolved.trip_window
            ],
            "different_month": [
                self._format_proposal(sp) for sp in resolved.different_month
            ],
        }

    @staticmethod
    def _format_proposal(sp: ScoredProposal) -> dict:
        """Format a trip-window proposal for the TripWindowProposal TS interface.

        TripWindowProposal: { outbound_date, return_date, trip_duration,
            duration_change, outbound_flight, return_flight, total_price,
            savings, savings_percent, same_airline, airline_name,
            user_airline, reason }
        """
        p = sp.proposal
        d = {
            "outbound_date": p.outbound_date,
            "return_date": p.return_date,
            "trip_duration": p.trip_duration,
            "duration_change": p.duration_change,
            "outbound_flight": p.outbound_flight.to_dict(),
            "return_flight": p.return_flight.to_dict(),
            "total_price": round(p.total_price, 2),
            "savings": round(p.savings_amount, 2),
            "savings_percent": round(p.savings_percent, 1),
            "same_airline": p.same_airline,
            "airline_name": p.airline_name,
            "user_airline": p.is_user_airline,
            "reason": p.reason,
        }
        if p.hotel_impact:
            d["hotel_impact"] = p.hotel_impact
        if p.net_savings:
            d["net_savings"] = p.net_savings
        return d

    # ------------------------------------------------------------------ #
    #  Manager-specific helpers                                           #
    # ------------------------------------------------------------------ #

    def _format_per_leg_summary(
        self,
        output: AdvisorOutput,
        context: TripContext,
    ) -> list[dict]:
        """Format per-leg summary for the LegSummary TS interface.

        LegSummary: { leg_id, route, selected_price, cheapest_price,
            most_expensive_price, selected_airline, justification_note,
            savings_note, policy_status }
        """
        ctx_map = {leg.leg_id: leg for leg in context.legs}
        summaries = []

        for leg in output.resolved.per_leg:
            ctx = ctx_map.get(leg.leg_id)

            selected_airline = leg.selected.get("airline") if leg.selected else None
            selected_price = leg.selected.get("price", 0) if leg.selected else 0

            most_exp = ctx.most_expensive_price if ctx else None

            savings_note = None
            if leg.savings_vs_cheapest > 0:
                savings_note = (
                    f"${leg.savings_vs_cheapest:.0f} ({leg.savings_percent:.0f}%) "
                    f"above cheapest option"
                )

            summaries.append({
                "leg_id": leg.leg_id,
                "route": leg.route,
                "selected_price": selected_price,
                "cheapest_price": leg.cheapest_price or 0,
                "most_expensive_price": most_exp,
                "selected_airline": selected_airline,
                "justification_note": None,
                "savings_note": savings_note,
            })
        return summaries

    # ------------------------------------------------------------------ #
    #  Cabin downgrade (backwards compat for JustificationModal)          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_cabin_downgrade_suggestion(
        output: AdvisorOutput,
        context: TripContext,
    ) -> dict | None:
        """Compute trip-level cabin downgrade suggestion from per-leg Layer 4 alternatives.

        JustificationModal.tsx expects a top-level cabin_downgrade_suggestion with:
        { current_cabin, suggested_cabin, current_total, suggested_total,
          savings_amount, savings_percent }

        Only returned when savings >= $200 AND >= 15%, and all legs have a downgrade.
        """
        if not context.legs:
            return None

        current_cabin = context.legs[0].cabin_class
        lower_cabin = CABIN_DOWNGRADE_MAP.get(current_cabin)
        if not lower_cabin:
            return None

        current_total = context.selected_total
        if current_total <= 0:
            return None

        suggested_total = 0.0
        for leg in output.resolved.per_leg:
            cabin_alts = [
                sa for sa in leg.alternatives
                if sa.alternative.alt_type == "cabin_downgrade"
            ]
            if not cabin_alts:
                return None  # Must have downgrade available for ALL legs
            cheapest = min(cabin_alts, key=lambda sa: sa.alternative.price)
            suggested_total += cheapest.alternative.price

        if suggested_total <= 0:
            return None

        savings = current_total - suggested_total
        savings_pct = round(savings / current_total * 100, 1)
        if savings < 200 or savings_pct < 15:
            return None

        return {
            "current_cabin": current_cabin,
            "suggested_cabin": lower_cabin,
            "current_total": round(current_total, 2),
            "suggested_total": round(suggested_total, 2),
            "savings_amount": round(savings, 2),
            "savings_percent": savings_pct,
        }

    # ------------------------------------------------------------------ #
    #  Audit-specific helpers                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_audit_alternative(sa: ScoredAlternative) -> dict:
        """Full alternative data for audit trail — includes scores and flags."""
        d = sa.alternative.to_dict()
        d["score"] = sa.score.to_dict()
        d["rank"] = sa.rank
        d["reason"] = sa.reason
        if sa.policy_flag:
            d["policy_flag"] = sa.policy_flag.to_dict()
        return d

    @staticmethod
    def _format_audit_proposal(sp: ScoredProposal) -> dict:
        """Full proposal data for audit trail — includes scores and flags."""
        d = sp.proposal.to_dict()
        d["score"] = sp.score.to_dict()
        d["rank"] = sp.rank
        d["category"] = sp.category
        if sp.policy_flag:
            d["policy_flag"] = sp.policy_flag.to_dict()
        return d


# Singleton
audience_adapter = AudienceAdapter()
