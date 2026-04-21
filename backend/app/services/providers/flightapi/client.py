"""Thin httpx client for FlightAPI.io.

This is the foundation — it wires up one-way search with correct auth and
response normalization. Round-trip, multi-city, fare rules, and historical
endpoints will land in follow-up PRs once the gate/cache/coalesce layer has
been proven in production.

FlightAPI.io's `onewaytrip` endpoint:
    GET /onewaytrip/{api_key}/{from}/{to}/{date}/{adults}/{children}/{infants}/{cabin}/{currency}

Response is deeply nested (itineraries → legs → segments) so we flatten into
the common FlightDict shape used by the rest of the app.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CABIN_MAP = {
    "economy": "Economy",
    "premium_economy": "Premium_Economy",
    "business": "Business",
    "first": "First",
}


class FlightAPIClient:
    """HTTP client for FlightAPI.io. No gating — callers must wrap in gates."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.flightapi_base_url,
                timeout=settings.flightapi_request_timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def is_configured(self) -> bool:
        return bool(settings.flightapi_api_key)

    async def search_one_way(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
        adults: int = 1,
        currency: str = "USD",
    ) -> list[dict[str, Any]]:
        """Fetch one-way flight offers for a single date.

        Returns a list of flattened FlightDict entries. Empty list on empty
        upstream response. Raises httpx.HTTPError on network/HTTP failure so
        the caller can refund credits.
        """
        if not self.is_configured():
            logger.warning("FlightAPI client has no api_key — returning empty")
            return []

        cabin = _CABIN_MAP.get(cabin_class.lower(), "Economy")
        path = (
            f"/onewaytrip/{settings.flightapi_api_key}/"
            f"{origin.upper()}/{destination.upper()}/"
            f"{departure_date.isoformat()}/"
            f"{adults}/0/0/{cabin}/{currency}"
        )

        client = await self._get_client()
        response = await client.get(path)
        response.raise_for_status()
        data = response.json()
        return self._flatten_offers(data)

    @staticmethod
    def _flatten_offers(raw: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten FlightAPI's nested shape into FlightDict entries."""
        itineraries = raw.get("itineraries") or []
        legs = {l.get("id"): l for l in raw.get("legs") or []}
        segments = {s.get("id"): s for s in raw.get("segments") or []}
        carriers = {c.get("id"): c for c in raw.get("carriers") or []}

        results: list[dict[str, Any]] = []
        for it in itineraries:
            pricing = (it.get("pricing_options") or [{}])[0]
            price = pricing.get("price", {}).get("amount")
            if price is None:
                continue

            leg_ids = it.get("leg_ids") or []
            first_leg = legs.get(leg_ids[0]) if leg_ids else None
            if first_leg is None:
                continue

            seg_ids = first_leg.get("segment_ids") or []
            first_seg = segments.get(seg_ids[0]) if seg_ids else {}
            carrier = carriers.get(first_seg.get("marketing_carrier_id"))

            results.append({
                "airline_code": (carrier or {}).get("iata", ""),
                "airline_name": (carrier or {}).get("name", ""),
                "price": float(price),
                "currency": pricing.get("price", {}).get("currency", "USD"),
                "stops": max(0, len(seg_ids) - 1),
                "departure_time": first_seg.get("departure"),
                "arrival_time": first_seg.get("arrival"),
                "duration_minutes": first_leg.get("duration"),
                "source": "flightapi",
            })
        return results


flight_api_client = FlightAPIClient()
