"""Reports router — PDF/CSV export endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.export_service import export_service

router = APIRouter()


@router.get("/savings/{trip_id}/pdf")
async def savings_pdf(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download savings report as PDF."""
    try:
        pdf_bytes = await export_service.generate_savings_pdf(db, trip_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=savings_{trip_id}.pdf"},
    )


@router.get("/audit/{trip_id}/pdf")
async def audit_pdf(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download audit trail as PDF."""
    # Get timeline via audit endpoint logic
    from app.routers.audit import get_trip_audit

    try:
        audit_data = await get_trip_audit(trip_id, db, user)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Trip not found")

    try:
        pdf_bytes = await export_service.generate_audit_pdf(
            db, trip_id, audit_data.get("timeline", [])
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=audit_{trip_id}.pdf"},
    )
