from fastapi import APIRouter

router = APIRouter()


@router.post("/register", status_code=201)
async def register():
    return {"detail": "Not implemented yet"}


@router.post("/login")
async def login():
    return {"detail": "Not implemented yet"}
