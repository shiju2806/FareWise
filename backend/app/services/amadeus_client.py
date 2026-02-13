"""Amadeus API client — adapter for flight search with OAuth2 and rate limiting."""

import asyncio
import hashlib
import json
import logging
import math
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Map Amadeus cabin to our cabin codes
CABIN_MAP = {
    "ECONOMY": "economy",
    "PREMIUM_ECONOMY": "premium_economy",
    "BUSINESS": "business",
    "FIRST": "first",
}

# Airline name lookup (common ones)
AIRLINE_NAMES = {
    "AC": "Air Canada", "WS": "WestJet", "AA": "American Airlines",
    "DL": "Delta Air Lines", "UA": "United Airlines", "B6": "JetBlue Airways",
    "NK": "Spirit Airlines", "F8": "Flair Airlines", "BA": "British Airways",
    "LH": "Lufthansa", "AF": "Air France", "KL": "KLM",
    "LX": "Swiss", "OS": "Austrian", "EK": "Emirates",
    "QR": "Qatar Airways", "SQ": "Singapore Airlines", "CX": "Cathay Pacific",
    "NH": "ANA", "JL": "Japan Airlines", "AS": "Alaska Airlines",
    "WN": "Southwest Airlines", "TS": "Air Transat", "PD": "Porter Airlines",
    "VS": "Virgin Atlantic", "FI": "Icelandair", "TP": "TAP Air Portugal",
    "AY": "Finnair", "SK": "SAS", "IB": "Iberia",
}


