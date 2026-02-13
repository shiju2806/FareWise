"""Notifications router — in-app notification management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.policy import Notification
from app.models.user import User

router = APIRouter()


@router.get("")
async def list_notifications(
    is_read: bool | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get user's notifications."""
    query = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )

    if is_read is not None:
        query = query.where(Notification.is_read == is_read)

    result = await db.execute(query)
    notifications = result.scalars().all()

    # Get unread count
    count_result = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user.id, Notification.is_read == False)
    )
    unread_count = count_result.scalar() or 0

    return {
        "notifications": [
            {
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "reference_type": n.reference_type,
                "reference_id": str(n.reference_id) if n.reference_id else None,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "unread_count": unread_count,
    }


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark a notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.commit()
    return {"ok": True}


@router.put("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}
