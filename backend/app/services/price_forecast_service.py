"""Price forecast service — parametric model for flight price prediction.

Uses a layered approach:
1. Days-to-departure (DTD) curve — U-shaped booking window
2. Day-of-week multiplier — weekend vs weekday pricing
3. Seasonality percentile — peak/shoulder/off-peak adjustment
4. Event impact — demand spike from nearby events
5. Seats remaining signal — scarcity pricing

Works from day 1 with no training data. Improves over time as search_logs accumulate.
"""

import logging
import math
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Days-to-departure price curve (multiplier relative to "sweet spot" price)
# Based on airline pricing research: U-shaped curve
DTD_CURVE = {
    # (min_days, max_days): (multiplier, label)
    (0, 3): (1.45, "last_minute"),
    (4, 7): (1.30, "last_minute"),
    (8, 14): (1.10, "short_notice"),
    (15, 21): (1.00, "sweet_spot"),
    (22, 42): (0.95, "sweet_spot"),
    (43, 60): (0.98, "early_bird"),
    (61, 90): (1.02, "early_bird"),
    (91, 180): (1.05, "very_early"),
    (181, 365): (1.08, "very_early"),
}

# Day-of-week departure multipliers (1=Mon, 7=Sun)
DOW_MULTIPLIER = {
    1: 1.02,  # Monday — business travel
    2: 0.97,  # Tuesday — cheapest
    3: 0.98,  # Wednesday
    4: 1.00,  # Thursday
    5: 1.05,  # Friday — weekend travel
    6: 1.03,  # Saturday
    7: 1.04,  # Sunday — return travel
}

# Seasonality multiplier based on percentile (0-1)
SEASON_MULTIPLIERS = {
    "peak": 1.20,
    "shoulder": 1.05,
    "off_peak": 0.88,
    "unknown": 1.00,
}


