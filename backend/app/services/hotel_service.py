"""Hotel search service — orchestrates hotel search with event-aware pricing."""

import asyncio
import hashlib
import logging
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import HotelOption, HotelSearch, HotelSelection
from app.models.trip import TripLeg
from app.services.event_service import event_service

logger = logging.getLogger(__name__)

# Scoring weights
WEIGHT_PRICE = 0.40
WEIGHT_RATING = 0.25
WEIGHT_DISTANCE = 0.20
WEIGHT_VENDOR = 0.15

PREFERRED_CHAINS = {"Marriott", "Hilton", "IHG", "Hyatt"}

# Hotel chains for mocking
HOTEL_CHAINS = [
    ("Marriott", ["Courtyard by Marriott", "Residence Inn", "Marriott Downtown", "Fairfield Inn"]),
    ("Hilton", ["Hilton Garden Inn", "Hampton Inn", "DoubleTree by Hilton", "Hilton Downtown"]),
    ("IHG", ["Holiday Inn Express", "Holiday Inn", "Crowne Plaza", "InterContinental"]),
    ("Hyatt", ["Hyatt Place", "Hyatt Regency", "Grand Hyatt"]),
    ("Best Western", ["Best Western Plus", "Best Western Premier"]),
    ("Independent", ["City Center Hotel", "Airport Lodge", "The Metropolitan", "Urban Suites", "Park View Hotel"]),
]

NEIGHBORHOODS = [
    "Downtown", "Financial District", "Midtown", "Airport Area",
    "University District", "Waterfront", "Convention Center", "Arts District",
]


