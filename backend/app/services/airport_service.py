"""Airport service — resolves cities to airports and finds nearby alternatives."""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import NearbyAirport

logger = logging.getLogger(__name__)


class AirportService:
    """Resolves cities to airports and finds nearby alternatives."""

    async def get_airports_for_city(self, db: AsyncSession, city_name: str) -> list[dict]:
        """Returns all airports for a city/metro area, primary first."""
        result = await db.execute(
            select(NearbyAirport)
            .where(func.lower(NearbyAirport.city_name) == city_name.lower())
            .order_by(NearbyAirport.is_primary.desc())
        )
        airports = result.scalars().all()

        if not airports:
            # Try partial match on city name or metro area
            result = await db.execute(
                select(NearbyAirport)
                .where(
                    func.lower(NearbyAirport.city_name).contains(city_name.lower())
                    | func.lower(NearbyAirport.metro_area).contains(city_name.lower())
                )
                .order_by(NearbyAirport.is_primary.desc())
            )
            airports = result.scalars().all()

        return [
            {
                "iata": a.airport_iata,
                "name": a.airport_name,
                "city": a.city_name,
                "is_primary": a.is_primary,
                "latitude": float(a.latitude) if a.latitude else None,
                "longitude": float(a.longitude) if a.longitude else None,
                "metro_area": a.metro_area,
            }
            for a in airports
        ]

    async def get_nearby_airports(
        self, db: AsyncSession, airport_iata: str, radius_km: int = 150
    ) -> list[dict]:
        """Given an airport IATA code, find alternatives in the same metro area."""
        # Find the metro area for this airport
        result = await db.execute(
            select(NearbyAirport).where(NearbyAirport.airport_iata == airport_iata)
        )
        airport = result.scalar_one_or_none()

        if not airport or not airport.metro_area:
            return []

        # Get all airports in the same metro area (excluding the given one)
        result = await db.execute(
            select(NearbyAirport)
            .where(
                NearbyAirport.metro_area == airport.metro_area,
                NearbyAirport.airport_iata != airport_iata,
            )
            .order_by(NearbyAirport.is_primary.desc())
        )
        nearby = result.scalars().all()

        return [
            {
                "iata": a.airport_iata,
                "name": a.airport_name,
                "city": a.city_name,
                "is_primary": a.is_primary,
                "latitude": float(a.latitude) if a.latitude else None,
                "longitude": float(a.longitude) if a.longitude else None,
                "metro_area": a.metro_area,
            }
            for a in nearby
        ]

    async def get_primary_airport(self, db: AsyncSession, city_name: str) -> dict | None:
        """Get the primary airport for a city."""
        airports = await self.get_airports_for_city(db, city_name)
        if airports:
            # Return the primary one, or first if none marked primary
            primary = next((a for a in airports if a["is_primary"]), airports[0])
            return primary
        return None

    async def search_airports(self, db: AsyncSession, query: str, limit: int = 10) -> list[dict]:
        """Search airports by city name, IATA code, or airport name."""
        q = query.strip().upper()

        # Try exact IATA match first
        result = await db.execute(
            select(NearbyAirport).where(NearbyAirport.airport_iata == q)
        )
        exact = result.scalar_one_or_none()
        if exact:
            return [
                {
                    "iata": exact.airport_iata,
                    "name": exact.airport_name,
                    "city": exact.city_name,
                    "is_primary": exact.is_primary,
                    "metro_area": exact.metro_area,
                }
            ]

        # Fuzzy search on city name and airport name
        q_lower = query.strip().lower()
        result = await db.execute(
            select(NearbyAirport)
            .where(
                func.lower(NearbyAirport.city_name).contains(q_lower)
                | func.lower(NearbyAirport.airport_name).contains(q_lower)
                | func.lower(NearbyAirport.airport_iata).contains(q_lower)
            )
            .order_by(NearbyAirport.is_primary.desc())
            .limit(limit)
        )
        airports = result.scalars().all()

        return [
            {
                "iata": a.airport_iata,
                "name": a.airport_name,
                "city": a.city_name,
                "is_primary": a.is_primary,
                "metro_area": a.metro_area,
            }
            for a in airports
        ]


airport_service = AirportService()
