"""Companion pricing service — calculates family/companion travel costs.

Given an employee's confirmed flight selections, queries DB1B for economy
and premium_economy fares on the same routes and dates for N companions.
"""

import logging
from dataclasses import dataclass, field

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
    near_miss_note: str | None = None
    savings_note: str | None = None
    source: str = "fallback"


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

        # Calculate combined totals
        companion_total = sum(o.total for o in companion_options)
        combined_total = employee_total + companion_total

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
            summary_parts.append(f"Combined: ${combined_total:,.0f}.")

        return CompanionPricingResult(
            employee_total=employee_total,
            companions_count=companions,
            companion_cabin_class=companion_cabin,
            companion_options=companion_options,
            combined_min=combined_total,
            combined_max=combined_total,
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

        # Build route summary for advisor context
        route_parts = []
        for leg in legs_sorted:
            route_parts.append(f"{leg.origin_airport} \u2192 {leg.destination_airport}")
        route_summary = ", ".join(route_parts)

        # Determine employee's cabin and airline
        employee_cabin = legs_sorted[0].cabin_class if legs_sorted else "business"
        first_airline = next(iter(employee_airline_per_leg.values()), "")

        # Convert CabinOption dataclasses to dicts for advisor
        advisor_options = [
            {
                "cabin": opt.cabin_class,
                "total_per_person": opt.total_per_person,
                "total_all_travelers": opt.total_all_travelers,
                "fits": opt.fits_budget,
                "delta": opt.budget_delta,
            }
            for opt in cabin_options
        ]

        # LLM advisor for recommendation (with rule-based fallback)
        from app.services.recommendation.companion_advisor import companion_budget_advisor

        advisor_output = await companion_budget_advisor.advise(
            cabin_options=advisor_options,
            budget=budget,
            total_travelers=total_travelers,
            employee_cabin=employee_cabin,
            employee_airline=first_airline,
            route_summary=route_summary,
        )

        econ_opt = next((o for o in cabin_options if o.cabin_class == "economy"), None)
        economy_savings = budget - (econ_opt.total_all_travelers if econ_opt else 0)

        return CabinBudgetResult(
            anchor_total=round(budget, 2),
            budget_envelope=round(budget, 2),
            budget_tolerance=tolerance,
            total_travelers=total_travelers,
            recommended_cabin=advisor_output.recommended_cabin,
            recommendation_reason=advisor_output.reasoning,
            cabin_options=cabin_options,
            economy_savings=round(max(economy_savings, 0), 2),
            near_miss_note=advisor_output.near_miss_note,
            savings_note=advisor_output.savings_note,
            source=advisor_output.source,
        )


companion_pricing_service = CompanionPricingService()
