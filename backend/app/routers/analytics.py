"""Analytics router — dashboard data, stats, leaderboard, export."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.analytics_service import analytics_service

router = APIRouter()


def _require_manager_or_admin(user: User):
    if user.role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="Manager or admin access required")


@router.get("/overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Analytics overview — headline metrics and trends."""
    _require_manager_or_admin(user)
    return await analytics_service.get_overview(db)


@router.get("/department/{department}")
async def get_department(
    department: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Department-level analytics."""
    _require_manager_or_admin(user)
    return await analytics_service.get_department_analytics(db, department)


@router.get("/route/{origin}/{destination}")
async def get_route(
    origin: str,
    destination: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Route-level analytics."""
    _require_manager_or_admin(user)
    return await analytics_service.get_route_analytics(db, origin, destination)


@router.get("/savings-report")
async def get_savings_report(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Company-wide savings summary."""
    _require_manager_or_admin(user)
    return await analytics_service.get_savings_summary(db)


@router.get("/savings-goal")
async def get_savings_goal(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Company-wide quarterly savings goal — accessible to all users."""
    return await analytics_service.get_savings_goal(db)


@router.get("/my-stats")
async def get_my_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Personal stats, score, badges for the logged-in user."""
    return await analytics_service.get_my_stats(db, user.id)


@router.get("/leaderboard")
async def get_leaderboard(
    department: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Leaderboard — optionally filtered by department."""
    return await analytics_service.get_leaderboard(db, department)


@router.get("/export/csv")
async def export_csv(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export analytics data as CSV."""
    _require_manager_or_admin(user)
    rows = await analytics_service.export_analytics_csv(db)
    if not rows:
        raise HTTPException(status_code=404, detail="No data to export")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=farewise_analytics.csv"},
    )
