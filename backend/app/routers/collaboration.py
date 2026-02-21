"""Collaboration router — trip overlaps."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.collaboration_service import collaboration_service

router = APIRouter()


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
