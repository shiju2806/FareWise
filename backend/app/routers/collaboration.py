"""Collaboration router — trip overlaps and group trips."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.collaboration_service import collaboration_service

router = APIRouter()


class GroupTripCreate(BaseModel):
    name: str
    destination_city: str
    start_date: date
    end_date: date
    notes: str | None = None
    member_emails: list[str] | None = None


# ─── Overlaps ───

@router.get("/trips/{trip_id}/overlaps")
async def get_overlaps(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get trip overlaps for a specific trip."""
    return await collaboration_service.get_trip_overlaps(db, trip_id)


@router.post("/overlaps/{overlap_id}/dismiss")
async def dismiss_overlap(
    overlap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dismiss an overlap notification."""
    success = await collaboration_service.dismiss_overlap(db, overlap_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Overlap not found or not yours")
    return {"status": "dismissed"}


# ─── Group Trips ───

@router.post("/group-trips")
async def create_group_trip(
    body: GroupTripCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new group trip."""
    gt = await collaboration_service.create_group_trip(
        db,
        organizer_id=user.id,
        name=body.name,
        destination_city=body.destination_city,
        start_date=body.start_date,
        end_date=body.end_date,
        notes=body.notes,
        member_emails=body.member_emails,
    )
    return {"id": str(gt.id), "name": gt.name, "status": gt.status}


@router.get("/group-trips")
async def list_group_trips(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List group trips the user belongs to."""
    return await collaboration_service.get_user_group_trips(db, user.id)


@router.get("/group-trips/{group_id}")
async def get_group_trip(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get detailed group trip info."""
    detail = await collaboration_service.get_group_trip_detail(db, group_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Group trip not found")
    return detail


@router.post("/group-trips/{group_id}/accept")
async def accept_invite(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept a group trip invitation."""
    success = await collaboration_service.respond_to_invite(db, group_id, user.id, accept=True)
    if not success:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return {"status": "accepted"}


@router.post("/group-trips/{group_id}/decline")
async def decline_invite(
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Decline a group trip invitation."""
    success = await collaboration_service.respond_to_invite(db, group_id, user.id, accept=False)
    if not success:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return {"status": "declined"}
