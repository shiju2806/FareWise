"""Search router — flight search, date options, re-scoring, and price intelligence."""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user
from app.models.policy import Selection
from app.models.search_log import FlightOption, SearchLog
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.schemas.search import ScoreRequest, SearchRequest
from app.services.scoring_engine import Weights, slider_to_weights
from app.services.search_orchestrator import search_orchestrator


class SelectionRequest(BaseModel):
    flight_option_id: str
    slider_position: float | None = None

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_user_leg(
    trip_leg_id: uuid.UUID,
    db: AsyncSession,
    user: User,
) -> TripLeg:
    """Fetch a trip leg ensuring it belongs to the current user."""
    result = await db.execute(
        select(TripLeg)
        .join(Trip, TripLeg.trip_id == Trip.id)
        .where(TripLeg.id == trip_leg_id, Trip.traveler_id == user.id)
    )
    leg = result.scalar_one_or_none()
    if not leg:
        raise HTTPException(status_code=404, detail="Trip leg not found")
    return leg


@router.post("/{trip_leg_id}")
async def search_flights(
    trip_leg_id: uuid.UUID,
    req: SearchRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Execute full search for a trip leg across dates and airports."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    # Override flexibility if provided
    if req and req.flexibility_days is not None:
        leg.flexibility_days = req.flexibility_days

    include_nearby = req.include_nearby_airports if req else True

    try:
        result = await search_orchestrator.search_leg(
            db=db,
            leg=leg,
            include_nearby=include_nearby,
        )
    except Exception as e:
        logger.error(f"Search orchestrator failed for leg {trip_leg_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    # Update trip status to searching
    try:
        trip_result = await db.execute(select(Trip).where(Trip.id == leg.trip_id))
        trip = trip_result.scalar_one_or_none()
        if trip and trip.status == "draft":
            trip.status = "searching"
            await db.commit()
    except Exception:
        pass  # Don't fail the search over a status update

    return result


@router.get("/{trip_leg_id}/options")
async def get_flight_options(
    trip_leg_id: uuid.UUID,
    date: str | None = Query(None, description="Filter by date (YYYY-MM-DD)"),
    sort: str = Query("price", description="Sort by: price, duration, departure"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get flight options for a specific date from the most recent search."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    if date:
        try:
            from datetime import date as date_type
            parts = date.split("-")
            target_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        target_date = leg.preferred_date

    options = await search_orchestrator.get_options_for_date(
        db=db, leg=leg, target_date=target_date, sort_by=sort
    )

    return {"date": target_date.isoformat(), "options": options, "count": len(options)}


@router.post("/{trip_leg_id}/score")
async def rescore_flights(
    trip_leg_id: uuid.UUID,
    req: ScoreRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recalculate scores based on weight preferences (from slider)."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    weights = Weights(
        cost=req.cost_weight,
        time=req.time_weight,
        stops=req.stops_weight,
        departure=req.departure_weight,
    )

    result = await search_orchestrator.rescore_leg(
        db=db, leg=leg, weights=weights
    )

    return result


@router.post("/{trip_leg_id}/slider")
async def slider_rescore(
    trip_leg_id: uuid.UUID,
    slider_position: float = Query(..., ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Rescore based on slider position (0=cheapest, 100=convenient)."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    weights = slider_to_weights(slider_position)

    result = await search_orchestrator.rescore_leg(
        db=db, leg=leg, weights=weights
    )

    return result


@router.post("/{trip_leg_id}/select")
async def select_flight(
    trip_leg_id: uuid.UUID,
    req: SelectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save a flight selection for a trip leg."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    # Verify the flight option exists
    result = await db.execute(
        select(FlightOption).where(FlightOption.id == uuid.UUID(req.flight_option_id))
    )
    flight_option = result.scalar_one_or_none()
    if not flight_option:
        raise HTTPException(status_code=404, detail="Flight option not found")

    # Remove any existing selection for this leg
    existing = await db.execute(
        select(Selection).where(Selection.trip_leg_id == leg.id)
    )
    for old in existing.scalars().all():
        await db.delete(old)

    # Create new selection
    from decimal import Decimal
    selection = Selection(
        trip_leg_id=leg.id,
        flight_option_id=flight_option.id,
        slider_position=Decimal(str(round(req.slider_position / 100, 2))) if req.slider_position is not None else None,
    )
    db.add(selection)
    await db.commit()

    return {
        "id": str(selection.id),
        "trip_leg_id": str(leg.id),
        "flight_option_id": str(flight_option.id),
        "airline": flight_option.airline_name,
        "flight_numbers": flight_option.flight_numbers,
        "price": float(flight_option.price),
        "selected_at": selection.selected_at.isoformat() if selection.selected_at else None,
    }


@router.get("/{trip_leg_id}/calendar")
async def get_month_calendar(
    trip_leg_id: uuid.UUID,
    year: int = Query(..., ge=2024, le=2028),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get price calendar for an entire month.

    Merges already-fetched dates from the initial search with
    lazy-loaded prices for the remaining days.
    """
    leg = await _get_user_leg(trip_leg_id, db, user)

    # Get existing search data to avoid re-fetching already-known dates
    existing_dates = {}
    result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = result.scalar_one_or_none()

    if search_log:
        # Pull existing prices from search_log's flight options
        result = await db.execute(
            select(FlightOption).where(FlightOption.search_log_id == search_log.id)
        )
        options = result.scalars().all()

        from collections import defaultdict
        by_date: dict[str, list] = defaultdict(list)
        for opt in options:
            if opt.departure_time:
                d = opt.departure_time.date().isoformat()
                by_date[d].append(opt)

        for d, opts in by_date.items():
            # Only include dates that fall in the requested month
            if d.startswith(f"{year}-{month:02d}"):
                prices = [float(o.price) for o in opts if o.price]
                has_direct = any(o.stops == 0 for o in opts)
                if prices:
                    existing_dates[d] = {
                        "min_price": round(min(prices), 2),
                        "has_direct": has_direct,
                        "option_count": len(prices),
                    }

    try:
        month_data = await search_orchestrator.fetch_month_prices(
            origin=leg.origin_airport,
            destination=leg.destination_airport,
            year=year,
            month=month,
            cabin_class=leg.cabin_class,
            existing_dates=existing_dates,
        )
    except Exception as e:
        logger.error(f"Month calendar fetch failed: {e}")
        # Return whatever we have from existing search
        month_data = {"dates": existing_dates, "month_stats": {}}

    return month_data


@router.get("/{trip_leg_id}/advisor")
async def get_price_advice(
    trip_leg_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get LLM-powered price intelligence advice for a trip leg.

    Uses the most recent search results for this leg.
    Returns book/wait/watch recommendation with analysis.
    """
    from app.services.price_advisor_service import price_advisor

    leg = await _get_user_leg(trip_leg_id, db, user)

    # Get most recent search
    result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = result.scalar_one_or_none()

    if not search_log:
        raise HTTPException(
            status_code=404,
            detail="No search results found. Run a search first.",
        )

    # Get flight options from the search
    result = await db.execute(
        select(FlightOption).where(FlightOption.search_log_id == search_log.id)
    )
    options = result.scalars().all()

    flights = [
        {
            "price": float(opt.price),
            "stops": opt.stops,
            "duration_minutes": opt.duration_minutes,
            "airline_name": opt.airline_name,
            "seats_remaining": opt.seats_remaining,
            "departure_time": opt.departure_time.isoformat() if opt.departure_time else "",
            "cabin_class": opt.cabin_class,
        }
        for opt in options
    ]

    # Get events if available
    events = None
    if search_log.events_during_travel:
        events = search_log.events_during_travel

    # Get trip for city names
    trip_result = await db.execute(select(Trip).where(Trip.id == leg.trip_id))
    trip = trip_result.scalar_one_or_none()

    advice = await price_advisor.get_advice(
        search_id=str(search_log.id),
        origin=leg.origin_airport,
        destination=leg.destination_airport,
        departure_date=leg.preferred_date,
        cabin_class=leg.cabin_class,
        flights=flights,
        events=events,
        origin_city=leg.origin_city,
        destination_city=leg.destination_city,
    )

    return advice


@router.get("/{trip_leg_id}/price-context")
async def get_price_context(
    trip_leg_id: uuid.UUID,
    target_date: str = Query(..., description="Date to check (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get historical price quartiles for a specific date on this route.

    Returns where the current price falls relative to historical data:
    min, Q1, median, Q3, max, and a percentile ranking.
    """
    from app.services.amadeus_client import amadeus_client
    from app.services.cache_service import cache_service

    leg = await _get_user_leg(trip_leg_id, db, user)

    try:
        parts = target_date.split("-")
        parsed_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Check cache first (route-based, not search-based)
    cached = await cache_service.get_price_metrics(
        leg.origin_airport, leg.destination_airport, target_date
    )
    if cached:
        return cached

    # Fetch from Amadeus
    metrics = await amadeus_client.get_price_metrics(
        origin=leg.origin_airport,
        destination=leg.destination_airport,
        departure_date=parsed_date,
    )

    if not metrics:
        result = {"available": False, "message": "Historical price data not available for this route"}
        return result

    # Compute where current cheapest price falls
    current_price = None
    search_result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = search_result.scalar_one_or_none()
    if search_log and search_log.cheapest_price:
        current_price = float(search_log.cheapest_price)

    percentile = None
    percentile_label = None
    if current_price and metrics.get("min") and metrics.get("max"):
        price_range = metrics["max"] - metrics["min"]
        if price_range > 0:
            percentile = round(((current_price - metrics["min"]) / price_range) * 100)
            percentile = max(0, min(100, percentile))
            if percentile <= 25:
                percentile_label = "excellent"
            elif percentile <= 50:
                percentile_label = "good"
            elif percentile <= 75:
                percentile_label = "average"
            else:
                percentile_label = "high"

    response = {
        "available": True,
        "route": f"{leg.origin_airport}-{leg.destination_airport}",
        "date": target_date,
        "historical": metrics,
        "current_price": current_price,
        "percentile": percentile,
        "percentile_label": percentile_label,
    }

    # Cache the result
    await cache_service.set_price_metrics(
        leg.origin_airport, leg.destination_airport, target_date, response
    )

    return response


@router.get("/{trip_leg_id}/price-trend")
async def get_price_trend(
    trip_leg_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get historical price trend for a route from past search logs.

    Returns price data points over time for the same route.
    """
    leg = await _get_user_leg(trip_leg_id, db, user)

    # Get all search logs for this leg, ordered by time
    result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.asc())
    )
    search_logs = result.scalars().all()

    trend_points = []
    for log in search_logs:
        if log.cheapest_price is not None:
            trend_points.append({
                "date": log.searched_at.isoformat() if log.searched_at else "",
                "price": float(log.cheapest_price),
                "most_expensive": float(log.most_expensive_price) if log.most_expensive_price else None,
                "results_count": log.results_count,
            })

    # Also search for the same route across other trip legs (broader history)
    result = await db.execute(
        select(SearchLog)
        .where(
            SearchLog.search_params["origin"].astext == leg.origin_airport,
            SearchLog.search_params["destination"].astext == leg.destination_airport,
            SearchLog.trip_leg_id != leg.id,
        )
        .order_by(SearchLog.searched_at.asc())
        .limit(50)
    )
    other_logs = result.scalars().all()

    route_history = []
    for log in other_logs:
        if log.cheapest_price is not None:
            route_history.append({
                "date": log.searched_at.isoformat() if log.searched_at else "",
                "price": float(log.cheapest_price),
            })

    return {
        "leg_trend": trend_points,
        "route_history": route_history,
        "route": f"{leg.origin_airport} → {leg.destination_airport}",
        "data_points": len(trend_points) + len(route_history),
    }
