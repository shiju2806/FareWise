"""Admin router — FlightAPI operational visibility.

Exposes per-company credit consumption for the current billing month so
ops can spot runaway tenants and forecast plan upgrades. Strictly scoped
to the caller's own company and gated behind the admin role.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.dependencies import get_current_user
from app.models.user import User
from app.services.providers.flightapi.credit_gate import (
    _month_bucket,
    credit_budget_gate,
)

router = APIRouter()


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/credits")
async def get_credit_status(user: User = Depends(get_current_user)) -> dict:
    """Current-month credit consumption for the caller's company."""
    _require_admin(user)
    if user.company_id is None:
        raise HTTPException(status_code=400, detail="User has no company")

    budget = await credit_budget_gate._resolve_budget(user.company_id)
    bucket = _month_bucket()
    spent = await credit_budget_gate._current_spend(user.company_id, bucket)
    remaining = max(0, budget - spent)

    return {
        "company_id": str(user.company_id),
        "month": bucket,
        "budget": budget,
        "spent": spent,
        "remaining": remaining,
        "credits_per_search": settings.flightapi_credits_per_search,
        "provider": settings.flight_data_provider,
    }
