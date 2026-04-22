"""FlightAPIProvider — FlightDataProvider implementation for FlightAPI.io.

Pipeline layering for search_flights:

    cache.get ──hit──> return
        │ miss
        ▼
    coalescer.run(key, factory)
        │
        ▼  (factory body)
    concurrency_gate.slot()        # cap 5 concurrent upstream calls
        │
        ▼
    credit_budget_gate.reserve()   # raises CreditBudgetExceeded
        │
        ▼
    flight_api_client.search_one_way()
        │    │
        │    └──fail──> credit_budget_gate.refund() + re-raise
        ▼
    cache.set(result)
        │
        ▼
    return result

Only `search_flights` is implemented end-to-end in this foundation PR. The
other protocol methods return empty/None scaffolding; real implementations
arrive in follow-up PRs (round-trip, month calendar, price context).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from app.config import settings
from app.services.flight_cache import flight_cache
from app.services.flight_coalescer import flight_coalescer
from app.services.flight_data_protocol import (
    FlightDict,
    MonthMatrixEntry,
    MonthPriceDict,
    PriceContextDict,
)

from .client import flight_api_client
from .concurrency_gate import concurrency_gate
from .credit_gate import CreditBudgetExceeded, credit_budget_gate

logger = logging.getLogger(__name__)


class FlightAPIProvider:
    """Live-fare provider backed by FlightAPI.io.

    Composes the tenant-aware cache, in-process coalescer, global concurrency
    gate, per-tenant credit budget gate, and the HTTP client.
    """

    async def initialize(self) -> None:
        # The httpx client is lazily constructed on first use.
        return None

    async def shutdown(self) -> None:
        await flight_api_client.close()

    def is_available(self) -> bool:
        return flight_api_client.is_configured()

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
        *,
        company_id: uuid.UUID | None = None,
    ) -> list[FlightDict]:
        origin = origin.upper()
        destination = destination.upper()
        date_iso = departure_date.isoformat()
        cabin = cabin_class.lower()

        cached = await flight_cache.get_flights(
            company_id, origin, destination, date_iso, cabin
        )
        if cached is not None:
            logger.debug(
                "flightapi cache hit company=%s %s->%s %s",
                company_id, origin, destination, date_iso,
            )
            return cached

        key = flight_cache.flight_key(
            company_id, origin, destination, date_iso, cabin
        )

        async def _fetch() -> list[FlightDict]:
            async with concurrency_gate.slot():
                if company_id is None:
                    # System/background searches bypass the credit gate.
                    # Keep this path narrow — production traffic should always
                    # carry a tenant.
                    logger.warning(
                        "flightapi search without company_id — skipping credit gate"
                    )
                    results = await flight_api_client.search_one_way(
                        origin, destination, departure_date, cabin_class
                    )
                else:
                    await credit_budget_gate.reserve(company_id)
                    try:
                        results = await flight_api_client.search_one_way(
                            origin, destination, departure_date, cabin_class
                        )
                    except Exception:
                        await credit_budget_gate.refund(company_id)
                        raise

            await flight_cache.set_flights(
                company_id, origin, destination, date_iso, cabin, results
            )
            return results

        try:
            return await flight_coalescer.run(key, _fetch)
        except CreditBudgetExceeded:
            logger.warning(
                "flightapi credit budget exceeded company=%s", company_id
            )
            return []

    async def search_flights_date_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: str = "economy",
        *,
        company_id: uuid.UUID | None = None,
    ) -> dict[str, list[FlightDict]]:
        # Foundation scaffolding: delegate day-by-day. Cost-optimized batching
        # (and coalescing across the range) will land in a follow-up once we
        # validate single-date behavior in production.
        from datetime import timedelta

        results: dict[str, list[FlightDict]] = {}
        current = start_date
        while current <= end_date:
            results[current.isoformat()] = await self.search_flights(
                origin, destination, current, cabin_class,
                company_id=company_id,
            )
            current = current + timedelta(days=1)
        return results

    async def search_month_prices(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str = "economy",
        *,
        company_id: uuid.UUID | None = None,
    ) -> MonthPriceDict:
        # Month calendar support needs a dedicated upstream endpoint to keep
        # credit usage reasonable; stubbed for now.
        _ = (origin, destination, year, month, cabin_class, company_id, settings)
        return {}

    async def search_month_matrix(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str = "economy",
        *,
        company_id: uuid.UUID | None = None,
    ) -> list[MonthMatrixEntry]:
        _ = (origin, destination, year, month, cabin_class, company_id)
        return []

    async def get_price_context(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
        current_price: float | None = None,
        *,
        company_id: uuid.UUID | None = None,
    ) -> PriceContextDict | None:
        # Historical context requires the history endpoint; follow-up PR.
        _ = (origin, destination, departure_date, cabin_class, current_price, company_id)
        return None


flight_api_provider = FlightAPIProvider()
