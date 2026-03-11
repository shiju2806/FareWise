"""Flight provider — singleton proxy that delegates to the configured provider.

Usage:
    from app.services.flight_provider import flight_provider

    flights = await flight_provider.search_flights("YYZ", "LHR", date(2025, 4, 12), "business")

Switch provider via FLIGHT_DATA_PROVIDER env var (db1b | amadeus | composite).
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


def _create_provider():
    """Factory — reads FLIGHT_DATA_PROVIDER from config and returns the provider."""
    from app.config import settings

    name = getattr(settings, "flight_data_provider", "db1b")

    if name == "amadeus":
        from app.services.providers.amadeus_provider import AmadeusProvider
        return AmadeusProvider()
    elif name == "composite":
        from app.services.providers.composite_provider import CompositeProvider
        return CompositeProvider()
    else:
        from app.services.providers.db1b_provider import DB1BProvider
        return DB1BProvider()


class _FlightProviderProxy:
    """Lazy proxy — allows module-level import before app startup.

    All FlightDataProvider methods are delegated to the underlying provider
    which is created on first access or via explicit initialize().
    """

    def __init__(self):
        self._provider = None

    def _ensure_provider(self):
        if self._provider is None:
            self._provider = _create_provider()
        return self._provider

    async def initialize(self) -> None:
        self._ensure_provider()
        await self._provider.initialize()
        logger.info(f"Flight provider initialized: {type(self._provider).__name__}")

    async def shutdown(self) -> None:
        if self._provider:
            await self._provider.shutdown()
            logger.info("Flight provider shut down")

    def is_available(self) -> bool:
        if self._provider is None:
            return False
        return self._provider.is_available()

    async def search_flights(
        self, origin: str, destination: str, departure_date: date,
        cabin_class: str = "economy",
    ) -> list[dict]:
        return await self._ensure_provider().search_flights(
            origin, destination, departure_date, cabin_class,
        )

    async def search_flights_date_range(
        self, origin: str, destination: str, start_date: date, end_date: date,
        cabin_class: str = "economy",
    ) -> dict[str, list[dict]]:
        return await self._ensure_provider().search_flights_date_range(
            origin, destination, start_date, end_date, cabin_class,
        )

    async def search_month_prices(
        self, origin: str, destination: str, year: int, month: int,
        cabin_class: str = "economy",
    ) -> dict[str, dict]:
        return await self._ensure_provider().search_month_prices(
            origin, destination, year, month, cabin_class,
        )

    async def search_month_matrix(
        self, origin: str, destination: str, year: int, month: int,
        cabin_class: str = "economy",
    ) -> list[dict]:
        return await self._ensure_provider().search_month_matrix(
            origin, destination, year, month, cabin_class,
        )

    async def get_price_context(
        self, origin: str, destination: str, departure_date: date,
        cabin_class: str = "economy", current_price: float | None = None,
    ) -> dict | None:
        return await self._ensure_provider().get_price_context(
            origin, destination, departure_date, cabin_class, current_price,
        )


flight_provider = _FlightProviderProxy()
