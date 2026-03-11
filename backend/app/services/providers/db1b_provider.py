"""DB1B provider — wraps DB1BClient behind the FlightDataProvider protocol."""

import logging
from datetime import date

from app.config import settings

logger = logging.getLogger(__name__)


class DB1BProvider:
    """FlightDataProvider backed by DB1B historical fare data in PostgreSQL."""

    def __init__(self):
        self._pool = None

    async def initialize(self) -> None:
        if not settings.db1b_enabled:
            logger.info("DB1B provider disabled via config")
            return

        import asyncpg
        from app.services.db1b_client import db1b_client

        self._pool = await asyncpg.create_pool(
            settings.db1b_database_url,
            min_size=settings.db1b_pool_min,
            max_size=settings.db1b_pool_max,
            timeout=settings.db1b_pool_timeout,
            command_timeout=settings.db1b_command_timeout,
        )
        db1b_client.pool = self._pool
        logger.info("DB1B provider initialized (asyncpg pool created)")

    async def shutdown(self) -> None:
        if self._pool:
            from app.services.db1b_client import db1b_client
            await self._pool.close()
            self._pool = None
            db1b_client.pool = None
            logger.info("DB1B provider shut down")

    def is_available(self) -> bool:
        return self._pool is not None

    async def search_flights(self, origin: str, destination: str, departure_date: date, cabin_class: str = "economy") -> list[dict]:
        from app.services.db1b_client import db1b_client
        return await db1b_client.search_flights(origin, destination, departure_date, cabin_class)

    async def search_flights_date_range(self, origin: str, destination: str, start_date: date, end_date: date, cabin_class: str = "economy") -> dict[str, list[dict]]:
        from app.services.db1b_client import db1b_client
        return await db1b_client.search_flights_date_range(origin, destination, start_date, end_date, cabin_class)

    async def search_month_prices(self, origin: str, destination: str, year: int, month: int, cabin_class: str = "economy") -> dict[str, dict]:
        from app.services.db1b_client import db1b_client
        return await db1b_client.search_month_prices(origin, destination, year, month, cabin_class)

    async def search_month_matrix(self, origin: str, destination: str, year: int, month: int, cabin_class: str = "economy") -> list[dict]:
        from app.services.db1b_client import db1b_client
        return await db1b_client.search_month_matrix(origin, destination, year, month, cabin_class)

    async def get_price_context(self, origin: str, destination: str, departure_date: date, cabin_class: str = "economy", current_price: float | None = None) -> dict | None:
        from app.services.db1b_client import db1b_client
        return await db1b_client.get_price_context(origin, destination, departure_date, cabin_class, current_price)
