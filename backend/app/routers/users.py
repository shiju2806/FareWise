from fastapi import APIRouter

router = APIRouter()


@router.get("/me")
async def get_current_user_profile():
    return {"detail": "Not implemented yet"}


@router.get("/me/frequent-routes")
async def get_frequent_routes():
    return {"detail": "Not implemented yet"}
