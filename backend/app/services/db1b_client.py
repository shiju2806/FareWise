"""DB1B historical fare data client.

Queries the calendar_fares table (loaded from DOT DB1B data pipeline)
and synthesizes realistic flight details for the FareWise search UI.
"""

import hashlib
import logging
import statistics
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Carrier code → name (from DB1B pipeline config/routes.py)
CARRIER_NAMES = {
    "AA": "American Airlines",
    "AC": "Air Canada",
    "AS": "Alaska Airlines",
    "B6": "JetBlue",
    "BA": "British Airways",
    "CX": "Cathay Pacific",
    "CZ": "China Southern",
    "DE": "Condor",
    "DL": "Delta Air Lines",
    "EI": "Aer Lingus",
    "F8": "Flair Airlines",
    "F9": "Frontier Airlines",
    "FI": "Icelandair",
    "FJ": "Fiji Airways",
    "HA": "Hawaiian Airlines",
    "KE": "Korean Air",
    "NK": "Spirit Airlines",
    "PR": "Philippine Airlines",
    "QF": "Qantas",
    "SQ": "Singapore Airlines",
    "TP": "TAP Portugal",
    "TS": "Air Transat",
    "UA": "United Airlines",
    "VS": "Virgin Atlantic",
    "WN": "Southwest Airlines",
    "WS": "WestJet",
}

# Common connecting hub airports by region
HUB_AIRPORTS = {
    "US_EAST": ["JFK", "EWR", "IAD", "BOS", "PHL", "CLT", "ATL", "MIA"],
    "US_WEST": ["LAX", "SFO", "SEA", "DEN", "ORD", "DFW", "PHX"],
    "EUROPE": ["LHR", "CDG", "AMS", "FRA", "MAD", "DUB", "KEF", "LIS"],
    "ASIA_PAC": ["NRT", "HND", "ICN", "HKG", "SIN", "CAN", "NAN", "SYD"],
}

# Carrier-specific hub preferences for connecting flights
CARRIER_HUBS = {
    "AA": ["DFW", "CLT", "MIA", "ORD", "PHL", "JFK"],
    "AC": ["YYZ", "YVR", "YUL"],
    "BA": ["LHR"],
    "B6": ["JFK", "BOS", "FLL"],
    "CX": ["HKG"],
    "CZ": ["CAN"],
    "DE": ["FRA"],
    "DL": ["ATL", "MSP", "DTW", "JFK", "LAX", "SEA"],
    "EI": ["DUB"],
    "FI": ["KEF"],
    "FJ": ["NAN"],
    "KE": ["ICN"],
    "NK": ["FLL", "DFW", "LAS"],
    "PR": ["MNL"],
    "QF": ["SYD", "MEL"],
    "TP": ["LIS"],
    "TS": ["YYZ", "YUL"],
    "UA": ["EWR", "IAH", "ORD", "SFO", "DEN", "LAX"],
    "VS": ["LHR"],
    "WS": ["YYC", "YYZ"],
}

# Base durations (minutes) by route distance class
DURATION_BY_DISTANCE = {
    # distance_nm ranges → (nonstop_minutes, per_stop_penalty_minutes)
    2000: (300, 150),   # ~5h nonstop, +2.5h per stop
    3000: (420, 150),   # ~7h nonstop
    5000: (600, 180),   # ~10h nonstop
    8000: (780, 200),   # ~13h nonstop
    10000: (960, 240),  # ~16h nonstop
}

# ─────────────────────────────────────────────────────────────
# Cabin class multipliers — applied on top of economy base fares
# Validated against real market data (Feb 2026):
#   BA business YYZ-LHR: real 4.5-5.5x → we use 5.5x
#   QF business SYD-YYZ: real 6.0-7.5x → we use 6.0x
#   AC premium economy:  real 1.6-2.0x → we use 1.8x
#   B6 Mint (business):  real 2.5-3.5x → we use 3.0x
# ─────────────────────────────────────────────────────────────

