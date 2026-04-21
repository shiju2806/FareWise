"""Per-company FlightAPI credit budget gate.

FlightAPI.io bills in credits per call. On the Lite plan each tenant must
stay inside its monthly allotment (Company.credit_budget_monthly, falling
back to settings.flightapi_default_credit_budget). This gate:

    1. Reads the tenant's budget (cached per request path).
    2. Reserves `credits_per_search` credits atomically before calling upstream.
    3. On upstream failure, refunds the reservation so we don't over-bill.

Backing store is Redis (INCRBY keyed by month) so multiple workers share the
counter. When Redis is unavailable we fall back to an in-process dict and log
a warning — the gate still prevents unbounded runaway within a single worker
but does not enforce cross-worker limits.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from calendar import monthrange
from datetime import date, datetime, timezone

from app.config import settings
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)


class CreditBudgetExceeded(Exception):
    """Raised when a company has no credits remaining for the current month."""

    def __init__(self, company_id: uuid.UUID, remaining: int, budget: int):
        super().__init__(
            f"FlightAPI monthly budget exceeded for company {company_id}: "
            f"remaining={remaining}, budget={budget}"
        )
        self.company_id = company_id
        self.remaining = remaining
        self.budget = budget


def _month_bucket(today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    return f"{today.year}-{today.month:02d}"


def _seconds_until_month_end(today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    _, days_in_month = monthrange(today.year, today.month)
    last_day = date(today.year, today.month, days_in_month)
    # Expire one day after the end of the month so we don't clip billing boundaries.
    days_left = (last_day - today).days + 1
    return days_left * 24 * 60 * 60


class CreditBudgetGate:
    """Monthly per-company credit ceiling, Redis-backed with in-memory fallback."""

    def __init__(self) -> None:
        self._local_counts: dict[tuple[uuid.UUID, str], int] = {}
        self._lock = asyncio.Lock()

    def _redis_key(self, company_id: uuid.UUID, bucket: str) -> str:
        return f"flightapi:credits:{company_id.hex}:{bucket}"

    async def _resolve_budget(self, company_id: uuid.UUID) -> int:
        """Resolve the per-company monthly budget.

        Looks up Company.credit_budget_monthly first; falls back to the global
        default. Returns 0 if the tenant is explicitly capped at zero.
        """
        from app.database import async_session_factory
        from app.models.company import Company
        from sqlalchemy import select

        async with async_session_factory() as db:
            result = await db.execute(
                select(Company.credit_budget_monthly).where(Company.id == company_id)
            )
            budget = result.scalar_one_or_none()

        if budget is None:
            return settings.flightapi_default_credit_budget
        return int(budget)

    async def _current_spend(self, company_id: uuid.UUID, bucket: str) -> int:
        r = await cache_service._get_redis()
        if r is None:
            return self._local_counts.get((company_id, bucket), 0)
        try:
            raw = await r.get(self._redis_key(company_id, bucket))
            return int(raw) if raw is not None else 0
        except Exception as e:
            logger.warning("Credit gate redis read failed, falling back: %s", e)
            return self._local_counts.get((company_id, bucket), 0)

    async def remaining(self, company_id: uuid.UUID) -> int:
        budget = await self._resolve_budget(company_id)
        spent = await self._current_spend(company_id, _month_bucket())
        return max(0, budget - spent)

    async def reserve(self, company_id: uuid.UUID, credits: int | None = None) -> int:
        """Reserve `credits` for a pending upstream call.

        Raises CreditBudgetExceeded if the reservation would breach the budget.
        Returns the new spend count for logging/observability.
        """
        if credits is None:
            credits = settings.flightapi_credits_per_search

        budget = await self._resolve_budget(company_id)
        bucket = _month_bucket()
        ttl = _seconds_until_month_end()
        key = self._redis_key(company_id, bucket)

        r = await cache_service._get_redis()
        if r is None:
            async with self._lock:
                current = self._local_counts.get((company_id, bucket), 0)
                if current + credits > budget:
                    raise CreditBudgetExceeded(
                        company_id, max(0, budget - current), budget
                    )
                self._local_counts[(company_id, bucket)] = current + credits
                return current + credits

        try:
            new_spend = await r.incrby(key, credits)
            # Set expiry on first increment only (won't reset existing TTL)
            if new_spend == credits:
                await r.expire(key, ttl)
        except Exception as e:
            logger.warning("Credit gate redis write failed, falling back: %s", e)
            async with self._lock:
                current = self._local_counts.get((company_id, bucket), 0)
                if current + credits > budget:
                    raise CreditBudgetExceeded(
                        company_id, max(0, budget - current), budget
                    )
                self._local_counts[(company_id, bucket)] = current + credits
                return current + credits

        if new_spend > budget:
            # Roll back this reservation and fail
            try:
                await r.decrby(key, credits)
            except Exception:
                pass
            raise CreditBudgetExceeded(
                company_id, max(0, budget - (new_spend - credits)), budget
            )
        return int(new_spend)

    async def refund(self, company_id: uuid.UUID, credits: int | None = None) -> None:
        """Refund a reservation — call this on upstream failure."""
        if credits is None:
            credits = settings.flightapi_credits_per_search

        bucket = _month_bucket()
        r = await cache_service._get_redis()
        if r is None:
            async with self._lock:
                current = self._local_counts.get((company_id, bucket), 0)
                self._local_counts[(company_id, bucket)] = max(0, current - credits)
            return

        try:
            await r.decrby(self._redis_key(company_id, bucket), credits)
        except Exception as e:
            logger.warning("Credit gate refund failed: %s", e)
            async with self._lock:
                current = self._local_counts.get((company_id, bucket), 0)
                self._local_counts[(company_id, bucket)] = max(0, current - credits)


credit_budget_gate = CreditBudgetGate()
