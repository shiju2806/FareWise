"""Audit trail router — complete trip audit timeline."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.policy import Approval, ApprovalHistory, PolicyViolation, Selection
from app.models.search_log import SearchLog
from app.models.trip import Trip
from app.models.user import User

router = APIRouter()


@router.get("/trip/{trip_id}")
async def get_trip_audit(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Complete audit trail for a trip."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.legs))
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Access check: trip owner, approver, or admin
    is_owner = trip.traveler_id == user.id
    approval_result = await db.execute(
        select(Approval).where(Approval.trip_id == trip_id)
    )
    approvals = approval_result.scalars().all()
    is_approver = any(a.approver_id == user.id for a in approvals)

    if not is_owner and not is_approver and user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Build timeline
    timeline = []

    # Get traveler name
    traveler_result = await db.execute(select(User).where(User.id == trip.traveler_id))
    traveler = traveler_result.scalar_one_or_none()
    traveler_name = f"{traveler.first_name} {traveler.last_name}" if traveler else "Unknown"

    # 1. Trip created
    timeline.append({
        "timestamp": trip.created_at.isoformat(),
        "event": "trip_created",
        "actor": traveler_name,
        "details": {
            "method": "natural_language" if trip.natural_language_input else "structured",
            "input": trip.natural_language_input or trip.title,
        },
    })

    # 2. Search events
    for leg in trip.legs:
        search_result = await db.execute(
            select(SearchLog)
            .where(SearchLog.trip_leg_id == leg.id)
            .order_by(SearchLog.searched_at)
        )
        searches = search_result.scalars().all()
        for s in searches:
            timeline.append({
                "timestamp": s.searched_at.isoformat(),
                "event": "search_executed",
                "actor": "system",
                "details": {
                    "leg": f"{leg.origin_airport} → {leg.destination_airport}",
                    "options_returned": s.results_count,
                    "cheapest": float(s.cheapest_price) if s.cheapest_price else None,
                    "most_expensive": float(s.most_expensive_price) if s.most_expensive_price else None,
                },
            })

    # 3. Flight selections
    leg_ids = [l.id for l in trip.legs]
    if leg_ids:
        sel_result = await db.execute(
            select(Selection).where(Selection.trip_leg_id.in_(leg_ids)).order_by(Selection.selected_at)
        )
        selections = sel_result.scalars().all()
        for sel in selections:
            leg = next((l for l in trip.legs if l.id == sel.trip_leg_id), None)
            timeline.append({
                "timestamp": sel.selected_at.isoformat() if sel.selected_at else trip.created_at.isoformat(),
                "event": "flight_selected",
                "actor": traveler_name,
                "details": {
                    "leg": f"{leg.origin_airport} → {leg.destination_airport}" if leg else "Unknown",
                    "slider_position": float(sel.slider_position) if sel.slider_position else None,
                },
            })

    # 4. Trip submitted
    if trip.submitted_at:
        timeline.append({
            "timestamp": trip.submitted_at.isoformat(),
            "event": "trip_submitted",
            "actor": traveler_name,
            "details": {
                "total": float(trip.total_estimated_cost) if trip.total_estimated_cost else None,
            },
        })

    # 5. Approval events
    for approval in approvals:
        approver_result = await db.execute(select(User).where(User.id == approval.approver_id))
        approver = approver_result.scalar_one_or_none()
        approver_name = f"{approver.first_name} {approver.last_name}" if approver else "Unknown"

        history_result = await db.execute(
            select(ApprovalHistory)
            .where(ApprovalHistory.approval_id == approval.id)
            .order_by(ApprovalHistory.created_at)
        )
        for h in history_result.scalars().all():
            actor_result = await db.execute(select(User).where(User.id == h.actor_id))
            actor = actor_result.scalar_one_or_none()

            event_type = {
                "created": "approval_created",
                "viewed": "approval_viewed",
                "approved": "trip_approved",
                "rejected": "trip_rejected",
                "changes_requested": "changes_requested",
                "escalated": "approval_escalated",
                "commented": "comment_added",
            }.get(h.action, h.action)

            timeline.append({
                "timestamp": h.created_at.isoformat(),
                "event": event_type,
                "actor": f"{actor.first_name} {actor.last_name}" if actor else "Unknown",
                "details": h.details or {},
            })

    # 6. Approval decision
    if trip.approved_at:
        timeline.append({
            "timestamp": trip.approved_at.isoformat(),
            "event": "trip_approved",
            "actor": "system",
            "details": {},
        })
    elif trip.rejected_at:
        timeline.append({
            "timestamp": trip.rejected_at.isoformat(),
            "event": "trip_rejected",
            "actor": "system",
            "details": {"reason": trip.rejection_reason},
        })

    # Sort by timestamp
    timeline.sort(key=lambda e: e["timestamp"])

    return {
        "trip_id": str(trip.id),
        "timeline": timeline,
    }
