"""Flight alternatives generator — produces all alternatives for a trip.

Replaces:
- selection_analysis_service.analyze_leg_selection() (per-leg alternatives)
- trip_intelligence_service.compute_trip_window_alternatives() (trip-window proposals)

Generates alternatives in 4 layers:
  Layer 1 (low disruption): Same-date swaps — different airline, nearby airport
  Layer 2 (medium disruption): Date shifts — same airline on nearby dates, trip-window shifts
  Layer 3 (high disruption): Different month — significant date shifts (>21 days)
  Layer 4 (high disruption): Trade-off alternatives — cabin downgrade, routing changes

Each alternative is tagged with layer, disruption level, what changes, and hotel impact.
Does NOT do DB queries — operates on pre-assembled TripContext.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services.recommendation.config import (
    CABIN_DOWNGRADE_MAP,
    CORPORATE_DAY_RULES,
    recommendation_config,
)
from app.services.recommendation.context_assembler import FlightData, LegContext, TripContext
from app.services.recommendation.hotel_impact import hotel_impact_calculator

logger = logging.getLogger(__name__)

cfg = recommendation_config


# ---------- Data structures ----------


@dataclass
class Alternative:
    """A single flight alternative with disruption metadata."""

    alt_type: str              # "same_date" | "same_airline_routing" | "nearby_airport" | "same_airline_date_shift" | "cabin_downgrade"
    layer: int                 # 1-4
    disruption_level: str      # "low" | "medium" | "high"
    what_changes: list[str]    # e.g. ["airline"], ["date"], ["cabin", "airline"]

    # Flight identification (for switching)
    flight_option_id: str

    # Display
    label: str
    airline_code: str
    airline_name: str
    origin_airport: str
    destination_airport: str
    departure_time: str
    arrival_time: str
    date: str                  # departure date (ISO)
    price: float
    stops: int
    duration_minutes: int
    cabin_class: str

    # Savings vs selected
    savings_amount: float
    savings_percent: float

    # Hotel impact (for date-shift alternatives)
    hotel_impact: dict | None = None
    net_savings: dict | None = None

    # Metadata
    is_user_airline: bool = False

    def to_dict(self) -> dict:
        """Serialize to dict, backwards-compatible with old format."""
        d = {
            "type": self.alt_type,
            "layer": self.layer,
            "disruption_level": self.disruption_level,
            "what_changes": self.what_changes,
            "label": self.label,
            "airline": self.airline_name,
            "airline_code": self.airline_code,
            "date": self.date,
            "price": self.price,
            "savings": self.savings_amount,
            "savings_percent": self.savings_percent,
            "stops": self.stops,
            "duration_minutes": self.duration_minutes,
            "flight_option_id": self.flight_option_id,
            "origin_airport": self.origin_airport,
            "destination_airport": self.destination_airport,
            "cabin_class": self.cabin_class,
            "is_user_airline": self.is_user_airline,
        }
        if self.hotel_impact:
            d["hotel_impact"] = self.hotel_impact
        if self.net_savings:
            d["net_savings"] = self.net_savings
        return d


@dataclass
class FlightSummary:
    """Minimal flight info for trip-window proposals."""

    airline_name: str
    airline_code: str
    price: float
    stops: int
    departure_time: str
    arrival_time: str
    duration_minutes: int

    def to_dict(self) -> dict:
        return {
            "airline_name": self.airline_name,
            "airline_code": self.airline_code,
            "price": self.price,
            "stops": self.stops,
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "duration_minutes": self.duration_minutes,
        }


@dataclass
class TripWindowProposal:
    """A trip-window date-shift proposal for round trips."""

    outbound_date: str
    return_date: str
    trip_duration: int
    duration_change: int
    outbound_flight: FlightSummary
    return_flight: FlightSummary
    total_price: float
    savings_amount: float
    savings_percent: float
    same_airline: bool
    airline_name: str | None
    is_user_airline: bool
    layer: int                 # 2 or 3
    disruption_level: str      # "medium" or "high"
    what_changes: list[str]

    # Hotel impact
    hotel_impact: dict | None = None
    net_savings: dict | None = None

    # LLM-assigned reason (filled in Phase 4 advisor)
    reason: str = ""

    def to_dict(self) -> dict:
        """Serialize, backwards-compatible with old trip-window format."""
        d = {
            "outbound_date": self.outbound_date,
            "return_date": self.return_date,
            "trip_duration": self.trip_duration,
            "duration_change": self.duration_change,
            "outbound_flight": self.outbound_flight.to_dict(),
            "return_flight": self.return_flight.to_dict(),
            "total_price": round(self.total_price, 2),
            "savings": round(self.savings_amount, 2),
            "savings_percent": round(self.savings_percent, 1),
            "same_airline": self.same_airline,
            "airline_name": self.airline_name,
            "user_airline": self.is_user_airline,
            "layer": self.layer,
            "disruption_level": self.disruption_level,
            "what_changes": self.what_changes,
            "reason": self.reason,
        }
        if self.hotel_impact:
            d["hotel_impact"] = self.hotel_impact
        if self.net_savings:
            d["net_savings"] = self.net_savings
        return d


@dataclass
class LegAlternatives:
    """All alternatives for a single leg."""

    leg_id: str
    route: str                 # "YYZ → LHR"
    selected: FlightData | None
    alternatives: list[Alternative] = field(default_factory=list)

    # Summary stats
    cheapest_price: float | None = None
    savings_vs_cheapest: float = 0.0
    savings_percent: float = 0.0

    def to_dict(self) -> dict:
        return {
            "leg_id": self.leg_id,
            "route": self.route,
            "selected": {
                "airline": self.selected.airline_name,
                "airline_code": self.selected.airline_code,
                "price": self.selected.price,
                "date": self.selected.departure_time[:10] if self.selected.departure_time else "",
                "stops": self.selected.stops,
                "duration_minutes": self.selected.duration_minutes,
                "flight_option_id": self.selected.id,
            } if self.selected else None,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "cheapest_price": self.cheapest_price,
            "savings_vs_cheapest": round(self.savings_vs_cheapest, 2),
            "savings_percent": round(self.savings_percent, 1),
        }


@dataclass
class FlightAlternativesResult:
    """Complete alternatives output for the trip."""

    per_leg: list[LegAlternatives]
    trip_window_proposals: list[TripWindowProposal] = field(default_factory=list)
    original_trip_duration: int | None = None
    original_total_price: float = 0.0
    preferred_outbound: str = ""
    preferred_return: str = ""

    def to_dict(self) -> dict:
        return {
            "legs": [leg.to_dict() for leg in self.per_leg],
            "trip_window_alternatives": {
                "original_trip_duration": self.original_trip_duration,
                "original_total_price": round(self.original_total_price, 2),
                "preferred_outbound": self.preferred_outbound,
                "proposals": [p.to_dict() for p in self.trip_window_proposals],
            } if self.trip_window_proposals else None,
        }


# ---------- Generator ----------


class FlightAlternativesGenerator:
    """Generates all flight alternatives for a trip.

    Operates on pre-assembled TripContext (no DB queries).
    Produces tagged alternatives ready for scoring (Phase 3) and curation (Phase 4).
    """

    def generate(self, context: TripContext) -> FlightAlternativesResult:
        """Generate all alternatives for the trip."""
        # Per-leg alternatives (Layer 1, 2, 4)
        per_leg = [
            self._generate_leg_alternatives(leg, context)
            for leg in context.legs
        ]

        # Trip-window proposals (Layer 2-3) — only for round trips
        trip_window: list[TripWindowProposal] = []
        original_duration = None
        preferred_out = ""
        preferred_ret = ""

        if context.is_round_trip:
            outbound = context.legs[0]
            return_leg = context.legs[-1]
            preferred_out = outbound.preferred_date
            preferred_ret = return_leg.preferred_date

            if preferred_out and preferred_ret:
                original_duration = (
                    date.fromisoformat(preferred_ret) - date.fromisoformat(preferred_out)
                ).days

                if original_duration > 0:
                    trip_window = self._generate_trip_window(
                        context, preferred_out, preferred_ret, original_duration,
                    )

        return FlightAlternativesResult(
            per_leg=per_leg,
            trip_window_proposals=trip_window,
            original_trip_duration=original_duration,
            original_total_price=context.selected_total,
            preferred_outbound=preferred_out,
            preferred_return=preferred_ret,
        )

    # ---- Per-leg alternatives ----

    def _generate_leg_alternatives(
        self, leg: LegContext, context: TripContext,
    ) -> LegAlternatives:
        """Generate all per-leg alternatives (Layers 1, 2, 4)."""
        result = LegAlternatives(
            leg_id=leg.leg_id,
            route=f"{leg.origin_airport} → {leg.destination_airport}",
            selected=leg.selected_flight,
        )

        selected = leg.selected_flight
        if not selected or not leg.all_options:
            return result

        sel_price = selected.price
        sel_date = _extract_date(selected.departure_time)
        options = [o for o in leg.all_options if o.price > 0]

        if not options:
            return result

        # Compute summary stats
        cheapest = min(options, key=lambda o: o.price)
        result.cheapest_price = cheapest.price
        result.savings_vs_cheapest = round(sel_price - cheapest.price, 2)
        result.savings_percent = (
            round((result.savings_vs_cheapest / sel_price) * 100, 1)
            if sel_price > 0 else 0.0
        )

        # Exclude traveler's excluded airlines
        excluded = context.traveler.excluded_airlines
        allowed = [o for o in options if o.airline_code not in excluded]

        alternatives: list[Alternative] = []

        # --- Layer 1a: Same-date swaps (low disruption) ---
        alternatives.extend(self._layer1_same_date(
            selected, sel_date, sel_price, allowed, leg,
        ))

        # --- Layer 1b: Same-airline cheaper routing (low disruption) ---
        alternatives.extend(self._layer1_same_airline_routing(
            selected, sel_date, sel_price, allowed, leg,
        ))

        # --- Layer 2: Same-airline date shifts (medium disruption) ---
        alternatives.extend(self._layer2_date_shifts(
            selected, sel_date, sel_price, allowed, leg, context,
        ))

        # --- Layer 4: Cabin downgrade (high disruption) ---
        alternatives.extend(self._layer4_cabin_downgrade(
            selected, sel_date, sel_price, allowed, leg,
        ))

        result.alternatives = alternatives
        return result

    def _layer1_same_date(
        self,
        selected: FlightData,
        sel_date: str,
        sel_price: float,
        options: list[FlightData],
        leg: LegContext,
    ) -> list[Alternative]:
        """Layer 1: Same-date, different airline or nearby airport (low disruption)."""
        alternatives: list[Alternative] = []
        min_savings = cfg.alternatives.layer1_min_savings

        # 1a: Different airline, same date, same airport, cheaper
        same_date_others = [
            o for o in options
            if _extract_date(o.departure_time) == sel_date
            and o.airline_code != selected.airline_code
            and not o.is_alternate_airport
            and o.price < sel_price
            and (sel_price - o.price) >= min_savings
        ]

        if same_date_others:
            # Group by airline, take cheapest per airline
            by_airline: dict[str, FlightData] = {}
            for o in same_date_others:
                if o.airline_code not in by_airline or o.price < by_airline[o.airline_code].price:
                    by_airline[o.airline_code] = o

            for o in sorted(by_airline.values(), key=lambda x: x.price)[:cfg.limits.layer1_max]:
                savings = sel_price - o.price
                alternatives.append(Alternative(
                    alt_type="same_date",
                    layer=1,
                    disruption_level="low",
                    what_changes=["airline"],
                    flight_option_id=o.id,
                    label=f"Same date, {o.airline_name}",
                    airline_code=o.airline_code,
                    airline_name=o.airline_name,
                    origin_airport=o.origin_airport,
                    destination_airport=o.destination_airport,
                    departure_time=o.departure_time,
                    arrival_time=o.arrival_time,
                    date=sel_date,
                    price=o.price,
                    stops=o.stops,
                    duration_minutes=o.duration_minutes,
                    cabin_class=o.cabin_class,
                    savings_amount=round(savings, 2),
                    savings_percent=round(savings / sel_price * 100, 1) if sel_price > 0 else 0,
                ))

        # 1b: Nearby airport, same date, cheaper
        nearby_options = [
            o for o in options
            if o.is_alternate_airport
            and _extract_date(o.departure_time) == sel_date
            and o.price < sel_price
            and (sel_price - o.price) >= min_savings
        ]

        existing_ids = {a.flight_option_id for a in alternatives}
        if nearby_options:
            cheapest_nearby = min(nearby_options, key=lambda o: o.price)
            if cheapest_nearby.id not in existing_ids:
                savings = sel_price - cheapest_nearby.price
                changes = ["airport"]
                if cheapest_nearby.airline_code != selected.airline_code:
                    changes.append("airline")
                alternatives.append(Alternative(
                    alt_type="nearby_airport",
                    layer=1,
                    disruption_level="low",
                    what_changes=changes,
                    flight_option_id=cheapest_nearby.id,
                    label=f"Nearby airport ({cheapest_nearby.origin_airport} → {cheapest_nearby.destination_airport})",
                    airline_code=cheapest_nearby.airline_code,
                    airline_name=cheapest_nearby.airline_name,
                    origin_airport=cheapest_nearby.origin_airport,
                    destination_airport=cheapest_nearby.destination_airport,
                    departure_time=cheapest_nearby.departure_time,
                    arrival_time=cheapest_nearby.arrival_time,
                    date=sel_date,
                    price=cheapest_nearby.price,
                    stops=cheapest_nearby.stops,
                    duration_minutes=cheapest_nearby.duration_minutes,
                    cabin_class=cheapest_nearby.cabin_class,
                    savings_amount=round(savings, 2),
                    savings_percent=round(savings / sel_price * 100, 1) if sel_price > 0 else 0,
                ))

        return alternatives

    def _layer1_same_airline_routing(
        self,
        selected: FlightData,
        sel_date: str,
        sel_price: float,
        options: list[FlightData],
        leg: LegContext,
    ) -> list[Alternative]:
        """Layer 1b: Same airline, same date, cheaper routing — more stops (low disruption).

        Catches the common case where Air Canada nonstop is $3,496 but
        Air Canada 1-stop is $2,139 — same loyalty, cheaper price.
        """
        min_savings = cfg.alternatives.layer1_routing_min_savings

        routing_options = [
            o for o in options
            if o.airline_code == selected.airline_code
            and _extract_date(o.departure_time) == sel_date
            and not o.is_alternate_airport
            and o.price < sel_price
            and (sel_price - o.price) >= min_savings
            and o.stops > selected.stops
            and o.id != selected.id
        ]

        if not routing_options:
            return []

        # Group by stop count, take cheapest per stop count
        by_stops: dict[int, FlightData] = {}
        for o in routing_options:
            if o.stops not in by_stops or o.price < by_stops[o.stops].price:
                by_stops[o.stops] = o

        sorted_opts = sorted(by_stops.values(), key=lambda o: o.price)[
            :cfg.limits.layer1_routing_max
        ]

        alternatives: list[Alternative] = []
        for o in sorted_opts:
            savings = sel_price - o.price
            stop_label = f"{o.stops} stop" if o.stops == 1 else f"{o.stops} stops"
            alternatives.append(Alternative(
                alt_type="same_airline_routing",
                layer=1,
                disruption_level="low",
                what_changes=["routing"],
                flight_option_id=o.id,
                label=f"{o.airline_name} with {stop_label}",
                airline_code=o.airline_code,
                airline_name=o.airline_name,
                origin_airport=o.origin_airport,
                destination_airport=o.destination_airport,
                departure_time=o.departure_time,
                arrival_time=o.arrival_time,
                date=sel_date,
                price=o.price,
                stops=o.stops,
                duration_minutes=o.duration_minutes,
                cabin_class=o.cabin_class,
                savings_amount=round(savings, 2),
                savings_percent=round(savings / sel_price * 100, 1) if sel_price > 0 else 0,
                is_user_airline=True,
            ))

        return alternatives

    def _layer2_date_shifts(
        self,
        selected: FlightData,
        sel_date: str,
        sel_price: float,
        options: list[FlightData],
        leg: LegContext,
        context: TripContext,
    ) -> list[Alternative]:
        """Layer 2: Same-airline, different date (medium disruption).

        Computes hotel impact for each date shift.
        """
        if leg.flexibility_days == 0:
            logger.debug(
                f"Leg {leg.leg_id}: flexibility_days=0, skipping date-shift alternatives"
            )
            return []

        min_savings = cfg.alternatives.layer2_min_savings

        same_airline_diff_date = [
            o for o in options
            if o.airline_code == selected.airline_code
            and _extract_date(o.departure_time) != sel_date
            and o.price < sel_price
            and (sel_price - o.price) >= min_savings
        ]

        if not same_airline_diff_date:
            return []

        # Determine leg position for trip-aware constraints
        is_outbound = leg.sequence == 1
        other_leg_date = None
        original_duration = None

        if context.is_round_trip:
            other_leg = context.legs[-1] if is_outbound else context.legs[0]
            if other_leg.selected_flight:
                other_leg_date = _extract_date(other_leg.selected_flight.departure_time)

            first_date = context.legs[0].preferred_date
            last_date = context.legs[-1].preferred_date
            if first_date and last_date:
                original_duration = (date.fromisoformat(last_date) - date.fromisoformat(first_date)).days

        # Apply trip-aware constraints
        if other_leg_date and original_duration:
            other_dt = date.fromisoformat(other_leg_date)
            max_flex = cfg.search_ranges.max_trip_duration_flex
            min_dur = cfg.search_ranges.min_trip_duration

            def _trip_ok(o: FlightData) -> bool:
                alt_date_str = _extract_date(o.departure_time)
                if not alt_date_str:
                    return False
                alt_dt = date.fromisoformat(alt_date_str)
                if is_outbound:
                    duration = (other_dt - alt_dt).days
                else:
                    duration = (alt_dt - other_dt).days
                if duration < min_dur:
                    return False
                if not ((original_duration - max_flex) <= duration <= (original_duration + max_flex)):
                    return False
                return _corporate_days_ok_single(alt_dt, is_outbound)

            same_airline_diff_date = [o for o in same_airline_diff_date if _trip_ok(o)]
        else:
            # Single-leg or no cross-leg context — only enforce corporate days
            same_airline_diff_date = [
                o for o in same_airline_diff_date
                if _corporate_days_ok_single(
                    date.fromisoformat(_extract_date(o.departure_time)),
                    is_outbound,
                )
            ]

        if not same_airline_diff_date:
            return []

        # Group by date, take cheapest per date, then top N
        by_date: dict[str, FlightData] = {}
        for o in same_airline_diff_date:
            d = _extract_date(o.departure_time)
            if d and (d not in by_date or o.price < by_date[d].price):
                by_date[d] = o

        sorted_opts = sorted(by_date.values(), key=lambda o: o.price)[:cfg.limits.layer2_max]

        alternatives: list[Alternative] = []
        for o in sorted_opts:
            alt_date = _extract_date(o.departure_time)
            savings = sel_price - o.price

            # Compute hotel impact for date shift
            hi = hotel_impact_calculator.compute_for_date_shift(
                original_date=sel_date,
                new_date=alt_date,
                leg_context=leg,
                is_outbound=is_outbound,
            )
            net = hotel_impact_calculator.compute_net_savings(savings, hi)

            alternatives.append(Alternative(
                alt_type="same_airline_date_shift",
                layer=2,
                disruption_level="medium",
                what_changes=["date"],
                flight_option_id=o.id,
                label=f"{selected.airline_name} on {alt_date}",
                airline_code=o.airline_code,
                airline_name=o.airline_name,
                origin_airport=o.origin_airport,
                destination_airport=o.destination_airport,
                departure_time=o.departure_time,
                arrival_time=o.arrival_time,
                date=alt_date,
                price=o.price,
                stops=o.stops,
                duration_minutes=o.duration_minutes,
                cabin_class=o.cabin_class,
                savings_amount=round(savings, 2),
                savings_percent=round(savings / sel_price * 100, 1) if sel_price > 0 else 0,
                hotel_impact=hi.to_dict() if hi.has_impact else None,
                net_savings=net.to_dict(),
                is_user_airline=True,
            ))

        return alternatives

    def _layer4_cabin_downgrade(
        self,
        selected: FlightData,
        sel_date: str,
        sel_price: float,
        options: list[FlightData],
        leg: LegContext,
    ) -> list[Alternative]:
        """Layer 4: Cabin downgrade (high disruption)."""
        lower_cabin = CABIN_DOWNGRADE_MAP.get(leg.cabin_class)
        if not lower_cabin:
            return []

        min_savings = cfg.alternatives.layer4_min_savings

        lower_options = [
            o for o in options
            if o.cabin_class == lower_cabin
            and _extract_date(o.departure_time) == sel_date
            and o.price < sel_price
            and (sel_price - o.price) >= min_savings
        ]

        if not lower_options:
            return []

        # Group by airline, cheapest per airline
        by_airline: dict[str, FlightData] = {}
        for o in lower_options:
            if o.airline_code not in by_airline or o.price < by_airline[o.airline_code].price:
                by_airline[o.airline_code] = o

        sorted_opts = sorted(by_airline.values(), key=lambda o: o.price)[:cfg.limits.layer4_max]

        alternatives: list[Alternative] = []
        for o in sorted_opts:
            savings = sel_price - o.price
            changes = ["cabin"]
            if o.airline_code != selected.airline_code:
                changes.append("airline")

            alternatives.append(Alternative(
                alt_type="cabin_downgrade",
                layer=4,
                disruption_level="high",
                what_changes=changes,
                flight_option_id=o.id,
                label=f"{lower_cabin.replace('_', ' ').title()} on {o.airline_name}",
                airline_code=o.airline_code,
                airline_name=o.airline_name,
                origin_airport=o.origin_airport,
                destination_airport=o.destination_airport,
                departure_time=o.departure_time,
                arrival_time=o.arrival_time,
                date=sel_date,
                price=o.price,
                stops=o.stops,
                duration_minutes=o.duration_minutes,
                cabin_class=o.cabin_class,
                savings_amount=round(savings, 2),
                savings_percent=round(savings / sel_price * 100, 1) if sel_price > 0 else 0,
            ))

        return alternatives

    # ---- Trip-window proposals ----

    def _generate_trip_window(
        self,
        context: TripContext,
        preferred_outbound: str,
        preferred_return: str,
        original_duration: int,
    ) -> list[TripWindowProposal]:
        """Generate trip-window date-shift proposals (Layer 2-3).

        3-pass algorithm:
        Pass 1: Cheapest overall per date (any airline)
        Pass 2: User's selected airline on shifted dates
        Pass 3: Same-airline proposals (both legs match, not user's airline)
        """
        outbound_leg = context.legs[0]
        return_leg = context.legs[-1]

        outbound_options = outbound_leg.all_options
        return_options = return_leg.all_options

        if not outbound_options or not return_options:
            return []

        pref_out = date.fromisoformat(preferred_outbound)

        # User's selected airlines
        selected_codes: set[str] = set()
        for leg in context.legs:
            if leg.selected_flight:
                selected_codes.add(leg.selected_flight.airline_code)

        # Reference price for savings computation
        original_total = context.selected_total if context.selected_total > 0 else 0.0

        # Build cheapest flight per date
        out_by_date = _cheapest_per_date(outbound_options)
        ret_by_date = _cheapest_per_date(return_options)

        # Build per-airline cheapest by date
        out_by_airline_date = _cheapest_per_airline_date(outbound_options)
        ret_by_airline_date = _cheapest_per_airline_date(return_options)

        # Fallback original total if no selection
        if original_total <= 0:
            out_f = out_by_date.get(preferred_outbound)
            ret_f = ret_by_date.get(preferred_return)
            original_total = (out_f.price if out_f else 0) + (ret_f.price if ret_f else 0)

        # User airline reference total
        selected_original_total = original_total
        if selected_codes:
            for code in selected_codes:
                out_f = out_by_airline_date.get((code, preferred_outbound))
                ret_f = ret_by_airline_date.get((code, preferred_return))
                if out_f and ret_f:
                    selected_original_total = out_f.price + ret_f.price
                    break

        duration_offsets = range(
            -cfg.search_ranges.max_trip_duration_flex,
            cfg.search_ranges.max_trip_duration_flex + 1,
        )

        raw_proposals: list[TripWindowProposal] = []

        # === Pass 1: Cheapest overall per date ===
        for out_date_str, out_flight in out_by_date.items():
            out_date = date.fromisoformat(out_date_str)
            for offset in duration_offsets:
                cand_duration = original_duration + offset
                if cand_duration < cfg.search_ranges.min_trip_duration:
                    continue
                ret_date = out_date + timedelta(days=cand_duration)
                ret_date_str = ret_date.isoformat()
                if out_date_str == preferred_outbound and ret_date_str == preferred_return:
                    continue
                if not _corporate_days_ok(out_date, ret_date):
                    continue
                ret_flight = ret_by_date.get(ret_date_str)
                if not ret_flight:
                    continue

                p = self._make_proposal(
                    out_flight, ret_flight, out_date_str, ret_date_str,
                    cand_duration, original_duration, original_total,
                    pref_out, context,
                    is_user_airline=False,
                )
                if p and p.savings_amount > 0:
                    raw_proposals.append(p)

        # === Pass 2: User's selected airline on shifted dates ===
        for code in selected_codes:
            for (airline, out_date_str), out_flight in out_by_airline_date.items():
                if airline != code:
                    continue
                out_date = date.fromisoformat(out_date_str)
                for offset in duration_offsets:
                    cand_duration = original_duration + offset
                    if cand_duration < cfg.search_ranges.min_trip_duration:
                        continue
                    ret_date = out_date + timedelta(days=cand_duration)
                    ret_date_str = ret_date.isoformat()
                    if out_date_str == preferred_outbound and ret_date_str == preferred_return:
                        continue
                    if not _corporate_days_ok(out_date, ret_date):
                        continue
                    ret_flight = ret_by_airline_date.get((code, ret_date_str))
                    if not ret_flight:
                        continue

                    p = self._make_proposal(
                        out_flight, ret_flight, out_date_str, ret_date_str,
                        cand_duration, original_duration, selected_original_total,
                        pref_out, context,
                        is_user_airline=True,
                    )
                    if p and p.savings_amount > 0:
                        raw_proposals.append(p)

        # === Pass 3: Same-airline proposals (any airline, both legs match) ===
        for (airline, out_date_str), out_flight in out_by_airline_date.items():
            if airline in selected_codes:
                continue
            out_date = date.fromisoformat(out_date_str)
            for offset in duration_offsets:
                cand_duration = original_duration + offset
                if cand_duration < cfg.search_ranges.min_trip_duration:
                    continue
                ret_date = out_date + timedelta(days=cand_duration)
                ret_date_str = ret_date.isoformat()
                if out_date_str == preferred_outbound and ret_date_str == preferred_return:
                    continue
                if not _corporate_days_ok(out_date, ret_date):
                    continue
                ret_flight = ret_by_airline_date.get((airline, ret_date_str))
                if not ret_flight:
                    continue

                p = self._make_proposal(
                    out_flight, ret_flight, out_date_str, ret_date_str,
                    cand_duration, original_duration, original_total,
                    pref_out, context,
                    is_user_airline=False,
                )
                if p and p.savings_amount > 0:
                    raw_proposals.append(p)

        # Deduplicate: keep best savings per (out_date, ret_date, airline_pair)
        unique: dict[tuple, TripWindowProposal] = {}
        for p in raw_proposals:
            key = (
                p.outbound_date, p.return_date,
                p.outbound_flight.airline_code, p.return_flight.airline_code,
            )
            if key not in unique or p.savings_amount > unique[key].savings_amount:
                unique[key] = p

        all_sorted = sorted(unique.values(), key=lambda p: p.savings_amount, reverse=True)

        # Ensure user-airline proposals are always included
        user_airline_proposals = [p for p in all_sorted if p.is_user_airline]
        non_user_proposals = [p for p in all_sorted if not p.is_user_airline]

        reserved_ua = user_airline_proposals[:4]
        remaining_slots = 15 - len(reserved_ua)
        raw_candidates = reserved_ua + non_user_proposals[:remaining_slots]
        raw_candidates.sort(key=lambda p: p.savings_amount, reverse=True)

        logger.info(
            f"Trip-window raw: {len(all_sorted)} unique, "
            f"{len(user_airline_proposals)} user-airline, "
            f"{len(raw_candidates)} final candidates"
        )

        return raw_candidates

    def _make_proposal(
        self,
        out_flight: FlightData,
        ret_flight: FlightData,
        out_date_str: str,
        ret_date_str: str,
        candidate_duration: int,
        original_duration: int,
        reference_total: float,
        pref_out: date,
        context: TripContext,
        is_user_airline: bool = False,
    ) -> TripWindowProposal | None:
        """Build a trip-window proposal with hotel impact."""
        total = out_flight.price + ret_flight.price
        savings = reference_total - total
        savings_pct = round((savings / reference_total) * 100, 1) if reference_total > 0 else 0

        same_airline = out_flight.airline_code == ret_flight.airline_code

        # Determine layer: ≤21 days shift = Layer 2 (medium), >21 = Layer 3 (high)
        days_shift = abs((date.fromisoformat(out_date_str) - pref_out).days)

        if days_shift <= 21:
            layer = 2
            disruption = "medium"
        else:
            layer = 3
            disruption = "high"

        what_changes: list[str] = ["date"]
        if not is_user_airline:
            selected_codes = {
                leg.selected_flight.airline_code
                for leg in context.legs
                if leg.selected_flight
            }
            if out_flight.airline_code not in selected_codes or ret_flight.airline_code not in selected_codes:
                what_changes.append("airline")
        if candidate_duration != original_duration:
            what_changes.append("trip_duration")

        # Compute hotel impact for trip-window shift
        preferred_return = context.legs[-1].preferred_date if len(context.legs) >= 2 else ""
        hi = hotel_impact_calculator.compute_for_trip_window(
            original_outbound=pref_out.isoformat(),
            original_return=preferred_return,
            new_outbound=out_date_str,
            new_return=ret_date_str,
            context=context,
        )
        net = hotel_impact_calculator.compute_net_savings(savings, hi)

        return TripWindowProposal(
            outbound_date=out_date_str,
            return_date=ret_date_str,
            trip_duration=candidate_duration,
            duration_change=candidate_duration - original_duration,
            outbound_flight=FlightSummary(
                airline_name=out_flight.airline_name,
                airline_code=out_flight.airline_code,
                price=out_flight.price,
                stops=out_flight.stops,
                departure_time=out_flight.departure_time,
                arrival_time=out_flight.arrival_time,
                duration_minutes=out_flight.duration_minutes,
            ),
            return_flight=FlightSummary(
                airline_name=ret_flight.airline_name,
                airline_code=ret_flight.airline_code,
                price=ret_flight.price,
                stops=ret_flight.stops,
                departure_time=ret_flight.departure_time,
                arrival_time=ret_flight.arrival_time,
                duration_minutes=ret_flight.duration_minutes,
            ),
            total_price=round(total, 2),
            savings_amount=round(savings, 2),
            savings_percent=savings_pct,
            same_airline=same_airline,
            airline_name=out_flight.airline_name if same_airline else None,
            is_user_airline=is_user_airline,
            layer=layer,
            disruption_level=disruption,
            what_changes=what_changes,
            hotel_impact=hi.to_dict() if hi.has_impact else None,
            net_savings=net.to_dict(),
        )


# ---------- Fallback rule-based selection ----------


def fallback_select_proposals(
    proposals: list[TripWindowProposal],
    max_proposals: int,
    preferred_outbound: str = "",
    category: str = "trip_window",
) -> list[TripWindowProposal]:
    """Rule-based trip-window selection when LLM is unavailable.

    Guarantees diversity:
    1. User's airline (best savings among user_airline proposals)
    2. Cheapest overall (any airline)
    3. Different airline from slots 1-2 (prefer premium carriers)
    4. Another diverse option

    When category is specified, filters proposals by date distance:
    - trip_window: ≤21 days from preferred date
    - different_month: >21 days from preferred date
    """
    if not proposals:
        return []

    # Category-aware filtering
    if preferred_outbound and category in ("trip_window", "different_month"):
        pref_out = date.fromisoformat(preferred_outbound)

        def _days_from_pref(p: TripWindowProposal) -> int:
            return abs((date.fromisoformat(p.outbound_date) - pref_out).days)

        if category == "different_month":
            filtered = [p for p in proposals if _days_from_pref(p) > 21]
        else:
            filtered = [p for p in proposals if _days_from_pref(p) <= 21]
        if filtered:
            proposals = filtered

    final: list[TripWindowProposal] = []
    used: set[int] = set()

    def _airline(p: TripWindowProposal) -> str:
        return p.outbound_flight.airline_code

    # Slot 1: User's airline — best savings
    user_airline_proposals = [p for p in proposals if p.is_user_airline]
    if user_airline_proposals:
        best_ua = max(user_airline_proposals, key=lambda p: p.savings_amount)
        final.append(best_ua)
        used.add(id(best_ua))

    # Slot 2: Cheapest overall (different from slot 1 if possible)
    for p in sorted(proposals, key=lambda p: p.total_price):
        if id(p) not in used:
            final.append(p)
            used.add(id(p))
            break

    # Slots 3+: Diverse airlines (not already in final)
    seen_airlines = {_airline(p) for p in final}
    for p in sorted(proposals, key=lambda p: -p.savings_amount):
        if len(final) >= max_proposals:
            break
        if id(p) in used:
            continue
        if _airline(p) not in seen_airlines:
            final.append(p)
            used.add(id(p))
            seen_airlines.add(_airline(p))

    # Fill remaining slots
    for p in sorted(proposals, key=lambda p: -p.savings_amount):
        if len(final) >= max_proposals:
            break
        if id(p) not in used:
            final.append(p)
            used.add(id(p))

    final.sort(key=lambda p: (not p.is_user_airline, -p.savings_amount))
    return final[:max_proposals]


# ---------- Helper functions ----------


def _extract_date(departure_time: str) -> str:
    """Extract date string from ISO datetime."""
    if not departure_time:
        return ""
    return departure_time[:10]


def _corporate_days_ok(out_date: date, ret_date: date) -> bool:
    """Check if dates comply with corporate travel day rules."""
    rules = CORPORATE_DAY_RULES
    return (
        out_date.weekday() in rules["outbound_weekdays"]
        and ret_date.weekday() in rules["return_weekdays"]
    )


def _corporate_days_ok_single(dt: date, is_outbound: bool) -> bool:
    """Check if a single date complies with corporate day rules."""
    rules = CORPORATE_DAY_RULES
    if is_outbound:
        return dt.weekday() in rules["outbound_weekdays"]
    return dt.weekday() in rules["return_weekdays"]


def _cheapest_per_date(options: list[FlightData]) -> dict[str, FlightData]:
    """Build mapping of date → cheapest flight on that date."""
    by_date: dict[str, FlightData] = {}
    for f in options:
        d = _extract_date(f.departure_time)
        if d and (d not in by_date or f.price < by_date[d].price):
            by_date[d] = f
    return by_date


def _cheapest_per_airline_date(
    options: list[FlightData],
) -> dict[tuple[str, str], FlightData]:
    """Build mapping of (airline_code, date) → cheapest flight."""
    by_key: dict[tuple[str, str], FlightData] = {}
    for f in options:
        d = _extract_date(f.departure_time)
        key = (f.airline_code, d)
        if d and (key not in by_key or f.price < by_key[key].price):
            by_key[key] = f
    return by_key


# Singleton
flight_alternatives_generator = FlightAlternativesGenerator()
