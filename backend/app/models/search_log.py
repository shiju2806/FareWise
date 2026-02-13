import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SearchLog(Base):
    __tablename__ = "search_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_legs.id", ondelete="CASCADE"), nullable=False
    )
    api_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    search_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    results_count: Mapped[int | None] = mapped_column(Integer)
    cheapest_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    most_expensive_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    flight_options: Mapped[list["FlightOption"]] = relationship(
        back_populates="search_log", cascade="all, delete-orphan"
    )


class FlightOption(Base):
    __tablename__ = "flight_options"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    search_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("search_logs.id", ondelete="CASCADE"), nullable=False
    )
    airline_code: Mapped[str] = mapped_column(String(10), nullable=False)
    airline_name: Mapped[str] = mapped_column(String(100), nullable=False)
    flight_numbers: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_airport: Mapped[str] = mapped_column(String(10), nullable=False)
    destination_airport: Mapped[str] = mapped_column(String(10), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    stops: Mapped[int] = mapped_column(Integer, default=0)
    stop_airports: Mapped[str | None] = mapped_column(String(100))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    cabin_class: Mapped[str | None] = mapped_column(String(20))
    seats_remaining: Mapped[int | None] = mapped_column(Integer)
    is_alternate_airport: Mapped[bool] = mapped_column(Boolean, default=False)
    is_alternate_date: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    search_log: Mapped["SearchLog"] = relationship(back_populates="flight_options")
