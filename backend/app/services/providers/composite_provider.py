"""Composite provider — DB1B primary with Amadeus fallback."""

import logging
import uuid
from datetime import date

from app.services.providers.db1b_provider import DB1BProvider
from app.services.providers.amadeus_provider import AmadeusProvider

logger = logging.getLogger(__name__)


class CompositeProvider:
    """FlightDataProvider that tries DB1B first, falls back to Amadeus."""

    def __init__(self):
        self._primary = DB1BProvider()
        self._fallback = AmadeusProvider()

    async def initialize(self) -> None:
        await self._primary.initialize()
        await self._fallback.initialize()
        logger.info("Composite provider initialized (DB1B primary, Amadeus fallback)")

    async def shutdown(self) -> None:
        await self._primary.shutdown()
        await self._fallback.shutdown()
        logger.info("Composite provider shut down")

    def is_available(self) -> bool:
        return self._primary.is_available() or self._fallback.is_available()

    async def _try_primary_then_fallback(self, method_name: str, *args, empty_result=None, **kwargs):
        if self._primary.is_available():
            try:
                result = await getattr(self._primary, method_name)(*args, **kwargs)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Primary provider failed for {method_name}: {e}")

        if self._fallback.is_available():
            return await getattr(self._fallback, method_name)(*args, **kwargs)
        return empty_result

    async def search_flights(self, origin: str, destination: str, departure_date: date, cabin_class: str = "economy", *, company_id: uuid.UUID | None = None) -> list[dict]:
        return await self._try_primary_then_fallback(
            "search_flights", origin, destination, departure_date, cabin_class, empty_result=[], company_id=company_id,
        )

    async def search_flights_date_range(self, origin: str, destination: str, start_date: date, end_date: date, cabin_class: str = "economy", *, company_id: uuid.UUID | None = None) -> dict[str, list[dict]]:
        return await self._try_primary_then_fallback(
            "search_flights_date_range", origin, destination, start_date, end_date, cabin_class, empty_result={}, company_id=company_id,
        )

    async def search_month_prices(self, origin: str, destination: str, year: int, month: int, cabin_class: str = "economy", *, company_id: uuid.UUID | None = None) -> dict[str, dict]:
        return await self._try_primary_then_fallback(
            "search_month_prices", origin, destination, year, month, cabin_class, empty_result={}, company_id=company_id,
        )

    async def search_month_matrix(self, origin: str, destination: str, year: int, month: int, cabin_class: str = "economy", *, company_id: uuid.UUID | None = None) -> list[dict]:
        return await self._try_primary_then_fallback(
            "search_month_matrix", origin, destination, year, month, cabin_class, empty_result=[], company_id=company_id,
        )

    async def get_price_context(self, origin: str, destination: str, departure_date: date, cabin_class: str = "economy", current_price: float | None = None, *, company_id: uuid.UUID | None = None) -> dict | None:
        return await self._try_primary_then_fallback(
            "get_price_context", origin, destination, departure_date, cabin_class, current_price, company_id=company_id,
        )
