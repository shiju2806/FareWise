"""Collaboration service — overlap detection, group trips, coordination tips."""

import logging
import uuid
from datetime import date

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collaboration import GroupTrip, GroupTripMember, TripOverlap
from app.models.trip import Trip, TripLeg
from app.models.user import User

logger = logging.getLogger(__name__)


class CollaborationService:
    """Detects trip overlaps and manages group trips."""

    # ─── Overlap Detection ───

    async def detect_overlaps(self, db: AsyncSession, trip: Trip) -> list[TripOverlap]:
        """Detect overlaps between this trip and others from different users."""
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

    # ─── Group Trips ───

    async def create_group_trip(
        self, db: AsyncSession, organizer_id: uuid.UUID,
        name: str, destination_city: str, start_date: date, end_date: date,
        notes: str | None = None, member_emails: list[str] | None = None,
    ) -> GroupTrip:
        """Create a group trip and invite members."""
        group = GroupTrip(
            name=name,
            organizer_id=organizer_id,
            destination_city=destination_city,
            start_date=start_date,
            end_date=end_date,
            notes=notes,
        )
        db.add(group)
        await db.flush()

        # Add organizer as member
        db.add(GroupTripMember(
            group_trip_id=group.id,
            user_id=organizer_id,
            role="organizer",
            status="accepted",
        ))

        # Invite members by email
        if member_emails:
            for email in member_emails:
                user_result = await db.execute(
                    select(User).where(User.email == email)
                )
                user = user_result.scalar_one_or_none()
                if user and user.id != organizer_id:
                    db.add(GroupTripMember(
                        group_trip_id=group.id,
                        user_id=user.id,
                        role="member",
                        status="invited",
                    ))

        await db.commit()
        await db.refresh(group)
        logger.info(f"Created group trip '{name}' by user {organizer_id}")
        return group

    async def get_user_group_trips(self, db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
        """Get all group trips the user is part of."""
        result = await db.execute(
            select(GroupTrip, GroupTripMember.role, GroupTripMember.status)
            .join(GroupTripMember, GroupTripMember.group_trip_id == GroupTrip.id)
            .where(GroupTripMember.user_id == user_id)
            .order_by(GroupTrip.start_date)
        )

        trips = []
        for gt, role, status in result.all():
            # Count members
            members_result = await db.execute(
                select(GroupTripMember).where(
                    GroupTripMember.group_trip_id == gt.id
                )
            )
            members = members_result.scalars().all()

            organizer = await db.execute(select(User).where(User.id == gt.organizer_id))
            org = organizer.scalar_one_or_none()

            trips.append({
                "id": str(gt.id),
                "name": gt.name,
                "destination_city": gt.destination_city,
                "start_date": gt.start_date.isoformat(),
                "end_date": gt.end_date.isoformat(),
                "status": gt.status,
                "notes": gt.notes,
                "my_role": role,
                "my_status": status,
                "organizer": f"{org.first_name} {org.last_name}" if org else "Unknown",
                "member_count": len(members),
                "accepted_count": sum(1 for m in members if m.status == "accepted"),
            })

        return trips

    async def get_group_trip_detail(
        self, db: AsyncSession, group_id: uuid.UUID
    ) -> dict | None:
        """Get detailed group trip info with members."""
        result = await db.execute(
            select(GroupTrip).where(GroupTrip.id == group_id)
        )
        gt = result.scalar_one_or_none()
        if not gt:
            return None

        # Get members with user info
        members_result = await db.execute(
            select(GroupTripMember, User.first_name, User.last_name, User.email, User.department)
            .join(User, User.id == GroupTripMember.user_id)
            .where(GroupTripMember.group_trip_id == group_id)
        )

        members = [
            {
                "id": str(m.id),
                "user_id": str(m.user_id),
                "name": f"{fname} {lname}",
                "email": email,
                "department": dept,
                "role": m.role,
                "status": m.status,
                "trip_id": str(m.trip_id) if m.trip_id else None,
            }
            for m, fname, lname, email, dept in members_result.all()
        ]

        organizer = await db.execute(select(User).where(User.id == gt.organizer_id))
        org = organizer.scalar_one_or_none()

        # Coordination tips
        tips = await self._generate_coordination_tips(db, gt, members)

        return {
            "id": str(gt.id),
            "name": gt.name,
            "destination_city": gt.destination_city,
            "start_date": gt.start_date.isoformat(),
            "end_date": gt.end_date.isoformat(),
            "status": gt.status,
            "notes": gt.notes,
            "organizer": f"{org.first_name} {org.last_name}" if org else "Unknown",
            "members": members,
            "coordination_tips": tips,
        }

    async def respond_to_invite(
        self, db: AsyncSession, group_id: uuid.UUID, user_id: uuid.UUID, accept: bool
    ) -> bool:
        """Accept or decline a group trip invitation."""
        result = await db.execute(
            select(GroupTripMember).where(
                and_(
                    GroupTripMember.group_trip_id == group_id,
                    GroupTripMember.user_id == user_id,
                )
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False

        member.status = "accepted" if accept else "declined"
        await db.commit()
        return True

    async def _generate_coordination_tips(
        self, db: AsyncSession, group: GroupTrip, members: list[dict]
    ) -> list[str]:
        """Generate smart tips for group coordination."""
        tips = []
        accepted = [m for m in members if m["status"] == "accepted"]

        if len(accepted) >= 2:
            tips.append(
                f"{len(accepted)} travelers heading to {group.destination_city} — "
                f"consider booking the same flights for group seating."
            )

        # Check if anyone has linked a trip
        linked = [m for m in members if m.get("trip_id")]
        if linked and len(linked) < len(accepted):
            tips.append(
                f"{len(linked)} of {len(accepted)} members have linked trips. "
                f"Others should create their trip for better coordination."
            )

        # Date range tip
        days = (group.end_date - group.start_date).days
        if days >= 5:
            tips.append(
                f"{days}-day trip — ask your admin about group hotel rates for extended stays."
            )

        # Departments
        depts = set(m.get("department") for m in accepted if m.get("department"))
        if len(depts) > 1:
            tips.append(
                f"Cross-department trip ({', '.join(depts)}) — "
                f"may qualify for conference or team-building policy exemptions."
            )

        return tips


collaboration_service = CollaborationService()
