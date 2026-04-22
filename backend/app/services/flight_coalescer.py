"""In-process request coalescer — collapse identical concurrent searches
into a single upstream call.

When N callers ask for the same (company, route, date, cabin) at the same
time, only one HTTP call fires; the other N-1 await the same Future. This
saves FlightAPI credits and is especially valuable when multiple legs of a
trip trigger overlapping month-calendar reads.

The coalescer is per-process (not Redis). That's intentional — the goal is
to fold simultaneous in-flight requests, not to cache across workers. The
distributed cache (flight_cache) handles cross-worker deduplication.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class RequestCoalescer:
    """Coalesce concurrent identical async operations by key."""

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    async def run(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Run `factory()` exactly once per `key` for concurrent callers.

        If another coroutine is already running the same key, this call awaits
        that in-flight Future instead of invoking `factory` again. Once the
        Future resolves (or fails), the entry is cleared so subsequent calls
        trigger a fresh invocation.
        """
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None and not existing.done():
                logger.debug("Coalescing request for key=%s", key)
                future = existing
                owner = False
            else:
                future = asyncio.get_running_loop().create_future()
                self._inflight[key] = future
                owner = True

        if not owner:
            return await future

        try:
            result = await factory()
        except BaseException as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            async with self._lock:
                # Clear only if this future is still the registered one.
                if self._inflight.get(key) is future:
                    del self._inflight[key]

    def inflight_count(self) -> int:
        return sum(1 for f in self._inflight.values() if not f.done())


flight_coalescer = RequestCoalescer()
