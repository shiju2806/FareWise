"""Search router — flight search, date options, and re-scoring."""

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
from app.models.search_log import FlightOption
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
