"""Corporate hotel rate model — negotiated rates by city and hotel chain."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CorporateHotelRate(Base):
    __tablename__ = "corporate_hotel_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    city_name: Mapped[str] = mapped_column(String(100), nullable=False)
    hotel_chain: Mapped[str] = mapped_column(String(50), nullable=False)
    property_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(20), nullable=False)  # fixed | dynamic_discount | capped
    fixed_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    discount_pct: Mapped[int | None] = mapped_column(Integer)
    rate_cap: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CAD")
    room_category: Mapped[str] = mapped_column(String(20), default="standard")
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
