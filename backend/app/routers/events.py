"""Events router — event intelligence for destination cities."""

import logging
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.services.event_service import event_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search/{trip_leg_id}")
async def get_leg_events(
    trip_leg_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get events relevant to a trip leg (destination + travel dates)."""
    result = await db.execute(
        select(TripLeg)
        .join(Trip, TripLeg.trip_id == Trip.id)
        .where(TripLeg.id == trip_leg_id, Trip.traveler_id == user.id)
    )
    leg = result.scalar_one_or_none()
    if not leg:
        raise HTTPException(status_code=404, detail="Trip leg not found")

    data = await event_service.get_events_for_leg(
        db=db,
        destination_city=leg.destination_city,
        preferred_date=leg.preferred_date,
        flexibility_days=leg.flexibility_days,
    )

    return {
        "trip_leg_id": str(leg.id),
        "destination": leg.destination_city,
        "preferred_date": leg.preferred_date.isoformat(),
        **data,
    }


@router.get("/{city}")
async def get_city_events(
    city: str,
    date_from: date = Query(..., description="Start date (YYYY-MM-DD)"),
    date_to: date = Query(..., description="End date (YYYY-MM-DD)"),
    min_rank: int = Query(None, description="Minimum event rank"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get events for a city within a date range."""
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")

    events = await event_service.get_events(
        db=db,
        city=city,
        date_from=date_from,
        date_to=date_to,
        min_rank=min_rank,
    )

    # Summary
    highest = max(events, key=lambda e: e["rank"]) if events else None
    peak_dates: dict[str, int] = {}
    for evt in events:
        s = date.fromisoformat(evt["start_date"])
        e = date.fromisoformat(evt["end_date"])
        d = s
        while d <= e:
            ds = d.isoformat()
            peak_dates[ds] = peak_dates.get(ds, 0) + 1
            d += timedelta(days=1)

    top_dates = sorted(peak_dates.keys(), key=lambda d: peak_dates[d], reverse=True)[:5]

    return {
        "city": city,
        "date_range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "events": events,
        "summary": {
            "total_events": len(events),
            "highest_impact_event": highest["title"] if highest else None,
            "highest_impact_rank": highest["rank"] if highest else None,
            "peak_impact_dates": top_dates,
        },
    }
