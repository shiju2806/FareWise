"""Phase C event and hotel models."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EventCache(Base):
    __tablename__ = "events_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    labels: Mapped[dict] = mapped_column(JSONB, default=list)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str | None] = mapped_column(String(10))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    venue_name: Mapped[str | None] = mapped_column(String(300))
    rank: Mapped[int | None] = mapped_column(Integer)
    local_rank: Mapped[int | None] = mapped_column(Integer)
    phq_attendance: Mapped[int | None] = mapped_column(Integer)
    demand_impact: Mapped[dict | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HotelSearch(Base):
    __tablename__ = "hotel_searches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_legs.id", ondelete="CASCADE"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, default=1)
    search_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    results_count: Mapped[int | None] = mapped_column(Integer)
    cheapest_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    most_expensive_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HotelOption(Base):
    __tablename__ = "hotel_options"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hotel_search_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hotel_searches.id", ondelete="CASCADE"), nullable=False
    )
    hotel_name: Mapped[str] = mapped_column(String(300), nullable=False)
    hotel_chain: Mapped[str | None] = mapped_column(String(100))
    star_rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    user_rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    nightly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    room_type: Mapped[str | None] = mapped_column(String(100))
    amenities: Mapped[dict] = mapped_column(JSONB, default=list)
    cancellation_policy: Mapped[str | None] = mapped_column(String(50))
    is_preferred_vendor: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HotelSelection(Base):
    __tablename__ = "hotel_selections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_legs.id"), nullable=False
    )
    hotel_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hotel_options.id"), nullable=False
    )
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    justification_note: Mapped[str | None] = mapped_column(Text)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceWatch(Base):
    __tablename__ = "price_watches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    watch_type: Mapped[str] = mapped_column(String(20), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(10))
    destination: Mapped[str | None] = mapped_column(String(10))
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    flexibility_days: Mapped[int] = mapped_column(Integer, default=3)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    current_best_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cabin_class: Mapped[str] = mapped_column(String(20), default="economy")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alert_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceWatchHistory(Base):
    __tablename__ = "price_watch_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    price_watch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("price_watches.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
