"""Companion pricing service — calculates family/companion travel costs.

Given an employee's confirmed flight selections, queries DB1B for economy
and premium_economy fares on the same routes and dates for N companions.
Also checks ±2 day shifts for cheaper companion fares.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)


@dataclass
class CompanionLegOption:
    """Pricing for companions on a single leg."""
    leg_id: str
    route: str
    date: str
    cabin_class: str
    airline_code: str
    airline_name: str
    per_person: float
    total: float  # per_person * companions
    stops: int
    duration_minutes: int


@dataclass
class NearbyDateOption:
    """A cheaper date alternative for companion travel."""
    leg_id: str
    route: str
    date: str
    cabin_class: str
    airline_code: str
    airline_name: str
    per_person: float
    total: float
    stops: int
    date_diff_days: int  # negative = earlier, positive = later
    savings_vs_selected: float  # savings per person vs selected date


@dataclass
class CompanionPricingResult:
    """Complete companion pricing breakdown."""
    employee_total: float
    companions_count: int
    companion_cabin_class: str
    companion_options: list[CompanionLegOption] = field(default_factory=list)
    nearby_date_options: list[NearbyDateOption] = field(default_factory=list)
    combined_min: float = 0.0
    combined_max: float = 0.0
    summary: str = ""


@dataclass
class CabinOption:
    """Pricing for all travelers at a given cabin class."""
    cabin_class: str
    per_person_per_leg: list[float]
    total_per_person: float
    total_all_travelers: float
    fits_budget: bool
    budget_delta: float           # positive = under budget
    budget_delta_percent: float
    airline_codes: list[str]


@dataclass
class CabinBudgetResult:
    """Cabin budget recommendation — which cabin fits the budget for all travelers."""
    anchor_total: float
    budget_envelope: float
    budget_tolerance: float
    total_travelers: int
    recommended_cabin: str
    recommendation_reason: str
    cabin_options: list[CabinOption] = field(default_factory=list)
    economy_savings: float = 0.0


class CompanionPricingService:
    """Calculates companion travel pricing using DB1B fare data."""

    async def get_companion_pricing(
        self,
        trip_id: str,
        companions: int,
        companion_cabin: str,
        db,
    ) -> CompanionPricingResult:
        """Build companion pricing for all legs of a trip.

        Args:
            trip_id: Trip UUID
            companions: Number of companion travelers
            companion_cabin: Desired cabin class for companions (economy, premium_economy)
            db: AsyncSession
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from uuid import UUID

        from app.models.trip import Trip, TripLeg
        from app.models.policy import Selection
        from app.models.search_log import FlightOption

        # Load trip with legs and selections
        result = await db.execute(
            select(Trip).options(selectinload(Trip.legs)).where(Trip.id == UUID(trip_id))
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError(f"Trip {trip_id} not found")

        legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

        # Get selections for each leg
        employee_total = 0.0
        leg_selections = []
        for leg in legs_sorted:
            sel_result = await db.execute(
                select(Selection).where(Selection.trip_leg_id == leg.id)
            )
            sel = sel_result.scalar_one_or_none()
            if not sel:
                continue

            fo_result = await db.execute(
                select(FlightOption).where(FlightOption.id == sel.flight_option_id)
            )
            fo = fo_result.scalar_one_or_none()
            if not fo:
                continue

            employee_total += float(fo.price) if fo.price else 0
            leg_selections.append((leg, fo))

        if not leg_selections:
            return CompanionPricingResult(
                employee_total=0,
                companions_count=companions,
                companion_cabin_class=companion_cabin,
                summary="No flights selected yet. Select flights first.",
            )

        # Query companion fares via configured flight provider
        from app.services.flight_provider import flight_provider

        if not flight_provider.is_available():
            return CompanionPricingResult(
                employee_total=employee_total,
                companions_count=companions,
                companion_cabin_class=companion_cabin,
                summary="Pricing data unavailable.",
            )

        companion_options = []
        nearby_date_options = []

        for leg, fo in leg_selections:
            route = f"{leg.origin_airport} → {leg.destination_airport}"
            sel_date = leg.companion_preferred_date or leg.preferred_date
            airline_code = fo.airline_code or ""

            # Get companion fare on selected date
            flights = await flight_provider.search_flights(
                leg.origin_airport,
                leg.destination_airport,
                sel_date,
                companion_cabin,
            )

            # Find same-airline option first, then cheapest overall
            same_airline = [f for f in flights if f.get("airline_code") == airline_code]
            cheapest = same_airline[0] if same_airline else (flights[0] if flights else None)

            if cheapest:
                per_person = cheapest["price"]
                companion_options.append(CompanionLegOption(
                    leg_id=str(leg.id),
                    route=route,
                    date=sel_date.isoformat(),
                    cabin_class=companion_cabin,
                    airline_code=cheapest.get("airline_code", ""),
                    airline_name=cheapest.get("airline_name", ""),
                    per_person=per_person,
                    total=per_person * companions,
                    stops=cheapest.get("stops", 0),
                    duration_minutes=cheapest.get("duration_minutes", 0),
                ))

                # Check ±2 days for cheaper options
                for day_offset in range(-2, 3):
                    if day_offset == 0:
                        continue
                    alt_date = sel_date + timedelta(days=day_offset)
                    alt_flights = await flight_provider.search_flights(
                        leg.origin_airport,
                        leg.destination_airport,
                        alt_date,
                        companion_cabin,
                    )
                    alt_same = [f for f in alt_flights if f.get("airline_code") == airline_code]
                    alt_best = alt_same[0] if alt_same else (alt_flights[0] if alt_flights else None)

                    if alt_best and alt_best["price"] < per_person:
                        nearby_date_options.append(NearbyDateOption(
                            leg_id=str(leg.id),
                            route=route,
                            date=alt_date.isoformat(),
                            cabin_class=companion_cabin,
                            airline_code=alt_best.get("airline_code", ""),
                            airline_name=alt_best.get("airline_name", ""),
                            per_person=alt_best["price"],
                            total=alt_best["price"] * companions,
                            stops=alt_best.get("stops", 0),
                            date_diff_days=day_offset,
                            savings_vs_selected=per_person - alt_best["price"],
                        ))

        # Sort nearby options by savings
        nearby_date_options.sort(key=lambda x: x.savings_vs_selected, reverse=True)

        # Calculate combined totals
        companion_total = sum(o.total for o in companion_options)
        combined_min = employee_total + companion_total
        combined_max = combined_min

        if nearby_date_options:
            # Best possible companion total using cheapest date per leg
            best_per_leg = {}
            for opt in nearby_date_options:
                if opt.leg_id not in best_per_leg or opt.per_person < best_per_leg[opt.leg_id]:
                    best_per_leg[opt.leg_id] = opt.per_person
            best_companion = sum(
                best_per_leg.get(o.leg_id, o.per_person) * companions
                for o in companion_options
            )
            combined_min = employee_total + best_companion

        # Build summary
        comp_per_person = sum(o.per_person for o in companion_options)
        summary_parts = [
            f"Your {leg_selections[0][1].cabin_class or 'business'} class: ${employee_total:,.0f}.",
        ]
        if companion_options:
            summary_parts.append(
                f"Family of {companions} in {companion_cabin}: "
                f"~${comp_per_person:,.0f}/person (${companion_total:,.0f} total)."
            )
            summary_parts.append(f"Combined: ${combined_min:,.0f}–${combined_max:,.0f}.")
        if nearby_date_options:
            best = nearby_date_options[0]
            summary_parts.append(
                f"Tip: shifting {best.route} by {abs(best.date_diff_days)} day(s) "
                f"saves ${best.savings_vs_selected * companions:,.0f} for companions."
            )

        return CompanionPricingResult(
            employee_total=employee_total,
            companions_count=companions,
            companion_cabin_class=companion_cabin,
            companion_options=companion_options,
            nearby_date_options=nearby_date_options[:6],  # Top 6 alternatives
            combined_min=combined_min,
            combined_max=combined_max,
            summary=" ".join(summary_parts),
        )


    async def get_cabin_budget_recommendation(
        self,
        trip_id: str,
        total_travelers: int,
        anchor_prices: dict[str, float],
        db,
    ) -> CabinBudgetResult:
        """Given anchor prices per leg, recommend the highest cabin that fits all travelers.

        Args:
            trip_id: Trip UUID
            total_travelers: Employee + companions (e.g. 4)
            anchor_prices: {leg_id: anchor_price} — one anchor per leg
            db: AsyncSession
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from uuid import UUID

        from app.models.trip import Trip
        from app.models.policy import Selection
        from app.models.search_log import FlightOption

        # Load trip legs
        result = await db.execute(
            select(Trip).options(selectinload(Trip.legs)).where(Trip.id == UUID(trip_id))
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError(f"Trip {trip_id} not found")

        legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

        # Load employee's selected airline per leg for same-airline preference
        employee_airline_per_leg: dict[str, str] = {}
        for leg in legs_sorted:
            sel_result = await db.execute(
                select(Selection).where(Selection.trip_leg_id == leg.id)
            )
            sel = sel_result.scalar_one_or_none()
            if sel:
                fo_result = await db.execute(
                    select(FlightOption).where(FlightOption.id == sel.flight_option_id)
                )
                fo = fo_result.scalar_one_or_none()
                if fo and fo.airline_code:
                    employee_airline_per_leg[str(leg.id)] = fo.airline_code

        # Budget = sum of anchor prices across legs
        budget = sum(anchor_prices.values())
        tolerance = 0.15
        ceiling = budget * (1 + tolerance)

        from app.services.flight_provider import flight_provider

        cabin_options: list[CabinOption] = []

        for cabin in ["business", "premium_economy", "economy"]:
            per_person_per_leg: list[float] = []
            airline_codes: list[str] = []

            for leg in legs_sorted:
                leg_id = str(leg.id)
                # Search flights for this cabin on this leg
                leg_date = leg.companion_preferred_date or leg.preferred_date
                flights = await flight_provider.search_flights(
                    leg.origin_airport,
                    leg.destination_airport,
                    leg_date,
                    cabin,
                )

                if not flights:
                    per_person_per_leg.append(0)
                    airline_codes.append("")
                    continue

                # Sort by price
                flights.sort(key=lambda f: f.get("price", float("inf")))

                # Prefer same airline as employee's selection, fall back to cheapest
                emp_airline = employee_airline_per_leg.get(leg_id, "")
                same_airline = [f for f in flights if f.get("airline_code") == emp_airline] if emp_airline else []
                best = same_airline[0] if same_airline else flights[0]

                per_person_per_leg.append(best["price"])
                airline_codes.append(best.get("airline_code", ""))

            total_per_person = sum(per_person_per_leg)
            total_all = total_per_person * total_travelers
            fits = total_all <= ceiling
            delta = budget - total_all
            delta_pct = (delta / budget * 100) if budget > 0 else 0

            cabin_options.append(CabinOption(
                cabin_class=cabin,
                per_person_per_leg=per_person_per_leg,
                total_per_person=round(total_per_person, 2),
                total_all_travelers=round(total_all, 2),
                fits_budget=fits,
                budget_delta=round(delta, 2),
                budget_delta_percent=round(delta_pct, 1),
                airline_codes=airline_codes,
            ))

        # Recommend highest cabin that fits
        recommended = "economy"
        for opt in cabin_options:
            if opt.fits_budget:
                recommended = opt.cabin_class
                break

        # Build reason string
        rec_opt = next((o for o in cabin_options if o.cabin_class == recommended), None)
        econ_opt = next((o for o in cabin_options if o.cabin_class == "economy"), None)
        economy_savings = budget - (econ_opt.total_all_travelers if econ_opt else 0)

        if recommended == "business":
            reason = (
                f"All {total_travelers} travelers can fly business class "
                f"for ${rec_opt.total_all_travelers:,.0f} — within your ${budget:,.0f} budget."
            )
        elif recommended == "premium_economy":
            biz_opt = next((o for o in cabin_options if o.cabin_class == "business"), None)
            reason = (
                f"Business for {total_travelers} would be ${biz_opt.total_all_travelers:,.0f} "
                f"(over budget). Premium economy fits at ${rec_opt.total_all_travelers:,.0f} "
                f"({abs(rec_opt.budget_delta_percent):.0f}% {'under' if rec_opt.budget_delta >= 0 else 'over'} budget)."
            )
        else:
            pe_opt = next((o for o in cabin_options if o.cabin_class == "premium_economy"), None)
            reason = (
                f"Premium economy for {total_travelers} would be ${pe_opt.total_all_travelers:,.0f} "
                f"(over budget). Economy fits at ${rec_opt.total_all_travelers:,.0f}, "
                f"saving ${economy_savings:,.0f} vs your business class budget."
            )

        return CabinBudgetResult(
            anchor_total=round(budget, 2),
            budget_envelope=round(budget, 2),
            budget_tolerance=tolerance,
            total_travelers=total_travelers,
            recommended_cabin=recommended,
            recommendation_reason=reason,
            cabin_options=cabin_options,
            economy_savings=round(max(economy_savings, 0), 2),
        )


companion_pricing_service = CompanionPricingService()
