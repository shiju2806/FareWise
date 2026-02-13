"""Airport search router — autocomplete and nearby airport lookup."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.airport_service import airport_service

router = APIRouter()


@router.get("/search")
async def search_airports(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Search airports by city, IATA code, or airport name."""
    return await airport_service.search_airports(db, q, limit)


@router.get("/nearby/{iata}")
async def get_nearby(
    iata: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get nearby alternative airports for a given IATA code."""
    return await airport_service.get_nearby_airports(db, iata)
