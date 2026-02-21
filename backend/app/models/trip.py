import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    traveler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    natural_language_input: Mapped[str | None] = mapped_column(Text)
    parsed_input: Mapped[dict | None] = mapped_column(JSONB)
    total_estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    analysis_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    legs: Mapped[list["TripLeg"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripLeg.sequence"
    )


class TripLeg(Base):
    __tablename__ = "trip_legs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    origin_airport: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_city: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_airport: Mapped[str] = mapped_column(String(10), nullable=False)
    destination_city: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_date: Mapped[date] = mapped_column(Date, nullable=False)
    flexibility_days: Mapped[int] = mapped_column(Integer, default=3)
    cabin_class: Mapped[str] = mapped_column(String(20), default="economy")
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    # Phase C — hotel fields
    needs_hotel: Mapped[bool] = mapped_column(Boolean, default=False)
    hotel_check_in: Mapped[date | None] = mapped_column(Date)
    hotel_check_out: Mapped[date | None] = mapped_column(Date)
    hotel_guests: Mapped[int] = mapped_column(Integer, default=1)
    hotel_max_stars: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="legs")
