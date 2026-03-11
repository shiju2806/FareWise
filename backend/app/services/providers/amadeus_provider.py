"""Amadeus provider — wraps AmadeusClient behind the FlightDataProvider protocol."""

import asyncio
import logging
from calendar import monthrange
from datetime import date, timedelta

from app.config import settings

logger = logging.getLogger(__name__)


class AmadeusProvider:
    """FlightDataProvider backed by Amadeus Self-Service API."""

    async def initialize(self) -> None:
        if not settings.amadeus_client_id:
            logger.warning("Amadeus provider has no credentials — will return empty results")
        logger.info("Amadeus provider initialized")

    async def shutdown(self) -> None:
        from app.services.amadeus_client import amadeus_client
        await amadeus_client.close()
        logger.info("Amadeus provider shut down")

    def is_available(self) -> bool:
        return bool(settings.amadeus_client_id)

    async def search_flights(self, origin: str, destination: str, departure_date: date, cabin_class: str = "economy") -> list[dict]:
        from app.services.amadeus_client import amadeus_client
        return await amadeus_client.search_flight_offers(
            origin=origin, destination=destination,
            departure_date=departure_date, cabin_class=cabin_class,
        )

    async def search_flights_date_range(self, origin: str, destination: str, start_date: date, end_date: date, cabin_class: str = "economy") -> dict[str, list[dict]]:
        """No native Amadeus equivalent — concurrent search_flights per date."""
        tasks = {}
        current = start_date
        while current <= end_date:
            tasks[current.isoformat()] = self.search_flights(origin, destination, current, cabin_class)
            current += timedelta(days=1)

        keys = list(tasks.keys())
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        results = {}
        for key, result in zip(keys, gathered):
            if isinstance(result, Exception):
                logger.warning(f"Amadeus date-range search failed for {key}: {result}")
                results[key] = []
            else:
                results[key] = result
        return results

    async def search_month_prices(self, origin: str, destination: str, year: int, month: int, cabin_class: str = "economy") -> dict[str, dict]:
        from app.services.amadeus_client import amadeus_client
        first_of_month = date(year, month, 1)
        raw = await amadeus_client.search_cheapest_dates(origin, destination, first_of_month)
        if not raw:
            return {}

        results = {}
        prefix = f"{year}-{month:02d}"
        for entry in raw:
            d = entry.get("date", "")
            if d.startswith(prefix):
                results[d] = {
                    "min_price": entry["price"],
                    "has_direct": None,
                    "option_count": 1,
                    "source": "amadeus",
                }
        return results

    async def search_month_matrix(self, origin: str, destination: str, year: int, month: int, cabin_class: str = "economy") -> list[dict]:
        """Synthesize from concurrent search_flights calls."""
        _, days_in_month = monthrange(year, month)
        dates = [date(year, month, day) for day in range(1, days_in_month + 1)]
        tasks = [self.search_flights(origin, destination, d, cabin_class) for d in dates]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        entries = []
        for d, result in zip(dates, gathered):
            if isinstance(result, Exception) or not result:
                continue
            by_airline: dict[str, dict] = {}
            for f in result:
                ac = f.get("airline_code", "")
                if ac not in by_airline or f["price"] < by_airline[ac]["price"]:
                    by_airline[ac] = f
            for ac, f in by_airline.items():
                entries.append({
                    "airline_code": ac,
                    "airline_name": f.get("airline_name", ac),
                    "date": d.isoformat(),
                    "price": f["price"],
                    "stops": f.get("stops", 0),
                })
        return entries

    async def get_price_context(self, origin: str, destination: str, departure_date: date, cabin_class: str = "economy", current_price: float | None = None) -> dict | None:
        from app.services.amadeus_client import amadeus_client
        metrics = await amadeus_client.get_price_metrics(
            origin=origin, destination=destination, departure_date=departure_date,
        )
        if not metrics:
            return None

        ref_price = current_price or metrics.get("median", 0)
        price_range = metrics.get("max", 0) - metrics.get("min", 0)
        if price_range > 0 and ref_price > 0:
            percentile = round(((ref_price - metrics["min"]) / price_range) * 100)
            percentile = max(0, min(100, percentile))
        else:
            percentile = 50

        if percentile <= 25:
            label = "excellent"
        elif percentile <= 50:
            label = "good"
        elif percentile <= 75:
            label = "average"
        else:
            label = "high"

        return {
            "available": True,
            "route": f"{origin}-{destination}",
            "date": departure_date.isoformat(),
            "historical": metrics,
            "current_price": ref_price,
            "percentile": percentile,
            "percentile_label": label,
        }
