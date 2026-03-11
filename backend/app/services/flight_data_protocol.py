"""Flight data provider protocol — common interface for all flight data sources."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

FlightDict = dict[str, Any]
PriceContextDict = dict[str, Any]
MonthPriceDict = dict[str, dict]
MonthMatrixEntry = dict[str, Any]


@runtime_checkable
class FlightDataProvider(Protocol):
    """Protocol for flight data providers.

    All providers implement these 5 search methods plus lifecycle.
    Method signatures match the DB1B canonical interface.
    """

    async def initialize(self) -> None:
        """Initialize provider resources (pool, HTTP client, etc.)."""
        ...

    async def shutdown(self) -> None:
        """Release provider resources."""
        ...

    def is_available(self) -> bool:
        """Check if provider is ready to serve requests."""
        ...

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
    ) -> list[FlightDict]:
        """Search flights for a single date."""
        ...

    async def search_flights_date_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: str = "economy",
    ) -> dict[str, list[FlightDict]]:
        """Search flights across a date range. Returns {date_iso: [flights]}."""
        ...

    async def search_month_prices(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str = "economy",
    ) -> MonthPriceDict:
        """Get cheapest price per day for an entire month."""
        ...

    async def search_month_matrix(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str = "economy",
    ) -> list[MonthMatrixEntry]:
        """Get airline x date matrix entries for an entire month."""
        ...

    async def get_price_context(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
        current_price: float | None = None,
    ) -> PriceContextDict | None:
        """Get historical price quartiles and percentile for a route."""
        ...
