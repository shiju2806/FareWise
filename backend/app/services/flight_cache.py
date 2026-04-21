"""Tenant-aware flight cache — wraps cache_service with company-prefixed v3 keys.

Key format:
    flights:v3:{company_id}:{origin}:{dest}:{date}:{cabin}
    monthcal:v3:{company_id}:{origin}:{dest}:{YYYY}:{MM}:{cabin}

Cache entries are scoped per-tenant so one company's search results never
leak into another's. The v3 suffix lets us cut over without colliding with
pre-tenancy v2 entries still in Redis.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.services.cache_service import (
    TTL_FLIGHT_PRICES,
    TTL_MONTH_CALENDAR,
    cache_service,
)

_CACHE_VERSION = "v3"


def _normalize(company_id: uuid.UUID | None) -> str:
    # None is reserved for background/system searches with no tenant context.
    return company_id.hex if company_id is not None else "system"


class FlightCache:
    """Tenant-scoped cache helpers for flight searches."""

    def flight_key(
        self,
        company_id: uuid.UUID | None,
        origin: str,
        dest: str,
        date_iso: str,
        cabin: str,
    ) -> str:
        return (
            f"flights:{_CACHE_VERSION}:{_normalize(company_id)}:"
            f"{origin}:{dest}:{date_iso}:{cabin}"
        )

    def month_calendar_key(
        self,
        company_id: uuid.UUID | None,
        origin: str,
        dest: str,
        year: int,
        month: int,
        cabin: str,
    ) -> str:
        return (
            f"monthcal:{_CACHE_VERSION}:{_normalize(company_id)}:"
            f"{origin}:{dest}:{year}:{month:02d}:{cabin}"
        )

    async def get_flights(
        self,
        company_id: uuid.UUID | None,
        origin: str,
        dest: str,
        date_iso: str,
        cabin: str,
    ) -> list[dict] | None:
        return await cache_service.get(
            self.flight_key(company_id, origin, dest, date_iso, cabin)
        )

    async def set_flights(
        self,
        company_id: uuid.UUID | None,
        origin: str,
        dest: str,
        date_iso: str,
        cabin: str,
        data: list[dict],
        ttl: int = TTL_FLIGHT_PRICES,
    ) -> None:
        await cache_service.set(
            self.flight_key(company_id, origin, dest, date_iso, cabin),
            data,
            ttl,
        )

    async def get_month_calendar(
        self,
        company_id: uuid.UUID | None,
        origin: str,
        dest: str,
        year: int,
        month: int,
        cabin: str,
    ) -> dict | None:
        return await cache_service.get(
            self.month_calendar_key(company_id, origin, dest, year, month, cabin)
        )

    async def set_month_calendar(
        self,
        company_id: uuid.UUID | None,
        origin: str,
        dest: str,
        year: int,
        month: int,
        cabin: str,
        data: dict,
        ttl: int = TTL_MONTH_CALENDAR,
    ) -> None:
        await cache_service.set(
            self.month_calendar_key(company_id, origin, dest, year, month, cabin),
            data,
            ttl,
        )


flight_cache = FlightCache()
