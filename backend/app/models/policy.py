import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Selection(Base):
    __tablename__ = "selections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_legs.id"), nullable=False
    )
    flight_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flight_options.id"), nullable=False
    )
    justification_note: Mapped[str | None] = mapped_column(Text)
    slider_position: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    threshold: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action: Mapped[str] = mapped_column(String(20), default="warn")
    severity: Mapped[int] = mapped_column(Integer, default=5)
    exception_roles: Mapped[dict | None] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_from: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approvals.id")
    )
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip: Mapped["Trip"] = relationship(foreign_keys=[trip_id])
    approver: Mapped["User"] = relationship(foreign_keys=[approver_id])


class SavingsReport(Base):
    __tablename__ = "savings_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    selected_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cheapest_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    most_expensive_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    policy_limit_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    savings_vs_expensive: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    premium_vs_cheapest: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    narrative_html: Mapped[str | None] = mapped_column(Text)
    policy_status: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_checks: Mapped[dict] = mapped_column(JSONB, nullable=False)
    slider_positions: Mapped[dict | None] = mapped_column(JSONB)
    # Phase C additions
    hotel_selected_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    hotel_cheapest_total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    bundle_savings: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    events_impacting_price: Mapped[dict | None] = mapped_column(JSONB, default=list)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PolicyViolation(Base):
    __tablename__ = "policy_violations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    trip_leg_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_legs.id")
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id"), nullable=False
    )
    violation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    traveler_justification: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApprovalHistory(Base):
    __tablename__ = "approval_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approvals.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NearbyAirport(Base):
    __tablename__ = "nearby_airports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False)
    airport_iata: Mapped[str] = mapped_column(String(10), nullable=False)
    airport_name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    metro_area: Mapped[str | None] = mapped_column(String(100))