class HotelService:
    """Orchestrates hotel search with event-aware pricing and scoring."""

    async def search_hotels(
        self,
        db: AsyncSession,
        leg: TripLeg,
        check_in: date,
        check_out: date,
        guests: int = 1,
        max_nightly_rate: float | None = None,
        max_stars: float | None = None,
        sort_by: str = "value",
    ) -> dict:
        """Search hotels for a trip leg with events fetched in parallel."""
        destination = leg.destination_city

        # Parallel fetch: hotels + events
        hotels_task = asyncio.create_task(
            self._fetch_hotels(destination, check_in, check_out, guests)
        )
        events_task = asyncio.create_task(
            event_service.get_events(db, destination, check_in, check_out)
        )

        raw_hotels, events = await asyncio.gather(hotels_task, events_task)

        # Apply filters
        if max_nightly_rate:
            raw_hotels = [h for h in raw_hotels if h["nightly_rate"] <= max_nightly_rate]
        if max_stars:
            raw_hotels = [h for h in raw_hotels if h["star_rating"] <= max_stars]

        # Score and rank
        scored = self._score_hotels(raw_hotels)

        # Sort
        if sort_by == "price":
            scored.sort(key=lambda h: h["nightly_rate"])
        elif sort_by == "rating":
            scored.sort(key=lambda h: h.get("user_rating", 0), reverse=True)
        elif sort_by == "distance":
            scored.sort(key=lambda h: h.get("distance_km", 999))
        else:  # value (default)
            scored.sort(key=lambda h: h.get("score", 0), reverse=True)

        # Save search log
        search_log = HotelSearch(
            trip_leg_id=leg.id,
            city=destination,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            search_params={
                "max_nightly_rate": max_nightly_rate,
                "max_stars": max_stars,
                "sort_by": sort_by,
            },
            results_count=len(scored),
            cheapest_rate=Decimal(str(scored[0]["nightly_rate"])) if scored else None,
            most_expensive_rate=Decimal(str(scored[-1]["nightly_rate"])) if scored else None,
        )
        db.add(search_log)
        await db.flush()

        # Save hotel options
        saved_options = []
        for h in scored:
            option = HotelOption(
                hotel_search_id=search_log.id,
                hotel_name=h["hotel_name"],
                hotel_chain=h.get("hotel_chain"),
                star_rating=Decimal(str(h["star_rating"])) if h.get("star_rating") else None,
                user_rating=Decimal(str(h["user_rating"])) if h.get("user_rating") else None,
                address=h.get("address"),
                latitude=Decimal(str(h["latitude"])) if h.get("latitude") else None,
                longitude=Decimal(str(h["longitude"])) if h.get("longitude") else None,
                distance_km=Decimal(str(h["distance_km"])) if h.get("distance_km") else None,
                nightly_rate=Decimal(str(h["nightly_rate"])),
                total_rate=Decimal(str(h["total_rate"])),
                currency=h.get("currency", "CAD"),
                room_type=h.get("room_type"),
                amenities=h.get("amenities", []),
                cancellation_policy=h.get("cancellation_policy"),
                is_preferred_vendor=h.get("is_preferred_vendor", False),
            )
            db.add(option)
            await db.flush()
            h["id"] = str(option.id)
            saved_options.append(h)

        await db.commit()

        # Recommendation
        recommendation = saved_options[0] if saved_options else None

        # Area comparison
        area_comparison = self._area_comparison(saved_options)

        # Event warnings
        event_warnings = self._event_warnings(events, check_in, check_out)

        # Hotel price calendar (±3 days)
        price_calendar = self._hotel_price_calendar(
            destination, check_in, check_out, guests
        )

        nights = (check_out - check_in).days

        return {
            "search_id": str(search_log.id),
            "destination": destination,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "nights": nights,
            "guests": guests,
            "recommendation": recommendation,
            "all_options": saved_options,
            "area_comparison": area_comparison,
            "event_warnings": event_warnings,
            "events": events,
            "price_calendar": price_calendar,
            "metadata": {
                "total_options": len(saved_options),
                "cheapest_rate": saved_options[0]["nightly_rate"] if saved_options else None,
                "most_expensive_rate": saved_options[-1]["nightly_rate"] if saved_options else None,
            },
        }

    async def select_hotel(
        self,
        db: AsyncSession,
        leg: TripLeg,
        hotel_option_id: str,
        check_in: date,
        check_out: date,
        justification_note: str | None = None,
    ) -> dict:
        """Save a hotel selection for a trip leg."""
        import uuid

        # Verify option exists
        result = await db.execute(
            select(HotelOption).where(HotelOption.id == uuid.UUID(hotel_option_id))
        )
        option = result.scalar_one_or_none()
        if not option:
            raise ValueError("Hotel option not found")

        # Remove existing selection
        existing = await db.execute(
            select(HotelSelection).where(HotelSelection.trip_leg_id == leg.id)
        )
        for old in existing.scalars().all():
            await db.delete(old)

        selection = HotelSelection(
            trip_leg_id=leg.id,
            hotel_option_id=option.id,
            check_in=check_in,
            check_out=check_out,
            justification_note=justification_note,
        )
        db.add(selection)

        # Update leg hotel fields
        leg.needs_hotel = True
        leg.hotel_check_in = check_in
        leg.hotel_check_out = check_out

        await db.commit()

        return {
            "id": str(selection.id),
            "hotel_name": option.hotel_name,
            "nightly_rate": float(option.nightly_rate),
            "total_rate": float(option.total_rate),
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
        }

    def _score_hotels(self, hotels: list[dict]) -> list[dict]:
        """Score hotels using weighted factors."""
        if not hotels:
            return []

        prices = [h["nightly_rate"] for h in hotels]
        min_p, max_p = min(prices), max(prices)
        price_range = max_p - min_p if max_p > min_p else 1

        for h in hotels:
            # Price score (0-1, lower is better)
            price_score = 1 - ((h["nightly_rate"] - min_p) / price_range)

            # Rating score (0-1)
            rating_score = (h.get("user_rating", 3.0) or 3.0) / 5.0

            # Distance score (0-1, closer is better)
            dist = h.get("distance_km", 10.0) or 10.0
            distance_score = max(0, 1 - (dist / 20.0))

            # Vendor preference
            vendor_score = 1.0 if h.get("is_preferred_vendor") else 0.0

            score = (
                WEIGHT_PRICE * price_score
                + WEIGHT_RATING * rating_score
                + WEIGHT_DISTANCE * distance_score
                + WEIGHT_VENDOR * vendor_score
            )
            h["score"] = round(score, 3)

        return hotels

    def _area_comparison(self, hotels: list[dict]) -> list[dict]:
        """Group hotels by neighborhood and compute stats."""
        areas: dict[str, list[float]] = {}
        for h in hotels:
            area = h.get("neighborhood", "Other")
            if area not in areas:
                areas[area] = []
            areas[area].append(h["nightly_rate"])

        return [
            {
                "area": area,
                "avg_rate": round(sum(rates) / len(rates), 2),
                "min_rate": round(min(rates), 2),
                "max_rate": round(max(rates), 2),
                "option_count": len(rates),
            }
            for area, rates in sorted(areas.items(), key=lambda x: sum(x[1]) / len(x[1]))
        ]

    def _event_warnings(
        self, events: list[dict], check_in: date, check_out: date
    ) -> list[dict]:
        """Generate actionable warnings for events during stay."""
        warnings = []
        for evt in events:
            if evt["impact_level"] in ("high", "very_high"):
                warnings.append({
                    "title": evt["title"],
                    "category": evt["category"],
                    "impact_level": evt["impact_level"],
                    "dates": f"{evt['start_date']} to {evt['end_date']}",
                    "message": (
                        f"{evt['title']} ({evt['category']}) may increase hotel rates "
                        f"by ~{int(evt['price_increase_pct'] * 100)}%. "
                        f"Book early or consider alternative dates."
                    ),
                })
        return warnings

    def _hotel_price_calendar(
        self,
        city: str,
        check_in: date,
        check_out: date,
        guests: int,
    ) -> list[dict]:
        """Generate hotel price calendar ±3 days."""
        seed_str = f"hotel_{city}_{check_in.isoformat()}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        base_rate = self._estimate_base_rate(city)
        nights = max(1, (check_out - check_in).days)
        results = []

        for offset in range(-3, 4):
            ci = check_in + timedelta(days=offset)
            co = ci + timedelta(days=nights)

            # Day-of-week pricing
            day_factor = {0: 0.95, 1: 0.90, 2: 0.90, 3: 0.95, 4: 1.15, 5: 1.20, 6: 1.10}.get(
                ci.weekday(), 1.0
            )
            rate = round(base_rate * day_factor * rng.uniform(0.85, 1.15), 2)
            total = round(rate * nights, 2)

            results.append({
                "check_in": ci.isoformat(),
                "check_out": co.isoformat(),
                "nightly_rate": rate,
                "total_rate": total,
                "is_preferred": offset == 0,
            })

        return results

    async def _fetch_hotels(
        self, city: str, check_in: date, check_out: date, guests: int
    ) -> list[dict]:
        """Fetch hotels — mock for now, Amadeus integration in future."""
        return self._generate_mock_hotels(city, check_in, check_out, guests)

    def _generate_mock_hotels(
        self, city: str, check_in: date, check_out: date, guests: int
    ) -> list[dict]:
        """Generate realistic mock hotel data."""
        seed_str = f"hotel_{city}_{check_in.isoformat()}_{check_out.isoformat()}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        base_rate = self._estimate_base_rate(city)
        nights = max(1, (check_out - check_in).days)
        num_hotels = rng.randint(8, 15)

        hotels = []
        for i in range(num_hotels):
            chain_name, hotel_names = rng.choice(HOTEL_CHAINS)
            hotel_name = rng.choice(hotel_names)
            neighborhood = rng.choice(NEIGHBORHOODS)

            star = rng.choice([3.0, 3.5, 4.0, 4.5, 5.0])
            star_multiplier = {3.0: 0.7, 3.5: 0.85, 4.0: 1.0, 4.5: 1.25, 5.0: 1.6}.get(star, 1.0)

            nightly = round(base_rate * star_multiplier * rng.uniform(0.8, 1.3), 2)
            total = round(nightly * nights, 2)
            user_rating = round(rng.uniform(3.2, 4.8), 1)
            distance = round(rng.uniform(0.5, 15.0), 1)

            is_preferred = chain_name in PREFERRED_CHAINS
            cancel = rng.choice(["free_cancellation", "non_refundable", "24h_cancellation"])
            room_type = rng.choice(["Standard Room", "Queen Room", "King Room", "Suite", "Double Room"])
            amenities = rng.sample(
                ["wifi", "breakfast", "parking", "gym", "pool", "business_center", "restaurant", "spa"],
                rng.randint(3, 6),
            )

            hotels.append({
                "hotel_name": f"{hotel_name} {city}" if "Downtown" not in hotel_name else hotel_name,
                "hotel_chain": chain_name if chain_name != "Independent" else None,
                "star_rating": star,
                "user_rating": user_rating,
                "address": f"{rng.randint(100, 999)} {neighborhood} Ave, {city}",
                "latitude": None,
                "longitude": None,
                "distance_km": distance,
                "nightly_rate": nightly,
                "total_rate": total,
                "currency": "CAD",
                "room_type": room_type,
                "amenities": amenities,
                "cancellation_policy": cancel,
                "is_preferred_vendor": is_preferred,
                "neighborhood": neighborhood,
            })

        return sorted(hotels, key=lambda h: h["nightly_rate"])

    @staticmethod
    def _estimate_base_rate(city: str) -> float:
        """Rough base hotel rate by city."""
        city_lower = city.lower()
        expensive = ["new york", "san francisco", "london", "tokyo", "paris", "zurich"]
        moderate = ["chicago", "toronto", "vancouver", "seattle", "boston", "los angeles"]
        budget = ["calgary", "ottawa", "portland", "austin"]

        if any(c in city_lower for c in expensive):
            return 280
        if any(c in city_lower for c in moderate):
            return 200
        if any(c in city_lower for c in budget):
            return 150
        return 180


hotel_service = HotelService()
