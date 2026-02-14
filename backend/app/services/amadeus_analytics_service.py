"""Amadeus analytics service — route seasonality from air-traffic APIs."""

import logging
from datetime import date

from app.services.amadeus_client import amadeus_client
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

# Month names for readability
MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


class AmadeusAnalyticsService:
    """Fetches and normalizes Amadeus air-traffic analytics with Redis caching."""

    async def get_route_seasonality(
        self,
        destination_city: str,
        travel_date: date,
    ) -> dict:
        """Get seasonality data for a destination city.

        Returns:
            {
                "peak_months": [7, 8, 12],
                "off_peak_months": [1, 2, 11],
                "current_month_percentile": 0.75,  # 0-1 where 1 = peak
                "season_label": "peak" | "shoulder" | "off_peak",
                "data_available": True,
            }
        """
        # Check cache first
        cached = await cache_service.get_analytics(destination_city)
        if cached:
            # Recalculate current_month fields for the travel_date
            return self._enrich_with_travel_date(cached, travel_date)

        # Fetch from Amadeus — try multiple years for better data
        monthly_scores: dict[int, float] = {}
        for year in ["2024", "2023"]:
            data = await amadeus_client.get_busiest_period(
                city_code=destination_city,
                period=year,
                direction="ARRIVING",
            )
            if data:
                for item in data:
                    month = item.get("month", 0)
                    score = item.get("travelers_score", 0)
                    if month > 0:
                        # Average across years if we have multiple
                        if month in monthly_scores:
                            monthly_scores[month] = (monthly_scores[month] + score) / 2
                        else:
                            monthly_scores[month] = score
                break  # Use first year that returns data

        if not monthly_scores:
            return {
                "peak_months": [],
                "off_peak_months": [],
                "current_month_percentile": 0.5,
                "season_label": "unknown",
                "data_available": False,
            }

        # Normalize scores to percentiles
        result = self._compute_seasonality(monthly_scores)

        # Cache the raw seasonality (without travel-date-specific fields)
        await cache_service.set_analytics(destination_city, result)

        return self._enrich_with_travel_date(result, travel_date)

    async def get_route_popularity(
        self,
        origin_city: str,
        destination_city: str,
        travel_date: date,
    ) -> dict:
        """Check if a route is popular (high demand) for the travel month.

        Returns:
            {
                "is_popular_route": True/False,
                "popularity_score": 0-100,
                "data_available": True,
            }
        """
        period = travel_date.strftime("%Y-%m")
        cache_key = f"popularity:{origin_city}:{destination_city}:{period}"
        cached = await cache_service.get(cache_key)
        if cached:
            return cached

        booked = await amadeus_client.get_most_booked(
            origin_code=origin_city,
            period=period,
        )

        if not booked:
            # Try a fallback period
            fallback_period = "2024-01"
            booked = await amadeus_client.get_most_booked(
                origin_code=origin_city,
                period=fallback_period,
            )

        result = {
            "is_popular_route": False,
            "popularity_score": 0,
            "data_available": bool(booked),
        }

        if booked:
            # Check if destination appears in most-booked list
            for item in booked:
                if item.get("destination", "").upper() == destination_city.upper():
                    result["is_popular_route"] = True
                    result["popularity_score"] = item.get("travelers_score", 0)
                    break

        from app.services.cache_service import TTL_ANALYTICS
        await cache_service.set(cache_key, result, TTL_ANALYTICS)
        return result

    def _compute_seasonality(self, monthly_scores: dict[int, float]) -> dict:
        """Compute peak/off-peak from monthly traveler scores."""
        if not monthly_scores:
            return {
                "monthly_scores": {},
                "peak_months": [],
                "off_peak_months": [],
                "shoulder_months": [],
            }

        scores = list(monthly_scores.values())
        max_score = max(scores) if scores else 1
        min_score = min(scores) if scores else 0
        score_range = max_score - min_score if max_score != min_score else 1

        peak_months = []
        off_peak_months = []
        shoulder_months = []

        for month, score in monthly_scores.items():
            percentile = (score - min_score) / score_range
            if percentile >= 0.7:
                peak_months.append(month)
            elif percentile <= 0.3:
                off_peak_months.append(month)
            else:
                shoulder_months.append(month)

        return {
            "monthly_scores": {str(m): s for m, s in monthly_scores.items()},
            "peak_months": sorted(peak_months),
            "off_peak_months": sorted(off_peak_months),
            "shoulder_months": sorted(shoulder_months),
        }

    def _enrich_with_travel_date(self, seasonality: dict, travel_date: date) -> dict:
        """Add travel-date-specific fields to cached seasonality data."""
        result = {**seasonality, "data_available": True}
        travel_month = travel_date.month
        monthly_scores = seasonality.get("monthly_scores", {})

        if monthly_scores:
            scores = [float(v) for v in monthly_scores.values()]
            max_score = max(scores) if scores else 1
            min_score = min(scores) if scores else 0
            score_range = max_score - min_score if max_score != min_score else 1

            current_score = float(monthly_scores.get(str(travel_month), (max_score + min_score) / 2))
            result["current_month_percentile"] = (current_score - min_score) / score_range
        else:
            result["current_month_percentile"] = 0.5

        if travel_month in seasonality.get("peak_months", []):
            result["season_label"] = "peak"
        elif travel_month in seasonality.get("off_peak_months", []):
            result["season_label"] = "off_peak"
        elif travel_month in seasonality.get("shoulder_months", []):
            result["season_label"] = "shoulder"
        else:
            result["season_label"] = "unknown"

        result["current_month_name"] = MONTH_NAMES[travel_month]
        return result


analytics_service = AmadeusAnalyticsService()
