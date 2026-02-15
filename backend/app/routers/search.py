"""Search router — flight search, date options, re-scoring, and price intelligence."""

import asyncio
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
    justification_note: str | None = None


class AnalyzeSelectionRequest(BaseModel):
    flight_option_id: str

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
        result = await asyncio.wait_for(
            search_orchestrator.search_leg(
                db=db,
                leg=leg,
                include_nearby=include_nearby,
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        logger.error(f"Search timed out for leg {trip_leg_id}")
        raise HTTPException(status_code=504, detail="Search timed out. Please try again.")
    except Exception as e:
        logger.error(f"Search orchestrator failed for leg {trip_leg_id}: {e}")
        # Reset trip status on failure
        try:
            trip_result = await db.execute(select(Trip).where(Trip.id == leg.trip_id))
            trip = trip_result.scalar_one_or_none()
            if trip and trip.status == "searching":
                trip.status = "draft"
                await db.commit()
        except Exception:
            pass
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


@router.post("/{trip_leg_id}/analyze-selection")
async def analyze_selection(
    trip_leg_id: uuid.UUID,
    req: AnalyzeSelectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Analyze a flight selection against alternatives to determine if justification is needed.

    Compares the selected flight against:
    - Cheapest on same date (different airline)
    - Cheapest across all dates
    - Cheapest on different date, same airline
    Returns savings analysis and LLM-generated justification prompt if threshold exceeded.
    """
    from app.services.justification_service import justification_service

    leg = await _get_user_leg(trip_leg_id, db, user)

    # Get the selected flight
    result = await db.execute(
        select(FlightOption).where(FlightOption.id == uuid.UUID(req.flight_option_id))
    )
    selected = result.scalar_one_or_none()
    if not selected:
        raise HTTPException(status_code=404, detail="Flight option not found")

    # Get all options from the most recent search
    search_result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = search_result.scalar_one_or_none()
    if not search_log:
        return {"justification_required": False, "reason": "no_search_data"}

    opts_result = await db.execute(
        select(FlightOption).where(FlightOption.search_log_id == search_log.id)
    )
    all_options = opts_result.scalars().all()

    # Get user's excluded airlines
    excluded_airlines: set[str] = set()
    if user.travel_preferences and isinstance(user.travel_preferences, dict):
        excluded_airlines = set(user.travel_preferences.get("excluded_airlines", []))

    # Filter to allowed airlines only
    allowed_options = [
        o for o in all_options
        if o.airline_name not in excluded_airlines
    ]

    if not allowed_options:
        return {"justification_required": False, "reason": "no_alternatives"}

    selected_date = selected.departure_time.date().isoformat() if selected.departure_time else ""
    selected_price = float(selected.price)

    # Find cheapest overall (among allowed airlines)
    overall_cheapest = min(allowed_options, key=lambda o: float(o.price))
    overall_cheapest_price = float(overall_cheapest.price)

    # Find cheapest on same date (different airline)
    same_date_options = [
        o for o in allowed_options
        if o.departure_time and o.departure_time.date().isoformat() == selected_date
        and o.airline_name != selected.airline_name
    ]
    cheapest_same_date = min(same_date_options, key=lambda o: float(o.price)) if same_date_options else None

    # Find cheapest any date (already computed as overall_cheapest)
    cheapest_any_date_info = None
    if overall_cheapest.id != selected.id:
        cheapest_any_date_info = {
            "airline": overall_cheapest.airline_name,
            "date": overall_cheapest.departure_time.date().isoformat() if overall_cheapest.departure_time else "",
            "price": overall_cheapest_price,
            "savings": round(selected_price - overall_cheapest_price, 2),
            "stops": overall_cheapest.stops,
            "duration_minutes": overall_cheapest.duration_minutes,
            "flight_option_id": str(overall_cheapest.id),
        }

    # Find cheapest same airline, different date
    same_airline_options = [
        o for o in allowed_options
        if o.airline_name == selected.airline_name
        and o.departure_time
        and o.departure_time.date().isoformat() != selected_date
        and float(o.price) < selected_price
    ]
    cheapest_same_airline = min(same_airline_options, key=lambda o: float(o.price)) if same_airline_options else None

    # Calculate max savings
    savings_amount = round(selected_price - overall_cheapest_price, 2)
    savings_percent = round((savings_amount / selected_price) * 100, 1) if selected_price > 0 else 0

    # Threshold: justification required if savings >= $100 or >= 10%
    justification_required = savings_amount >= 100 or savings_percent >= 10

    # Build alternatives list for response
    alternatives = []

    if cheapest_same_date:
        sd_price = float(cheapest_same_date.price)
        alternatives.append({
            "type": "same_date",
            "label": "Same date, different airline",
            "airline": cheapest_same_date.airline_name,
            "date": selected_date,
            "price": sd_price,
            "savings": round(selected_price - sd_price, 2),
            "stops": cheapest_same_date.stops,
            "duration_minutes": cheapest_same_date.duration_minutes,
            "flight_option_id": str(cheapest_same_date.id),
        })

    if cheapest_any_date_info and (
        not cheapest_same_date or overall_cheapest.id != cheapest_same_date.id
    ):
        alternatives.append({
            "type": "any_date",
            "label": "Different date",
            **cheapest_any_date_info,
        })

    if cheapest_same_airline:
        sa_price = float(cheapest_same_airline.price)
        alternatives.append({
            "type": "same_airline",
            "label": f"Same airline ({selected.airline_name}), different date",
            "airline": selected.airline_name,
            "date": cheapest_same_airline.departure_time.date().isoformat() if cheapest_same_airline.departure_time else "",
            "price": sa_price,
            "savings": round(selected_price - sa_price, 2),
            "stops": cheapest_same_airline.stops,
            "duration_minutes": cheapest_same_airline.duration_minutes,
            "flight_option_id": str(cheapest_same_airline.id),
        })

    # Generate LLM justification prompt if needed
    justification_prompt = None
    if justification_required:
        route = f"{leg.origin_airport} → {leg.destination_airport}"
        selected_info = {
            "airline": selected.airline_name,
            "date": selected_date,
            "price": selected_price,
            "stops": selected.stops,
            "duration_minutes": selected.duration_minutes,
        }
        same_date_info = {
            "airline": cheapest_same_date.airline_name,
            "price": float(cheapest_same_date.price),
            "savings": round(selected_price - float(cheapest_same_date.price), 2),
        } if cheapest_same_date else None

        same_airline_info = {
            "date": cheapest_same_airline.departure_time.date().isoformat() if cheapest_same_airline.departure_time else "",
            "price": float(cheapest_same_airline.price),
            "savings": round(selected_price - float(cheapest_same_airline.price), 2),
        } if cheapest_same_airline else None

        overall_info = {
            "airline": overall_cheapest.airline_name,
            "date": overall_cheapest.departure_time.date().isoformat() if overall_cheapest.departure_time else "",
            "price": overall_cheapest_price,
        }

        justification_prompt = await justification_service.generate_prompt(
            selected_flight=selected_info,
            cheapest_same_date=same_date_info,
            cheapest_any_date=cheapest_any_date_info,
            cheapest_same_airline=same_airline_info,
            overall_cheapest=overall_info,
            savings_amount=savings_amount,
            savings_percent=savings_percent,
            route=route,
        )

    return {
        "justification_required": justification_required,
        "selected": {
            "airline": selected.airline_name,
            "date": selected_date,
            "price": selected_price,
            "stops": selected.stops,
            "duration_minutes": selected.duration_minutes,
            "flight_option_id": str(selected.id),
        },
        "savings": {
            "amount": savings_amount,
            "percent": savings_percent,
        },
        "alternatives": alternatives,
        "justification_prompt": justification_prompt,
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

    # Primary: Google Flights — compute real quartiles from flight results
    from app.services import google_flights_client

    response = None
    try:
        gf_context = await google_flights_client.get_price_context(
            origin=leg.origin_airport,
            destination=leg.destination_airport,
            departure_date=parsed_date,
            cabin_class=leg.cabin_class,
            current_price=current_price,
        )
        if gf_context:
            response = gf_context
    except Exception as e:
        logger.warning(f"Google Flights price context failed: {e}")

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