# Carrier-specific multipliers: {carrier: {cabin: multiplier}}
# Carriers not listed use DEFAULT_CABIN_MULTIPLIERS
CARRIER_CABIN_MULTIPLIERS: dict[str, dict[str, float]] = {
    # Full-service legacy carriers — premium products
    "BA": {"premium_economy": 2.2, "business": 5.5, "first": 9.0},
    "AC": {"premium_economy": 1.8, "business": 4.5, "first": 7.5},
    "AA": {"premium_economy": 1.9, "business": 4.2, "first": 7.0},
    "UA": {"premium_economy": 1.9, "business": 4.3, "first": 7.2},
    "DL": {"premium_economy": 2.0, "business": 4.8, "first": 7.5},
    "VS": {"premium_economy": 2.0, "business": 4.5},  # no first class

    # Asian/Pacific premium carriers
    "QF": {"premium_economy": 2.2, "business": 6.0, "first": 10.0},
    "SQ": {"premium_economy": 2.0, "business": 5.5, "first": 9.5},
    "CX": {"premium_economy": 2.0, "business": 5.0, "first": 8.5},
    "KE": {"premium_economy": 1.8, "business": 4.5, "first": 7.0},

    # Mid-range carriers — limited premium products
    "WS": {"premium_economy": 1.6, "business": 3.5},
    "TS": {"premium_economy": 1.5},  # charter, no business
    "EI": {"premium_economy": 1.7, "business": 3.8},
    "FI": {"premium_economy": 1.6, "business": 3.5},
    "TP": {"premium_economy": 1.7, "business": 4.0},
    "DE": {"premium_economy": 1.5, "business": 3.5},
    "CZ": {"premium_economy": 1.6, "business": 3.8},
    "PR": {"premium_economy": 1.6, "business": 3.5},
    "FJ": {"premium_economy": 1.7, "business": 4.0},

    # JetBlue — Mint is their business product
    "B6": {"premium_economy": 1.6, "business": 3.0},

    # ULCCs — no premium cabins (economy only)
    "NK": {},
    "F9": {},
    "F8": {},
    "WN": {},
}

DEFAULT_CABIN_MULTIPLIERS = {
    "premium_economy": 1.8,
    "business": 4.5,
    "first": 7.5,
}


def _get_cabin_multiplier(carrier_code: str, cabin_class: str) -> float | None:
    """Get the fare multiplier for a carrier + cabin class.

    Returns None if the carrier doesn't offer that cabin (e.g., Spirit business).
    Returns 1.0 for economy.
    """
    if cabin_class == "economy":
        return 1.0

    carrier_mults = CARRIER_CABIN_MULTIPLIERS.get(carrier_code)
    if carrier_mults is not None:
        # Carrier has explicit config — use it (empty dict = economy-only carrier)
        return carrier_mults.get(cabin_class)

    # Carrier not in table — use defaults
    return DEFAULT_CABIN_MULTIPLIERS.get(cabin_class)


def _seed_int(seed_str: str) -> int:
    """Deterministic integer from a string seed."""
    return int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)


def _synthesize_flight_number(carrier_code: str, origin: str, dest: str, travel_date: date, stops: int = 0) -> str:
    """Generate a deterministic, realistic flight number.

    Includes stops in the seed so direct and connecting flights
    for the same carrier get different flight numbers (avoids dedup collision).
    """
    seed = _seed_int(f"{carrier_code}-{origin}-{dest}-{travel_date.isoformat()}-s{stops}")
    # Carriers typically use 3-4 digit flight numbers
    num = 100 + (seed % 900)  # 100-999
    return f"{carrier_code} {num}"


def _synthesize_departure_hour(carrier_code: str, origin: str, dest: str, travel_date: date, stops: int = 0) -> tuple[int, int]:
    """Generate a deterministic, realistic departure hour and minute.

    Returns (hour, minute) in 24h format. Range: 06:00 - 22:00.
    Includes stops in seed so direct vs connecting get different times.
    """
    seed = _seed_int(f"dep-{carrier_code}-{origin}-{dest}-{travel_date.isoformat()}-s{stops}")
    # Spread departures across 06:00 - 22:00 (16 hour window)
    hour = 6 + (seed % 16)  # 6-21
    minute = (seed >> 4) % 12 * 5  # 0, 5, 10, ..., 55
    return hour, minute


def _synthesize_duration(distance_nm: int, stops: int) -> int:
    """Estimate flight duration in minutes based on distance and stops."""
    # Find the closest distance bracket
    brackets = sorted(DURATION_BY_DISTANCE.keys())
    base_minutes, stop_penalty = DURATION_BY_DISTANCE[brackets[-1]]
    for bracket in brackets:
        if distance_nm <= bracket:
            base_minutes, stop_penalty = DURATION_BY_DISTANCE[bracket]
            break

    # Scale within bracket
    scale = distance_nm / max(bracket, 1)
    nonstop_duration = int(base_minutes * min(scale, 1.3))

    return nonstop_duration + (stops * stop_penalty)


