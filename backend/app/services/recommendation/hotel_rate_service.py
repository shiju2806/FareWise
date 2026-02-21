"""Hotel rate service — looks up corporate rates by city/airport code."""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hotel_rate import CorporateHotelRate

logger = logging.getLogger(__name__)


class HotelRateResult:
    """Result of a corporate hotel rate lookup."""

    __slots__ = (
        "available", "rate_type", "nightly_rate", "hotel_chain",
        "property_name", "currency", "is_preferred", "is_estimated",
    )

    def __init__(
        self,
        available: bool = False,
        rate_type: str | None = None,
        nightly_rate: Decimal | None = None,
        hotel_chain: str | None = None,
        property_name: str | None = None,
        currency: str = "CAD",
        is_preferred: bool = False,
        is_estimated: bool = False,
    ):
        self.available = available
        self.rate_type = rate_type
        self.nightly_rate = nightly_rate
        self.hotel_chain = hotel_chain
        self.property_name = property_name
        self.currency = currency
        self.is_preferred = is_preferred
        self.is_estimated = is_estimated

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "rate_type": self.rate_type,
            "nightly_rate": float(self.nightly_rate) if self.nightly_rate else None,
            "hotel_chain": self.hotel_chain,
            "property_name": self.property_name,
            "currency": self.currency,
            "is_preferred": self.is_preferred,
            "is_estimated": self.is_estimated,
        }


# Airport code → city code mapping for common alternates
AIRPORT_TO_CITY: dict[str, str] = {
    # Toronto
    "YYZ": "YYZ", "YTZ": "YYZ",
    # New York
    "JFK": "JFK", "LGA": "JFK", "EWR": "JFK",
    # London
    "LHR": "LHR", "LGW": "LHR", "STN": "LHR", "LTN": "LHR",
    # Chicago
    "ORD": "ORD", "MDW": "ORD",
    # San Francisco
    "SFO": "SFO", "OAK": "SFO", "SJC": "SFO",
    # Los Angeles
    "LAX": "LAX", "BUR": "LAX", "LGB": "LAX",
    # Washington DC
    "IAD": "IAD", "DCA": "IAD", "BWI": "IAD",
    # Montreal
    "YUL": "YUL",
    # Vancouver
    "YVR": "YVR",
    # Calgary
    "YYC": "YYC",
}


class HotelRateService:
    """Looks up corporate hotel rates for a destination."""

    async def get_preferred_rate(
        self,
        db: AsyncSession,
        airport_code: str,
        travel_date: date | None = None,
    ) -> HotelRateResult:
        """Get the preferred corporate hotel rate for a destination.

        Looks up by city code (normalizing alternate airports).
        Returns the preferred hotel if available, else cheapest corporate rate.
        """
        city_code = AIRPORT_TO_CITY.get(airport_code, airport_code)

        query = select(CorporateHotelRate).where(
            CorporateHotelRate.city_code == city_code,
            CorporateHotelRate.room_category == "standard",
        )

        # Filter by validity period if date provided
        if travel_date:
            query = query.where(
                CorporateHotelRate.valid_from <= travel_date,
                CorporateHotelRate.valid_to >= travel_date,
            )

        # Prefer the preferred hotel, then cheapest fixed rate
        query = query.order_by(
            CorporateHotelRate.is_preferred.desc(),
            CorporateHotelRate.fixed_rate.asc().nullslast(),
        ).limit(1)

        result = await db.execute(query)
        rate = result.scalar_one_or_none()

        if not rate:
            return HotelRateResult(available=False)

        nightly = self._compute_nightly_rate(rate)

        return HotelRateResult(
            available=True,
            rate_type=rate.rate_type,
            nightly_rate=nightly,
            hotel_chain=rate.hotel_chain,
            property_name=rate.property_name,
            currency=rate.currency,
            is_preferred=rate.is_preferred,
            is_estimated=(rate.rate_type != "fixed"),
        )

    async def get_all_rates(
        self,
        db: AsyncSession,
        airport_code: str,
        travel_date: date | None = None,
    ) -> list[HotelRateResult]:
        """Get all corporate hotel rates for a destination."""
        city_code = AIRPORT_TO_CITY.get(airport_code, airport_code)

        query = select(CorporateHotelRate).where(
            CorporateHotelRate.city_code == city_code,
        )
        if travel_date:
            query = query.where(
                CorporateHotelRate.valid_from <= travel_date,
                CorporateHotelRate.valid_to >= travel_date,
            )
        query = query.order_by(
            CorporateHotelRate.is_preferred.desc(),
            CorporateHotelRate.fixed_rate.asc().nullslast(),
        )

        result = await db.execute(query)
        rates = result.scalars().all()

        return [
            HotelRateResult(
                available=True,
                rate_type=r.rate_type,
                nightly_rate=self._compute_nightly_rate(r),
                hotel_chain=r.hotel_chain,
                property_name=r.property_name,
                currency=r.currency,
                is_preferred=r.is_preferred,
                is_estimated=(r.rate_type != "fixed"),
            )
            for r in rates
        ]

    @staticmethod
    def _compute_nightly_rate(rate: CorporateHotelRate) -> Decimal:
        """Compute the effective nightly rate based on rate type."""
        if rate.rate_type == "fixed":
            return rate.fixed_rate or Decimal("0")
        elif rate.rate_type == "capped":
            # Use the cap as a conservative estimate
            return rate.rate_cap or Decimal("0")
        elif rate.rate_type == "dynamic_discount":
            # Can't compute without BAR — use cap if available, else flag as estimated
            if rate.rate_cap:
                return rate.rate_cap
            # Rough estimate: assume average BAR of $250, apply discount
            pct = rate.discount_pct or 0
            return Decimal(str(round(250 * (1 - pct / 100), 2)))
        return Decimal("0")


hotel_rate_service = HotelRateService()
