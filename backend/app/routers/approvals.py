"""Approval workflow router — submission, decisions, comments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from datetime import date

from app.database import get_db
from app.dependencies import get_current_user
from app.models.analytics import TravelerScore
from app.models.policy import Approval, ApprovalHistory, SavingsReport, PolicyViolation
from app.models.trip import Trip
from app.models.user import User
from app.services.analytics_service import compute_tier
from app.services.approval_service import approval_service

router = APIRouter()


def _get_traveler_tier(score: TravelerScore | None) -> str:
    """Get tier from a TravelerScore, defaulting to bronze."""
    return compute_tier(score.score if score else 0)


class SubmitRequest(BaseModel):
    traveler_notes: str | None = None
    violation_justifications: dict[str, str] | None = None


class DecideRequest(BaseModel):
    action: str  # approve | reject | changes_requested | escalate
    comments: str | None = None
    escalate_to: str | None = None
    reason: str | None = None


class CommentRequest(BaseModel):
    comment: str


@router.post("/trips/{trip_id}/evaluate")
async def evaluate_trip(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run policy checks and generate savings report WITHOUT submitting."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
        .options(selectinload(Trip.legs))
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    eval_result = await approval_service.evaluate_trip(db, trip, user)
    return eval_result


@router.post("/trips/{trip_id}/submit")
async def submit_trip(
    trip_id: uuid.UUID,
    req: SubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submit trip for approval."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
        .options(selectinload(Trip.legs))
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.status not in ("draft", "searching", "changes_requested"):
        raise HTTPException(
            status_code=400,
            detail=f"Trip cannot be submitted in status '{trip.status}'"
        )

    try:
        submit_result = await approval_service.submit_trip(
            db, trip, user,
            traveler_notes=req.traveler_notes,
            violation_justifications=req.violation_justifications,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if submit_result.get("error") == "blocking_violations":
        raise HTTPException(status_code=422, detail=submit_result)

    return submit_result


@router.get("/approvals")
async def list_approvals(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Manager's approval queue."""
    query = (
        select(Approval)
        .where(Approval.approver_id == user.id)
        .order_by(Approval.created_at.desc())
    )

    if status:
        query = query.where(Approval.status == status)

    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    approvals = result.scalars().all()

    # Get counts
    counts_result = await db.execute(
        select(Approval.status, func.count(Approval.id))
        .where(Approval.approver_id == user.id)
        .group_by(Approval.status)
    )
    counts_raw = counts_result.all()
    counts = {row[0]: row[1] for row in counts_raw}

    # Build response with trip details
    approval_list = []
    for a in approvals:
        trip_result = await db.execute(
            select(Trip).where(Trip.id == a.trip_id).options(selectinload(Trip.legs))
        )
        trip = trip_result.scalar_one_or_none()
        if not trip:
            continue

        traveler_result = await db.execute(select(User).where(User.id == trip.traveler_id))
        traveler = traveler_result.scalar_one_or_none()

        # Get savings report
        sr_result = await db.execute(
            select(SavingsReport).where(SavingsReport.trip_id == trip.id).order_by(SavingsReport.generated_at.desc())
        )
        sr = sr_result.scalar_one_or_none()

        # Count warnings/violations
        violations_result = await db.execute(
            select(func.count(PolicyViolation.id)).where(PolicyViolation.trip_id == trip.id)
        )
        violations_count = violations_result.scalar() or 0

        # Calculate travel dates
        dates = [l.preferred_date for l in trip.legs] if trip.legs else []
        travel_dates = ""
        if dates:
            min_d, max_d = min(dates), max(dates)
            travel_dates = f"{min_d.strftime('%b %d')}-{max_d.strftime('%d, %Y')}"

        approval_list.append({
            "id": str(a.id),
            "trip": {
                "id": str(trip.id),
                "title": trip.title,
                "traveler": {
                    "id": str(traveler.id) if traveler else None,
                    "name": f"{traveler.first_name} {traveler.last_name}" if traveler else "Unknown",
                    "department": traveler.department if traveler else None,
                },
                "total_estimated_cost": float(trip.total_estimated_cost) if trip.total_estimated_cost else None,
                "legs_count": len(trip.legs),
                "travel_dates": travel_dates,
            },
            "savings_report": {
                "policy_status": sr.policy_status if sr else None,
                "savings_vs_expensive": float(sr.savings_vs_expensive) if sr else None,
                "premium_vs_cheapest": float(sr.premium_vs_cheapest) if sr else None,
                "narrative": sr.narrative if sr else None,
            } if sr else None,
            "warnings_count": sr.policy_checks.count("warn") if sr and isinstance(sr.policy_checks, list) else 0,
            "violations_count": violations_count,
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return {
        "approvals": approval_list,
        "counts": {
            "pending": counts.get("pending", 0),
            "approved": counts.get("approved", 0),
            "rejected": counts.get("rejected", 0),
        },
    }


@router.get("/approvals/{approval_id}")
async def get_approval_detail(
    approval_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full approval detail."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    # Check access: approver or traveler
    trip_result = await db.execute(
        select(Trip).where(Trip.id == approval.trip_id).options(selectinload(Trip.legs))
    )
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if user.id != approval.approver_id and user.id != trip.traveler_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Get all details
    traveler_result = await db.execute(select(User).where(User.id == trip.traveler_id))
    traveler = traveler_result.scalar_one_or_none()

    # Get traveler's current score for tier
    period = f"{date.today().year}-{date.today().month:02d}"
    ts_result = await db.execute(
        select(TravelerScore).where(
            TravelerScore.user_id == trip.traveler_id,
            TravelerScore.period == period,
        )
    )
    traveler_score = ts_result.scalar_one_or_none()

    approver_result = await db.execute(select(User).where(User.id == approval.approver_id))
    approver = approver_result.scalar_one_or_none()

    sr_result = await db.execute(
        select(SavingsReport).where(SavingsReport.trip_id == trip.id).order_by(SavingsReport.generated_at.desc())
    )
    savings_report = sr_result.scalar_one_or_none()

    history_result = await db.execute(
        select(ApprovalHistory).where(ApprovalHistory.approval_id == approval.id).order_by(ApprovalHistory.created_at)
    )
    history = history_result.scalars().all()

    # Build history with actor names
    history_list = []
    for h in history:
        actor_result = await db.execute(select(User).where(User.id == h.actor_id))
        actor = actor_result.scalar_one_or_none()
        history_list.append({
            "id": str(h.id),
            "action": h.action,
            "actor": f"{actor.first_name} {actor.last_name}" if actor else "Unknown",
            "details": h.details,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        })

    # Record view in history
    existing_view = any(
        h.action == "viewed" and h.actor_id == user.id for h in history
    )
    if not existing_view and user.id == approval.approver_id:
        view_history = ApprovalHistory(
            approval_id=approval.id,
            action="viewed",
            actor_id=user.id,
        )
        db.add(view_history)
        await db.commit()

    return {
        "id": str(approval.id),
        "status": approval.status,
        "comments": approval.comments,
        "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
        "created_at": approval.created_at.isoformat() if approval.created_at else None,
        "trip": {
            "id": str(trip.id),
            "title": trip.title,
            "status": trip.status,
            "legs": [
                {
                    "id": str(l.id),
                    "sequence": l.sequence,
                    "origin_airport": l.origin_airport,
                    "origin_city": l.origin_city,
                    "destination_airport": l.destination_airport,
                    "destination_city": l.destination_city,
                    "preferred_date": l.preferred_date.isoformat(),
                    "cabin_class": l.cabin_class,
                    "passengers": l.passengers,
                }
                for l in trip.legs
            ],
            "total_estimated_cost": float(trip.total_estimated_cost) if trip.total_estimated_cost else None,
        },
        "traveler": {
            "id": str(traveler.id) if traveler else None,
            "name": f"{traveler.first_name} {traveler.last_name}" if traveler else "Unknown",
            "department": traveler.department if traveler else None,
            "tier": _get_traveler_tier(traveler_score),
        },
        "approver": {
            "id": str(approver.id) if approver else None,
            "name": f"{approver.first_name} {approver.last_name}" if approver else "Unknown",
        },
        "savings_report": {
            "id": str(savings_report.id),
            "selected_total": float(savings_report.selected_total),
            "cheapest_total": float(savings_report.cheapest_total),
            "most_expensive_total": float(savings_report.most_expensive_total),
            "policy_limit_total": float(savings_report.policy_limit_total) if savings_report.policy_limit_total else None,
            "savings_vs_expensive": float(savings_report.savings_vs_expensive),
            "premium_vs_cheapest": float(savings_report.premium_vs_cheapest),
            "narrative": savings_report.narrative,
            "policy_status": savings_report.policy_status,
            "policy_checks": savings_report.policy_checks,
            "slider_positions": savings_report.slider_positions,
        } if savings_report else None,
        "history": history_list,
    }


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(
    approval_id: uuid.UUID,
    req: DecideRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Manager action on an approval."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.approver_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Only the assigned approver can decide")

    # Cannot approve own trip
    trip_result = await db.execute(select(Trip).where(Trip.id == approval.trip_id))
    trip = trip_result.scalar_one_or_none()
    if trip and trip.traveler_id == user.id:
        raise HTTPException(status_code=403, detail="Cannot approve your own trip")

    if approval.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Cannot decide on {approval.status} approval")

    valid_actions = {"approve", "reject", "changes_requested", "escalate"}
    if req.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")

    try:
        decide_result = await approval_service.decide(
            db, approval, user, req.action,
            comments=req.comments,
            escalate_to=req.escalate_to,
            escalation_reason=req.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return decide_result


@router.post("/approvals/{approval_id}/comment")
async def add_comment(
    approval_id: uuid.UUID,
    req: CommentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a comment without deciding."""
    result = await db.execute(
        select(Approval).where(Approval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    # Check access
    trip_result = await db.execute(select(Trip).where(Trip.id == approval.trip_id))
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404)

    if user.id != approval.approver_id and user.id != trip.traveler_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    comment_result = await approval_service.add_comment(db, approval, user, req.comment)
    return comment_result
