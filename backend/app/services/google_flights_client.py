"""Google Flights client using the fast-flights library.

Provides calendar pricing and price context data by scraping Google Flights
via protobuf — no API key required, works for any IATA route.
"""

import asyncio
import logging
import statistics
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# Cabin class mapping: our names → fast-flights names
CABIN_MAP = {
    "economy": "economy",
    "premium_economy": "premium-economy",
    "business": "business",
    "first": "first",
}

# Google assessment → our percentile labels
ASSESSMENT_MAP = {
    "low": ("excellent", 20),
    "typical": ("average", 50),
    "high": ("high", 80),
}


def _parse_price(price_str: str | None) -> float | None:
    """Parse price string like 'CA$326' or '$450' into a float."""
    if not price_str:
        return None
    try:
        cleaned = price_str.replace(",", "")
        # Remove currency prefix (CA$, $, €, £, etc.)
        for prefix in ("CA$", "US$", "AU$", "NZ$", "$", "€", "£", "¥"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        return float(cleaned)
    except (ValueError, TypeError):
        return None


async def search_date(
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: str = "economy",
) -> dict[str, Any] | None:
    """Search Google Flights for a single date.

    Returns dict with cheapest_price, has_direct, option_count,
    price_assessment, and all_prices. Returns None on failure.
    """
    try:
        from fast_flights import FlightData, Passengers, get_flights

        seat = CABIN_MAP.get(cabin_class, "economy")
        date_str = departure_date.isoformat()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: get_flights(
                flight_data=[
                    FlightData(
                        date=date_str,
                        from_airport=origin,
                        to_airport=destination,
                    )
                ],
                trip="one-way",
                seat=seat,
                passengers=Passengers(adults=1),
            ),
        )

        if not result or not result.flights:
            return None

        prices = []
        has_direct = False
        for f in result.flights:
            p = _parse_price(f.price)
            if p and p > 0:
                prices.append(p)
            if f.stops == 0:
                has_direct = True

        if not prices:
            return None

        return {
            "cheapest_price": min(prices),
            "has_direct": has_direct,
            "option_count": len(result.flights),
            "price_assessment": result.current_price or "typical",
            "all_prices": sorted(prices),
        }

    except Exception as e:
        logger.warning(f"Google Flights search failed for {origin}-{destination} on {departure_date}: {e}")
        return None


def _parse_duration_str(dur: str) -> int:
    """Parse duration like '10 hr 10 min' or '7 hr 5 min' into minutes."""
    if not dur:
        return 0
    minutes = 0
    parts = dur.lower().replace("hours", "hr").replace("hour", "hr").replace("mins", "min")
    if "hr" in parts:
        h_part, rest = parts.split("hr", 1)
        minutes += int(h_part.strip()) * 60
        parts = rest
    if "min" in parts:
        m_part = parts.replace("min", "").strip()
        if m_part:
            minutes += int(m_part)
    return minutes


def _parse_departure_to_iso(dep_str: str, departure_date: date) -> str:
    """Parse '8:45 PM on Mon, Jun 15' into ISO datetime string."""
    if not dep_str:
        return departure_date.isoformat() + "T00:00:00"
    try:
        # Extract time part (before 'on')
        time_part = dep_str.split(" on ")[0].strip() if " on " in dep_str else dep_str.strip()
        from datetime import datetime
        t = datetime.strptime(time_part, "%I:%M %p")
        return f"{departure_date.isoformat()}T{t.strftime('%H:%M:%S')}"
    except (ValueError, IndexError):
        return departure_date.isoformat() + "T00:00:00"


def _parse_arrival_to_iso(arr_str: str, departure_date: date, time_ahead: str | None) -> str:
    """Parse arrival time + day offset into ISO datetime string."""
    if not arr_str:
        return departure_date.isoformat() + "T23:59:00"
    try:
        time_part = arr_str.split(" on ")[0].strip() if " on " in arr_str else arr_str.strip()
        from datetime import datetime, timedelta
        t = datetime.strptime(time_part, "%I:%M %p")
        arr_date = departure_date
        if time_ahead and "+1" in time_ahead:
            arr_date = departure_date + timedelta(days=1)
        elif time_ahead and "+2" in time_ahead:
            arr_date = departure_date + timedelta(days=2)
        return f"{arr_date.isoformat()}T{t.strftime('%H:%M:%S')}"
    except (ValueError, IndexError):
        return departure_date.isoformat() + "T23:59:00"


