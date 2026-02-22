"""Search router — flight search, date options, re-scoring, and price intelligence."""

import asyncio
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal

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


class SyntheticFlightData(BaseModel):
    """Optional flight data for DB1B-sourced synthetic flights that don't exist in the DB yet."""
    airline_code: str
    airline_name: str
    origin_airport: str
    destination_airport: str
    departure_time: str
    arrival_time: str
    duration_minutes: int = 0
    stops: int = 0
    price: float
    currency: str = "USD"
    cabin_class: str | None = None


class SelectionRequest(BaseModel):
    flight_option_id: str
    slider_position: float | None = None
    justification_note: str | None = None
    synthetic_flight: SyntheticFlightData | None = None


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


async def _reset_trip_status(db: AsyncSession, trip_id: uuid.UUID) -> None:
    """Reset trip status to draft on search failure."""
    try:
        await db.rollback()
        trip_result = await db.execute(select(Trip).where(Trip.id == trip_id))
        trip = trip_result.scalar_one_or_none()
        if trip and trip.status == "searching":
            trip.status = "draft"
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to reset trip status for {trip_id}: {e}")


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

    # Load user travel preferences
    user_preferences = None
    if user.travel_preferences and isinstance(user.travel_preferences, dict):
        user_preferences = user.travel_preferences

    # Set trip status to "searching" BEFORE starting the search
    try:
        trip_result = await db.execute(select(Trip).where(Trip.id == leg.trip_id))
        trip = trip_result.scalar_one_or_none()
        if trip and trip.status == "draft":
            trip.status = "searching"
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to set trip status to searching for leg {trip_leg_id}: {e}")

    try:
        result = await asyncio.wait_for(
            search_orchestrator.search_leg(
                db=db,
                leg=leg,
                include_nearby=include_nearby,
                user_preferences=user_preferences,
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Search timed out for leg {trip_leg_id}")
        await _reset_trip_status(db, leg.trip_id)
        raise HTTPException(status_code=504, detail="Search timed out. Please try again.")
    except Exception as e:
        logger.error(f"Search orchestrator failed for leg {trip_leg_id}: {e}")
        await _reset_trip_status(db, leg.trip_id)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

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

    flight_option = None

    # Handle synthetic DB1B flights that don't exist in the DB yet
    if req.flight_option_id.startswith("db1b-") and req.synthetic_flight:
        sf = req.synthetic_flight
        # Create a search log for this DB1B-sourced selection
        search_log = SearchLog(
            trip_leg_id=leg.id,
            api_provider="db1b_historical",
            search_params={"source": "trip_window_alternative", "original_id": req.flight_option_id},
            results_count=1,
            cheapest_price=Decimal(str(round(sf.price, 2))),
            cached=False,
            is_synthetic=True,
        )
        db.add(search_log)
        await db.flush()  # get search_log.id

        dep_time = datetime.fromisoformat(sf.departure_time)
        arr_time = datetime.fromisoformat(sf.arrival_time)
        flight_option = FlightOption(
            search_log_id=search_log.id,
            airline_code=sf.airline_code,
            airline_name=sf.airline_name,
            flight_numbers=sf.airline_code,
            origin_airport=sf.origin_airport,
            destination_airport=sf.destination_airport,
            departure_time=dep_time,
            arrival_time=arr_time,
            duration_minutes=sf.duration_minutes,
            stops=sf.stops,
            price=Decimal(str(round(sf.price, 2))),
            currency=sf.currency,
            cabin_class=sf.cabin_class,
            is_alternate_date=True,
        )
        db.add(flight_option)
        await db.flush()
    else:
        # Standard flow: look up existing flight option
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

    # Update leg preferred_date to match the selected flight's actual departure
    if flight_option.departure_time:
        leg.preferred_date = flight_option.departure_time.date()

    # Create new selection
    selection = Selection(
        trip_leg_id=leg.id,
        flight_option_id=flight_option.id,
        slider_position=Decimal(str(round(req.slider_position / 100, 2))) if req.slider_position is not None else None,
        justification_note=req.justification_note,
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
        "justification_note": selection.justification_note,
        "selected_at": selection.selected_at.isoformat() if selection.selected_at else None,
    }


@router.get("/{trip_leg_id}/matrix")
async def get_month_matrix(
    trip_leg_id: uuid.UUID,
    year: int = Query(..., ge=2024, le=2028),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get airline x date matrix data for an entire month from DB1B.

    Returns per-carrier, per-date entries for the AirlineDateMatrix component.
    Cached for 1 hour.
    """
    from app.services.cache_service import cache_service
    from app.services.db1b_client import db1b_client

    leg = await _get_user_leg(trip_leg_id, db, user)

    cache_key = f"matrix:{leg.origin_airport}:{leg.destination_airport}:{year}-{month:02d}:{leg.cabin_class}"
    cached = await cache_service.get(cache_key)
    if cached is not None:
        return cached

    try:
        entries = await db1b_client.search_month_matrix(
            origin=leg.origin_airport,
            destination=leg.destination_airport,
            year=year,
            month=month,
            cabin_class=leg.cabin_class,
        )
    except Exception as e:
        logger.error(f"Matrix fetch failed: {e}")
        entries = []

    result = {
        "entries": entries,
        "month": f"{year}-{month:02d}",
    }

    if entries:
        await cache_service.set(cache_key, result, ttl=3600)

    return result


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

    # Get events — from stored data or fetch on-demand
    events = None
    if search_log.events_during_travel:
        events = search_log.events_during_travel
    else:
        try:
            from app.services.event_service import event_service
            event_data = await event_service.get_events_for_leg(
                db=db,
                destination_city=leg.destination_city,
                preferred_date=leg.preferred_date,
                flexibility_days=leg.flexibility_days,
            )
            if event_data.get("events"):
                events = event_data["events"]
                # Persist for future calls
                search_log.events_during_travel = events
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to fetch events for advisor: {e}")

    # Get trip context for city names and leg/trip type inference
    trip_result = await db.execute(select(Trip).where(Trip.id == leg.trip_id))
    trip = trip_result.scalar_one_or_none()

    from sqlalchemy import func as sa_func
    leg_count = await db.scalar(
        select(sa_func.count()).select_from(TripLeg).where(TripLeg.trip_id == leg.trip_id)
    )
    trip_type = "round_trip" if leg_count >= 2 else "one_way"
    leg_type = "one_way" if trip_type == "one_way" else ("outbound" if leg.sequence == 0 else "return")

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
        trip_type=trip_type,
        leg_label=leg_type,
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

    # Check cache first (route + cabin specific)
    cached = await cache_service.get_price_metrics(
        leg.origin_airport, leg.destination_airport, target_date, leg.cabin_class
    )
    if cached:
        return cached

    # Get current cheapest price from most recent search
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

    # Primary: DB1B historical data — compute quartiles from real fare data
    from app.services.db1b_client import db1b_client

    response = None
    try:
        db1b_context = await db1b_client.get_price_context(
            origin=leg.origin_airport,
            destination=leg.destination_airport,
            departure_date=parsed_date,
            cabin_class=leg.cabin_class,
            current_price=current_price,
        )
        if db1b_context:
            response = db1b_context
    except Exception as e:
        logger.warning(f"DB1B price context failed: {e}")

    # Fallback: Amadeus price metrics
    if not response:
        try:
            metrics = await amadeus_client.get_price_metrics(
                origin=leg.origin_airport,
                destination=leg.destination_airport,
                departure_date=parsed_date,
            )
            if metrics:
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
        except Exception as e:
            logger.warning(f"Amadeus price metrics failed: {e}")

    if not response:
        return {"available": False, "message": "Price data not available for this route"}

    # Cache the result (cabin-class specific)
    await cache_service.set_price_metrics(
        leg.origin_airport, leg.destination_airport, target_date, leg.cabin_class, response
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

    # Also search for the same route across this user's other trip legs (broader history)
    result = await db.execute(
        select(SearchLog)
        .join(TripLeg, SearchLog.trip_leg_id == TripLeg.id)
        .join(Trip, TripLeg.trip_id == Trip.id)
        .where(
            Trip.traveler_id == user.id,
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
