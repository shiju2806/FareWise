"""Collaboration models — trip overlaps."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TripOverlap(Base):
    __tablename__ = "trip_overlaps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False
    )
    trip_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False
    )
    overlap_city: Mapped[str] = mapped_column(String(100), nullable=False)
    overlap_start: Mapped[date] = mapped_column(Date, nullable=False)
    overlap_end: Mapped[date] = mapped_column(Date, nullable=False)
    overlap_days: Mapped[int] = mapped_column(Integer, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_by_a: Mapped[bool] = mapped_column(Boolean, default=False)
    dismissed_by_b: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