async def search_flights(
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: str = "economy",
) -> list[dict]:
    """Search Google Flights and return flights in the same dict format as Amadeus.

    Each flight dict has: airline_code, airline_name, flight_numbers,
    origin_airport, destination_airport, departure_time, arrival_time,
    duration_minutes, stops, stop_airports, price, currency, cabin_class,
    seats_remaining, raw_response.
    """
    try:
        from fast_flights import FlightData, Passengers, get_flights

        seat = CABIN_MAP.get(cabin_class, "economy")
        date_str = departure_date.isoformat()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: get_flights(
                flight_data=[
                    FlightData(
                        date=date_str,
                        from_airport=origin,
                        to_airport=destination,
                    )
                ],
                trip="one-way",
                seat=seat,
                passengers=Passengers(adults=1),
            ),
        )

        if not result or not result.flights:
            return []

        flights = []
        seen = set()  # Deduplicate by airline+price+departure

        for f in result.flights:
            price = _parse_price(f.price)
            if not price or price <= 0:
                continue
            if not f.name and not f.departure:
                continue

            airline_name = f.name or "Unknown"
            # Extract first airline as code (first word, uppercase, max 2 chars)
            airline_parts = airline_name.split(",")
            primary_airline = airline_parts[0].strip()
            # Generate a pseudo airline code from name
            words = primary_airline.split()
            airline_code = "".join(w[0] for w in words[:2]).upper() if words else "XX"

            dep_iso = _parse_departure_to_iso(f.departure, departure_date)
            arr_iso = _parse_arrival_to_iso(f.arrival, departure_date, f.arrival_time_ahead)
            duration = _parse_duration_str(f.duration)

            # Deduplicate
            dedup_key = (airline_name, price, dep_iso)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            stops = f.stops if isinstance(f.stops, int) else 0

            flights.append({
                "airline_code": airline_code,
                "airline_name": primary_airline,
                "flight_numbers": f"{airline_code}{len(flights)+100}",  # Placeholder
                "origin_airport": origin,
                "destination_airport": destination,
                "departure_time": dep_iso,
                "arrival_time": arr_iso,
                "duration_minutes": duration,
                "stops": stops,
                "stop_airports": None,
                "price": price,
                "currency": "CAD",
                "cabin_class": cabin_class,
                "seats_remaining": None,  # Google Flights doesn't provide this
                "source": "google_flights",
            })

        # Sort by price
        flights.sort(key=lambda x: x["price"])
        return flights

    except Exception as e:
        logger.warning(f"Google Flights search failed for {origin}-{destination} on {departure_date}: {e}")
        return []


async def search_month_sample(
    origin: str,
    destination: str,
    year: int,
    month: int,
    cabin_class: str = "economy",
) -> dict[str, dict]:
    """Sample 8 dates across a month from Google Flights.

    Returns dict mapping date strings to price data.
    Runs sequentially with small delays to avoid blocking.
    """
    import calendar as cal

    today = date.today()
    last_day = cal.monthrange(year, month)[1]
    sample_days = [1, 4, 8, 12, 16, 20, 24, min(28, last_day)]

    sample_dates = []
    for d in sample_days:
        sd = date(year, month, d)
        if sd >= today:
            sample_dates.append(sd)

    if not sample_dates:
        return {}

    results: dict[str, dict] = {}

    for sd in sample_dates:
        data = await search_date(origin, destination, sd, cabin_class)
        if data:
            results[sd.isoformat()] = {
                "min_price": round(data["cheapest_price"], 2),
                "has_direct": data["has_direct"],
                "option_count": data["option_count"],
                "price_assessment": data["price_assessment"],
                "source": "google_flights",
            }
        # Small delay between requests to be respectful
        await asyncio.sleep(0.3)

    return results


async def get_price_context(
    origin: str,
    destination: str,
    departure_date: date,
    cabin_class: str = "economy",
    current_price: float | None = None,
) -> dict[str, Any] | None:
    """Get price context using Google Flights data.

    Computes quartiles from all flight prices returned by Google,
    plus maps Google's price assessment to our percentile labels.
    Returns same format as the price-context endpoint.
    """
    data = await search_date(origin, destination, departure_date, cabin_class)
    if not data or len(data["all_prices"]) < 3:
        return None

    prices = data["all_prices"]
    n = len(prices)

    historical = {
        "min": round(prices[0], 2),
        "q1": round(prices[n // 4], 2),
        "median": round(statistics.median(prices), 2),
        "q3": round(prices[(3 * n) // 4], 2),
        "max": round(prices[-1], 2),
    }

    # Use Google's assessment for the percentile label
    assessment = data.get("price_assessment", "typical")
    label, default_pct = ASSESSMENT_MAP.get(assessment, ("average", 50))

    # Compute actual percentile if we have a current price
    ref_price = current_price or data["cheapest_price"]
    percentile = default_pct
    price_range = historical["max"] - historical["min"]
    if price_range > 0 and ref_price:
        percentile = round(((ref_price - historical["min"]) / price_range) * 100)
        percentile = max(0, min(100, percentile))
        # Refine label based on actual percentile
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
        "google_assessment": assessment,
    }
