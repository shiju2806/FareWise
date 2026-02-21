"""Cost driver analyzer — identifies WHY a selection costs what it does."""

import logging
from dataclasses import dataclass
from datetime import date

from app.services.recommendation.config import recommendation_config, CABIN_DOWNGRADE_MAP
from app.services.recommendation.context_assembler import FlightData, LegContext, TripContext

logger = logging.getLogger(__name__)

cfg = recommendation_config.cost_drivers


@dataclass
class CostDriver:
    """A single cost driver with its dollar impact."""
    driver_type: str    # "airline" | "date" | "cabin" | "route" | "stops" | "timing"
    impact_amount: float  # $ amount this driver adds
    impact_percent: float  # % of selected price
    description: str       # human-readable explanation
    leg_id: str | None = None  # which leg, or None for trip-level


@dataclass
class CostDriverReport:
    """Complete cost driver analysis for a trip."""
    drivers: list[CostDriver]
    primary_driver: CostDriver | None
    total_premium: float          # $ over cheapest possible
    total_premium_percent: float  # % over cheapest possible

    def to_dict(self) -> dict:
        return {
            "drivers": [
                {
                    "type": d.driver_type,
                    "impact_amount": round(d.impact_amount, 2),
                    "impact_percent": round(d.impact_percent, 1),
                    "description": d.description,
                    "leg_id": d.leg_id,
                }
                for d in self.drivers
            ],
            "primary_driver": self.drivers[0].driver_type if self.drivers else None,
            "total_premium": round(self.total_premium, 2),
            "total_premium_percent": round(self.total_premium_percent, 1),
        }


