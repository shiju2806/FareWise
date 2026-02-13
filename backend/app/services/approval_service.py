"""Approval service — manages trip submission and approval workflow."""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.policy import (
    Approval,
    ApprovalHistory,
    PolicyViolation,
    SavingsReport,
    Selection,
)
from app.models.search_log import FlightOption, SearchLog
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.services.narrative_generator import narrative_generator
from app.services.notification_service import notification_service
from app.services.policy_engine import policy_engine

logger = logging.getLogger(__name__)


class ApprovalService:
    """Manages the approval state machine and trip submission flow."""

    async def evaluate_trip(self, db: AsyncSession, trip: Trip, user: User) -> dict:
        """Run policy checks and generate savings data WITHOUT submitting."""
        legs = trip.legs

        # Get selections for each leg
        leg_ids = [l.id for l in legs]
        sel_result = await db.execute(
            select(Selection).where(Selection.trip_leg_id.in_(leg_ids))
        )
        selections = sel_result.scalars().all()

        if not selections:
            return {
                "savings_report": None,
                "violations": [],
                "warnings": [],
                "blocks": [],
                "error": "No flight selections found. Please select flights for all legs.",
            }

        # Load flight options for selections
        flight_ids = [s.flight_option_id for s in selections]
        fo_result = await db.execute(
            select(FlightOption).where(FlightOption.id.in_(flight_ids))
        )
        flights = {str(f.id): f for f in fo_result.scalars().all()}

        # Run policy evaluation
        evaluation = await policy_engine.evaluate_trip(
            db, trip, selections, flights, legs, user.role
        )

        # Calculate totals
        selected_total = Decimal("0")
        cheapest_total = Decimal("0")
        most_expensive_total = Decimal("0")
        per_leg_details = []

        for leg in legs:
            sel = next((s for s in selections if s.trip_leg_id == leg.id), None)
            if not sel:
                continue
            flight = flights.get(str(sel.flight_option_id))
            if not flight:
                continue

            selected_total += flight.price

            # Get cheapest and most expensive for this leg's search
            search_result = await db.execute(
                select(SearchLog).where(SearchLog.trip_leg_id == leg.id).order_by(SearchLog.searched_at.desc())
            )
            latest_search = search_result.scalar_one_or_none()
            leg_cheapest = flight.price
            leg_expensive = flight.price

            if latest_search:
                leg_cheapest = latest_search.cheapest_price or flight.price
                leg_expensive = latest_search.most_expensive_price or flight.price

            cheapest_total += leg_cheapest
            most_expensive_total += leg_expensive

            per_leg_details.append({
                "leg_id": str(leg.id),
                "route": f"{leg.origin_airport} → {leg.destination_airport}",
                "selected_price": float(flight.price),
                "cheapest_price": float(leg_cheapest),
                "most_expensive_price": float(leg_expensive),
                "savings_note": None,
                "policy_status": "compliant",
            })

        savings_vs_expensive = most_expensive_total - selected_total
        premium_vs_cheapest = selected_total - cheapest_total

        # Generate narrative
        traveler_name = f"{user.first_name} {user.last_name}"
        narrative = await narrative_generator.generate(
            traveler_name=traveler_name,
            trip_title=trip.title or "Untitled Trip",
            selected_total=selected_total,
            cheapest_total=cheapest_total,
            most_expensive_total=most_expensive_total,
            policy_status=evaluation.overall_status,
            per_leg_details=per_leg_details,
        )

        # Build slider positions map
        slider_positions = {
            str(s.trip_leg_id): float(s.slider_position) if s.slider_position else None
            for s in selections
        }

        report_data = {
            "selected_total": float(selected_total),
            "cheapest_total": float(cheapest_total),
            "most_expensive_total": float(most_expensive_total),
            "policy_limit_total": None,
            "savings_vs_expensive": float(savings_vs_expensive),
            "premium_vs_cheapest": float(premium_vs_cheapest),
            "narrative": narrative,
            "policy_status": evaluation.overall_status,
            "policy_checks": [
                {
                    "policy_id": c.policy_id,
                    "policy_name": c.policy_name,
                    "rule_type": c.rule_type,
                    "status": c.status,
                    "details": c.details,
                    "severity": c.severity,
                }
                for c in evaluation.checks
            ],
            "per_leg_summary": per_leg_details,
            "slider_positions": slider_positions,
        }

        return {
            "savings_report": report_data,
            "violations": [
                {
                    "policy_name": b.policy_name,
                    "message": b.details,
                    "action": b.action,
                    "policy_id": b.policy_id,
                }
                for b in evaluation.blocks
            ],
            "warnings": [
                {
                    "policy_name": w.policy_name,
                    "message": w.details,
                    "action": w.action,
                    "requires_justification": False,
                }
                for w in evaluation.warnings
            ],
            "blocks": [
                {
                    "policy_name": b.policy_name,
                    "message": b.details,
                    "policy_id": b.policy_id,
                }
                for b in evaluation.blocks
            ],
        }

    async def submit_trip(
        self,
        db: AsyncSession,
        trip: Trip,
        user: User,
        traveler_notes: str | None = None,
        violation_justifications: dict[str, str] | None = None,
    ) -> dict:
        """Submit a trip for approval. Full flow per spec."""
        # 1. Validate all legs have selections
        legs = trip.legs
        leg_ids = [l.id for l in legs]
        sel_result = await db.execute(
            select(Selection).where(Selection.trip_leg_id.in_(leg_ids))
        )
        selections = sel_result.scalars().all()

        legs_with_selections = {s.trip_leg_id for s in selections}
        missing = [l for l in legs if l.id not in legs_with_selections]
        if missing:
            routes = [f"{l.origin_airport}→{l.destination_airport}" for l in missing]
            raise ValueError(f"Missing flight selections for legs: {', '.join(routes)}")

        # 2. Run policy evaluation
        flight_ids = [s.flight_option_id for s in selections]
        fo_result = await db.execute(
            select(FlightOption).where(FlightOption.id.in_(flight_ids))
        )
        flights = {str(f.id): f for f in fo_result.scalars().all()}

        evaluation = await policy_engine.evaluate_trip(
            db, trip, selections, flights, legs, user.role
        )

        # 3. Check for blocking violations
        if evaluation.blocks and not violation_justifications:
            return {
                "error": "blocking_violations",
                "detail": "Trip cannot be submitted due to policy violations",
                "blocks": [
                    {
                        "policy_name": b.policy_name,
                        "message": b.details,
                        "policy_id": b.policy_id,
                    }
                    for b in evaluation.blocks
                ],
            }

        # 4. Save violation justifications
        if violation_justifications:
            for policy_id_str, justification in violation_justifications.items():
                violation = PolicyViolation(
                    trip_id=trip.id,
                    policy_id=uuid.UUID(policy_id_str),
                    violation_type="block",
                    details={"justification": justification},
                    traveler_justification=justification,
                )
                db.add(violation)

        # 5-6. Generate savings narrative and create report
        eval_data = await self.evaluate_trip(db, trip, user)
        report_data = eval_data["savings_report"]

        if report_data:
            savings_report = SavingsReport(
                trip_id=trip.id,
                selected_total=Decimal(str(report_data["selected_total"])),
                cheapest_total=Decimal(str(report_data["cheapest_total"])),
                most_expensive_total=Decimal(str(report_data["most_expensive_total"])),
                policy_limit_total=Decimal(str(report_data["policy_limit_total"])) if report_data["policy_limit_total"] else None,
                savings_vs_expensive=Decimal(str(report_data["savings_vs_expensive"])),
                premium_vs_cheapest=Decimal(str(report_data["premium_vs_cheapest"])),
                narrative=report_data["narrative"],
                policy_status=report_data["policy_status"],
                policy_checks=report_data["policy_checks"],
                slider_positions=report_data.get("slider_positions"),
            )
            db.add(savings_report)

        # 7. Determine approver
        approver = await self._find_approver(db, user)
        if not approver:
            raise ValueError("No approver configured. Please contact admin.")

        # 8. Create approval record
        approval = Approval(
            trip_id=trip.id,
            approver_id=approver.id,
            status="pending",
        )
        db.add(approval)
        await db.flush()  # Get the approval ID

        # Create history entry
        history = ApprovalHistory(
            approval_id=approval.id,
            action="created",
            actor_id=user.id,
            details={"traveler_notes": traveler_notes},
        )
        db.add(history)

        # 9. Send notification to approver
        traveler_name = f"{user.first_name} {user.last_name}"
        await notification_service.send_approval_request(
            db, approver.id, trip.title or "Untitled Trip", traveler_name, trip.id
        )

        # 10. Update trip status
        trip.status = "submitted"
        trip.submitted_at = datetime.now(timezone.utc)
        if report_data:
            trip.total_estimated_cost = Decimal(str(report_data["selected_total"]))

        await db.commit()

        return {
            "trip_id": str(trip.id),
            "status": "submitted",
            "approval": {
                "id": str(approval.id),
                "approver_id": str(approver.id),
                "approver_name": f"{approver.first_name} {approver.last_name}",
                "status": "pending",
                "created_at": approval.created_at.isoformat() if approval.created_at else None,
            },
            "savings_report": report_data,
            "notification_sent": True,
        }

    async def decide(
        self,
        db: AsyncSession,
        approval: Approval,
        actor: User,
        action: str,
        comments: str | None = None,
        escalate_to: str | None = None,
        escalation_reason: str | None = None,
    ) -> dict:
        """Manager action on an approval."""
        now = datetime.now(timezone.utc)

        # Load the trip
        trip_result = await db.execute(
            select(Trip).where(Trip.id == approval.trip_id)
        )
        trip = trip_result.scalar_one_or_none()
        if not trip:
            raise ValueError("Trip not found")

        # Get traveler for notification
        traveler_result = await db.execute(
            select(User).where(User.id == trip.traveler_id)
        )
        traveler = traveler_result.scalar_one_or_none()
        actor_name = f"{actor.first_name} {actor.last_name}"

        if action == "approve":
            approval.status = "approved"
            approval.decided_at = now
            approval.comments = comments
            trip.status = "approved"
            trip.approved_at = now

        elif action == "reject":
            approval.status = "rejected"
            approval.decided_at = now
            approval.comments = comments
            trip.status = "rejected"
            trip.rejected_at = now
            trip.rejection_reason = comments

        elif action == "changes_requested":
            approval.status = "changes_requested"
            approval.decided_at = now
            approval.comments = comments
            trip.status = "changes_requested"

        elif action == "escalate":
            if not escalate_to:
                raise ValueError("escalate_to is required for escalation")
            approval.status = "escalated"
            approval.escalation_reason = escalation_reason

            # Create new approval for escalation target
            new_approval = Approval(
                trip_id=trip.id,
                approver_id=uuid.UUID(escalate_to),
                status="pending",
                escalated_from=approval.id,
                escalation_reason=escalation_reason,
            )
            db.add(new_approval)

            # Notify new approver
            await notification_service.send_escalation(
                db, uuid.UUID(escalate_to),
                trip.title or "Untitled Trip", actor_name, trip.id
            )

        # Record history
        history = ApprovalHistory(
            approval_id=approval.id,
            action=action,
            actor_id=actor.id,
            details={"comments": comments},
        )
        db.add(history)

        # Notify traveler
        if traveler and action in ("approve", "reject", "changes_requested"):
            await notification_service.send_decision(
                db, traveler.id, trip.title or "Untitled Trip",
                actor_name, action, trip.id
            )

        await db.commit()

        return {
            "approval_id": str(approval.id),
            "status": approval.status,
            "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            "trip_status": trip.status,
            "notification_sent": True,
        }

    async def add_comment(
        self, db: AsyncSession, approval: Approval, actor: User, comment: str
    ) -> dict:
        """Add a comment without deciding."""
        history = ApprovalHistory(
            approval_id=approval.id,
            action="commented",
            actor_id=actor.id,
            details={"comment": comment},
        )
        db.add(history)

        # Determine who to notify (the other party)
        trip_result = await db.execute(select(Trip).where(Trip.id == approval.trip_id))
        trip = trip_result.scalar_one_or_none()

        if trip:
            # If commenter is the approver, notify traveler; and vice versa
            notify_id = trip.traveler_id if actor.id == approval.approver_id else approval.approver_id
            actor_name = f"{actor.first_name} {actor.last_name}"
            await notification_service.send_comment(
                db, notify_id, trip.title or "Untitled Trip", actor_name, trip.id
            )

        await db.commit()

        return {
            "comment_id": str(history.id),
            "notification_sent": True,
        }

    async def _find_approver(self, db: AsyncSession, traveler: User) -> User | None:
        """Find the appropriate approver for a traveler."""
        # 1. Direct manager
        if traveler.manager_id:
            result = await db.execute(
                select(User).where(User.id == traveler.manager_id, User.is_active == True)
            )
            manager = result.scalar_one_or_none()
            if manager:
                return manager

        # 2. Any manager in same department
        if traveler.department:
            result = await db.execute(
                select(User).where(
                    User.role == "manager",
                    User.department == traveler.department,
                    User.is_active == True,
                    User.id != traveler.id,
                )
            )
            dept_manager = result.scalar_one_or_none()
            if dept_manager:
                return dept_manager

        # 3. Any admin
        result = await db.execute(
            select(User).where(User.role == "admin", User.is_active == True)
        )
        admin = result.scalar_one_or_none()
        return admin


approval_service = ApprovalService()
