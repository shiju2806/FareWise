"""Proactive alert service — generates alerts without user action."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.events import HotelSelection
from app.models.policy import Notification
from app.models.trip import Trip, TripLeg
from app.services.event_service import event_service

logger = logging.getLogger(__name__)


class ProactiveAlertService:
    """Generates proactive alerts for upcoming trips."""

    async def check_unbooked_hotels(self, db: AsyncSession) -> int:
        """Alert travelers with trips within 14 days that have no hotel booking."""
        today = date.today()
        cutoff = today + timedelta(days=14)

        # Find trip legs with preferred_date within 14 days
        result = await db.execute(
            select(TripLeg)
            .join(Trip, TripLeg.trip_id == Trip.id)
            .where(
                TripLeg.preferred_date >= today,
                TripLeg.preferred_date <= cutoff,
                Trip.status.in_(["searching", "draft"]),
            )
        )
        legs = result.scalars().all()

        alert_count = 0
        for leg in legs:
            # Check if hotel already selected
            sel_result = await db.execute(
                select(HotelSelection).where(HotelSelection.trip_leg_id == leg.id)
            )
            if sel_result.scalar_one_or_none():
                continue

            # Check for existing notification (avoid duplicates)
            existing = await db.execute(
                select(Notification).where(
                    Notification.type == "booking_reminder",
                    Notification.reference_type == "trip_leg",
                    Notification.reference_id == leg.id,
                    Notification.is_read == False,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Get trip for traveler_id
            trip_result = await db.execute(
                select(Trip).where(Trip.id == leg.trip_id)
            )
            trip = trip_result.scalar_one_or_none()
            if not trip:
                continue

            days_until = (leg.preferred_date - today).days
            db.add(Notification(
                user_id=trip.traveler_id,
                type="booking_reminder",
                title="Hotel Booking Reminder",
                body=(
                    f"Your trip to {leg.destination_city} departs in {days_until} days "
                    f"but you haven't booked a hotel yet."
                ),
                reference_type="trip_leg",
                reference_id=leg.id,
            ))
            alert_count += 1

        if alert_count > 0:
            await db.commit()
        return alert_count

    async def check_event_alerts(self, db: AsyncSession) -> int:
        """Alert travelers about high-impact events overlapping upcoming trips."""
        today = date.today()
        cutoff = today + timedelta(days=30)

        result = await db.execute(
            select(TripLeg)
            .join(Trip, TripLeg.trip_id == Trip.id)
            .where(
                TripLeg.preferred_date >= today,
                TripLeg.preferred_date <= cutoff,
                Trip.status.in_(["searching", "draft", "submitted"]),
            )
        )
        legs = result.scalars().all()

        alert_count = 0
        for leg in legs:
            events = await event_service.get_events(
                db,
                leg.destination_city,
                leg.preferred_date - timedelta(days=1),
                leg.preferred_date + timedelta(days=1),
            )

            high_impact = [e for e in events if e["impact_level"] in ("high", "very_high")]
            if not high_impact:
                continue

            # Check for existing notification
            existing = await db.execute(
                select(Notification).where(
                    Notification.type == "event_warning",
                    Notification.reference_type == "trip_leg",
                    Notification.reference_id == leg.id,
                    Notification.is_read == False,
                )
            )
            if existing.scalar_one_or_none():
                continue

            trip_result = await db.execute(
                select(Trip).where(Trip.id == leg.trip_id)
            )
            trip = trip_result.scalar_one_or_none()
            if not trip:
                continue

            event_names = ", ".join(e["title"] for e in high_impact[:2])
            db.add(Notification(
                user_id=trip.traveler_id,
                type="event_warning",
                title="Event Alert",
                body=(
                    f"Major events ({event_names}) overlap your trip to "
                    f"{leg.destination_city} on {leg.preferred_date}. "
                    f"Prices may be elevated."
                ),
                reference_type="trip_leg",
                reference_id=leg.id,
            ))
            alert_count += 1

        if alert_count > 0:
            await db.commit()
        return alert_count


proactive_alert_service = ProactiveAlertService()
