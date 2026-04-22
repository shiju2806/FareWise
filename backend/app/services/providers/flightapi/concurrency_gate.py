"""Global concurrency gate for FlightAPI.io.

The Lite plan caps simultaneous requests at 5. Exceeding it triggers 429s that
waste credits (the failed call is still billed in some pricing tiers). This
gate uses a single asyncio.Semaphore across the worker so no more than the
configured limit of upstream HTTP calls are in flight at once.

The limit is per-worker. Running multiple backend processes behind a load
balancer means each gets its own budget — tune the deployment to match the
plan ceiling (e.g., 1 worker for Lite, or lower flightapi_concurrency_limit).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from app.config import settings

logger = logging.getLogger(__name__)


class ConcurrencyGate:
    """asyncio.Semaphore wrapper sized by settings.flightapi_concurrency_limit."""

    def __init__(self, limit: int | None = None) -> None:
        self._limit = limit if limit is not None else settings.flightapi_concurrency_limit
        self._semaphore = asyncio.Semaphore(self._limit)

    @property
    def limit(self) -> int:
        return self._limit

    def available(self) -> int:
        # Semaphore internal counter is private; approximate via _value when present.
        value = getattr(self._semaphore, "_value", None)
        return value if value is not None else self._limit

    @asynccontextmanager
    async def slot(self):
        await self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()


concurrency_gate = ConcurrencyGate()
