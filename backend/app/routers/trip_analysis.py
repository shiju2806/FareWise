"""Trip Analysis router — trip-level cost analysis and LLM insights."""

import logging
import uuid
from datetime import date, datetime

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


class AnalyzeSelectionsRequest(BaseModel):
    """Selected flight IDs for each leg — for trip-level justification analysis."""
    selected_flights: dict[str, str]  # leg_id → flight_option_id


class AnalysisSnapshotRequest(BaseModel):
    """Snapshot of the analysis shown to the traveler at confirmation time."""
    legs: list[dict] | None = None
    trip_totals: dict | None = None
    trip_window_alternatives: dict | None = None


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


@router.post("/{trip_id}/analyze-selections")
async def analyze_selections(
    trip_id: uuid.UUID,
    req: AnalyzeSelectionsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trip-level justification analysis using the modular recommendation pipeline.

    Runs the full pipeline: context assembly → alternative generation →
    cost driver analysis → trade-off scoring → LLM reasoning → audience formatting.
    Returns ReviewAnalysis-compatible output for the traveler UI.
    """
    logger.info(f"analyze-selections called: trip_id={trip_id}, selected_flights={req.selected_flights}")
    from app.services.recommendation.context_assembler import context_assembler
    from app.services.recommendation.flight_alternatives import flight_alternatives_generator
    from app.services.recommendation.cost_driver_analyzer import cost_driver_analyzer
    from app.services.recommendation.trade_off_resolver import trade_off_resolver
    from app.services.recommendation.advisor import travel_advisor
    from app.services.recommendation.audience_adapter import audience_adapter

    try:
        # 1. Assemble context (DB reads: trip, legs, selections, hotel rates)
        context = await context_assembler.assemble(
            db, str(trip_id), user, req.selected_flights,
        )

        # 2. Load broad date range for trip-window proposals (DB1B + fallback)
        await context_assembler.load_trip_window_options(db, context)

        # 3. Generate alternatives (Layer 1-4, trip-window, cabin downgrade)
        raw = flight_alternatives_generator.generate(context)

        # 4. Analyze cost drivers
        cost_drivers = cost_driver_analyzer.analyze(context)

        # 5. Score, rank, curate
        resolved = trade_off_resolver.resolve(raw, context)

        # 6. LLM reasoning + narrative (with fallback)
        output = await travel_advisor.advise(resolved, context, cost_drivers)

        # 7. Format for traveler view
        return audience_adapter.for_traveler(output, context)
    except Exception as e:
        logger.exception(f"analyze-selections FAILED for trip {trip_id}: {e}")
        raise


class CheaperMonthRequest(BaseModel):
    """Airline codes to check for cheaper months."""
    airline_codes: list[str]


@router.post("/{trip_id}/cheaper-months")
async def cheaper_months(
    trip_id: uuid.UUID,
    req: CheaperMonthRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find cheaper months for the user's selected airline on this route.

    Queries DB1B data for the selected airline across adjacent months
    and returns suggestions if a significantly cheaper month exists.
    """
    from app.services.db1b_client import db1b_client

    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    if not legs_sorted:
        return {"suggestions": []}

    outbound_leg = legs_sorted[0]
    if not outbound_leg.preferred_date:
        return {"suggestions": []}

    pref_date = outbound_leg.preferred_date
    cabin = outbound_leg.cabin_class or "economy"
    origin = outbound_leg.origin_airport
    destination = outbound_leg.destination_airport
    airline_codes = set(req.airline_codes)

    # Query 3 months: prev, current, next
    months_to_check = []
    for offset in [-1, 0, 1, 2]:
        m = pref_date.month + offset
        y = pref_date.year
        if m < 1:
            m += 12
            y -= 1
        elif m > 12:
            m -= 12
            y += 1
        months_to_check.append((y, m))

    # Fetch matrix data for each month (per-airline per-date)
    import asyncio
    month_tasks = [
        db1b_client.search_month_matrix(origin, destination, y, m, cabin)
        for y, m in months_to_check
    ]
    month_results = await asyncio.gather(*month_tasks, return_exceptions=True)

    # Compute per-month average for selected airline(s)
    airline_month_prices: dict[tuple[int, int], list[float]] = {}
    for i, (y, m) in enumerate(months_to_check):
        data = month_results[i]
        if isinstance(data, Exception) or not data:
            continue
        for entry in data:
            if entry["airline_code"] in airline_codes:
                airline_month_prices.setdefault((y, m), []).append(entry["price"])

    if not airline_month_prices:
        return {"suggestions": []}

    # Current month average
    current_key = (pref_date.year, pref_date.month)
    current_prices = airline_month_prices.get(current_key, [])
    current_avg = sum(current_prices) / len(current_prices) if current_prices else None

    suggestions = []
    for (y, m), prices in sorted(airline_month_prices.items()):
        if (y, m) == current_key:
            continue
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)

        if current_avg and avg_price < current_avg * 0.8:  # 20%+ cheaper
            savings_pct = round((1 - avg_price / current_avg) * 100, 1)
            month_name = date(y, m, 1).strftime("%B %Y")
            suggestions.append({
                "month": month_name,
                "year": y,
                "month_num": m,
                "avg_price": round(avg_price, 2),
                "min_price": round(min_price, 2),
                "current_month_avg": round(current_avg, 2),
                "savings_percent": savings_pct,
                "data_points": len(prices),
            })

    suggestions.sort(key=lambda s: s["savings_percent"], reverse=True)

    return {"suggestions": suggestions[:3]}


@router.post("/{trip_id}/save-analysis-snapshot")
async def save_analysis_snapshot(
    trip_id: uuid.UUID,
    req: AnalysisSnapshotRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist the analysis snapshot (alternatives shown to traveler) on the trip."""
    trip = await _get_user_trip(trip_id, db, user)
    trip.analysis_snapshot = {
        "legs": req.legs,
        "trip_totals": req.trip_totals,
        "trip_window_alternatives": req.trip_window_alternatives,
        "saved_at": datetime.utcnow().isoformat(),
    }
    await db.commit()
    return {"ok": True}
