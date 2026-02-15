"""Trip Analysis router — trip-level cost analysis, date optimization, and LLM insights."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.search_log import FlightOption, SearchLog
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.services.trip_intelligence_service import trip_intelligence

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalyzeTripRequest(BaseModel):
    """Selected flight IDs for each leg, keyed by leg_id."""
    selected_flights: dict[str, str]  # leg_id → flight_option_id


class OptimizeDatesRequest(BaseModel):
    """Optional: specify which two legs to optimize."""
    outbound_leg_id: str | None = None
    return_leg_id: str | None = None


async def _get_user_trip(
    trip_id: uuid.UUID,
    db: AsyncSession,
    user: User,
) -> Trip:
    """Fetch a trip with legs, ensuring it belongs to the current user."""
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.legs))
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


async def _get_leg_flights(
    leg: TripLeg,
    db: AsyncSession,
) -> list[dict]:
    """Get all flight options from the most recent search for a leg."""
    search_result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = search_result.scalar_one_or_none()
    if not search_log:
        return []

    opts_result = await db.execute(
        select(FlightOption).where(FlightOption.search_log_id == search_log.id)
    )
    all_options = opts_result.scalars().all()

    return [
        {
            "id": str(o.id),
            "airline_name": o.airline_name,
            "airline_code": o.airline_code,
            "flight_numbers": o.flight_numbers,
            "origin_airport": o.origin_airport,
            "destination_airport": o.destination_airport,
            "departure_time": o.departure_time.isoformat() if o.departure_time else "",
            "arrival_time": o.arrival_time.isoformat() if o.arrival_time else "",
            "duration_minutes": o.duration_minutes,
            "stops": o.stops,
            "price": float(o.price),
            "currency": o.currency or "CAD",
            "cabin_class": o.cabin_class,
        }
        for o in all_options
        if o.price and float(o.price) > 0
    ]


@router.post("/{trip_id}/analyze-trip")
async def analyze_trip(
    trip_id: uuid.UUID,
    req: AnalyzeTripRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Analyze entire trip cost with LLM-powered insights.

    Compares selected flights across all legs against:
    - Cheapest alternatives (different airlines, with stops, different dates)
    - Company policy budgets per cabin class
    - Routing alternatives

    Returns LLM-generated trip-level recommendation and justification prompt.
    """
    trip = await _get_user_trip(trip_id, db, user)

    # Sort legs by sequence
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    legs_info = []
    selected_flights = []
    all_options_per_leg = []

    for leg in legs_sorted:
        # Get all flight options for this leg
        options = await _get_leg_flights(leg, db)
        all_options_per_leg.append(options)

        legs_info.append({
            "origin_airport": leg.origin_airport,
            "destination_airport": leg.destination_airport,
            "origin_city": leg.origin_city,
            "destination_city": leg.destination_city,
            "preferred_date": leg.preferred_date.isoformat() if leg.preferred_date else "",
            "cabin_class": leg.cabin_class or "economy",
        })

        # Find the selected flight
        flight_id = req.selected_flights.get(str(leg.id))
        if flight_id:
            matching = [o for o in options if o["id"] == flight_id]
            selected_flights.append(matching[0] if matching else None)
        else:
            selected_flights.append(None)

    # Get LLM analysis
    analysis = await trip_intelligence.analyze_trip(
        legs=legs_info,
        selected_flights=selected_flights,
        all_options_per_leg=all_options_per_leg,
    )

    # Also include cost summary (non-LLM structured data)
    cost_summary = trip_intelligence.get_cost_summary(
        legs=legs_info,
        selected_flights=selected_flights,
        all_options_per_leg=all_options_per_leg,
    )

    return {
        "analysis": analysis,
        "cost_summary": cost_summary,
    }


@router.get("/{trip_id}/cost-summary")
async def get_cost_summary(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get structured cost summary for the trip (no LLM, fast).

    Returns per-leg breakdown with cheapest alternatives, policy budgets,
    and total comparisons. Used by the Trip Cost Bar component.
    """
    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    legs_info = []
    all_options_per_leg = []

    for leg in legs_sorted:
        options = await _get_leg_flights(leg, db)
        all_options_per_leg.append(options)

        legs_info.append({
            "origin_airport": leg.origin_airport,
            "destination_airport": leg.destination_airport,
            "cabin_class": leg.cabin_class or "economy",
        })

    cost_summary = trip_intelligence.get_cost_summary(
        legs=legs_info,
        selected_flights=None,
        all_options_per_leg=all_options_per_leg,
    )

    return cost_summary


@router.post("/{trip_id}/optimize-dates")
async def optimize_dates(
    trip_id: uuid.UUID,
    req: OptimizeDatesRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cross-reference outbound × return prices for optimal date combinations.

    Uses LLM to analyze date patterns and recommend the best round-trip
    date combinations considering price, convenience, and trip duration.

    Only works for round trips (2 legs where leg 2 is reverse of leg 1).
    """
    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    if len(legs_sorted) < 2:
        raise HTTPException(
            status_code=400,
            detail="Date optimization requires at least 2 legs (round trip)",
        )

    # Identify outbound and return legs
    if req and req.outbound_leg_id and req.return_leg_id:
        outbound_leg = next((l for l in legs_sorted if str(l.id) == req.outbound_leg_id), None)
        return_leg = next((l for l in legs_sorted if str(l.id) == req.return_leg_id), None)
    else:
        # Default: first leg = outbound, second = return
        outbound_leg = legs_sorted[0]
        return_leg = legs_sorted[1]

    if not outbound_leg or not return_leg:
        raise HTTPException(status_code=400, detail="Could not identify outbound/return legs")

    # Verify it's a round trip
    if outbound_leg.origin_city != return_leg.destination_city:
        raise HTTPException(
            status_code=400,
            detail="Legs do not form a round trip",
        )

    # Get flight options for both legs
    outbound_options = await _get_leg_flights(outbound_leg, db)
    return_options = await _get_leg_flights(return_leg, db)

    if not outbound_options or not return_options:
        raise HTTPException(
            status_code=400,
            detail="Both legs must have search results before optimizing dates",
        )

    outbound_info = {
        "origin_airport": outbound_leg.origin_airport,
        "destination_airport": outbound_leg.destination_airport,
        "cabin_class": outbound_leg.cabin_class or "economy",
    }
    return_info = {
        "origin_airport": return_leg.origin_airport,
        "destination_airport": return_leg.destination_airport,
        "cabin_class": return_leg.cabin_class or "economy",
    }

    result = await trip_intelligence.optimize_dates(
        outbound_leg=outbound_info,
        return_leg=return_info,
        outbound_options=outbound_options,
        return_options=return_options,
        preferred_outbound=outbound_leg.preferred_date.isoformat() if outbound_leg.preferred_date else "",
        preferred_return=return_leg.preferred_date.isoformat() if return_leg.preferred_date else "",
    )

    return result
