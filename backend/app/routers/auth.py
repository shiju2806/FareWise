from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@router.post("/register", status_code=201, response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Auto-assign manager: department manager first, then any admin
    manager_id = None
    if req.department:
        mgr = await db.execute(
            select(User).where(
                User.role == "manager",
                User.department == req.department,
                User.is_active == True,
            ).limit(1)
        )
        mgr_user = mgr.scalar_one_or_none()
        if mgr_user:
            manager_id = mgr_user.id
    if not manager_id:
        admin = await db.execute(
            select(User).where(User.role.in_(["manager", "admin"]), User.is_active == True).limit(1)
        )
        admin_user = admin.scalar_one_or_none()
        if admin_user:
            manager_id = admin_user.id

    user = User(
        email=req.email,
        password_hash=pwd_context.hash(req.password),
        first_name=req.first_name,
        last_name=req.last_name,
        role=req.role,
        department=req.department,
        manager_id=manager_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    return AuthResponse(token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token(str(user.id))
    return AuthResponse(token=token, user=UserResponse.model_validate(user))
