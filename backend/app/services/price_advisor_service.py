"""Price Advisor service — LLM-powered booking recommendation engine.

Orchestrates signals from:
- PriceForecastService (parametric model)
- AmadeusAnalyticsService (seasonality)
- PredictHQ events
- Search results (prices, seats, direct vs connecting)

Synthesizes via Claude into actionable book/wait/watch advice.
Falls back to rule-based recommendations if Claude fails.
"""

import json
import logging
from datetime import date

from app.config import settings
from app.services.llm_client import llm_client
from app.services.amadeus_analytics_service import analytics_service
from app.services.cache_service import cache_service
from app.services.price_forecast_service import forecast_service
from app.services.recommendation.prompts import load_prompt

logger = logging.getLogger(__name__)

# Load reasoning guide once at module level
_PRICE_GUIDE = load_prompt("price_advisor_guide.md")

ADVISOR_SYSTEM_PROMPT = f"""{_PRICE_GUIDE}

---

Your response MUST be valid JSON with this exact structure:
{{
    "recommendation": "book" | "wait" | "watch",
    "confidence": 0.0-1.0,
    "headline": "One compelling sentence summarizing the advice",
    "analysis": "2-3 sentences explaining the reasoning with specific data points",
    "factors": [
        {{"name": "Factor Name", "impact": "positive" | "negative" | "neutral", "detail": "Brief explanation"}}
    ],
    "timing_advice": "When to book and what to watch for",
    "savings_potential": "$X-Y CAD potential savings if timing is optimized"
}}

The user message contains a JSON object matching the input schema above.
Analyze all fields, apply the reasoning steps, and respond with ONLY
the JSON recommendation. No markdown formatting, no preamble."""


# Direction label mapping — forecast uses rising/falling, guide uses increasing/decreasing
_DIRECTION_MAP = {
    "rising": "increasing",
    "falling": "decreasing",
    "stable": "stable",
}


