from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.get("/me/frequent-routes")
async def get_frequent_routes(user: User = Depends(get_current_user)):
    return {"routes": []}
