"""Collaboration service — overlap detection."""

import logging
import uuid
from datetime import date

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import TripOverlap
from app.models.trip import Trip, TripLeg
from app.models.user import User

logger = logging.getLogger(__name__)


class CollaborationService:
    """Detects trip overlaps between travelers."""

    # ─── Overlap Detection ───

    async def detect_overlaps(self, db: AsyncSession, trip: Trip) -> list[TripOverlap]:
        """Detect overlaps between this trip and others from different users."""
        from sqlalchemy.orm import selectinload

        legs = trip.legs
        if not legs:
            result = await db.execute(
                select(Trip).where(Trip.id == trip.id).options(selectinload(Trip.legs))
            )
            trip = result.scalar_one()
            legs = trip.legs

        new_overlaps = []
        for leg in legs:
            dest_city = leg.destination_city
            trip_date = leg.preferred_date
            flex = leg.flexibility_days or 3

            # Find other trips with legs going to the same city in overlapping dates
            other_legs = await db.execute(
                select(TripLeg)
                .join(Trip, Trip.id == TripLeg.trip_id)
                .where(
                    and_(
                        TripLeg.destination_city == dest_city,
                        Trip.traveler_id != trip.traveler_id,
                        Trip.status.in_(["submitted", "approved"]),
                        TripLeg.preferred_date.between(
                            date.fromordinal(trip_date.toordinal() - flex),
                            date.fromordinal(trip_date.toordinal() + flex),
                        ),
                    )
                )
            )

            for other_leg in other_legs.scalars().all():
                other_trip_id = other_leg.trip_id

                # Skip if already detected
                existing = await db.execute(
                    select(TripOverlap).where(
                        or_(
                            and_(
                                TripOverlap.trip_a_id == trip.id,
                                TripOverlap.trip_b_id == other_trip_id,
                            ),
                            and_(
                                TripOverlap.trip_a_id == other_trip_id,
                                TripOverlap.trip_b_id == trip.id,
                            ),
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Compute overlap dates
                overlap_start = max(
                    date.fromordinal(trip_date.toordinal() - flex),
                    date.fromordinal(other_leg.preferred_date.toordinal() - (other_leg.flexibility_days or 3)),
                )
                overlap_end = min(
                    date.fromordinal(trip_date.toordinal() + flex),
                    date.fromordinal(other_leg.preferred_date.toordinal() + (other_leg.flexibility_days or 3)),
                )
                overlap_days = (overlap_end - overlap_start).days + 1

                if overlap_days > 0:
                    overlap = TripOverlap(
                        trip_a_id=trip.id,
                        trip_b_id=other_trip_id,
                        overlap_city=dest_city,
                        overlap_start=overlap_start,
                        overlap_end=overlap_end,
                        overlap_days=overlap_days,
                    )
                    db.add(overlap)
                    new_overlaps.append(overlap)

        if new_overlaps:
            await db.flush()
            logger.info(f"Detected {len(new_overlaps)} overlaps for trip {trip.id}")

        return new_overlaps

    async def get_trip_overlaps(self, db: AsyncSession, trip_id: uuid.UUID) -> list[dict]:
        """Get all overlaps for a trip."""
        result = await db.execute(
            select(TripOverlap).where(
                or_(
                    TripOverlap.trip_a_id == trip_id,
                    TripOverlap.trip_b_id == trip_id,
                )
            )
        )
        overlaps = result.scalars().all()

        enriched = []
        for o in overlaps:
            other_trip_id = o.trip_b_id if o.trip_a_id == trip_id else o.trip_a_id
            is_a = o.trip_a_id == trip_id

            # Get other trip details
            from sqlalchemy.orm import selectinload

            other_trip = await db.execute(
                select(Trip).where(Trip.id == other_trip_id).options(selectinload(Trip.legs))
            )
            other = other_trip.scalar_one_or_none()
            if not other:
                continue

            # Get traveler name
            traveler = await db.execute(select(User).where(User.id == other.traveler_id))
            trav = traveler.scalar_one_or_none()

            enriched.append({
                "id": str(o.id),
                "overlap_city": o.overlap_city,
                "overlap_start": o.overlap_start.isoformat(),
                "overlap_end": o.overlap_end.isoformat(),
                "overlap_days": o.overlap_days,
                "dismissed": o.dismissed_by_a if is_a else o.dismissed_by_b,
                "other_trip": {
                    "id": str(other.id),
                    "title": other.title or "Untitled",
                    "traveler": f"{trav.first_name} {trav.last_name}" if trav else "Unknown",
                    "department": trav.department if trav else None,
                },
            })

        return enriched

    async def dismiss_overlap(
        self, db: AsyncSession, overlap_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Dismiss an overlap for the given user."""
        result = await db.execute(select(TripOverlap).where(TripOverlap.id == overlap_id))
        overlap = result.scalar_one_or_none()
        if not overlap:
            return False

        # Determine which side the user is on
        trip_a = await db.execute(select(Trip).where(Trip.id == overlap.trip_a_id))
        trip_a_obj = trip_a.scalar_one_or_none()
        trip_b = await db.execute(select(Trip).where(Trip.id == overlap.trip_b_id))
        trip_b_obj = trip_b.scalar_one_or_none()

        if trip_a_obj and trip_a_obj.traveler_id == user_id:
            overlap.dismissed_by_a = True
        elif trip_b_obj and trip_b_obj.traveler_id == user_id:
            overlap.dismissed_by_b = True
        else:
            return False

        await db.commit()
        return True


collaboration_service = CollaborationService()
