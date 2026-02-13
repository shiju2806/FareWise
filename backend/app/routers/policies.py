"""Policy management router — admin CRUD for travel policies."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.policy import Policy
from app.models.user import User

router = APIRouter()


class PolicyCreate(BaseModel):
    name: str
    description: str | None = None
    rule_type: str
    conditions: dict = {}
    threshold: dict
    action: str = "warn"
    severity: int = 5
    exception_roles: list[str] = []


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    rule_type: str | None = None
    conditions: dict | None = None
    threshold: dict | None = None
    action: str | None = None
    severity: int | None = None
    exception_roles: list[str] | None = None
    is_active: bool | None = None


def _require_admin(user: User):
    if user.role not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("")
async def list_policies(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all policies. All authenticated users can view."""
    result = await db.execute(
        select(Policy).where(Policy.is_active == True).order_by(Policy.severity.desc())
    )
    policies = result.scalars().all()

    return {
        "policies": [
            {
                "id": str(p.id),
                "name": p.name,
                "description": p.description,
                "rule_type": p.rule_type,
                "conditions": p.conditions,
                "threshold": p.threshold,
                "action": p.action,
                "severity": p.severity,
                "exception_roles": p.exception_roles or [],
                "is_active": p.is_active,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in policies
        ]
    }


@router.post("", status_code=201)
async def create_policy(
    req: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new policy (admin only)."""
    _require_admin(user)

    policy = Policy(
        name=req.name,
        description=req.description,
        rule_type=req.rule_type,
        conditions=req.conditions,
        threshold=req.threshold,
        action=req.action,
        severity=req.severity,
        exception_roles=req.exception_roles,
        created_by=user.id,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    return {
        "id": str(policy.id),
        "name": policy.name,
        "description": policy.description,
        "rule_type": policy.rule_type,
        "conditions": policy.conditions,
        "threshold": policy.threshold,
        "action": policy.action,
        "severity": policy.severity,
        "exception_roles": policy.exception_roles or [],
        "is_active": policy.is_active,
    }


@router.put("/{policy_id}")
async def update_policy(
    policy_id: uuid.UUID,
    req: PolicyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a policy (admin only)."""
    _require_admin(user)

    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(policy, field, value)

    await db.commit()
    await db.refresh(policy)

    return {
        "id": str(policy.id),
        "name": policy.name,
        "description": policy.description,
        "rule_type": policy.rule_type,
        "conditions": policy.conditions,
        "threshold": policy.threshold,
        "action": policy.action,
        "severity": policy.severity,
        "exception_roles": policy.exception_roles or [],
        "is_active": policy.is_active,
    }


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft delete a policy (admin only)."""
    _require_admin(user)

    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    policy.is_active = False
    await db.commit()
