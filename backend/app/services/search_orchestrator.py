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
        user_preferences: dict | None = None,
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

        # 2. Build date ranges
        # Primary pair always searches ±7 days (for matrix display)
        # Nearby pairs only search ±flexibility_days (to limit query volume)
        flex = min(leg.flexibility_days, 7)
        primary_dates = [
            leg.preferred_date + timedelta(days=d)
            for d in range(-7, 8)
        ]
        flex_dates = [
            leg.preferred_date + timedelta(days=d)
            for d in range(-flex, flex + 1)
        ]

        # 3. Group dates by route pair and execute batch queries
        all_flights: list[dict] = []
        airports_searched = set()

        # Group dates by (origin, dest) pair for batch DB1B queries
        route_pairs: dict[tuple[str, str], list[tuple[date, bool, bool]]] = {}
        search_tasks = []  # Still needed for metadata (dates_searched)
        for orig in origin_airports:
            for dest in dest_airports:
                if orig == dest:
                    continue
                airports_searched.add(orig)
                airports_searched.add(dest)
                is_primary_pair = (orig == leg.origin_airport and dest == leg.destination_airport)
                search_dates = primary_dates if is_primary_pair else flex_dates
                pair_key = (orig, dest)
                route_pairs[pair_key] = [
                    (d, not is_primary_pair, d != leg.preferred_date)
                    for d in search_dates
                ]
                for d in search_dates:
                    search_tasks.append((orig, dest, d, leg.cabin_class, leg.passengers,
                                         not is_primary_pair, d != leg.preferred_date))

        # Execute batch queries per route pair (1 SQL query per pair instead of 1 per date)
        pair_coros = [
            self._batch_search_pair(
                orig, dest, dates_info, leg.cabin_class, leg.passengers,
            )
            for (orig, dest), dates_info in route_pairs.items()
        ]
        pair_results = await asyncio.gather(*pair_coros, return_exceptions=True)
        pair_keys = list(route_pairs.keys())
        warnings = []
        for idx, result in enumerate(pair_results):
            if isinstance(result, Exception):
                pair_key = pair_keys[idx]
                is_primary = (pair_key[0] == leg.origin_airport and pair_key[1] == leg.destination_airport)
                msg = f"{'Primary' if is_primary else 'Alternate'} pair {pair_key[0]}->{pair_key[1]} failed: {result}"
                if is_primary:
                    logger.error(msg)
                else:
                    logger.warning(msg)
                warnings.append(msg)
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

        # 4b. Tag each flight with within_flexibility
        for f in all_flights:
            dep_str = f.get("departure_time", "")
            if dep_str:
                try:
                    dep_date = date.fromisoformat(dep_str.split("T")[0])
                    f["within_flexibility"] = abs((dep_date - leg.preferred_date).days) <= flex
                except (ValueError, TypeError):
                    f["within_flexibility"] = False
            else:
                f["within_flexibility"] = False

        # 5. Score all flights
        scored_flights = score_flights(all_flights, weights)

        # 6. Apply user preference filters & boosts
        if user_preferences:
            max_stops = user_preferences.get("max_stops")
            max_layover = user_preferences.get("max_layover_minutes")
            prefer_nonstop = user_preferences.get("prefer_nonstop", False)

            if max_stops is not None or max_layover is not None:
                filtered = []
                for f in scored_flights:
                    if max_stops is not None and f.get("stops", 0) > max_stops:
                        continue
                    if max_layover is not None and f.get("layover_minutes", 0) > max_layover:
                        continue
                    filtered.append(f)
                # Only apply filter if it doesn't eliminate everything
                if filtered:
                    scored_flights = filtered

            if prefer_nonstop:
                for f in scored_flights:
                    if f.get("stops", 0) == 0:
                        f["score"] = f.get("score", 50) + 10
                scored_flights.sort(key=lambda x: x.get("score", 0), reverse=True)

            # Boost flights from preferred alliances
            preferred_alliances = user_preferences.get("preferred_alliances", [])
            if preferred_alliances:
                from app.data.airline_tiers import get_alliance
                for f in scored_flights:
                    airline_alliance = get_alliance(f.get("airline_code", ""))
                    if airline_alliance and airline_alliance in preferred_alliances:
                        f["score"] = f.get("score", 50) + 5
                scored_flights.sort(key=lambda x: x.get("score", 0), reverse=True)

        # 7. Build price calendar
        price_calendar = self._build_price_calendar(
            all_flights, leg.preferred_date
        )

        # 8. Group alternatives
        alternatives = self._group_alternatives(
            scored_flights, leg.origin_airport, leg.destination_airport, leg.preferred_date
        )

        # 9. Include ALL flights in response (no filtering by date/airport)
        # Need enough to cover all airline×date combos for the price matrix
        all_options = scored_flights[:500]

        recommendation = None
        if scored_flights:
            best = scored_flights[0]
            recommendation = {
                **best,
                "reason": self._generate_reason(best, scored_flights, leg),
            }

        # Collect all unique flights for DB persistence
        response_flights: list[dict] = []
        seen_ids = set()
        for f in all_options:
            key = id(f)
            if key not in seen_ids:
                seen_ids.add(key)
                response_flights.append(f)
        if recommendation:
            key = id(recommendation)
            if key not in seen_ids:
                seen_ids.add(key)
                response_flights.append(recommendation)

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

        # All dates that were actually searched
        all_searched_dates = sorted(set(
            d.isoformat() for _, _, d, *_ in search_tasks
        ))

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
            "all_options": all_options,
            "metadata": {
                "total_options_found": len(all_flights),
                "airports_searched": sorted(airports_searched),
                "dates_searched": all_searched_dates,
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

    async def _batch_search_pair(
        self,
        origin: str,
        destination: str,
        dates_info: list[tuple[date, bool, bool]],
        cabin_class: str,
        passengers: int,
    ) -> list[dict]:
        """Search all dates for a single route pair using one batch DB1B query.

        Falls back to individual Amadeus queries ONLY for the primary pair
        (not alternate airports) when DB1B has no data.
        """
        # Check cache for each date first
        cached_flights: list[dict] = []
        uncached_dates: list[tuple[date, bool, bool]] = []

        for d, is_alt_ap, is_alt_dt in dates_info:
            date_str = d.isoformat()
            cached = await cache_service.get_flights(origin, destination, date_str, cabin_class)
            if cached is not None:
                for f in cached:
                    f["is_alternate_airport"] = is_alt_ap
                    f["is_alternate_date"] = is_alt_dt
                cached_flights.extend(cached)
            else:
                uncached_dates.append((d, is_alt_ap, is_alt_dt))

        if not uncached_dates:
            return cached_flights

        # Batch DB1B query for all uncached dates (one SQL query)
        batch_results: dict[str, list[dict]] = {}
        try:
            from app.services.db1b_client import db1b_client
            batch_results = await db1b_client.search_flights_date_range(
                origin, destination,
                min(d for d, _, _ in uncached_dates),
                max(d for d, _, _ in uncached_dates),
                cabin_class,
            )
        except Exception as e:
            logger.warning(f"DB1B batch search failed for {origin}-{destination}: {e}")

        flights: list[dict] = list(cached_flights)

        # Process each uncached date: use DB1B result, or fall back to Amadeus
        amadeus_fallback_coros = []
        amadeus_fallback_info = []

        for d, is_alt_ap, is_alt_dt in uncached_dates:
            date_str = d.isoformat()
            date_flights = batch_results.get(date_str, [])

            if date_flights:
                for f in date_flights:
                    f["is_alternate_airport"] = is_alt_ap
                    f["is_alternate_date"] = is_alt_dt
                flights.extend(date_flights)
                await cache_service.set_flights(origin, destination, date_str, cabin_class, date_flights)
            else:
                # Queue Amadeus fallback
                amadeus_fallback_coros.append(
                    amadeus_client.search_flight_offers(
                        origin, destination, d, cabin_class, passengers
                    )
                )
                amadeus_fallback_info.append((d, is_alt_ap, is_alt_dt))

        # Execute Amadeus fallbacks in parallel (typically few or zero)
        if amadeus_fallback_coros:
            amadeus_results = await asyncio.gather(*amadeus_fallback_coros, return_exceptions=True)
            for idx, result in enumerate(amadeus_results):
                d, is_alt_ap, is_alt_dt = amadeus_fallback_info[idx]
                date_str = d.isoformat()
                if isinstance(result, Exception):
                    logger.warning(f"Amadeus fallback failed for {origin}-{destination} on {d}: {result}")
                    continue
                for f in result:
                    f["is_alternate_airport"] = is_alt_ap
                    f["is_alternate_date"] = is_alt_dt
                flights.extend(result)
                if result:
                    await cache_service.set_flights(origin, destination, date_str, cabin_class, result)

        return flights

    async def _search_with_timeout(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        adults: int,
        is_alt_airport: bool,
        is_alt_date: bool,
    ) -> list[dict]:
        """Wrapper around _search_with_cache with a 20s timeout."""
        try:
            return await asyncio.wait_for(
                self._search_with_cache(
                    origin, destination, departure_date, cabin_class, adults,
                    is_alt_airport=is_alt_airport, is_alt_date=is_alt_date,
                ),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Search timeout for {origin}->{destination} on {departure_date}")
            return []

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
        """Search with cache layer. DB1B primary, Amadeus fallback."""
        date_str = departure_date.isoformat()

        # Check cache
        cached = await cache_service.get_flights(origin, destination, date_str, cabin_class)
        if cached is not None:
            for f in cached:
                f["is_alternate_airport"] = is_alt_airport
                f["is_alternate_date"] = is_alt_date
            return cached

        # Primary: DB1B historical fare data (real pricing, reliable)
        flights = []
        try:
            from app.services.db1b_client import db1b_client
            flights = await db1b_client.search_flights(
                origin, destination, departure_date, cabin_class
            )
        except Exception as e:
            logger.warning(f"DB1B search failed for {origin}-{destination}: {e}")

        # Fallback: Amadeus (if DB1B has no data for this route)
        if not flights:
            flights = await amadeus_client.search_flight_offers(
                origin, destination, departure_date, cabin_class, adults
            )

        # Tag with flags
        for f in flights:
            f["is_alternate_airport"] = is_alt_airport
            f["is_alternate_date"] = is_alt_date

        # Cache results (only cache non-empty to avoid poisoning)
        if flights:
            await cache_service.set_flights(origin, destination, date_str, cabin_class, flights)

        return flights

    @staticmethod
    def _build_price_calendar(flights: list[dict], preferred_date: date) -> dict:
        """Build price calendar from all search results."""
        by_date: dict[str, list[dict]] = defaultdict(list)

        for f in flights:
            dep_time = f.get("departure_time", "")
            if not dep_time:
                continue
            try:
                d = dep_time.split("T")[0] if "T" in dep_time else dep_time
                by_date[d].append(f)
            except (ValueError, KeyError):
                continue

        dates_data = {}
        cheapest_date = None
        cheapest_price = float("inf")

        for d, day_flights in sorted(by_date.items()):
            prices = [f["price"] for f in day_flights]
            min_p = min(prices)
            has_direct = any(f.get("stops", 1) == 0 for f in day_flights)
            dates_data[d] = {
                "min_price": round(min_p, 2),
                "max_price": round(max(prices), 2),
                "option_count": len(prices),
                "has_direct": has_direct,
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

    async def fetch_month_prices(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str,
        existing_dates: dict | None = None,
    ) -> dict:
        """Fetch cheapest prices for every day in a month.

        Uses Amadeus Flight Cheapest Date Search — single API call for the
        entire month instead of 30 individual flight-offers calls.
        Merges with existing_dates from the initial search (which have
        accurate stop info and live prices).
        """
        # Check month calendar cache
        cached = await cache_service.get_month_calendar(origin, destination, year, month, cabin_class)
        if cached:
            return cached

        # Start with existing search data (real data with stop info)
        dates_data: dict[str, dict] = {}
        if existing_dates:
            dates_data.update(existing_dates)

        # Primary: DB1B historical data
        db1b_ok = False
        try:
            from app.services.db1b_client import db1b_client
            db1b_data = await db1b_client.search_month_prices(
                origin=origin,
                destination=destination,
                year=year,
                month=month,
                cabin_class=cabin_class,
            )
            for d, entry in db1b_data.items():
                # Never overwrite prices from the initial flight search —
                # those are authoritative (same flights user sees in listing)
                if d not in dates_data:
                    dates_data[d] = entry
            if db1b_data:
                db1b_ok = True
        except Exception as e:
            logger.warning(f"DB1B calendar failed for {origin}-{destination}: {e}")

        # Fallback: Amadeus Flight Cheapest Date Search
        if not db1b_ok and not dates_data:
            today = date.today()
            first_of_month = date(year, month, 1)
            anchor_date = max(first_of_month, today)

            try:
                cheapest_dates = await amadeus_client.search_cheapest_dates(
                    origin=origin,
                    destination=destination,
                    departure_date=anchor_date,
                )

                month_prefix = f"{year}-{month:02d}"
                for entry in cheapest_dates:
                    d = entry.get("date", "")
                    if not d.startswith(month_prefix):
                        continue
                    if d not in dates_data:
                        dates_data[d] = {
                            "min_price": round(entry["price"], 2),
                            "has_direct": False,
                            "option_count": 1,
                            "source": "cheapest_dates",
                        }
            except Exception as e:
                logger.warning(f"Amadeus cheapest dates failed for {origin}-{destination}: {e}")

        # Compute month stats
        all_prices = [v["min_price"] for v in dates_data.values() if v.get("min_price", 0) > 0]
        month_stats = {
            "cheapest_price": min(all_prices) if all_prices else 0,
            "cheapest_date": min(dates_data, key=lambda d: dates_data[d].get("min_price", float("inf"))) if dates_data else None,
            "avg_price": round(sum(all_prices) / len(all_prices), 2) if all_prices else 0,
            "dates_with_flights": len([p for p in all_prices if p > 0]),
            "dates_with_direct": len([d for d, v in dates_data.items() if v.get("has_direct")]),
        }

        result = {"dates": dates_data, "month_stats": month_stats}

        # Cache the month calendar
        await cache_service.set_month_calendar(origin, destination, year, month, cabin_class, result)

        return result

    @staticmethod
    def _group_alternatives(
        scored_flights: list[dict],
        primary_origin: str,
        primary_dest: str,
        preferred_date: date,
    ) -> dict:
        """Group flights into cheaper_dates, same_airline_cheaper, alternate_airports, different_routing."""
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

        # Same-airline cheaper date: for each airline, find flights on other
        # dates that are cheaper than that airline's preferred-date price.
        preferred_by_airline: dict[str, dict] = {}
        for f in scored_flights:
            dep_date = f.get("departure_time", "").split("T")[0] if f.get("departure_time") else ""
            if dep_date != preferred_str:
                continue
            if f.get("is_alternate_airport"):
                continue
            airline = f.get("airline_code", "")
            if airline not in preferred_by_airline or f["price"] < preferred_by_airline[airline]["price"]:
                preferred_by_airline[airline] = f

        same_airline_cheaper = []
        for f in scored_flights:
            dep_date = f.get("departure_time", "").split("T")[0] if f.get("departure_time") else ""
            if dep_date == preferred_str:
                continue
            if f.get("is_alternate_airport"):
                continue
            airline = f.get("airline_code", "")
            pref_flight = preferred_by_airline.get(airline)
            if not pref_flight:
                continue
            savings = round(pref_flight["price"] - f["price"], 2)
            if savings > 0:
                f["savings_vs_preferred"] = savings
                f["preferred_date_price"] = pref_flight["price"]
                same_airline_cheaper.append(f)

        same_airline_cheaper.sort(key=lambda x: x.get("savings_vs_preferred", 0), reverse=True)

        return {
            "same_airline_cheaper": same_airline_cheaper[:10],
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
        option_flight_pairs = []
        try:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            prices = [f["price"] for f in flights] if flights else [0]

            # Determine which provider supplied data
            provider = "db1b_historical"
            if flights and flights[0].get("source") == "amadeus":
                provider = "amadeus"

            search_log = SearchLog(
                trip_leg_id=leg.id,
                api_provider=provider,
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

            # Save flight options in bulk and map DB IDs back
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
                option_flight_pairs.append((option, f))

            # Single flush for all options (instead of per-flight)
            await db.flush()

            # Map persisted DB IDs back to flight dicts
            for option, f in option_flight_pairs:
                f["id"] = str(option.id)

            await db.commit()
            return search_log
        except Exception as e:
            logger.error(f"Failed to save search log: {e}", exc_info=True)
            await db.rollback()
            # Clear IDs mapped during flush so UUID fallback in search_leg() kicks in
            for _option, f in option_flight_pairs:
                f.pop("id", None)
            return None


search_orchestrator = SearchOrchestrator()
