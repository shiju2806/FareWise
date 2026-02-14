"""Amadeus API client — adapter for flight search with OAuth2 and rate limiting."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

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
    "AY": "Finnair", "SK": "SAS", "IB": "Iberia", "TK": "Turkish Airlines",
    "EI": "Aer Lingus", "AV": "Avianca", "S4": "AZAL Azerbaijan Airlines",
    "LO": "LOT Polish", "SN": "Brussels Airlines", "AZ": "ITA Airways",
    "ET": "Ethiopian Airlines", "MS": "EgyptAir", "RJ": "Royal Jordanian",
}


class AmadeusClient:
    """Adapter for Amadeus Self-Service API."""

    def __init__(self):
        self._token: str | None = None
        self._token_expires: datetime | None = None
        self._semaphore = asyncio.Semaphore(10)  # 10 req/s rate limit
        self._client: httpx.AsyncClient | None = None
        if not settings.amadeus_client_id:
            logger.warning("AMADEUS_CLIENT_ID not set — flight searches will return empty results")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.amadeus_base_url,
                timeout=30.0,
            )
        return self._client

    async def _ensure_token(self):
        """Get or refresh OAuth2 token."""
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
        if not settings.amadeus_client_id:
            return []

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
                            # 6X is Amadeus test sandbox airline — filter it out
                            if offer.get("validatingAirlineCodes", [""])[0] != "6X"
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
            logger.error(f"Amadeus API error: {e}")

        return []

    async def search_cheapest_dates(
        self,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> list[dict]:
        """Get cheapest prices by date (for calendar)."""
        if not settings.amadeus_client_id:
            return []

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
                        "oneWay": "true",
                        "viewBy": "DATE",
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

    async def get_price_metrics(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        currency: str = "CAD",
    ) -> dict | None:
        """Get historical price quartiles for a route+date.

        Uses GET /v1/analytics/itinerary-price-metrics.
        Returns {min, q1, median, q3, max} or None on failure.
        """
        if not settings.amadeus_client_id:
            return None

        try:
            async with self._semaphore:
                await self._ensure_token()
                client = await self._get_client()

                resp = await client.get(
                    "/v1/analytics/itinerary-price-metrics",
                    params={
                        "originIataCode": origin,
                        "destinationIataCode": destination,
                        "departureDate": departure_date.isoformat(),
                        "currencyCode": currency,
                        "oneWay": "true",
                    },
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if resp.status_code == 429:
                    await asyncio.sleep(1)
                    return None
                resp.raise_for_status()
                data = resp.json()

                items = data.get("data", [])
                if not items:
                    return None

                metrics = items[0].get("priceMetrics", [])
                result = {}
                ranking_map = {
                    "MINIMUM": "min",
                    "FIRST": "q1",
                    "MEDIUM": "median",
                    "THIRD": "q3",
                    "MAXIMUM": "max",
                }
                for m in metrics:
                    key = ranking_map.get(m.get("quartileRanking", ""), "")
                    if key:
                        result[key] = float(m["amount"])

                return result if result else None

        except Exception as e:
            logger.warning(f"Amadeus price-metrics error for {origin}-{destination}: {e}")
            return None

    async def get_busiest_period(
        self,
        city_code: str,
        period: str = "2024",
        direction: str = "ARRIVING",
    ) -> list[dict]:
        """Get busiest travel months for a city from Amadeus analytics.

        Args:
            city_code: IATA city code (e.g., "LON", "NYC")
            period: Year to query (test tier has limited data, 2017-2024)
            direction: "ARRIVING" or "DEPARTING"

        Returns list of {month, travelers_count, period} dicts.
        """
        if not settings.amadeus_client_id:
            return []

        try:
            async with self._semaphore:
                await self._ensure_token()
                client = await self._get_client()
                resp = await client.get(
                    "/v1/travel/analytics/air-traffic/busiest-period",
                    params={
                        "cityCode": city_code,
                        "period": period,
                        "direction": direction,
                    },
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if resp.status_code == 429:
                    await asyncio.sleep(1)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return [
                    {
                        "month": int(item["period"][-2:]) if len(item.get("period", "")) >= 6 else 0,
                        "period": item.get("period", ""),
                        "travelers_score": float(item.get("analytics", {}).get("travelers", {}).get("score", 0)),
                    }
                    for item in data.get("data", [])
                ]
        except Exception as e:
            logger.warning(f"Amadeus busiest-period error for {city_code}: {e}")
            return []

    async def get_most_booked(
        self,
        origin_code: str,
        period: str = "2024-01",
    ) -> list[dict]:
        """Get most booked destinations from an origin city.

        Args:
            origin_code: IATA city code (e.g., "YYZ", "LON")
            period: Month to query (YYYY-MM format)

        Returns list of {destination, travelers_score} dicts.
        """
        if not settings.amadeus_client_id:
            return []

        try:
            async with self._semaphore:
                await self._ensure_token()
                client = await self._get_client()
                resp = await client.get(
                    "/v1/travel/analytics/air-traffic/booked",
                    params={
                        "originCityCode": origin_code,
                        "period": period,
                    },
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                if resp.status_code == 429:
                    await asyncio.sleep(1)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return [
                    {
                        "destination": item.get("destination", ""),
                        "travelers_score": float(item.get("analytics", {}).get("travelers", {}).get("score", 0)),
                    }
                    for item in data.get("data", [])
                ]
        except Exception as e:
            logger.warning(f"Amadeus most-booked error for {origin_code}: {e}")
            return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


amadeus_client = AmadeusClient()
