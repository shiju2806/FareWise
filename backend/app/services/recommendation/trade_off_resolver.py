"""Trade-off resolver — scores, ranks, and curates alternatives.

Takes raw alternatives from flight_alternatives_generator (Phase 2) and produces
a ranked, curated set ready for the advisor (Phase 4).

Scoring dimensions (see TradeOffWeights in config):
  Net savings (60)       — flight savings minus hotel cost, normalized to pool
  Traveler preference (70) — airline loyalty and preferred alliances
  Disruption level (40)  — lower disruption = higher score
  Sustainability (10)    — fewer stops = less emissions

Hard filters / flags:
  Policy compliance (100) — flags alternatives exceeding cabin budget
  Connection safety (90)  — future: flags unsafe layover times

Selection guarantees:
  - User's airline always included (when available)
  - Airline diversity (no all-same-airline results)
  - At least one per unique type (when available)
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date

from app.services.recommendation.config import (
    CORPORATE_DAY_RULES,
    recommendation_config,
)
from app.services.recommendation.context_assembler import TripContext
from app.services.recommendation.flight_alternatives import (
    Alternative,
    FlightAlternativesResult,
    LegAlternatives,
    TripWindowProposal,
)

logger = logging.getLogger(__name__)

cfg = recommendation_config
weights = cfg.trade_offs
limits = cfg.limits


# ---------- Data structures ----------


@dataclass
class ScoreBreakdown:
    """How an alternative was scored."""

    net_savings: float = 0.0       # 0-1, weighted
    preference: float = 0.0        # 0-1, weighted
    disruption: float = 0.0        # 0-1, weighted
    sustainability: float = 0.0    # 0-1, weighted
    total: float = 0.0             # composite 0-100

    def to_dict(self) -> dict:
        return {
            "net_savings": round(self.net_savings, 2),
            "preference": round(self.preference, 2),
            "disruption": round(self.disruption, 2),
            "sustainability": round(self.sustainability, 2),
            "total": round(self.total, 1),
        }


@dataclass
class PolicyFlag:
    """Policy compliance flag for an alternative."""

    flag_type: str         # "over_budget" | "compliant"
    details: str | None    # e.g. "Exceeds business budget by $300"
    budget_limit: float | None = None
    overage: float | None = None

    def to_dict(self) -> dict:
        return {
            "flag_type": self.flag_type,
            "details": self.details,
        }


@dataclass
class ScoredAlternative:
    """An alternative with its composite score."""

    alternative: Alternative
    score: ScoreBreakdown
    rank: int = 0                        # 1-based within leg
    policy_flag: PolicyFlag | None = None
    reason: str = ""                     # LLM or fallback reason (set by advisor)

    def to_dict(self) -> dict:
        d = self.alternative.to_dict()
        d["score"] = self.score.total
        d["score_breakdown"] = self.score.to_dict()
        d["rank"] = self.rank
        if self.reason:
            d["reason"] = self.reason
        if self.policy_flag:
            d["policy_flag"] = self.policy_flag.to_dict()
        return d


@dataclass
class ScoredProposal:
    """A trip-window proposal with its composite score."""

    proposal: TripWindowProposal
    score: ScoreBreakdown
    rank: int = 0
    category: str = ""                   # "trip_window" | "different_month"
    policy_flag: PolicyFlag | None = None

    def to_dict(self) -> dict:
        d = self.proposal.to_dict()
        d["score"] = self.score.total
        d["score_breakdown"] = self.score.to_dict()
        d["rank"] = self.rank
        if self.policy_flag:
            d["policy_flag"] = self.policy_flag.to_dict()
        return d


@dataclass
class ResolvedLeg:
    """Resolved alternatives for a single leg."""

    leg_id: str
    route: str
    selected: dict | None
    alternatives: list[ScoredAlternative]
    cheapest_price: float | None = None
    savings_vs_cheapest: float = 0.0
    savings_percent: float = 0.0

    def to_dict(self) -> dict:
        return {
            "leg_id": self.leg_id,
            "route": self.route,
            "selected": self.selected,
            "alternatives": [sa.to_dict() for sa in self.alternatives],
            "cheapest_price": self.cheapest_price,
            "savings_vs_cheapest": round(self.savings_vs_cheapest, 2),
            "savings_percent": round(self.savings_percent, 1),
        }


@dataclass
class ResolvedResult:
    """Complete resolved output — scored, ranked, curated."""

    per_leg: list[ResolvedLeg]
    trip_window: list[ScoredProposal] = field(default_factory=list)
    different_month: list[ScoredProposal] = field(default_factory=list)
    original_trip_duration: int | None = None
    original_total_price: float = 0.0
    preferred_outbound: str = ""

    def to_dict(self) -> dict:
        """Produces frontend-compatible output with scores."""
        tw_data = None
        if self.trip_window or self.different_month:
            tw_data = {
                "original_trip_duration": self.original_trip_duration,
                "original_total_price": round(self.original_total_price, 2),
                "preferred_outbound": self.preferred_outbound,
                "proposals": [sp.to_dict() for sp in self.trip_window],
                "different_month": [sp.to_dict() for sp in self.different_month],
            }
        return {
            "legs": [leg.to_dict() for leg in self.per_leg],
            "trip_window_alternatives": tw_data,
        }


# ---------- Resolver ----------


class TradeOffResolver:
    """Scores and ranks alternatives using weighted multi-factor scoring.

    Takes raw FlightAlternativesResult and TripContext, produces ResolvedResult
    with scored, ranked, curated alternatives.
    """

    def resolve(
        self,
        raw: FlightAlternativesResult,
        context: TripContext,
    ) -> ResolvedResult:
        """Score, rank, and curate all alternatives."""
        # Build preference context
        pref = self._build_preference_context(context)

        # 1. Score and curate per-leg alternatives
        resolved_legs = [
            self._resolve_leg(leg, context, pref)
            for leg in raw.per_leg
        ]

        # 2. Score and curate trip-window proposals
        trip_window, different_month = self._resolve_trip_window(
            raw.trip_window_proposals,
            raw.preferred_outbound,
            context,
            pref,
        )

        return ResolvedResult(
            per_leg=resolved_legs,
            trip_window=trip_window,
            different_month=different_month,
            original_trip_duration=raw.original_trip_duration,
            original_total_price=raw.original_total_price,
            preferred_outbound=raw.preferred_outbound,
        )

    # ---- Per-leg resolution ----

    def _resolve_leg(
        self,
        leg: LegAlternatives,
        context: TripContext,
        pref: "_PreferenceContext",
    ) -> ResolvedLeg:
        """Score, rank, and curate alternatives for a single leg."""
        # Filter out alternatives with invalid prices before scoring
        valid_alts = [
            alt for alt in leg.alternatives
            if _is_finite(alt.price) and _is_finite(alt.savings_amount)
        ]

        if not valid_alts:
            return ResolvedLeg(
                leg_id=leg.leg_id,
                route=leg.route,
                selected=leg.to_dict().get("selected"),
                alternatives=[],
                cheapest_price=leg.cheapest_price,
                savings_vs_cheapest=leg.savings_vs_cheapest,
                savings_percent=leg.savings_percent,
            )

        # Score all valid alternatives
        scored = [
            self._score_alternative(alt, valid_alts, context, pref)
            for alt in valid_alts
        ]

        # Sort by score descending (secondary: lower price breaks ties)
        scored.sort(key=lambda sa: (-sa.score.total, sa.alternative.price))

        # Curate: select top N with diversity
        curated = self._curate_leg_alternatives(scored)

        # Assign ranks
        for i, sa in enumerate(curated):
            sa.rank = i + 1

        return ResolvedLeg(
            leg_id=leg.leg_id,
            route=leg.route,
            selected=leg.to_dict().get("selected"),
            alternatives=curated,
            cheapest_price=leg.cheapest_price,
            savings_vs_cheapest=leg.savings_vs_cheapest,
            savings_percent=leg.savings_percent,
        )

    def _score_alternative(
        self,
        alt: Alternative,
        pool: list[Alternative],
        context: TripContext,
        pref: "_PreferenceContext",
    ) -> ScoredAlternative:
        """Compute composite score for a per-leg alternative."""
        # --- Net savings dimension ---
        valid_savings = [a.savings_amount for a in pool if _is_finite(a.savings_amount)]
        max_savings = max(valid_savings, default=1.0)
        if max_savings <= 0:
            max_savings = 1.0

        # Use net savings if available, else raw flight savings
        if alt.net_savings and alt.net_savings.get("net_amount") is not None:
            effective_savings = alt.net_savings["net_amount"]
        else:
            effective_savings = alt.savings_amount

        if not _is_finite(effective_savings):
            effective_savings = 0.0

        savings_norm = max(0.0, min(1.0, effective_savings / max_savings))

        # --- Preference dimension ---
        pref_score = self._compute_preference(alt.airline_code, pref)

        # --- Disruption dimension ---
        disruption_map = {"low": 1.0, "medium": 0.6, "high": 0.2}
        disruption_score = disruption_map.get(alt.disruption_level, 0.5)

        # Red-eye penalty: reduce disruption score for late-night departures
        if _is_red_eye(alt.departure_time):
            cabin = alt.cabin_class or "economy"
            if cabin in ("business", "first"):
                disruption_score *= cfg.red_eye.penalty_business
            else:
                disruption_score *= cfg.red_eye.penalty_economy

        # --- Sustainability dimension ---
        sustainability_score = _stops_to_sustainability(alt.stops)

        # --- Weighted composite ---
        total_weight = (
            weights.net_savings + weights.traveler_preference
            + weights.disruption + weights.sustainability
        )
        composite = (
            weights.net_savings * savings_norm
            + weights.traveler_preference * pref_score
            + weights.disruption * disruption_score
            + weights.sustainability * sustainability_score
        ) / total_weight * 100

        breakdown = ScoreBreakdown(
            net_savings=savings_norm,
            preference=pref_score,
            disruption=disruption_score,
            sustainability=sustainability_score,
            total=composite,
        )

        # --- Policy check ---
        policy_flag = self._check_policy_budget(alt.price, alt.cabin_class)

        return ScoredAlternative(
            alternative=alt,
            score=breakdown,
            policy_flag=policy_flag,
        )

    def _curate_leg_alternatives(
        self,
        scored: list[ScoredAlternative],
    ) -> list[ScoredAlternative]:
        """Select top alternatives for a leg with diversity guarantees.

        Ensures:
        - At least one per type (same_date, nearby_airport, date_shift, cabin) if available
        - No more than total_max alternatives
        - User's airline alternatives always included
        """
        if len(scored) <= limits.total_max:
            return scored

        curated: list[ScoredAlternative] = []
        used: set[str] = set()  # flight_option_id

        # Guarantee: one per unique alt_type (highest scored of each)
        types_seen: set[str] = set()
        for sa in scored:
            if len(curated) >= limits.total_max:
                break
            alt_type = sa.alternative.alt_type
            if alt_type not in types_seen:
                curated.append(sa)
                used.add(sa.alternative.flight_option_id)
                types_seen.add(alt_type)

        # Guarantee: user's airline
        for sa in scored:
            if len(curated) >= limits.total_max:
                break
            if sa.alternative.is_user_airline and sa.alternative.flight_option_id not in used:
                curated.append(sa)
                used.add(sa.alternative.flight_option_id)
                break

        # Guarantee: same-alliance partner (if available and not already included)
        if cfg.curation.same_alliance_slots > 0:
            from app.services.recommendation.airline_tiers import same_alliance as _same_alliance

            # Use user's airline codes as the reference for alliance matching
            user_codes = {
                sa.alternative.airline_code
                for sa in curated
                if sa.alternative.is_user_airline
            }
            if not user_codes and curated:
                user_codes = {curated[0].alternative.airline_code}

            alliance_count = 0
            for sa in scored:
                if alliance_count >= cfg.curation.same_alliance_slots:
                    break
                if len(curated) >= limits.total_max:
                    break
                if sa.alternative.flight_option_id in used:
                    continue
                # Skip if this airline is already the user's airline
                if sa.alternative.airline_code in user_codes:
                    continue
                for ref_code in user_codes:
                    if _same_alliance(sa.alternative.airline_code, ref_code):
                        curated.append(sa)
                        used.add(sa.alternative.flight_option_id)
                        alliance_count += 1
                        break

        # Fill remaining slots — prefer diverse airlines first
        seen_airlines = {sa.alternative.airline_code for sa in curated}
        for sa in scored:
            if len(curated) >= limits.total_max:
                break
            if sa.alternative.flight_option_id not in used and sa.alternative.airline_code not in seen_airlines:
                curated.append(sa)
                used.add(sa.alternative.flight_option_id)
                seen_airlines.add(sa.alternative.airline_code)

        # Then fill any remaining slots by score regardless of airline
        for sa in scored:
            if len(curated) >= limits.total_max:
                break
            if sa.alternative.flight_option_id not in used:
                curated.append(sa)
                used.add(sa.alternative.flight_option_id)

        # Re-sort by score (secondary: lower price breaks ties)
        curated.sort(key=lambda sa: (-sa.score.total, sa.alternative.price))
        return curated

    # ---- Trip-window resolution ----

    def _resolve_trip_window(
        self,
        proposals: list[TripWindowProposal],
        preferred_outbound: str,
        context: TripContext,
        pref: "_PreferenceContext",
    ) -> tuple[list[ScoredProposal], list[ScoredProposal]]:
        """Score trip-window proposals and split into trip_window / different_month."""
        if not proposals:
            return [], []

        # Score all
        scored = [
            self._score_proposal(p, proposals, context, pref)
            for p in proposals
        ]

        # Split by category (layer 2 = trip_window, layer 3 = different_month)
        tw_scored = [sp for sp in scored if sp.proposal.layer == 2]
        dm_scored = [sp for sp in scored if sp.proposal.layer == 3]

        # Fallback: if layer-based split yields empty categories, use date distance
        if not tw_scored and not dm_scored:
            # All proposals in one bucket — try date-based split
            if preferred_outbound:
                pref_out = date.fromisoformat(preferred_outbound)
                for sp in scored:
                    days_shift = abs((date.fromisoformat(sp.proposal.outbound_date) - pref_out).days)
                    if days_shift <= 21:
                        tw_scored.append(sp)
                    else:
                        dm_scored.append(sp)
            else:
                tw_scored = scored

        # Sort by score
        tw_scored.sort(key=lambda sp: sp.score.total, reverse=True)
        dm_scored.sort(key=lambda sp: sp.score.total, reverse=True)

        # Curate each category
        tw_curated = self._curate_proposals(tw_scored, limits.layer2_max, "trip_window")
        dm_curated = self._curate_proposals(dm_scored, limits.layer3_max, "different_month")

        return tw_curated, dm_curated

    def _score_proposal(
        self,
        proposal: TripWindowProposal,
        pool: list[TripWindowProposal],
        context: TripContext,
        pref: "_PreferenceContext",
    ) -> ScoredProposal:
        """Compute composite score for a trip-window proposal."""
        # --- Net savings ---
        valid_savings = [p.savings_amount for p in pool if _is_finite(p.savings_amount)]
        max_savings = max(valid_savings, default=1.0)
        if max_savings <= 0:
            max_savings = 1.0

        # Use net savings after hotel impact if available
        if proposal.net_savings and proposal.net_savings.get("net_amount") is not None:
            effective_savings = proposal.net_savings["net_amount"]
        else:
            effective_savings = proposal.savings_amount

        if not _is_finite(effective_savings):
            effective_savings = 0.0

        savings_norm = max(0.0, min(1.0, effective_savings / max_savings))

        # --- Preference ---
        # For trip-window, check both legs' airlines
        out_pref = self._compute_preference(proposal.outbound_flight.airline_code, pref)
        ret_pref = self._compute_preference(proposal.return_flight.airline_code, pref)
        pref_score = (out_pref + ret_pref) / 2.0

        # --- Disruption ---
        disruption_map = {"low": 1.0, "medium": 0.6, "high": 0.2}
        disruption_score = disruption_map.get(proposal.disruption_level, 0.5)

        # Red-eye penalty for trip-window proposals (check both legs)
        red_eye_out = _is_red_eye(proposal.outbound_flight.departure_time)
        red_eye_ret = _is_red_eye(proposal.return_flight.departure_time)
        if red_eye_out or red_eye_ret:
            cabin = context.legs[0].cabin_class if context.legs else "economy"
            penalty = (
                cfg.red_eye.penalty_business
                if cabin in ("business", "first")
                else cfg.red_eye.penalty_economy
            )
            if red_eye_out and red_eye_ret:
                disruption_score *= penalty * penalty
            else:
                disruption_score *= penalty

        # --- Sustainability ---
        avg_stops = (proposal.outbound_flight.stops + proposal.return_flight.stops) / 2.0
        sustainability_score = _stops_to_sustainability(avg_stops)

        # --- Weighted composite ---
        total_weight = (
            weights.net_savings + weights.traveler_preference
            + weights.disruption + weights.sustainability
        )
        composite = (
            weights.net_savings * savings_norm
            + weights.traveler_preference * pref_score
            + weights.disruption * disruption_score
            + weights.sustainability * sustainability_score
        ) / total_weight * 100

        breakdown = ScoreBreakdown(
            net_savings=savings_norm,
            preference=pref_score,
            disruption=disruption_score,
            sustainability=sustainability_score,
            total=composite,
        )

        # --- Policy check ---
        # Check both legs against budget
        out_flag = self._check_policy_budget(
            proposal.outbound_flight.price,
            self._cabin_for_context(context, 0),
        )
        ret_flag = self._check_policy_budget(
            proposal.return_flight.price,
            self._cabin_for_context(context, -1),
        )
        # Use the worse flag
        policy_flag = out_flag if (out_flag and out_flag.flag_type != "compliant") else ret_flag

        return ScoredProposal(
            proposal=proposal,
            score=breakdown,
            policy_flag=policy_flag,
        )

    def _curate_proposals(
        self,
        scored: list[ScoredProposal],
        max_proposals: int,
        category: str,
    ) -> list[ScoredProposal]:
        """Select top proposals with diversity guarantees.

        Ensures:
        1. User's airline included (highest scored user-airline proposal)
        2. At least 2 different airlines
        3. Max N proposals
        """
        if not scored:
            return []
        if len(scored) <= max_proposals:
            for i, sp in enumerate(scored):
                sp.rank = i + 1
                sp.category = category
            return scored

        curated: list[ScoredProposal] = []
        used: set[int] = set()  # id() of proposal

        # Slot 1: User's airline (best scored)
        for sp in scored:
            if sp.proposal.is_user_airline:
                curated.append(sp)
                used.add(id(sp))
                break

        # Slot 2: Best scored overall (different from slot 1)
        for sp in scored:
            if id(sp) not in used:
                curated.append(sp)
                used.add(id(sp))
                break

        # Slot 3: Same-alliance partner (if available)
        if cfg.curation.same_alliance_slots > 0:
            from app.services.recommendation.airline_tiers import same_alliance as _same_alliance

            user_codes = {
                sp.proposal.outbound_flight.airline_code
                for sp in curated
                if sp.proposal.is_user_airline
            }
            alliance_count = 0
            for sp in scored:
                if alliance_count >= cfg.curation.same_alliance_slots:
                    break
                if len(curated) >= max_proposals:
                    break
                if id(sp) in used:
                    continue
                out_code = sp.proposal.outbound_flight.airline_code
                if out_code in user_codes:
                    continue
                for ref_code in user_codes:
                    if _same_alliance(out_code, ref_code):
                        curated.append(sp)
                        used.add(id(sp))
                        alliance_count += 1
                        break

        # Remaining slots: diverse airlines, by score
        seen_airlines = {
            sp.proposal.outbound_flight.airline_code for sp in curated
        }
        for sp in scored:
            if len(curated) >= max_proposals:
                break
            if id(sp) in used:
                continue
            if sp.proposal.outbound_flight.airline_code not in seen_airlines:
                curated.append(sp)
                used.add(id(sp))
                seen_airlines.add(sp.proposal.outbound_flight.airline_code)

        # Fill remaining by score
        for sp in scored:
            if len(curated) >= max_proposals:
                break
            if id(sp) not in used:
                curated.append(sp)
                used.add(id(sp))

        # Sort by (user_airline first, then score)
        curated.sort(key=lambda sp: (not sp.proposal.is_user_airline, -sp.score.total))
        for i, sp in enumerate(curated):
            sp.rank = i + 1
            sp.category = category

        return curated

    # ---- Scoring helpers ----

    def _build_preference_context(self, context: TripContext) -> "_PreferenceContext":
        """Extract preference data from TripContext."""
        selected_airlines: set[str] = set()
        for leg in context.legs:
            if leg.selected_flight:
                selected_airlines.add(leg.selected_flight.airline_code)

        # Map airline codes to alliances (simplified — extend as needed)
        preferred_alliances = set(context.traveler.preferred_alliances)
        loyalty_airlines = set(context.traveler.loyalty_programs)

        return _PreferenceContext(
            selected_airlines=selected_airlines,
            preferred_alliances=preferred_alliances,
            loyalty_airlines=loyalty_airlines,
            excluded_airlines=context.traveler.excluded_airlines,
        )

    def _compute_preference(
        self,
        airline_code: str,
        pref: "_PreferenceContext",
    ) -> float:
        """Compute graduated preference score for an airline.

        Scores (from AirlinePreferenceScores config):
        1.0  = user's selected/loyalty airline
        0.8  = same alliance partner (e.g. United for an Air Canada traveler)
        0.5  = full-service carrier, different alliance
        0.3  = mid-tier carrier (regional/leisure)
        0.15 = low-cost/ULCC
        """
        from app.services.recommendation.airline_tiers import get_tier, same_alliance

        scores = cfg.airline_preferences

        # 1. User's selected or loyalty airline
        if airline_code in pref.selected_airlines or airline_code in pref.loyalty_airlines:
            return scores.user_airline

        # 2. Same alliance as any selected airline
        for sel_code in pref.selected_airlines:
            if same_alliance(airline_code, sel_code):
                return scores.same_alliance

        # 3. Tier-based scoring
        tier = get_tier(airline_code)
        if tier == "full_service":
            return scores.other_full_service
        if tier == "mid_tier":
            return scores.mid_tier
        return scores.low_cost

    def _check_policy_budget(
        self,
        price: float,
        cabin_class: str,
    ) -> PolicyFlag | None:
        """Check if a price exceeds the cabin's policy budget.

        Returns a flag if over budget, None if compliant.
        """
        budget = cfg.policy_budgets.get(cabin_class)
        if budget is None:
            return None

        if price > budget:
            overage = price - budget
            return PolicyFlag(
                flag_type="over_budget",
                details=f"Exceeds {cabin_class} budget (${budget}) by ${overage:.0f}",
                budget_limit=float(budget),
                overage=round(overage, 2),
            )
        return PolicyFlag(
            flag_type="compliant",
            details=None,
        )

    @staticmethod
    def _cabin_for_context(context: TripContext, leg_index: int) -> str:
        """Get cabin class for a leg by index."""
        if context.legs:
            leg = context.legs[leg_index]
            return leg.cabin_class
        return "economy"


# ---------- Internal types ----------


@dataclass
class _PreferenceContext:
    """Extracted preference data for scoring."""

    selected_airlines: set[str]
    preferred_alliances: set[str]
    loyalty_airlines: set[str]
    excluded_airlines: set[str]


# ---------- Helper functions ----------


def _is_finite(value: float | None) -> bool:
    """Check if a numeric value is finite (not NaN, inf, or None)."""
    if value is None:
        return False
    try:
        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


def _stops_to_sustainability(stops: float) -> float:
    """Convert stop count to a sustainability score (0-1)."""
    if stops <= 0:
        return 1.0
    if stops <= 1:
        return 0.5
    return 0.2


def _is_red_eye(departure_time: str) -> bool:
    """Check if departure time falls in the red-eye window (config-driven).

    Red-eye = departure between start_hour (e.g. 23:00) and end_hour (e.g. 06:00).
    """
    if not departure_time or len(departure_time) < 16:
        return False
    try:
        hour = int(departure_time[11:13])
        return hour >= cfg.red_eye.start_hour or hour < cfg.red_eye.end_hour
    except (ValueError, IndexError):
        return False


# Singleton
trade_off_resolver = TradeOffResolver()
