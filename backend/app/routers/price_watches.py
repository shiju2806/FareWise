"""Price watch and alerts router."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.price_watch_service import price_watch_service

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateWatchRequest(BaseModel):
    watch_type: str = "flight"
    origin: str | None = None
    destination: str | None = None
    target_date: str
    flexibility_days: int = 3
    target_price: float | None = None
    cabin_class: str = "economy"
    current_price: float | None = None


@router.post("/price-watches")
async def create_price_watch(
    req: CreateWatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a price watch."""
    result = await price_watch_service.create_watch(
        db=db,
        user_id=user.id,
        watch_type=req.watch_type,
        origin=req.origin,
        destination=req.destination,
        target_date=req.target_date,
        flexibility_days=req.flexibility_days,
        target_price=req.target_price,
        cabin_class=req.cabin_class,
        current_price=req.current_price,
    )
    return result


@router.get("/price-watches")
async def list_price_watches(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List user's active price watches."""
    watches = await price_watch_service.get_user_watches(db, user.id)
    return {"watches": watches, "count": len(watches)}


@router.delete("/price-watches/{watch_id}")
async def delete_price_watch(
    watch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cancel a price watch."""
    deleted = await price_watch_service.delete_watch(db, watch_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Price watch not found")
    return {"deleted": True}


