"""Calendar view endpoint for trips."""
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.trip import Trip, TripLeg
from app.models.user import User

router = APIRouter()


class CalendarLeg(BaseModel):
    id: str
    origin: str
    destination: str
    date: str

    model_config = {"from_attributes": True}


class CalendarTrip(BaseModel):
    id: str
    title: str
    status: str
    start_date: str
    end_date: str
    legs: list[CalendarLeg]
    total_estimated_cost: float | None
    currency: str

    model_config = {"from_attributes": True}


class CalendarResponse(BaseModel):
    month: str
    trips: list[CalendarTrip]


@router.get("/calendar", response_model=CalendarResponse)
async def get_calendar(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return trips overlapping with the given month for calendar display."""
    year, mon = int(month[:4]), int(month[5:7])
    first_day = date(year, mon, 1)
    # Last day of month
    if mon == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, mon + 1, 1) - timedelta(days=1)

    # Expand window by 7 days for trips that partially overlap
    window_start = first_day - timedelta(days=7)
    window_end = last_day + timedelta(days=7)

    # Only show trips that have been submitted (not drafts/searching)
    CALENDAR_STATUSES = {"submitted", "approved", "changes_requested", "rejected"}

    result = await db.execute(
        select(Trip)
        .where(Trip.traveler_id == user.id, Trip.status.in_(CALENDAR_STATUSES))
        .options(selectinload(Trip.legs))
        .order_by(Trip.updated_at.desc())
    )
    all_trips = result.scalars().unique().all()

    calendar_trips: list[CalendarTrip] = []
    for trip in all_trips:
        if not trip.legs:
            continue

        leg_dates = [leg.preferred_date for leg in trip.legs]
        start_date = min(leg_dates)
        end_date = max(leg_dates)

        # Single-day trips get +1 day for visual width
        if start_date == end_date:
            end_date = start_date + timedelta(days=1)

        # Check if trip overlaps with our window
        if end_date < window_start or start_date > window_end:
            continue

        calendar_trips.append(
            CalendarTrip(
                id=str(trip.id),
                title=trip.title or "Untitled Trip",
                status=trip.status,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                legs=[
                    CalendarLeg(
                        id=str(leg.id),
                        origin=leg.origin_airport,
                        destination=leg.destination_airport,
                        date=leg.preferred_date.isoformat(),
                    )
                    for leg in sorted(trip.legs, key=lambda l: l.sequence)
                ],
                total_estimated_cost=float(trip.total_estimated_cost) if trip.total_estimated_cost else None,
                currency=trip.currency,
            )
        )

    return CalendarResponse(month=month, trips=calendar_trips)