def _synthesize_stop_airports(carrier_code: str, origin: str, dest: str, stops: int) -> str | None:
    """Generate plausible connecting airports based on carrier hubs."""
    if stops == 0:
        return None

    hubs = CARRIER_HUBS.get(carrier_code, ["JFK", "ORD", "LAX"])
    # Filter out origin/dest from possible stops
    candidates = [h for h in hubs if h != origin and h != dest]
    if not candidates:
        candidates = ["JFK", "ORD", "LAX"]
        candidates = [h for h in candidates if h != origin and h != dest]

    seed = _seed_int(f"stop-{carrier_code}-{origin}-{dest}")
    selected = []
    for i in range(min(stops, len(candidates))):
        idx = (seed + i * 7) % len(candidates)
        selected.append(candidates[idx])

    return ", ".join(selected) if selected else None


class DB1BClient:
    """Queries DB1B fare data from PostgreSQL and synthesizes flight details."""

    def __init__(self):
        self._pool = None

    @property
    def pool(self):
        """Get the asyncpg pool from FastAPI app state."""
        return self._pool

    @pool.setter
    def pool(self, value):
        self._pool = value

    def _get_pool(self):
        """Get pool, raising if not initialized."""
        if self._pool is None:
            raise RuntimeError("DB1B pool not initialized. Ensure db1b_enabled=True in config.")
        return self._pool

    async def _find_route(self, conn, origin: str, dest: str) -> dict | None:
        """Find route_market matching an origin-destination pair.

        Tries both directions since routes are bidirectional.
        """
        row = await conn.fetchrow(
            """SELECT route_id, distance_nm, market_type, has_direct, typical_hours
               FROM route_markets
               WHERE primary_origin = $1 AND primary_dest = $2
               LIMIT 1""",
            origin, dest,
        )
        if not row:
            # Try reversed direction
            row = await conn.fetchrow(
                """SELECT route_id, distance_nm, market_type, has_direct, typical_hours
                   FROM route_markets
                   WHERE primary_origin = $1 AND primary_dest = $2
                   LIMIT 1""",
                dest, origin,
            )
        return dict(row) if row else None

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
    ) -> list[dict]:
        """Search DB1B fares and return flights in the standard dict format.

        Returns the same 15-field dict format as google_flights_client and
        amadeus_client, so the scoring engine and orchestrator work unchanged.
        """
        pool = self._get_pool()

        async with pool.acquire() as conn:
            route = await self._find_route(conn, origin, destination)
            if not route:
                return []

            rows = await conn.fetch(
                """SELECT cf.carrier_code, c.carrier_name, cf.fare_usd, cf.stops
                   FROM calendar_fares cf
                   JOIN carriers c ON cf.carrier_code = c.carrier_code
                   WHERE cf.route_id = $1 AND cf.travel_date = $2
                   ORDER BY cf.fare_usd""",
                route["route_id"], departure_date,
            )

        if not rows:
            return []

        distance = route.get("distance_nm") or 3000
        flights = []

        for row in rows:
            carrier = row["carrier_code"]
            carrier_name = row["carrier_name"] or CARRIER_NAMES.get(carrier, carrier)
            base_fare = float(row["fare_usd"])
            stops = row["stops"]

            # Apply cabin class multiplier (DB1B fares are economy base)
            multiplier = _get_cabin_multiplier(carrier, cabin_class)
            if multiplier is None:
                # Carrier doesn't offer this cabin — skip
                continue
            fare = round(base_fare * multiplier, 2)

            flight_num = _synthesize_flight_number(carrier, origin, destination, departure_date, stops)
            dep_hour, dep_min = _synthesize_departure_hour(carrier, origin, destination, departure_date, stops)
            duration = _synthesize_duration(distance, stops)
            stop_airports = _synthesize_stop_airports(carrier, origin, destination, stops)

            dep_dt = datetime(
                departure_date.year, departure_date.month, departure_date.day,
                dep_hour, dep_min,
            )
            arr_dt = dep_dt + timedelta(minutes=duration)

            flights.append({
                "airline_code": carrier,
                "airline_name": carrier_name,
                "flight_numbers": flight_num,
                "origin_airport": origin,
                "destination_airport": destination,
                "departure_time": dep_dt.isoformat(),
                "arrival_time": arr_dt.isoformat(),
                "duration_minutes": duration,
                "stops": stops,
                "stop_airports": stop_airports,
                "price": fare,
                "currency": "USD",
                "cabin_class": cabin_class,
                "seats_remaining": None,
                "source": "db1b_historical",
            })

        # Re-sort by price after applying multipliers
        flights.sort(key=lambda f: f["price"])
        return flights

    async def search_flights_date_range(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: str = "economy",
    ) -> dict[str, list[dict]]:
        """Search DB1B fares for all dates in [start_date, end_date] in ONE query.

        Returns dict keyed by date ISO string -> list of flight dicts.
        Replaces N individual search_flights() calls with a single SQL query.
        """
        pool = self._get_pool()

        async with pool.acquire() as conn:
            route = await self._find_route(conn, origin, destination)
            if not route:
                return {}

            rows = await conn.fetch(
                """SELECT cf.travel_date, cf.carrier_code, c.carrier_name,
                          cf.fare_usd, cf.stops
                   FROM calendar_fares cf
                   JOIN carriers c ON cf.carrier_code = c.carrier_code
                   WHERE cf.route_id = $1
                     AND cf.travel_date >= $2
                     AND cf.travel_date <= $3
                   ORDER BY cf.travel_date, cf.fare_usd""",
                route["route_id"], start_date, end_date,
            )

        if not rows:
            return {}

        distance = route.get("distance_nm") or 3000
        results: dict[str, list[dict]] = {}

        for row in rows:
            carrier = row["carrier_code"]
            carrier_name = row["carrier_name"] or CARRIER_NAMES.get(carrier, carrier)
            base_fare = float(row["fare_usd"])
            stops = row["stops"]
            travel_date = row["travel_date"]

            multiplier = _get_cabin_multiplier(carrier, cabin_class)
            if multiplier is None:
                continue
            fare = round(base_fare * multiplier, 2)

            flight_num = _synthesize_flight_number(carrier, origin, destination, travel_date, stops)
            dep_hour, dep_min = _synthesize_departure_hour(carrier, origin, destination, travel_date, stops)
            duration = _synthesize_duration(distance, stops)
            stop_airports = _synthesize_stop_airports(carrier, origin, destination, stops)

            dep_dt = datetime(travel_date.year, travel_date.month, travel_date.day, dep_hour, dep_min)
            arr_dt = dep_dt + timedelta(minutes=duration)

            date_key = travel_date.isoformat()
            if date_key not in results:
                results[date_key] = []

            results[date_key].append({
                "airline_code": carrier,
                "airline_name": carrier_name,
                "flight_numbers": flight_num,
                "origin_airport": origin,
                "destination_airport": destination,
                "departure_time": dep_dt.isoformat(),
                "arrival_time": arr_dt.isoformat(),
                "duration_minutes": duration,
                "stops": stops,
                "stop_airports": stop_airports,
                "price": fare,
                "currency": "USD",
                "cabin_class": cabin_class,
                "seats_remaining": None,
                "source": "db1b_historical",
            })

        for flights in results.values():
            flights.sort(key=lambda f: f["price"])

        return results

    async def search_month_prices(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str = "economy",
    ) -> dict[str, dict]:
        """Get cheapest fare per date for an entire month.

        Returns same format as google_flights_client.search_month_sample().
        For non-economy cabins, applies multipliers and filters to carriers
        that offer that cabin.
        """
        pool = self._get_pool()

        async with pool.acquire() as conn:
            route = await self._find_route(conn, origin, destination)
            if not route:
                return {}

            first_of_month = date(year, month, 1)
            if month == 12:
                first_of_next = date(year + 1, 1, 1)
            else:
                first_of_next = date(year, month + 1, 1)

            # For non-economy, we need per-carrier fares to apply multipliers
            if cabin_class != "economy":
                rows = await conn.fetch(
                    """SELECT travel_date, carrier_code, fare_usd, stops
                       FROM calendar_fares
                       WHERE route_id = $1
                         AND travel_date >= $2
                         AND travel_date < $3
                       ORDER BY travel_date""",
                    route["route_id"], first_of_month, first_of_next,
                )

                from collections import defaultdict
                by_date: dict[str, list] = defaultdict(list)
                for row in rows:
                    mult = _get_cabin_multiplier(row["carrier_code"], cabin_class)
                    if mult is None:
                        continue  # carrier doesn't offer this cabin
                    by_date[row["travel_date"].isoformat()].append({
                        "price": round(float(row["fare_usd"]) * mult, 2),
                        "stops": row["stops"],
                    })

                results = {}
                for d, fares in sorted(by_date.items()):
                    if not fares:
                        continue
                    results[d] = {
                        "min_price": min(f["price"] for f in fares),
                        "has_direct": any(f["stops"] == 0 for f in fares),
                        "option_count": len(fares),
                        "source": "db1b_historical",
                    }
                return results

            # Economy path — simple aggregate query
            rows = await conn.fetch(
                """SELECT travel_date,
                          MIN(fare_usd) as min_price,
                          BOOL_OR(stops = 0) as has_direct,
                          COUNT(*) as option_count
                   FROM calendar_fares
                   WHERE route_id = $1
                     AND travel_date >= $2
                     AND travel_date < $3
                   GROUP BY travel_date
                   ORDER BY travel_date""",
                route["route_id"], first_of_month, first_of_next,
            )

        results = {}
        for row in rows:
            d = row["travel_date"].isoformat()
            results[d] = {
                "min_price": round(float(row["min_price"]), 2),
                "has_direct": row["has_direct"],
                "option_count": row["option_count"],
                "source": "db1b_historical",
            }

        return results

    async def search_month_matrix(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
        cabin_class: str = "economy",
    ) -> list[dict]:
        """Get airline x date matrix data for an entire month.

        Returns list of {airline_code, airline_name, date, price, stops}
        entries — one per carrier per date.  ~780 rows per route, sub-second.
        """
        pool = self._get_pool()

        async with pool.acquire() as conn:
            route = await self._find_route(conn, origin, destination)
            if not route:
                return []

            first_of_month = date(year, month, 1)
            if month == 12:
                first_of_next = date(year + 1, 1, 1)
            else:
                first_of_next = date(year, month + 1, 1)

            rows = await conn.fetch(
                """SELECT cf.travel_date, cf.carrier_code, c.carrier_name,
                          cf.fare_usd, cf.stops
                   FROM calendar_fares cf
                   JOIN carriers c ON cf.carrier_code = c.carrier_code
                   WHERE cf.route_id = $1
                     AND cf.travel_date >= $2
                     AND cf.travel_date < $3
                   ORDER BY cf.travel_date, cf.fare_usd""",
                route["route_id"], first_of_month, first_of_next,
            )

        entries = []
        for row in rows:
            carrier = row["carrier_code"]
            multiplier = _get_cabin_multiplier(carrier, cabin_class)
            if multiplier is None:
                continue
            fare = round(float(row["fare_usd"]) * multiplier, 2)
            entries.append({
                "airline_code": carrier,
                "airline_name": row["carrier_name"] or CARRIER_NAMES.get(carrier, carrier),
                "date": row["travel_date"].isoformat(),
                "price": fare,
                "stops": row["stops"],
            })

        return entries

    async def get_price_context(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
        current_price: float | None = None,
    ) -> dict[str, Any] | None:
        """Get price context (quartiles) from DB1B data.

        Returns same format as google_flights_client.get_price_context().
        """
        pool = self._get_pool()

        async with pool.acquire() as conn:
            route = await self._find_route(conn, origin, destination)
            if not route:
                return None

            # Get all fares for this route (across all dates) for distribution
            rows = await conn.fetch(
                """SELECT fare_usd FROM calendar_fares
                   WHERE route_id = $1
                   ORDER BY fare_usd""",
                route["route_id"],
            )

        if len(rows) < 3:
            return None

        prices = sorted(float(r["fare_usd"]) for r in rows)
        n = len(prices)

        historical = {
            "min": round(prices[0], 2),
            "q1": round(prices[n // 4], 2),
            "median": round(statistics.median(prices), 2),
            "q3": round(prices[(3 * n) // 4], 2),
            "max": round(prices[-1], 2),
        }

        # Compute percentile for the reference price
        ref_price = current_price or historical["median"]
        price_range = historical["max"] - historical["min"]
        if price_range > 0:
            percentile = round(((ref_price - historical["min"]) / price_range) * 100)
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
            "historical": historical,
            "current_price": ref_price,
            "percentile": percentile,
            "percentile_label": label,
        }


# Module-level singleton — pool injected at startup via main.py
db1b_client = DB1BClient()
