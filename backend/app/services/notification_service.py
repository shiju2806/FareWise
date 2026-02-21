"""Notification service — creates in-app notifications."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import Notification

logger = logging.getLogger(__name__)


class NotificationService:
    """Creates in-app notifications for approval workflow events."""

    async def send_approval_request(
        self, db: AsyncSession, approver_id: uuid.UUID, trip_title: str, traveler_name: str, trip_id: uuid.UUID
    ) -> Notification:
        return await self._create(
            db,
            user_id=approver_id,
            type="approval_requested",
            title="New Trip Approval Request",
            body=f"{traveler_name} submitted '{trip_title}' for your approval.",
            reference_type="trip",
            reference_id=trip_id,
        )

    async def send_decision(
        self, db: AsyncSession, traveler_id: uuid.UUID, trip_title: str,
        approver_name: str, decision: str, trip_id: uuid.UUID
    ) -> Notification:
        titles = {
            "approve": "Trip Approved",
            "approved": "Trip Approved",
            "reject": "Trip Rejected",
            "rejected": "Trip Rejected",
            "changes_requested": "Changes Requested",
        }
        bodies = {
            "approve": f"{approver_name} approved your trip '{trip_title}'.",
            "approved": f"{approver_name} approved your trip '{trip_title}'.",
            "reject": f"{approver_name} rejected your trip '{trip_title}'.",
            "rejected": f"{approver_name} rejected your trip '{trip_title}'.",
            "changes_requested": f"{approver_name} requested changes to '{trip_title}'.",
        }
        return await self._create(
            db,
            user_id=traveler_id,
            type="approval_decided",
            title=titles.get(decision, "Trip Update"),
            body=bodies.get(decision, f"Your trip '{trip_title}' has been updated."),
            reference_type="trip",
            reference_id=trip_id,
        )

    async def send_escalation(
        self, db: AsyncSession, new_approver_id: uuid.UUID,
        trip_title: str, escalated_by: str, trip_id: uuid.UUID
    ) -> Notification:
        return await self._create(
            db,
            user_id=new_approver_id,
            type="escalated",
            title="Escalated Approval Request",
            body=f"{escalated_by} escalated '{trip_title}' to you for approval.",
            reference_type="trip",
            reference_id=trip_id,
        )

    async def send_comment(
        self, db: AsyncSession, recipient_id: uuid.UUID,
        trip_title: str, commenter_name: str, trip_id: uuid.UUID
    ) -> Notification:
        return await self._create(
            db,
            user_id=recipient_id,
            type="comment",
            title="New Comment",
            body=f"{commenter_name} commented on '{trip_title}'.",
            reference_type="trip",
            reference_id=trip_id,
        )

    async def send_overlap_detected(
        self, db: AsyncSession, user_id: uuid.UUID,
        overlap_city: str, other_traveler: str, trip_id: uuid.UUID
    ) -> Notification:
        return await self._create(
            db,
            user_id=user_id,
            type="overlap_detected",
            title="Trip Overlap Detected",
            body=f"{other_traveler} is also traveling to {overlap_city} around the same dates. Consider coordinating!",
            reference_type="trip",
            reference_id=trip_id,
        )

    async def send_badge_earned(
        self, db: AsyncSession, user_id: uuid.UUID, badge_name: str
    ) -> Notification:
        return await self._create(
            db,
            user_id=user_id,
            type="badge_earned",
            title="Badge Earned!",
            body=f"Congratulations! You earned the '{badge_name}' badge.",
        )

    async def _create(
        self, db: AsyncSession, user_id: uuid.UUID, type: str,
        title: str, body: str, reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        db.add(notification)
        return notification


notification_service = NotificationService()
