"""Bundle optimizer router — flight + hotel combinations."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.services.bundle_optimizer import bundle_optimizer

logger = logging.getLogger(__name__)

router = APIRouter()


class BundleRequest(BaseModel):
    hotel_nights: int = 3
    flexibility_days: int | None = None


@router.post("/{trip_leg_id}/bundle")
async def optimize_bundle(
    trip_leg_id: uuid.UUID,
    req: BundleRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find optimal flight + hotel combination across flexible dates."""
    result = await db.execute(
        select(TripLeg)
        .join(Trip, TripLeg.trip_id == Trip.id)
        .where(TripLeg.id == trip_leg_id, Trip.traveler_id == user.id)
    )
    leg = result.scalar_one_or_none()
    if not leg:
        raise HTTPException(status_code=404, detail="Trip leg not found")

    hotel_nights = req.hotel_nights if req else 3
    flexibility = req.flexibility_days if req else None

    data = await bundle_optimizer.optimize(
        db=db,
        leg=leg,
        hotel_nights=hotel_nights,
        flexibility_days=flexibility,
    )

    return {
        "trip_leg_id": str(leg.id),
        "origin": leg.origin_airport,
        "destination": leg.destination_airport,
        **data,
    }