class PriceForecastService:
    """Parametric price forecast model."""

    def forecast(
        self,
        current_price: float,
        departure_date: date,
        booking_date: date | None = None,
        seasonality: dict | None = None,
        event_impact: str | None = None,
        seats_remaining: int | None = None,
        historical_prices: list[dict] | None = None,
    ) -> dict:
        """Generate price forecast and booking window analysis.

        Args:
            current_price: Current cheapest price found
            departure_date: When the flight departs
            booking_date: When we're computing the forecast (default: today)
            seasonality: Output from AmadeusAnalyticsService.get_route_seasonality()
            event_impact: "low"/"medium"/"high"/"very_high" from PredictHQ
            seats_remaining: Lowest seats remaining across options
            historical_prices: Past search_log prices for this route [{date, price}]

        Returns:
            {
                "predicted_price": float,
                "confidence_band": {"low": float, "high": float},
                "confidence_level": "low" | "medium" | "high",
                "booking_window": {
                    "position": "last_minute" | "sweet_spot" | "early_bird" | "very_early",
                    "days_to_departure": int,
                    "sweet_spot_starts": date,
                    "sweet_spot_ends": date,
                },
                "price_direction": "rising" | "falling" | "stable",
                "factors": [
                    {"name": str, "impact": "positive" | "negative" | "neutral", "detail": str}
                ],
                "urgency_score": float,  # 0-1, higher = book sooner
            }
        """
        if booking_date is None:
            booking_date = date.today()

        dtd = (departure_date - booking_date).days
        if dtd < 0:
            dtd = 0

        factors = []
        urgency_signals = []

        # 1. Days-to-departure analysis
        dtd_multiplier, dtd_label = self._get_dtd_multiplier(dtd)
        sweet_spot_start = departure_date - timedelta(days=42)
        sweet_spot_end = departure_date - timedelta(days=15)

        factors.append({
            "name": "Booking Window",
            "impact": "positive" if dtd_label == "sweet_spot" else "negative" if dtd_label == "last_minute" else "neutral",
            "detail": self._dtd_detail(dtd, dtd_label, sweet_spot_start, sweet_spot_end),
        })

        if dtd_label == "last_minute":
            urgency_signals.append(0.9)
        elif dtd_label == "sweet_spot":
            urgency_signals.append(0.3)
        else:
            urgency_signals.append(0.5)

        # 2. Day-of-week
        dow = departure_date.isoweekday()
        dow_mult = DOW_MULTIPLIER.get(dow, 1.0)
        dow_names = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if dow_mult < 1.0:
            factors.append({
                "name": "Departure Day",
                "impact": "positive",
                "detail": f"{dow_names[dow]} departures tend to be {(1-dow_mult)*100:.0f}% cheaper",
            })
        elif dow_mult > 1.02:
            factors.append({
                "name": "Departure Day",
                "impact": "negative",
                "detail": f"{dow_names[dow]} departures tend to be {(dow_mult-1)*100:.0f}% more expensive",
            })

        # 3. Seasonality
        season_label = "unknown"
        season_mult = 1.0
        if seasonality and seasonality.get("data_available"):
            season_label = seasonality.get("season_label", "unknown")
            season_mult = SEASON_MULTIPLIERS.get(season_label, 1.0)
            month_name = seasonality.get("current_month_name", "")

            if season_label == "peak":
                factors.append({
                    "name": "Peak Season",
                    "impact": "negative",
                    "detail": f"{month_name} is peak travel season — prices are ~{(season_mult-1)*100:.0f}% above average",
                })
                urgency_signals.append(0.7)
            elif season_label == "off_peak":
                factors.append({
                    "name": "Off-Peak Season",
                    "impact": "positive",
                    "detail": f"{month_name} is off-peak — prices are ~{(1-season_mult)*100:.0f}% below average",
                })
                urgency_signals.append(0.2)
            elif season_label == "shoulder":
                factors.append({
                    "name": "Shoulder Season",
                    "impact": "neutral",
                    "detail": f"{month_name} is shoulder season — moderate demand, prices near average",
                })
                urgency_signals.append(0.4)

        # 4. Event impact
        event_mult = 1.0
        if event_impact:
            event_multipliers = {
                "low": 1.02,
                "medium": 1.08,
                "high": 1.15,
                "very_high": 1.25,
            }
            event_mult = event_multipliers.get(event_impact, 1.0)
            if event_mult > 1.05:
                factors.append({
                    "name": "Local Events",
                    "impact": "negative",
                    "detail": f"Events near destination may increase prices by ~{(event_mult-1)*100:.0f}%",
                })
                urgency_signals.append(0.6 + (event_mult - 1))

        # 5. Seats remaining
        seats_mult = 1.0
        if seats_remaining is not None:
            if seats_remaining <= 3:
                seats_mult = 1.15
                factors.append({
                    "name": "Limited Availability",
                    "impact": "negative",
                    "detail": f"Only {seats_remaining} seat{'s' if seats_remaining != 1 else ''} remaining — price likely to increase",
                })
                urgency_signals.append(0.95)
            elif seats_remaining <= 6:
                seats_mult = 1.05
                factors.append({
                    "name": "Moderate Availability",
                    "impact": "neutral",
                    "detail": f"{seats_remaining} seats remaining — availability is tightening",
                })
                urgency_signals.append(0.6)

        # 6. Historical price trend
        price_direction = "stable"
        trend_mult = 1.0
        if historical_prices and len(historical_prices) >= 2:
            trend_result = self._compute_trend(historical_prices)
            price_direction = trend_result["direction"]
            trend_mult = trend_result["multiplier"]
            if price_direction == "rising":
                factors.append({
                    "name": "Price Trend",
                    "impact": "negative",
                    "detail": f"Prices have risen {trend_result['change_pct']:.0f}% over recent searches",
                })
                urgency_signals.append(0.7)
            elif price_direction == "falling":
                factors.append({
                    "name": "Price Trend",
                    "impact": "positive",
                    "detail": f"Prices have dropped {abs(trend_result['change_pct']):.0f}% over recent searches",
                })
                urgency_signals.append(0.2)

        # Compute predicted price
        combined_multiplier = dtd_multiplier * dow_mult * season_mult * event_mult * seats_mult * trend_mult
        predicted_price = current_price * combined_multiplier

        # Confidence band — wider when we have less data
        base_uncertainty = 0.12
        if historical_prices and len(historical_prices) >= 5:
            base_uncertainty = 0.08
        elif not historical_prices:
            base_uncertainty = 0.18

        confidence_band = {
            "low": round(predicted_price * (1 - base_uncertainty), 2),
            "high": round(predicted_price * (1 + base_uncertainty), 2),
        }

        confidence_level = "medium"
        if historical_prices and len(historical_prices) >= 10:
            confidence_level = "high"
        elif not historical_prices or len(historical_prices) < 3:
            confidence_level = "low"

        # Urgency score
        urgency_score = sum(urgency_signals) / len(urgency_signals) if urgency_signals else 0.5
        urgency_score = min(1.0, max(0.0, urgency_score))

        return {
            "predicted_price": round(predicted_price, 2),
            "confidence_band": confidence_band,
            "confidence_level": confidence_level,
            "booking_window": {
                "position": dtd_label,
                "days_to_departure": dtd,
                "sweet_spot_starts": sweet_spot_start.isoformat(),
                "sweet_spot_ends": sweet_spot_end.isoformat(),
            },
            "price_direction": price_direction,
            "factors": factors,
            "urgency_score": round(urgency_score, 2),
        }

    def _get_dtd_multiplier(self, dtd: int) -> tuple[float, str]:
        """Get price multiplier and label for days-to-departure."""
        for (min_d, max_d), (mult, label) in DTD_CURVE.items():
            if min_d <= dtd <= max_d:
                return mult, label
        # Beyond 365 days
        return 1.10, "very_early"

    def _dtd_detail(self, dtd: int, label: str, sweet_start: date, sweet_end: date) -> str:
        """Human-readable detail about booking window position."""
        if label == "last_minute":
            return f"Booking {dtd} days before departure — last-minute premium likely applies"
        elif label == "short_notice":
            return f"Booking {dtd} days out — slightly above sweet-spot pricing"
        elif label == "sweet_spot":
            return f"Booking {dtd} days out — in the optimal booking window (15-42 days)"
        elif label == "early_bird":
            return f"Booking {dtd} days early — prices may drop closer to the sweet spot ({sweet_start.strftime('%b %d')}–{sweet_end.strftime('%b %d')})"
        else:
            return f"Booking {dtd} days out — very early, prices will likely adjust"

    def _compute_trend(self, historical_prices: list[dict]) -> dict:
        """Compute price trend from historical search logs."""
        # Sort by date
        sorted_prices = sorted(historical_prices, key=lambda x: x.get("date", ""))

        if len(sorted_prices) < 2:
            return {"direction": "stable", "multiplier": 1.0, "change_pct": 0}

        # Compare recent vs older prices
        midpoint = len(sorted_prices) // 2
        older_avg = sum(p.get("price", 0) for p in sorted_prices[:midpoint]) / midpoint
        recent_avg = sum(p.get("price", 0) for p in sorted_prices[midpoint:]) / (len(sorted_prices) - midpoint)

        if older_avg == 0:
            return {"direction": "stable", "multiplier": 1.0, "change_pct": 0}

        change_pct = ((recent_avg - older_avg) / older_avg) * 100

        if change_pct > 5:
            return {"direction": "rising", "multiplier": 1.0 + min(change_pct / 200, 0.1), "change_pct": change_pct}
        elif change_pct < -5:
            return {"direction": "falling", "multiplier": 1.0 + max(change_pct / 200, -0.1), "change_pct": change_pct}
        else:
            return {"direction": "stable", "multiplier": 1.0, "change_pct": change_pct}


forecast_service = PriceForecastService()
