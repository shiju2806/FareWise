"""Phase D analytics and gamification models."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TravelerScore(Base):
    __tablename__ = "traveler_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    total_trips: Mapped[int] = mapped_column(Integer, default=0)
    total_spend: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_savings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    smart_savings: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    policy_compliance_rate: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=1.0)
    avg_advance_booking_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=0)
    avg_slider_position: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=50)
    score: Mapped[int] = mapped_column(Integer, default=0)
    rank_in_department: Mapped[int | None] = mapped_column(Integer)
    rank_in_company: Mapped[int | None] = mapped_column(Integer)
    badges: Mapped[dict] = mapped_column(JSONB, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
