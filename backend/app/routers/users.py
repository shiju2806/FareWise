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
    prefer_nonstop: bool = False
    max_stops: int | None = None
    max_layover_minutes: int | None = None
    seat_preference: str | None = None  # window | aisle | no_preference
    preferred_alliances: list[str] = []  # ["star_alliance", "oneworld", "skyteam"]
    prefer_same_tier: bool = False  # suggest similar-quality airlines in alternatives


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
        "prefer_nonstop": prefs.get("prefer_nonstop", False),
        "max_stops": prefs.get("max_stops"),
        "max_layover_minutes": prefs.get("max_layover_minutes"),
        "seat_preference": prefs.get("seat_preference"),
        "preferred_alliances": prefs.get("preferred_alliances", []),
        "prefer_same_tier": prefs.get("prefer_same_tier", False),
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
    prefs["prefer_nonstop"] = req.prefer_nonstop
    if req.max_stops is not None:
        prefs["max_stops"] = req.max_stops
    if req.max_layover_minutes is not None:
        prefs["max_layover_minutes"] = req.max_layover_minutes
    if req.seat_preference is not None:
        prefs["seat_preference"] = req.seat_preference
    prefs["preferred_alliances"] = req.preferred_alliances
    prefs["prefer_same_tier"] = req.prefer_same_tier
    user.travel_preferences = prefs
    await db.commit()
    return {
        "excluded_airlines": prefs.get("excluded_airlines", []),
        "preferred_cabin": prefs.get("preferred_cabin"),
        "prefer_nonstop": prefs.get("prefer_nonstop", False),
        "max_stops": prefs.get("max_stops"),
        "max_layover_minutes": prefs.get("max_layover_minutes"),
        "seat_preference": prefs.get("seat_preference"),
        "preferred_alliances": prefs.get("preferred_alliances", []),
        "prefer_same_tier": prefs.get("prefer_same_tier", False),
    }


@router.get("/me/frequent-routes")
async def get_frequent_routes(user: User = Depends(get_current_user)):
    return {"routes": []}