class AmadeusClient:
    """Adapter for Amadeus Self-Service API."""

    def __init__(self):
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._semaphore = asyncio.Semaphore(10)  # 10 req/s rate limit
        self._client: httpx.AsyncClient | None = None
        self._use_mock = not settings.amadeus_client_id

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.amadeus_base_url,
                timeout=30.0,
            )
        return self._client

    async def _ensure_token(self):
        """Get or refresh OAuth2 token."""
        if self._use_mock:
            return

        if self._token and self._token_expires and datetime.now(timezone.utc) < self._token_expires:
            return

        client = await self._get_client()
        for attempt in range(3):
            try:
                resp = await client.post(
                    "/v1/security/oauth2/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.amadeus_client_id,
                        "client_secret": settings.amadeus_client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()
                self._token = data["access_token"]
                self._token_expires = datetime.now(timezone.utc) + timedelta(
                    seconds=data.get("expires_in", 1799) - 60
                )
                logger.info("Amadeus token refreshed")
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except httpx.RequestError:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

    async def search_flight_offers(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str = "economy",
        adults: int = 1,
        max_results: int = 50,
    ) -> list[dict]:
        """Search for flight offers on a specific date."""
        if self._use_mock:
            return self._generate_mock_flights(
                origin, destination, departure_date, cabin_class, adults
            )

        try:
            async with self._semaphore:
                await self._ensure_token()
                client = await self._get_client()

                amadeus_cabin = {
                    "economy": "ECONOMY",
                    "premium_economy": "PREMIUM_ECONOMY",
                    "business": "BUSINESS",
                    "first": "FIRST",
                }.get(cabin_class, "ECONOMY")

                params = {
                    "originLocationCode": origin,
                    "destinationLocationCode": destination,
                    "departureDate": departure_date.isoformat(),
                    "adults": adults,
                    "travelClass": amadeus_cabin,
                    "max": max_results,
                    "currencyCode": "CAD",
                }

                for attempt in range(3):
                    try:
                        resp = await client.get(
                            "/v2/shopping/flight-offers",
                            params=params,
                            headers={"Authorization": f"Bearer {self._token}"},
                        )
                        if resp.status_code == 429:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                        return [
                            self._parse_offer(offer, origin, destination)
                            for offer in data.get("data", [])
                        ]
                    except httpx.HTTPStatusError as e:
                        logger.error(f"Amadeus search error: {e.response.status_code}")
                        if attempt == 2:
                            return []
                    except httpx.RequestError as e:
                        logger.error(f"Amadeus request error: {e}")
                        if attempt == 2:
                            return []
        except Exception as e:
            logger.error(f"Amadeus API failed, falling back to mock: {e}")
            return self._generate_mock_flights(
                origin, destination, departure_date, cabin_class, adults
            )

        return []

    async def search_cheapest_dates(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> list[dict]:
        """Get cheapest prices by date (for calendar)."""
        if self._use_mock:
            return self._generate_mock_calendar(origin, destination, departure_date)

        async with self._semaphore:
            await self._ensure_token()
            client = await self._get_client()

            try:
                resp = await client.get(
                    "/v1/shopping/flight-dates",
                    params={
                        "origin": origin,
                        "destination": destination,
                        "departureDate": departure_date.isoformat(),
                    },
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    {
                        "date": d["departureDate"],
                        "price": float(d["price"]["total"]),
                        "currency": d["price"].get("currency", "CAD"),
                    }
                    for d in data.get("data", [])
                ]
            except Exception as e:
                logger.error(f"Amadeus calendar error: {e}")
                return []

    def _parse_offer(self, offer: dict, origin: str, destination: str) -> dict:
        """Parse Amadeus offer JSON into our FlightOffer format."""
        price = float(offer.get("price", {}).get("grandTotal", 0))
        currency = offer.get("price", {}).get("currency", "CAD")

        itineraries = offer.get("itineraries", [{}])
        itin = itineraries[0] if itineraries else {}
        segments = itin.get("segments", [])

        if not segments:
            return {}

        first_seg = segments[0]
        last_seg = segments[-1]

        # Flight numbers
        flight_nums = ", ".join(
            f"{s['carrierCode']}{s['number']}" for s in segments
        )
        airline_code = first_seg.get("carrierCode", "")
        airline_name = AIRLINE_NAMES.get(airline_code, airline_code)

        # Duration
        duration_str = itin.get("duration", "PT0H0M")
        duration_minutes = self._parse_duration(duration_str)

        # Stops
        stops = len(segments) - 1
        stop_airports = ", ".join(
            s["arrival"]["iataCode"] for s in segments[:-1]
        ) if stops > 0 else None

        # Cabin
        cabin = "economy"
        traveler_pricings = offer.get("travelerPricings", [])
        if traveler_pricings:
            fare_details = traveler_pricings[0].get("fareDetailsBySegment", [])
            if fare_details:
                cabin = CABIN_MAP.get(
                    fare_details[0].get("cabin", "ECONOMY"), "economy"
                )

        # Seats remaining
        seats = None
        if "numberOfBookableSeats" in offer:
            seats = offer["numberOfBookableSeats"]

        departure_time = first_seg["departure"]["at"]
        arrival_time = last_seg["arrival"]["at"]

        return {
            "airline_code": airline_code,
            "airline_name": airline_name,
            "flight_numbers": flight_nums,
            "origin_airport": first_seg["departure"]["iataCode"],
            "destination_airport": last_seg["arrival"]["iataCode"],
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "duration_minutes": duration_minutes,
            "stops": stops,
            "stop_airports": stop_airports,
            "price": price,
            "currency": currency,
            "cabin_class": cabin,
            "seats_remaining": seats,
            "raw_response": offer,
        }

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Parse ISO 8601 duration (PT2H30M) to minutes."""
        if not duration_str or not duration_str.startswith("PT"):
            return 0
        duration_str = duration_str[2:]
        hours = 0
        minutes = 0
        if "H" in duration_str:
            h_part, duration_str = duration_str.split("H")
            hours = int(h_part)
        if "M" in duration_str:
            m_part = duration_str.replace("M", "")
            if m_part:
                minutes = int(m_part)
        return hours * 60 + minutes

    # --- Mock data generation for demo mode ---

    def _generate_mock_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        adults: int,
    ) -> list[dict]:
        """Generate realistic mock flight data for demo/development."""
        # Deterministic seed based on route+date+cabin for consistency
        seed_str = f"{origin}{destination}{departure_date.isoformat()}{cabin_class}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # Base price depends on route distance (rough estimates)
        base_prices = self._estimate_base_price(origin, destination, cabin_class)
        num_flights = rng.randint(5, 12)

        airlines = self._get_route_airlines(origin, destination)
        flights = []

        for i in range(num_flights):
            airline = rng.choice(airlines)
            price_factor = rng.uniform(0.8, 1.8)
            price = round(base_prices * price_factor, 2)

            # Departure between 6:00 and 21:00
            dep_hour = rng.randint(6, 21)
            dep_minute = rng.choice([0, 15, 30, 45])
            dep_time = datetime(
                departure_date.year, departure_date.month, departure_date.day,
                dep_hour, dep_minute, tzinfo=timezone.utc
            )

            # Duration: base + random variation
            base_duration = self._estimate_duration(origin, destination)
            stops = rng.choices([0, 1, 2], weights=[60, 30, 10])[0]
            duration = base_duration + stops * rng.randint(45, 90)

            arr_time = dep_time + timedelta(minutes=duration)

            stop_airports = None
            if stops > 0:
                hubs = ["YYZ", "ORD", "DFW", "ATL", "DEN", "LAX", "JFK", "EWR"]
                possible = [h for h in hubs if h not in (origin, destination)]
                stop_airports = ", ".join(rng.sample(possible, min(stops, len(possible))))

            flight_num = f"{airline}{rng.randint(100, 9999)}"
            seats = rng.randint(1, 9) if rng.random() < 0.3 else None

            flights.append({
                "airline_code": airline,
                "airline_name": AIRLINE_NAMES.get(airline, airline),
                "flight_numbers": flight_num,
                "origin_airport": origin,
                "destination_airport": destination,
                "departure_time": dep_time.isoformat(),
                "arrival_time": arr_time.isoformat(),
                "duration_minutes": duration,
                "stops": stops,
                "stop_airports": stop_airports,
                "price": price,
                "currency": "CAD",
                "cabin_class": cabin_class,
                "seats_remaining": seats,
                "raw_response": None,
            })

        return sorted(flights, key=lambda f: f["price"])

    def _generate_mock_calendar(
        self, origin: str, destination: str, departure_date: date
    ) -> list[dict]:
        """Generate mock calendar price data for ±7 days."""
        base = self._estimate_base_price(origin, destination, "economy")
        seed_str = f"{origin}{destination}{departure_date.isoformat()}cal"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        results = []
        for offset in range(-7, 8):
            d = departure_date + timedelta(days=offset)
            # Weekday pricing: Tue/Wed cheaper, Fri/Sun more expensive
            day_factor = {0: 1.0, 1: 0.9, 2: 0.85, 3: 0.95, 4: 1.15, 5: 1.1, 6: 1.2}.get(
                d.weekday(), 1.0
            )
            price = round(base * day_factor * rng.uniform(0.85, 1.15), 2)
            results.append({"date": d.isoformat(), "price": price, "currency": "CAD"})

        return results

    @staticmethod
    def _estimate_base_price(origin: str, destination: str, cabin_class: str) -> float:
        """Rough base price estimate by route characteristics."""
        # Domestic Canada/US short-haul
        domestic_short = {"YYZ-YUL", "YUL-YYZ", "YYZ-YOW", "YOW-YYZ", "LGA-BOS", "BOS-LGA",
                          "DCA-LGA", "LGA-DCA", "SFO-LAX", "LAX-SFO", "ORD-DTW", "DTW-ORD"}
        # Medium-haul
        medium = {"YYZ-JFK", "JFK-YYZ", "YYZ-ORD", "ORD-YYZ", "YYZ-MIA", "MIA-YYZ",
                  "YYZ-DFW", "DFW-YYZ", "SFO-JFK", "JFK-SFO", "LAX-JFK", "JFK-LAX",
                  "YYZ-YVR", "YVR-YYZ", "YYZ-YYC", "YYC-YYZ"}

        route_key = f"{origin}-{destination}"
        if route_key in domestic_short:
            base = 180
        elif route_key in medium:
            base = 340
        elif any(a in route_key for a in ["LHR", "CDG", "ORY"]):
            base = 850  # Transatlantic
        elif any(a in route_key for a in ["NRT", "HND"]):
            base = 1200  # Transpacific
        else:
            base = 420  # Default medium

        cabin_multiplier = {
            "economy": 1.0, "premium_economy": 1.8,
            "business": 3.5, "first": 6.0,
        }.get(cabin_class, 1.0)

        return base * cabin_multiplier

    @staticmethod
    def _estimate_duration(origin: str, destination: str) -> int:
        """Rough flight duration in minutes."""
        short_routes = {"YYZ-YUL", "YUL-YYZ", "YYZ-YOW", "YOW-YYZ", "LGA-BOS",
                        "BOS-LGA", "DCA-LGA", "LGA-DCA"}
        route_key = f"{origin}-{destination}"
        if route_key in short_routes:
            return 75
        if any(a in route_key for a in ["LHR", "CDG", "ORY"]):
            return 420  # 7h transatlantic
        if any(a in route_key for a in ["NRT", "HND"]):
            return 780  # 13h transpacific
        return 180  # Default ~3h

    @staticmethod
    def _get_route_airlines(origin: str, destination: str) -> list[str]:
        """Return plausible airlines for a route."""
        canadian = {"YYZ", "YUL", "YVR", "YYC", "YOW", "YTZ"}
        european = {"LHR", "LGW", "STN", "CDG", "ORY", "AMS", "FRA", "MUC", "ZRH", "FCO"}
        middle_east = {"DXB", "DOH", "AUH"}
        asia_pacific = {"NRT", "HND", "SIN", "HKG"}

        is_canadian = origin in canadian or destination in canadian
        is_european = origin in european or destination in european
        is_me = origin in middle_east or destination in middle_east
        is_ap = origin in asia_pacific or destination in asia_pacific

        if is_canadian and is_european:
            return ["AC", "BA", "LH", "AF", "KL", "LX", "VS", "AA", "DL", "UA"]
        if is_canadian and is_me:
            return ["AC", "EK", "QR", "BA", "LH"]
        if is_canadian and is_ap:
            return ["AC", "NH", "JL", "CX", "SQ", "UA"]
        if is_canadian:
            return ["AC", "WS", "TS", "PD", "AA", "DL", "UA"]
        if is_european:
            return ["BA", "LH", "AF", "KL", "LX", "AA", "DL", "UA"]
        return ["AA", "DL", "UA", "B6", "NK", "AS", "WN"]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


amadeus_client = AmadeusClient()