class CostDriverAnalyzer:
    """Identifies cost drivers by comparing the selection against alternatives."""

    def analyze(self, context: TripContext) -> CostDriverReport:
        """Analyze all legs and produce a ranked cost driver report."""
        all_drivers: list[CostDriver] = []

        for leg in context.legs:
            if not leg.selected_flight or not leg.all_options:
                continue
            leg_drivers = self._analyze_leg(leg)
            all_drivers.extend(leg_drivers)

        # Sort by impact (highest first)
        all_drivers.sort(key=lambda d: d.impact_amount, reverse=True)

        total_premium = context.selected_total - context.cheapest_total
        total_premium_pct = (
            (total_premium / context.selected_total * 100)
            if context.selected_total > 0
            else 0.0
        )

        return CostDriverReport(
            drivers=all_drivers,
            primary_driver=all_drivers[0] if all_drivers else None,
            total_premium=total_premium,
            total_premium_percent=total_premium_pct,
        )

    def _analyze_leg(self, leg: LegContext) -> list[CostDriver]:
        """Identify cost drivers for a single leg."""
        drivers: list[CostDriver] = []
        selected = leg.selected_flight
        if not selected:
            return drivers

        sel_price = selected.price
        sel_date = self._extract_date(selected.departure_time)
        options = [o for o in leg.all_options if o.price > 0]

        if not options:
            return drivers

        # 1. AIRLINE driver — cheapest same-date, different airline
        same_date_others = [
            o for o in options
            if self._extract_date(o.departure_time) == sel_date
            and o.airline_code != selected.airline_code
        ]
        if same_date_others:
            cheapest_same_date = min(same_date_others, key=lambda o: o.price)
            gap = sel_price - cheapest_same_date.price
            gap_pct = (gap / sel_price * 100) if sel_price > 0 else 0
            if gap > 0 and gap_pct >= cfg.airline_gap_pct:
                drivers.append(CostDriver(
                    driver_type="airline",
                    impact_amount=gap,
                    impact_percent=gap_pct,
                    description=(
                        f"{selected.airline_name} costs ${gap:.0f} more than "
                        f"{cheapest_same_date.airline_name} on the same date"
                    ),
                    leg_id=leg.leg_id,
                ))

        # 2. DATE driver — cheapest any-date vs selected date
        all_prices = [o.price for o in options]
        cheapest_any = min(all_prices)
        if cheapest_any < sel_price:
            date_gap = sel_price - cheapest_any
            date_gap_pct = (date_gap / sel_price * 100) if sel_price > 0 else 0
            # Only flag as DATE driver if the same-day cheapest is close to selected
            # (i.e., the airline isn't the problem, the date is)
            same_date_cheapest = min(
                (o.price for o in options if self._extract_date(o.departure_time) == sel_date),
                default=sel_price,
            )
            date_specific_gap = same_date_cheapest - cheapest_any
            date_specific_pct = (date_specific_gap / sel_price * 100) if sel_price > 0 else 0
            if date_specific_pct >= cfg.date_gap_pct:
                cheapest_opt = min(options, key=lambda o: o.price)
                cheapest_date = self._extract_date(cheapest_opt.departure_time)
                drivers.append(CostDriver(
                    driver_type="date",
                    impact_amount=date_specific_gap,
                    impact_percent=date_specific_pct,
                    description=(
                        f"Flying on {sel_date or 'selected date'} costs ${date_specific_gap:.0f} "
                        f"more than {cheapest_date or 'cheapest date'}"
                    ),
                    leg_id=leg.leg_id,
                ))

        # 3. STOPS driver — nonstop vs 1-stop
        if selected.stops == 0:
            with_stops = [o for o in options if o.stops > 0 and self._extract_date(o.departure_time) == sel_date]
            if with_stops:
                cheapest_stops = min(with_stops, key=lambda o: o.price)
                gap = sel_price - cheapest_stops.price
                gap_pct = (gap / sel_price * 100) if sel_price > 0 else 0
                if gap > 0 and gap_pct >= cfg.stops_gap_pct:
                    drivers.append(CostDriver(
                        driver_type="stops",
                        impact_amount=gap,
                        impact_percent=gap_pct,
                        description=(
                            f"Nonstop costs ${gap:.0f} more than "
                            f"{cheapest_stops.stops}-stop on {cheapest_stops.airline_name}"
                        ),
                        leg_id=leg.leg_id,
                    ))

        # 4. ROUTE driver — alternate airport
        alt_airport = [o for o in options if o.is_alternate_airport and self._extract_date(o.departure_time) == sel_date]
        if alt_airport:
            cheapest_alt = min(alt_airport, key=lambda o: o.price)
            gap = sel_price - cheapest_alt.price
            gap_pct = (gap / sel_price * 100) if sel_price > 0 else 0
            if gap > 0 and gap_pct >= cfg.route_gap_pct:
                drivers.append(CostDriver(
                    driver_type="route",
                    impact_amount=gap,
                    impact_percent=gap_pct,
                    description=(
                        f"Flying into {selected.destination_airport} costs ${gap:.0f} "
                        f"more than {cheapest_alt.destination_airport}"
                    ),
                    leg_id=leg.leg_id,
                ))

        # 5. CABIN driver — estimate one-down cabin price
        lower_cabin = CABIN_DOWNGRADE_MAP.get(leg.cabin_class)
        if lower_cabin:
            # Check if any options in lower cabin exist
            lower_options = [o for o in options if o.cabin_class == lower_cabin]
            if lower_options:
                cheapest_lower = min(lower_options, key=lambda o: o.price)
                gap = sel_price - cheapest_lower.price
                gap_pct = (gap / sel_price * 100) if sel_price > 0 else 0
                if gap > 0 and gap_pct >= cfg.cabin_gap_pct:
                    drivers.append(CostDriver(
                        driver_type="cabin",
                        impact_amount=gap,
                        impact_percent=gap_pct,
                        description=(
                            f"{leg.cabin_class.replace('_', ' ').title()} costs ${gap:.0f} "
                            f"more than {lower_cabin.replace('_', ' ')}"
                        ),
                        leg_id=leg.leg_id,
                    ))

        return drivers

    @staticmethod
    def _extract_date(departure_time: str) -> str | None:
        """Extract date string from ISO datetime."""
        if not departure_time:
            return None
        return departure_time[:10]  # "2026-04-15T08:30:00" → "2026-04-15"


cost_driver_analyzer = CostDriverAnalyzer()