class PriceAdvisorService:
    """Orchestrates all pricing signals and produces LLM-powered advice."""

    def __init__(self):
        pass

    async def get_advice(
        self,
        search_id: str,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        flights: list[dict],
        events: list[dict] | None = None,
        origin_city: str | None = None,
        destination_city: str | None = None,
        trip_type: str | None = None,
        leg_label: str | None = None,
    ) -> dict:
        """Generate price advice for a search result.

        Args:
            search_id: Unique search identifier (for caching)
            origin: Origin airport code (e.g., "YYZ")
            destination: Destination airport code (e.g., "LHR")
            departure_date: Travel date
            cabin_class: "economy", "business", etc.
            flights: List of flight options from search results
            events: Optional PredictHQ events near destination
            origin_city: Origin city name for display
            destination_city: Destination city name for display
            trip_type: "one_way" or "round_trip"
            leg_label: "outbound", "return", or "one_way"

        Returns:
            Advisor response dict with recommendation, analysis, factors, etc.
        """
        if not settings.price_intelligence_enabled:
            return self._disabled_response()

        # Check cache
        cached = await cache_service.get_advisor(search_id)
        if cached:
            return cached

        # Gather signals
        signals = await self._gather_signals(
            origin, destination, departure_date, cabin_class,
            flights, events,
        )

        # Generate advice via LLM
        advice = await self._generate_llm_advice(
            signals, origin, destination, departure_date,
            cabin_class, origin_city, destination_city,
            trip_type, leg_label,
        )

        # Cache the result
        await cache_service.set_advisor(search_id, advice)

        return advice

    async def _gather_signals(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        flights: list[dict],
        events: list[dict] | None,
    ) -> dict:
        """Collect all pricing signals for the advisor."""
        # Price stats from search results
        prices = [f.get("price", 0) for f in flights if f.get("price", 0) > 0]
        direct_flights = [f for f in flights if f.get("stops", 1) == 0]
        connecting_flights = [f for f in flights if f.get("stops", 0) > 0]
        direct_prices = [f.get("price", 0) for f in direct_flights if f.get("price", 0) > 0]
        connecting_prices = [f.get("price", 0) for f in connecting_flights if f.get("price", 0) > 0]

        # Seats remaining — use the cheapest flight's seats, not global minimum
        # Global min is misleading (e.g., 1 seat on a $10k flight is irrelevant)
        cheapest_price = min(prices) if prices else 0
        cheapest_flights = [f for f in flights if f.get("price", 0) == cheapest_price]
        if cheapest_flights and cheapest_flights[0].get("seats_remaining") is not None:
            min_seats = cheapest_flights[0]["seats_remaining"]
        else:
            # Fallback: median seats across all options
            seats = sorted([f.get("seats_remaining") for f in flights if f.get("seats_remaining") is not None])
            min_seats = seats[len(seats) // 2] if seats else None

        # Determine flight type of cheapest option
        cheapest_is_direct = any(
            f.get("stops", 1) == 0
            for f in cheapest_flights
        ) if cheapest_flights else False

        price_stats = {
            "cheapest": min(prices) if prices else 0,
            "most_expensive": max(prices) if prices else 0,
            "average": sum(prices) / len(prices) if prices else 0,
            "option_count": len(flights),
            "direct_count": len(direct_flights),
            "connecting_count": len(connecting_flights),
            "cheapest_direct": min(direct_prices) if direct_prices else None,
            "cheapest_connecting": min(connecting_prices) if connecting_prices else None,
            "min_seats_remaining": min_seats,
            "cheapest_is_direct": cheapest_is_direct,
        }

        # Seasonality from Amadeus analytics
        # Use first 3 chars of airport code as city code approximation
        dest_city = destination[:3]
        seasonality = await analytics_service.get_route_seasonality(
            destination_city=dest_city,
            travel_date=departure_date,
        )

        # Event impact level
        event_impact = None
        event_details = []
        if events:
            for evt in events[:5]:  # Top 5 events
                impact = evt.get("impact_level", evt.get("impact", "low"))
                event_details.append({
                    "name": evt.get("title", evt.get("name", "Event")),
                    "impact": impact,
                    "category": evt.get("category", ""),
                    "date": evt.get("date", evt.get("start_date", "")),
                })
            # Overall event impact = highest individual impact
            impact_order = {"low": 0, "medium": 1, "high": 2, "very_high": 3}
            max_impact = max(
                (impact_order.get(e.get("impact", "low"), 0) for e in event_details),
                default=0,
            )
            event_impact = {0: "low", 1: "medium", 2: "high", 3: "very_high"}.get(max_impact, "low")

        # Price forecast
        forecast = forecast_service.forecast(
            current_price=price_stats["cheapest"],
            departure_date=departure_date,
            seasonality=seasonality,
            event_impact=event_impact,
            seats_remaining=min_seats,
        )

        # Historical price context — DB1B primary, Amadeus fallback
        from app.services.db1b_client import db1b_client
        from app.services.amadeus_client import amadeus_client

        price_metrics = None
        price_percentile = None
        price_percentile_label = None
        price_assessment = None  # LOW/TYPICAL/HIGH — populated if data source provides it

        try:
            # Check cache first
            cached_metrics = await cache_service.get_price_metrics(
                origin, destination, departure_date.isoformat(), cabin_class
            )
            if cached_metrics and cached_metrics.get("available"):
                price_metrics = cached_metrics.get("historical")
                price_percentile = cached_metrics.get("percentile")
                price_percentile_label = cached_metrics.get("percentile_label")
                price_assessment = cached_metrics.get("price_assessment")
            elif cached_metrics is None:
                # Primary: DB1B historical data
                db1b_context = await db1b_client.get_price_context(
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    cabin_class=cabin_class,
                    current_price=price_stats["cheapest"],
                )
                if db1b_context and db1b_context.get("available"):
                    price_metrics = db1b_context.get("historical")
                    price_percentile = db1b_context.get("percentile")
                    price_percentile_label = db1b_context.get("percentile_label")
                    # Cache it
                    await cache_service.set_price_metrics(
                        origin, destination, departure_date.isoformat(),
                        cabin_class, db1b_context,
                    )
                else:
                    # Fallback: Amadeus (no cabin-specific metrics available)
                    raw_metrics = await amadeus_client.get_price_metrics(
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                    )
                    if raw_metrics:
                        price_metrics = raw_metrics
                        cheapest = price_stats["cheapest"]
                        price_range = raw_metrics.get("max", 0) - raw_metrics.get("min", 0)
                        if price_range > 0 and cheapest > 0:
                            price_percentile = round(((cheapest - raw_metrics["min"]) / price_range) * 100)
                            price_percentile = max(0, min(100, price_percentile))
                            if price_percentile <= 25:
                                price_percentile_label = "excellent"
                            elif price_percentile <= 50:
                                price_percentile_label = "good"
                            elif price_percentile <= 75:
                                price_percentile_label = "average"
                            else:
                                price_percentile_label = "high"
        except Exception as e:
            logger.warning(f"Failed to fetch price metrics: {e}")

        return {
            "price_stats": price_stats,
            "seasonality": seasonality,
            "event_impact": event_impact,
            "event_details": event_details,
            "forecast": forecast,
            "cabin_class": cabin_class,
            "price_metrics": price_metrics,
            "price_percentile": price_percentile,
            "price_percentile_label": price_percentile_label,
            "price_assessment": price_assessment,
        }

    async def _generate_llm_advice(
        self,
        signals: dict,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        origin_city: str | None,
        destination_city: str | None,
        trip_type: str | None,
        leg_label: str | None,
    ) -> dict:
        """Call Claude to synthesize signals into natural-language advice."""
        prompt = self._build_prompt(
            signals, origin, destination, departure_date,
            cabin_class, origin_city, destination_city,
            trip_type, leg_label,
        )

        try:
            raw_text = await llm_client.complete(
                system=ADVISOR_SYSTEM_PROMPT,
                user=prompt,
                max_tokens=800,
                temperature=0.2,
                json_mode=True,
            )
            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

            advice = json.loads(raw_text)

            # Validate required fields
            required = ["recommendation", "confidence", "headline", "analysis", "factors"]
            if not all(k in advice for k in required):
                raise ValueError(f"Missing required fields: {[k for k in required if k not in advice]}")

            # Ensure recommendation is valid
            if advice["recommendation"] not in ("book", "wait", "watch"):
                advice["recommendation"] = "watch"

            advice["source"] = "llm"
            return advice

        except Exception as e:
            logger.error(f"Claude advisor failed, using fallback: {e}")
            return self._fallback_advice(signals, origin, destination, departure_date)

    def _build_prompt(
        self,
        signals: dict,
        origin: str,
        destination: str,
        departure_date: date,
        cabin_class: str,
        origin_city: str | None,
        destination_city: str | None,
        trip_type: str | None,
        leg_label: str | None,
    ) -> str:
        """Build a structured JSON prompt matching the v4 guide schema."""
        from app.services.recommendation.config import recommendation_config

        ps = signals["price_stats"]
        forecast = signals["forecast"]
        seasonality = signals["seasonality"]

        # Build historical object (null if no data)
        historical = None
        pm = signals.get("price_metrics")
        if pm:
            historical = {
                "percentile": signals.get("price_percentile"),
                "low": pm.get("min"),
                "q1": pm.get("q1"),
                "median": pm.get("median"),
                "q3": pm.get("q3"),
                "high": pm.get("max"),
                "data_points": pm.get("data_points"),  # null for DB1B
            }

        # Build forecast object
        direction_raw = forecast.get("price_direction", "stable")
        forecast_obj = {
            "predicted_price": forecast["predicted_price"],
            "direction": _DIRECTION_MAP.get(direction_raw, direction_raw),
            "urgency": forecast["urgency_score"],
            "confidence_band_low": forecast["confidence_band"]["low"],
            "confidence_band_high": forecast["confidence_band"]["high"],
        }

        # Build events list
        events_list = []
        for evt in signals.get("event_details", []):
            entry = {
                "name": evt["name"],
                "impact": evt["impact"],
            }
            if evt.get("date"):
                entry["date"] = evt["date"]
            events_list.append(entry)

        # Season label — normalize off_peak → off-peak
        season_label = seasonality.get("season_label", "unknown") if seasonality.get("data_available") else None
        if season_label == "off_peak":
            season_label = "off-peak"

        # Flight type of cheapest option
        flight_type = "nonstop" if ps.get("cheapest_is_direct") else "connecting"

        # Corporate rate cap from policy config
        corporate_rate_cap = recommendation_config.policy_budgets.get(cabin_class)

        # Origin/destination display — prefer city names
        origin_display = f"{origin_city} ({origin})" if origin_city else origin
        dest_display = f"{destination_city} ({destination})" if destination_city else destination

        input_data = {
            "current_price": round(ps["cheapest"], 2),
            "currency": "CAD",
            "origin": origin_display,
            "destination": dest_display,
            "departure_date": departure_date.isoformat(),
            "booking_date": date.today().isoformat(),
            "cabin_class": cabin_class,
            "flight_type": flight_type,
            "trip_type": trip_type,
            "leg": leg_label,
            "historical": historical,
            "price_assessment": signals.get("price_assessment"),
            "forecast": forecast_obj,
            "seats_remaining_cheapest_fare": ps.get("min_seats_remaining"),
            "events": events_list if events_list else [],
            "season": season_label,
            "corporate_rate_cap": corporate_rate_cap,
        }

        return json.dumps(input_data, indent=2)

    def _fallback_advice(
        self,
        signals: dict,
        origin: str,
        destination: str,
        departure_date: date,
    ) -> dict:
        """Rule-based fallback when Claude is unavailable."""
        forecast = signals["forecast"]
        ps = signals["price_stats"]
        bw = forecast["booking_window"]
        urgency = forecast["urgency_score"]

        # Determine recommendation from rules
        if ps.get("min_seats_remaining") is not None and ps["min_seats_remaining"] <= 3:
            recommendation = "book"
            headline = f"Only {ps['min_seats_remaining']} seat{'s' if ps['min_seats_remaining'] != 1 else ''} remaining — book now to secure this price"
        elif bw["days_to_departure"] <= 7:
            recommendation = "book"
            headline = f"Departure in {bw['days_to_departure']} days — book now, prices will only increase"
        elif urgency >= 0.7:
            recommendation = "book"
            headline = f"Multiple signals suggest prices are likely to rise — consider booking at ${ps['cheapest']:.0f} CAD"
        elif urgency <= 0.3 and bw["position"] in ("early_bird", "very_early"):
            recommendation = "wait"
            headline = f"You're booking early — prices may drop closer to the sweet spot ({bw['sweet_spot_starts']})"
        else:
            recommendation = "watch"
            headline = f"Price is near average at ${ps['cheapest']:.0f} CAD — monitor for dips"

        # Historical price context can override recommendation
        if signals.get("price_metrics") and signals.get("price_percentile") is not None:
            pct = signals["price_percentile"]
            if pct <= 25 and recommendation != "book":
                recommendation = "book"
                headline = f"Price at ${ps['cheapest']:.0f} CAD is historically low ({pct}th percentile) — strong buy signal"
            elif pct >= 75 and recommendation not in ("book",):
                # Don't override "book" from seats/timing rules
                recommendation = "wait"
                headline = f"Price at ${ps['cheapest']:.0f} CAD is above average ({pct}th percentile) — consider waiting"

        # Build factors from forecast
        factors = forecast.get("factors", [])
        if not factors:
            factors = [
                {"name": "Current Price", "impact": "neutral", "detail": f"${ps['cheapest']:.0f} CAD cheapest option"},
                {"name": "Booking Window", "impact": "neutral", "detail": f"{bw['days_to_departure']} days to departure"},
            ]

        # Add historical price factor
        if signals.get("price_metrics") and signals.get("price_percentile") is not None:
            pct = signals["price_percentile"]
            pct_label = signals["price_percentile_label"]
            impact = "positive" if pct <= 25 else "negative" if pct >= 75 else "neutral"
            factors.append({
                "name": "Historical Price",
                "impact": impact,
                "detail": f"Current price is {pct_label} ({pct}th percentile historically)",
            })

        return {
            "recommendation": recommendation,
            "confidence": round(min(0.6, urgency), 2),
            "headline": headline,
            "analysis": (
                f"Based on {ps['option_count']} flight options found, "
                f"the cheapest fare is ${ps['cheapest']:.0f} CAD. "
                f"You are booking {bw['days_to_departure']} days before departure "
                f"({bw['position'].replace('_', ' ')} window)."
            ),
            "factors": factors[:6],
            "timing_advice": self._fallback_timing(bw, urgency),
            "savings_potential": self._fallback_savings(ps, forecast),
            "source": "fallback",
        }

    def _fallback_timing(self, bw: dict, urgency: float) -> str:
        if bw["position"] == "last_minute":
            return "Prices are in the last-minute premium zone. Book as soon as possible."
        elif bw["position"] == "sweet_spot":
            return "You're in the optimal booking window. Good time to lock in your fare."
        elif bw["position"] in ("early_bird", "very_early"):
            return f"Consider waiting until the sweet spot ({bw['sweet_spot_starts']}) for potentially lower prices."
        return "Monitor prices and book when you see a price you're comfortable with."

    def _fallback_savings(self, ps: dict, forecast: dict) -> str:
        spread = ps["most_expensive"] - ps["cheapest"]
        if spread > 100:
            return f"${spread:.0f} CAD spread between cheapest and most expensive options"
        return "Limited price variation across available options"

    def _disabled_response(self) -> dict:
        return {
            "recommendation": "watch",
            "confidence": 0,
            "headline": "Price intelligence is currently disabled",
            "analysis": "Enable price_intelligence_enabled in settings to get booking recommendations.",
            "factors": [],
            "timing_advice": "",
            "savings_potential": "",
            "source": "disabled",
        }


price_advisor = PriceAdvisorService()
