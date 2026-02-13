"""Hotel search router — hotel search, selection, and pricing."""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.services.hotel_service import hotel_service

logger = logging.getLogger(__name__)

router = APIRouter()


class HotelSearchRequest(BaseModel):
    check_in: date
    check_out: date
    guests: int = 1
    max_nightly_rate: float | None = None
    max_stars: float | None = None
    sort_by: str = "value"


class HotelSelectRequest(BaseModel):
    hotel_option_id: str
    check_in: date
    check_out: date
    justification_note: str | None = None


async def _get_user_leg(
    trip_leg_id: uuid.UUID, db: AsyncSession, user: User
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


@router.post("/{trip_leg_id}/hotels")
async def search_hotels(
    trip_leg_id: uuid.UUID,
    req: HotelSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search hotels for a trip leg."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    if req.check_in >= req.check_out:
        raise HTTPException(status_code=400, detail="check_in must be before check_out")

    result = await hotel_service.search_hotels(
        db=db,
        leg=leg,
        check_in=req.check_in,
        check_out=req.check_out,
        guests=req.guests,
        max_nightly_rate=req.max_nightly_rate,
        max_stars=req.max_stars,
        sort_by=req.sort_by,
    )

    return result


@router.post("/{trip_leg_id}/hotels/select")
async def select_hotel(
    trip_leg_id: uuid.UUID,
    req: HotelSelectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Select a hotel for a trip leg."""
    leg = await _get_user_leg(trip_leg_id, db, user)

    try:
        result = await hotel_service.select_hotel(
            db=db,
            leg=leg,
            hotel_option_id=req.hotel_option_id,
            check_in=req.check_in,
            check_out=req.check_out,
            justification_note=req.justification_note,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
