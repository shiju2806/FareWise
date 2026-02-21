"""Audit trail router — complete trip audit timeline."""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.events import HotelSelection, HotelOption
from app.models.policy import Approval, ApprovalHistory, PolicyViolation, Selection
from app.models.search_log import FlightOption, SearchLog
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

    # 2. Search executed — group concurrent searches into one event
    all_searches = []
    for leg in trip.legs:
        search_result = await db.execute(
            select(SearchLog)
            .where(SearchLog.trip_leg_id == leg.id, SearchLog.is_synthetic == False)
            .order_by(SearchLog.searched_at)
        )
        for s in search_result.scalars().all():
            all_searches.append((s, leg))

    # Group searches by timestamp (searches within 5 seconds are one event)
    if all_searches:
        groups: list[list[tuple]] = []
        current_group: list[tuple] = [all_searches[0]]
        for s, leg in all_searches[1:]:
            prev_time = current_group[-1][0].searched_at
            if abs((s.searched_at - prev_time).total_seconds()) <= 5:
                current_group.append((s, leg))
            else:
                groups.append(current_group)
                current_group = [(s, leg)]
        groups.append(current_group)

        for group in groups:
            total_options = sum(s.results_count or 0 for s, _ in group)
            all_cheapest = [float(s.cheapest_price) for s, _ in group if s.cheapest_price]
            all_expensive = [float(s.most_expensive_price) for s, _ in group if s.most_expensive_price]
            legs_searched = [f"{leg.origin_airport} → {leg.destination_airport}" for _, leg in group]

            timeline.append({
                "timestamp": group[0][0].searched_at.isoformat(),
                "event": "search_executed",
                "actor": "system",
                "details": {
                    "legs": legs_searched,
                    "total_options": total_options,
                    "cheapest": min(all_cheapest) if all_cheapest else None,
                    "most_expensive": max(all_expensive) if all_expensive else None,
                },
            })

    # 3. Date shift — detect if user selected trip-window alternatives
    snapshot = trip.analysis_snapshot or {}
    tw = snapshot.get("trip_window_alternatives")
    has_date_shift = False

    if tw and tw.get("original_total_price"):
        # Check if selected flights are from synthetic (trip-window) search logs
        synthetic_result = await db.execute(
            select(SearchLog).where(
                SearchLog.trip_leg_id.in_([l.id for l in trip.legs]),
                SearchLog.is_synthetic == True,
            )
        )
        synthetic_logs = synthetic_result.scalars().all()
        if synthetic_logs:
            has_date_shift = True
            shift_time = min(s.searched_at for s in synthetic_logs)

            # The actual booked total (from trip record, set at submission)
            new_total = float(trip.total_estimated_cost) if trip.total_estimated_cost else None
            original_total = tw["original_total_price"]

            # Build per-leg date comparison: original search dates vs booked dates
            original_dates = []
            new_dates = []
            snapshot_legs = snapshot.get("legs", [])
            for i, leg in enumerate(trip.legs):
                snap_leg = snapshot_legs[i] if i < len(snapshot_legs) else None
                orig_date = snap_leg["selected"]["date"] if snap_leg and snap_leg.get("selected") else None
                new_date = leg.preferred_date.isoformat() if leg.preferred_date else None
                route = f"{leg.origin_airport} → {leg.destination_airport}"
                if orig_date and new_date and orig_date != new_date:
                    original_dates.append(f"{route}: {orig_date}")
                    new_dates.append(f"{route}: {new_date}")

            timeline.append({
                "timestamp": shift_time.isoformat(),
                "event": "date_shift_selected",
                "actor": traveler_name,
                "details": {
                    "original_dates": original_dates or None,
                    "new_dates": new_dates or None,
                    "original_total": original_total,
                    "new_total": new_total,
                    "savings": round(original_total - new_total, 2) if new_total and original_total and original_total > new_total else None,
                },
            })

    # 4. Flights confirmed — group all selections into one event
    leg_ids = [l.id for l in trip.legs]
    confirmed_flights = []
    confirm_time = None

    if leg_ids:
        sel_result = await db.execute(
            select(Selection).where(Selection.trip_leg_id.in_(leg_ids)).order_by(Selection.selected_at)
        )
        selections = sel_result.scalars().all()

        for sel in selections:
            leg = next((l for l in trip.legs if l.id == sel.trip_leg_id), None)

            fo_result = await db.execute(
                select(FlightOption).where(FlightOption.id == sel.flight_option_id)
            )
            fo = fo_result.scalar_one_or_none()

            flight_info = {
                "leg": f"{leg.origin_airport} → {leg.destination_airport}" if leg else "Unknown",
            }
            if fo:
                flight_info.update({
                    "airline": fo.airline_name,
                    "price": float(fo.price),
                    "currency": fo.currency,
                    "date": fo.departure_time.date().isoformat() if fo.departure_time else None,
                    "stops": fo.stops,
                })
            confirmed_flights.append(flight_info)

            ts = sel.selected_at if sel.selected_at else trip.created_at
            if confirm_time is None or ts > confirm_time:
                confirm_time = ts

    if confirmed_flights:
        total_price = sum(f.get("price", 0) for f in confirmed_flights)
        timeline.append({
            "timestamp": confirm_time.isoformat() if confirm_time else trip.created_at.isoformat(),
            "event": "flights_confirmed",
            "actor": traveler_name,
            "details": {
                "flights": confirmed_flights,
                "total": round(total_price, 2),
                "currency": confirmed_flights[0].get("currency", "CAD"),
            },
        })

    # 4b. Hotel selections
    for leg in trip.legs:
        hotel_sel_result = await db.execute(
            select(HotelSelection).where(HotelSelection.trip_leg_id == leg.id)
        )
        hotel_sel = hotel_sel_result.scalar_one_or_none()
        if hotel_sel:
            opt_result = await db.execute(
                select(HotelOption).where(HotelOption.id == hotel_sel.hotel_option_id)
            )
            hotel_opt = opt_result.scalar_one_or_none()
            timeline.append({
                "timestamp": hotel_sel.selected_at.isoformat() if hotel_sel.selected_at else trip.created_at.isoformat(),
                "event": "hotel_selected",
                "actor": traveler_name,
                "details": {
                    "leg": f"{leg.origin_airport} → {leg.destination_airport}",
                    "hotel": hotel_opt.hotel_name if hotel_opt else "Unknown",
                    "total_rate": float(hotel_opt.total_rate) if hotel_opt else None,
                    "check_in": hotel_sel.check_in.isoformat(),
                    "check_out": hotel_sel.check_out.isoformat(),
                },
            })

    # 5. Trip submitted — include approver info
    if trip.submitted_at:
        submit_details: dict = {
            "total": float(trip.total_estimated_cost) if trip.total_estimated_cost else None,
        }
        if approvals:
            approver_result = await db.execute(
                select(User).where(User.id == approvals[0].approver_id)
            )
            approver = approver_result.scalar_one_or_none()
            if approver:
                submit_details["sent_to"] = f"{approver.first_name} {approver.last_name}"

        timeline.append({
            "timestamp": trip.submitted_at.isoformat(),
            "event": "trip_submitted",
            "actor": traveler_name,
            "details": submit_details,
        })

    # 6. Approval events (from ApprovalHistory) — skip "created" since it's part of submission
    for approval in approvals:
        history_result = await db.execute(
            select(ApprovalHistory)
            .where(ApprovalHistory.approval_id == approval.id)
            .order_by(ApprovalHistory.created_at)
        )
        for h in history_result.scalars().all():
            if h.action == "created":
                continue

            actor_result = await db.execute(select(User).where(User.id == h.actor_id))
            actor = actor_result.scalar_one_or_none()

            event_type = {
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

    # Sort by timestamp
    timeline.sort(key=lambda e: e["timestamp"])

    return {
        "trip_id": str(trip.id),
        "timeline": timeline,
    }
