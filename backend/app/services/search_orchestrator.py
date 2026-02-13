"""Search orchestrator — coordinates full flight search for a trip leg."""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_log import FlightOption, SearchLog
from app.models.trip import Trip, TripLeg
from app.services.amadeus_client import amadeus_client
from app.services.airport_service import airport_service
from app.services.cache_service import cache_service
from app.services.scoring_engine import Weights, score_flights, slider_to_weights

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    """Coordinates search across dates, airports, and providers."""

    async def search_leg(
        self,
        db: AsyncSession,
        leg: TripLeg,
        weights: Weights | None = None,
        include_nearby: bool = True,
    ) -> dict:
        """
        Execute full search for a trip leg.

        Returns dict with: search_id, price_calendar, recommendation,
        alternatives, all_options, metadata.
        """
        start_time = time.monotonic()

        if weights is None:
            weights = Weights()

        # 1. Resolve airport combos
        origin_airports = [leg.origin_airport]
        dest_airports = [leg.destination_airport]

        if include_nearby:
            nearby_origins = await airport_service.get_nearby_airports(db, leg.origin_airport)
            nearby_dests = await airport_service.get_nearby_airports(db, leg.destination_airport)
            origin_airports.extend(a["iata"] for a in nearby_origins)
            dest_airports.extend(a["iata"] for a in nearby_dests)

        # 2. Build date range (±flexibility_days, capped at 7)
        flex = min(leg.flexibility_days, 7)
        dates = [
            leg.preferred_date + timedelta(days=d)
            for d in range(-flex, flex + 1)
        ]

        # 3. Build search matrix and execute searches in parallel
        all_flights: list[dict] = []
        airports_searched = set()

        # Build task list for parallel execution
        search_tasks = []
        for orig in origin_airports:
            for dest in dest_airports:
                if orig == dest:
                    continue
                airports_searched.add(orig)
                airports_searched.add(dest)
                for d in dates:
                    search_tasks.append((
                        orig, dest, d, leg.cabin_class, leg.passengers,
                        orig != leg.origin_airport or dest != leg.destination_airport,
                        d != leg.preferred_date,
                    ))

        # Execute in parallel batches of 10 (Amadeus rate limit)
        batch_size = 10
        for i in range(0, len(search_tasks), batch_size):
            batch = search_tasks[i:i + batch_size]
            coros = [
                self._search_with_cache(
                    orig, dest, d, cabin, pax,
                    is_alt_airport=is_alt_ap,
                    is_alt_date=is_alt_dt,
                )
                for orig, dest, d, cabin, pax, is_alt_ap, is_alt_dt in batch
            ]
            results = await asyncio.gather(*coros, return_exceptions=True)
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    task = batch[idx]
                    logger.warning(f"Search task failed for {task[0]}->{task[1]} on {task[2]}: {result}")
                else:
                    all_flights.extend(result)

        # 4. Deduplicate flights (same flight_number + departure_time)
        seen = set()
        unique_flights = []
        for f in all_flights:
            key = (f.get("flight_numbers", ""), f.get("departure_time", ""))
            if key not in seen:
                seen.add(key)
                unique_flights.append(f)
        all_flights = unique_flights

        # 5. Score all flights
        scored_flights = score_flights(all_flights, weights)

        # 7. Build price calendar
        price_calendar = self._build_price_calendar(
            all_flights, leg.preferred_date
        )

        # 8. Group alternatives
        alternatives = self._group_alternatives(
            scored_flights, leg.origin_airport, leg.destination_airport, leg.preferred_date
        )

        # 9. Build response data first (to know which flights to persist)
        main_options = [
            f for f in scored_flights
            if not f.get("is_alternate_airport") and not f.get("is_alternate_date")
        ][:50]

        recommendation = None
        if scored_flights:
            best = scored_flights[0]
            recommendation = {
                **best,
                "reason": self._generate_reason(best, scored_flights, leg),
            }

        # Collect all flights that appear in the response
        response_flights: list[dict] = []
        seen_ids = set()
        for f in main_options:
            key = id(f)
            if key not in seen_ids:
                seen_ids.add(key)
                response_flights.append(f)
        if recommendation:
            key = id(recommendation)
            if key not in seen_ids:
                seen_ids.add(key)
                response_flights.append(recommendation)
        for cat in alternatives.values():
            for f in cat:
                key = id(f)
                if key not in seen_ids:
                    seen_ids.add(key)
                    response_flights.append(f)

        # 10. Save response flights to database (assigns real DB IDs)
        search_log = await self._save_search_log(
            db, leg, response_flights, start_time,
            total_results_count=len(all_flights),
        )

        # Ensure all flights have IDs (fallback if DB save failed)
        for f in response_flights:
            if not f.get("id"):
                f["id"] = str(uuid.uuid4())

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return {
            "search_id": str(search_log.id) if search_log else str(uuid.uuid4()),
            "leg": {
                "origin": leg.origin_airport,
                "destination": leg.destination_airport,
                "preferred_date": leg.preferred_date.isoformat(),
            },
            "price_calendar": price_calendar,
            "recommendation": recommendation,
            "alternatives": alternatives,
            "all_options": main_options,
            "metadata": {
                "total_options_found": len(all_flights),
                "airports_searched": sorted(airports_searched),
                "dates_searched": [d.isoformat() for d in dates],
                "cached": False,
                "search_time_ms": elapsed_ms,
            },
        }

    async def rescore_leg(
        self,
        db: AsyncSession,
        leg: TripLeg,
        weights: Weights,
    ) -> dict:
        """Rescore existing search results with new weights."""
        # Get the most recent search log for this leg
        result = await db.execute(
            select(SearchLog)
            .where(SearchLog.trip_leg_id == leg.id)
            .order_by(SearchLog.searched_at.desc())
            .limit(1)
        )
        search_log = result.scalar_one_or_none()

        if not search_log:
            return {"recommendation": None, "rescored_options": []}

        # Fetch all flight options for this search
        result = await db.execute(
            select(FlightOption).where(FlightOption.search_log_id == search_log.id)
        )
        options = result.scalars().all()

        flights = [
            {
                "id": str(opt.id),
                "airline_code": opt.airline_code,
                "airline_name": opt.airline_name,
                "flight_numbers": opt.flight_numbers,
                "origin_airport": opt.origin_airport,
                "destination_airport": opt.destination_airport,
                "departure_time": opt.departure_time.isoformat() if opt.departure_time else "",
                "arrival_time": opt.arrival_time.isoformat() if opt.arrival_time else "",
                "duration_minutes": opt.duration_minutes,
                "stops": opt.stops,
                "stop_airports": opt.stop_airports,
                "price": float(opt.price),
                "currency": opt.currency,
                "cabin_class": opt.cabin_class,
                "seats_remaining": opt.seats_remaining,
                "is_alternate_airport": opt.is_alternate_airport,
                "is_alternate_date": opt.is_alternate_date,
            }
            for opt in options
        ]

        rescored = score_flights(flights, weights)

        recommendation = None
        if rescored:
            best = rescored[0]
            recommendation = {
                **best,
                "reason": self._generate_reason(best, rescored, leg),
            }

        return {
            "recommendation": recommendation,
            "rescored_options": rescored[:50],
        }

    async def get_options_for_date(
        self,
        db: AsyncSession,
        leg: TripLeg,
        target_date: date,
        sort_by: str = "price",
    ) -> list[dict]:
        """Get flight options for a specific date from the most recent search."""
        result = await db.execute(
            select(SearchLog)
            .where(SearchLog.trip_leg_id == leg.id)
            .order_by(SearchLog.searched_at.desc())
            .limit(1)
        )
        search_log = result.scalar_one_or_none()

        if not search_log:
            return []

        result = await db.execute(
            select(FlightOption).where(FlightOption.search_log_id == search_log.id)
        )
        options = result.scalars().all()

        # Filter to target date
        filtered = []
        for opt in options:
            if opt.departure_time and opt.departure_time.date() == target_date:
                filtered.append({
                    "id": str(opt.id),
                    "airline_code": opt.airline_code,
                    "airline_name": opt.airline_name,
                    "flight_numbers": opt.flight_numbers,
                    "origin_airport": opt.origin_airport,
                    "destination_airport": opt.destination_airport,
                    "departure_time": opt.departure_time.isoformat(),
                    "arrival_time": opt.arrival_time.isoformat() if opt.arrival_time else "",
                    "duration_minutes": opt.duration_minutes,
                    "stops": opt.stops,
                    "stop_airports": opt.stop_airports,
                    "price": float(opt.price),
                    "currency": opt.currency,
                    "cabin_class": opt.cabin_class,
                    "seats_remaining": opt.seats_remaining,
                    "is_alternate_airport": opt.is_alternate_airport,
                    "is_alternate_date": opt.is_alternate_date,
                })

        sort_key = {"price": "price", "duration": "duration_minutes", "departure": "departure_time"}
        key = sort_key.get(sort_by, "price")
        filtered.sort(key=lambda f: f.get(key, 0))

        return filtered

    # --- Private helpers ---

    @staticmethod
    def _parse_iso(s: str) -> datetime | None:
        """Parse ISO datetime string to datetime object."""
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    async def _search_with_cache(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        adults: int,
        is_alt_airport: bool,
        is_alt_date: bool,
    ) -> list[dict]:
        """Search with cache layer."""
        date_str = departure_date.isoformat()

        # Check cache
        cached = await cache_service.get_flights(origin, destination, date_str, cabin_class)
        if cached is not None:
            # Tag with alt flags
            for f in cached:
                f["is_alternate_airport"] = is_alt_airport
                f["is_alternate_date"] = is_alt_date
            return cached

        # Call Amadeus
        flights = await amadeus_client.search_flight_offers(
            origin, destination, departure_date, cabin_class, adults
        )

        # Tag with flags
        for f in flights:
            f["is_alternate_airport"] = is_alt_airport
            f["is_alternate_date"] = is_alt_date

        # Cache results
        await cache_service.set_flights(origin, destination, date_str, cabin_class, flights)

        return flights

    @staticmethod
    def _build_price_calendar(flights: list[dict], preferred_date: date) -> dict:
        """Build price calendar from all search results."""
        by_date: dict[str, list[float]] = defaultdict(list)

        for f in flights:
            dep_time = f.get("departure_time", "")
            if not dep_time:
                continue
            try:
                d = dep_time.split("T")[0] if "T" in dep_time else dep_time
                by_date[d].append(f["price"])
            except (ValueError, KeyError):
                continue

        dates_data = {}
        cheapest_date = None
        cheapest_price = float("inf")

        for d, prices in sorted(by_date.items()):
            min_p = min(prices)
            dates_data[d] = {
                "min_price": round(min_p, 2),
                "max_price": round(max(prices), 2),
                "option_count": len(prices),
            }
            if min_p < cheapest_price:
                cheapest_price = min_p
                cheapest_date = d

        # Compute preferred date rank and savings
        preferred_str = preferred_date.isoformat()
        preferred_price = dates_data.get(preferred_str, {}).get("min_price", 0)
        savings = round(preferred_price - cheapest_price, 2) if preferred_price and cheapest_price < float("inf") else 0

        # Rank preferred date
        sorted_prices = sorted(dates_data.items(), key=lambda x: x[1]["min_price"])
        rank = 1
        for i, (d, _) in enumerate(sorted_prices):
            if d == preferred_str:
                rank = i + 1
                break

        return {
            "dates": dates_data,
            "cheapest_date": cheapest_date,
            "preferred_date_rank": rank,
            "savings_if_flexible": savings,
        }

    @staticmethod
    def _group_alternatives(
        scored_flights: list[dict],
        primary_origin: str,
        primary_dest: str,
        preferred_date: date,
    ) -> dict:
        """Group flights into cheaper_dates, alternate_airports, different_routing."""
        preferred_str = preferred_date.isoformat()

        cheaper_dates = []
        alternate_airports = []
        different_routing = []

        for f in scored_flights:
            dep_date = f.get("departure_time", "").split("T")[0] if f.get("departure_time") else ""
            is_alt_airport = f.get("is_alternate_airport", False)
            is_alt_date = f.get("is_alternate_date", False)
            has_stops = f.get("stops", 0) > 0

            if is_alt_date and not is_alt_airport and dep_date != preferred_str:
                cheaper_dates.append(f)
            elif is_alt_airport:
                alternate_airports.append(f)
            elif has_stops and not is_alt_airport and not is_alt_date:
                different_routing.append(f)

        return {
            "cheaper_dates": cheaper_dates[:10],
            "alternate_airports": alternate_airports[:10],
            "different_routing": different_routing[:10],
        }

    @staticmethod
    def _generate_reason(best: dict, all_flights: list[dict], leg: TripLeg) -> str:
        """Generate a human-readable reason for the recommendation."""
        parts = []

        prices = [f["price"] for f in all_flights]
        if best["price"] <= min(prices) * 1.05:
            parts.append("lowest price available")
        elif best["price"] <= sorted(prices)[len(prices) // 4]:
            parts.append("in the bottom 25% by price")

        if best["stops"] == 0:
            parts.append("non-stop flight")
        elif best["stops"] == 1:
            parts.append("1 stop")

        durations = [f["duration_minutes"] for f in all_flights]
        if best["duration_minutes"] <= min(durations) * 1.1:
            parts.append("shortest travel time")

        if best.get("is_alternate_date"):
            parts.append("flexible date option")
        if best.get("is_alternate_airport"):
            parts.append(f"via {best['origin_airport']}→{best['destination_airport']}")

        if not parts:
            parts.append("best overall score for your preferences")

        return "Recommended: " + ", ".join(parts) + "."

    async def _save_search_log(
        self,
        db: AsyncSession,
        leg: TripLeg,
        flights: list[dict],
        start_time: float,
        total_results_count: int | None = None,
    ) -> SearchLog | None:
        """Persist search results to database."""
        try:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            prices = [f["price"] for f in flights] if flights else [0]

            search_log = SearchLog(
                trip_leg_id=leg.id,
                api_provider="amadeus" if not amadeus_client._use_mock else "mock",
                search_params={
                    "origin": leg.origin_airport,
                    "destination": leg.destination_airport,
                    "date": leg.preferred_date.isoformat(),
                    "cabin": leg.cabin_class,
                    "flexibility": leg.flexibility_days,
                },
                results_count=total_results_count or len(flights),
                cheapest_price=Decimal(str(min(prices))) if prices else None,
                most_expensive_price=Decimal(str(max(prices))) if prices else None,
                cached=False,
                response_time_ms=elapsed_ms,
            )
            db.add(search_log)
            await db.flush()

            # Save flight options and map DB IDs back to flight dicts
            for f in flights:
                dep_time = self._parse_iso(f.get("departure_time", ""))
                arr_time = self._parse_iso(f.get("arrival_time", ""))

                if not dep_time or not arr_time:
                    continue

                option = FlightOption(
                    search_log_id=search_log.id,
                    airline_code=f.get("airline_code", ""),
                    airline_name=f.get("airline_name", ""),
                    flight_numbers=f.get("flight_numbers", ""),
                    origin_airport=f.get("origin_airport", ""),
                    destination_airport=f.get("destination_airport", ""),
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_minutes=f.get("duration_minutes", 0),
                    stops=f.get("stops", 0),
                    stop_airports=f.get("stop_airports"),
                    price=Decimal(str(f.get("price", 0))),
                    currency=f.get("currency", "CAD"),
                    cabin_class=f.get("cabin_class"),
                    seats_remaining=f.get("seats_remaining"),
                    is_alternate_airport=f.get("is_alternate_airport", False),
                    is_alternate_date=f.get("is_alternate_date", False),
                    raw_response=f.get("raw_response"),
                )
                db.add(option)
                await db.flush()
                # Map the persisted DB ID back to the flight dict
                f["id"] = str(option.id)

            await db.commit()
            return search_log
        except Exception as e:
            logger.error(f"Failed to save search log: {e}", exc_info=True)
            await db.rollback()
            return None


search_orchestrator = SearchOrchestrator()
