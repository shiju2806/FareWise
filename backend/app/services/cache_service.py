"""Redis cache service for flight prices, airport data, and calendar data."""

import json
import logging
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

# TTLs in seconds
TTL_FLIGHT_PRICES = 15 * 60       # 15 minutes
TTL_AIRPORT_DATA = 24 * 60 * 60   # 24 hours
TTL_CALENDAR = 30 * 60            # 30 minutes
TTL_ANALYTICS = 24 * 60 * 60      # 24 hours — seasonality data
TTL_ADVISOR = 30 * 60             # 30 minutes — LLM advisor results
TTL_MONTH_CALENDAR = 60 * 60      # 1 hour — month calendar prices
TTL_PRICE_METRICS = 24 * 60 * 60  # 24 hours — historical quartile data


class CacheService:
    """Redis-backed cache with typed TTLs."""

    def __init__(self):
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis | None:
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable, cache disabled: {e}")
                self._redis = None
                return None
        return self._redis

    async def get(self, key: str) -> Any | None:
        """Get a value from cache. Returns None on miss or error."""
        try:
            r = await self._get_redis()
            if r is None:
                return None
            raw = await r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int = TTL_FLIGHT_PRICES) -> bool:
        """Set a value in cache with TTL. Returns False on error."""
        try:
            r = await self._get_redis()
            if r is None:
                return False
            await r.set(key, json.dumps(value, default=str), ex=ttl)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key."""
        try:
            r = await self._get_redis()
            if r is None:
                return False
            await r.delete(key)
            return True
        except Exception:
            return False

    # Typed helpers

    def flight_key(self, origin: str, dest: str, date: str, cabin: str) -> str:
        return f"flights:{origin}:{dest}:{date}:{cabin}"

    def calendar_key(self, origin: str, dest: str, center_date: str) -> str:
        return f"calendar:{origin}:{dest}:{center_date}"

    def airport_key(self, city: str) -> str:
        return f"airports:{city.lower()}"

    async def get_flights(self, origin: str, dest: str, date: str, cabin: str) -> list[dict] | None:
        return await self.get(self.flight_key(origin, dest, date, cabin))

    async def set_flights(self, origin: str, dest: str, date: str, cabin: str, data: list[dict]):
        await self.set(self.flight_key(origin, dest, date, cabin), data, TTL_FLIGHT_PRICES)

    async def get_calendar(self, origin: str, dest: str, center_date: str) -> list[dict] | None:
        return await self.get(self.calendar_key(origin, dest, center_date))

    async def set_calendar(self, origin: str, dest: str, center_date: str, data: list[dict]):
        await self.set(self.calendar_key(origin, dest, center_date), data, TTL_CALENDAR)

    async def get_airport_data(self, city: str) -> list[dict] | None:
        return await self.get(self.airport_key(city))

    async def set_airport_data(self, city: str, data: list[dict]):
        await self.set(self.airport_key(city), data, TTL_AIRPORT_DATA)

    # Analytics + Advisor helpers

    def analytics_key(self, city_code: str, direction: str = "ARRIVING") -> str:
        return f"analytics:busiest:{city_code}:{direction}"

    def most_booked_key(self, origin: str, period: str) -> str:
        return f"analytics:booked:{origin}:{period}"

    def advisor_key(self, search_id: str) -> str:
        return f"advisor:{search_id}"

    def month_calendar_key(self, origin: str, dest: str, year: int, month: int, cabin: str) -> str:
        return f"monthcal:{origin}:{dest}:{year}:{month:02d}:{cabin}"

    async def get_analytics(self, city_code: str, direction: str = "ARRIVING") -> dict | None:
        return await self.get(self.analytics_key(city_code, direction))

    async def set_analytics(self, city_code: str, data: dict, direction: str = "ARRIVING"):
        await self.set(self.analytics_key(city_code, direction), data, TTL_ANALYTICS)

    async def get_advisor(self, search_id: str) -> dict | None:
        return await self.get(self.advisor_key(search_id))

    async def set_advisor(self, search_id: str, data: dict):
        await self.set(self.advisor_key(search_id), data, TTL_ADVISOR)

    async def get_month_calendar(self, origin: str, dest: str, year: int, month: int, cabin: str) -> dict | None:
        return await self.get(self.month_calendar_key(origin, dest, year, month, cabin))

    async def set_month_calendar(self, origin: str, dest: str, year: int, month: int, cabin: str, data: dict):
        await self.set(self.month_calendar_key(origin, dest, year, month, cabin), data, TTL_MONTH_CALENDAR)

    # Price metrics (historical quartiles)

    def price_metrics_key(self, origin: str, dest: str, date_str: str) -> str:
        return f"pricemetrics:{origin}:{dest}:{date_str}"

    async def get_price_metrics(self, origin: str, dest: str, date_str: str) -> dict | None:
        return await self.get(self.price_metrics_key(origin, dest, date_str))

    async def set_price_metrics(self, origin: str, dest: str, date_str: str, data: dict):
        await self.set(self.price_metrics_key(origin, dest, date_str), data, TTL_PRICE_METRICS)

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


cache_service = CacheService()
