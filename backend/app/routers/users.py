from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter()


class TravelPreferencesRequest(BaseModel):
    excluded_airlines: list[str] = []
    preferred_cabin: str | None = None


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.get("/me/preferences")
async def get_travel_preferences(user: User = Depends(get_current_user)):
    """Get the current user's travel preferences."""
    prefs = user.travel_preferences or {}
    return {
        "excluded_airlines": prefs.get("excluded_airlines", []),
        "preferred_cabin": prefs.get("preferred_cabin"),
    }


@router.patch("/me/preferences")
async def update_travel_preferences(
    req: TravelPreferencesRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update the current user's travel preferences (excluded airlines, preferred cabin)."""
    prefs = dict(user.travel_preferences or {})
    prefs["excluded_airlines"] = req.excluded_airlines
    if req.preferred_cabin is not None:
        prefs["preferred_cabin"] = req.preferred_cabin
    user.travel_preferences = prefs
    await db.commit()
    return {
        "excluded_airlines": prefs.get("excluded_airlines", []),
        "preferred_cabin": prefs.get("preferred_cabin"),
    }


@router.get("/me/frequent-routes")
async def get_frequent_routes(user: User = Depends(get_current_user)):
    return {"routes": []}
