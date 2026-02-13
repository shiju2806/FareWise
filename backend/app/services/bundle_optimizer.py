"""Bundle optimizer — finds optimal flight + hotel date combinations."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trip import TripLeg
from app.services.amadeus_client import amadeus_client
from app.services.event_service import event_service
from app.services.hotel_service import hotel_service

logger = logging.getLogger(__name__)


class BundleOptimizer:
    """Finds optimal flight + hotel combinations across flexible dates."""

    async def optimize(
        self,
        db: AsyncSession,
        leg: TripLeg,
        hotel_nights: int = 3,
        flexibility_days: int | None = None,
    ) -> dict:
        """Build date matrix and return top 3 bundle strategies."""
        flex = flexibility_days if flexibility_days is not None else leg.flexibility_days
        preferred = leg.preferred_date
        origin = leg.origin_airport
        destination = leg.destination_airport
        destination_city = leg.destination_city
        cabin = leg.cabin_class

        # Generate candidate dates
        candidates = []
        for offset in range(-flex, flex + 1):
            dep_date = preferred + timedelta(days=offset)
            candidates.append(dep_date)

        # Fetch flight prices for each candidate date
        flight_prices: dict[str, float] = {}
        for d in candidates:
            flights = await amadeus_client.search_flight_offers(
                origin=origin,
                destination=destination,
                departure_date=d,
                cabin_class=cabin,
                adults=leg.passengers,
                max_results=5,
            )
            if flights:
                cheapest = min(f["price"] for f in flights)
                flight_prices[d.isoformat()] = cheapest

        # Fetch events for the date range
        date_from = candidates[0]
        date_to = candidates[-1] + timedelta(days=hotel_nights)
        events = await event_service.get_events(db, destination_city, date_from, date_to)

        # Build event annotations by date
        event_by_date: dict[str, list[str]] = {}
        for evt in events:
            s = date.fromisoformat(evt["start_date"])
            e = date.fromisoformat(evt["end_date"])
            d = s
            while d <= e:
                ds = d.isoformat()
                if ds not in event_by_date:
                    event_by_date[ds] = []
                event_by_date[ds].append(evt["title"])
                d += timedelta(days=1)

        # Generate hotel estimates for each check-in date
        hotel_rates: dict[str, float] = {}
        for d in candidates:
            ci = d
            co = d + timedelta(days=hotel_nights)
            cal = hotel_service._hotel_price_calendar(destination_city, ci, co, 1)
            # Use the preferred entry (offset 0)
            preferred_entry = next((c for c in cal if c["is_preferred"]), cal[0])
            hotel_rates[d.isoformat()] = preferred_entry["nightly_rate"]

        # Build date matrix
        date_matrix = []
        for d in candidates:
            ds = d.isoformat()
            flight_cost = flight_prices.get(ds)
            hotel_nightly = hotel_rates.get(ds)

            if flight_cost is None or hotel_nightly is None:
                continue

            hotel_total = hotel_nightly * hotel_nights
            combined = flight_cost + hotel_total
            per_night = combined / hotel_nights if hotel_nights > 0 else combined

            date_events = event_by_date.get(ds, [])

            date_matrix.append({
                "departure_date": ds,
                "check_in": ds,
                "check_out": (d + timedelta(days=hotel_nights)).isoformat(),
                "flight_cost": round(flight_cost, 2),
                "hotel_nightly": round(hotel_nightly, 2),
                "hotel_total": round(hotel_total, 2),
                "combined_total": round(combined, 2),
                "per_night_total": round(per_night, 2),
                "events": date_events,
                "is_preferred": d == preferred,
            })

        if not date_matrix:
            return {
                "bundles": [],
                "date_matrix": [],
                "events": events,
                "message": "No flight/hotel combinations found",
            }

        # Sort strategies
        preferred_bundle = next((b for b in date_matrix if b["is_preferred"]), date_matrix[0])
        preferred_total = preferred_bundle["combined_total"]

        # Best value (lowest per-night combined)
        by_per_night = sorted(date_matrix, key=lambda b: b["per_night_total"])
        best_value = by_per_night[0]
        best_value["strategy"] = "best_value"
        best_value["label"] = "Best Value"
        best_value["savings_vs_preferred"] = round(preferred_total - best_value["combined_total"], 2)

        # Cheapest absolute
        by_total = sorted(date_matrix, key=lambda b: b["combined_total"])
        cheapest = by_total[0]
        cheapest["strategy"] = "cheapest"
        cheapest["label"] = "Cheapest"
        cheapest["savings_vs_preferred"] = round(preferred_total - cheapest["combined_total"], 2)

        # Preferred dates
        preferred_bundle["strategy"] = "preferred"
        preferred_bundle["label"] = "Your Dates"
        preferred_bundle["savings_vs_preferred"] = 0

        # Deduplicate bundles
        seen = set()
        bundles = []
        for b in [best_value, preferred_bundle, cheapest]:
            key = b["departure_date"]
            if key not in seen:
                seen.add(key)
                bundles.append(b)

        return {
            "bundles": bundles[:3],
            "date_matrix": date_matrix,
            "events": events,
            "hotel_nights": hotel_nights,
            "destination": destination_city,
            "preferred_date": preferred.isoformat(),
        }


bundle_optimizer = BundleOptimizer()
