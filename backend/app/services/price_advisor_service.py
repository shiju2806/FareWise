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
from decimal import Decimal

import anthropic

from app.config import settings
from app.services.amadeus_analytics_service import analytics_service
from app.services.cache_service import cache_service
from app.services.price_forecast_service import forecast_service

logger = logging.getLogger(__name__)

ADVISOR_SYSTEM_PROMPT = """You are a corporate travel price intelligence advisor. Analyze the provided flight pricing signals and produce a clear, actionable recommendation for a corporate traveler.

Your response MUST be valid JSON with this exact structure:
{
    "recommendation": "book" | "wait" | "watch",
    "confidence": 0.0-1.0,
    "headline": "One compelling sentence summarizing the advice",
    "analysis": "2-3 sentences explaining the reasoning with specific data points",
    "factors": [
        {"name": "Factor Name", "impact": "positive" | "negative" | "neutral", "detail": "Brief explanation"}
    ],
    "timing_advice": "When to book and what to watch for",
    "savings_potential": "$X-Y CAD potential savings if timing is optimized"
}

Guidelines:
- "book" = price is good, book now before it increases
- "wait" = price will likely drop, wait for sweet spot
- "watch" = price is volatile, monitor daily
- Be specific with dollar amounts and dates
- Factor in corporate travel context (expense reports, approval timelines)
- If departure is within 7 days, always recommend "book" (no time to wait)
- Provide 3-6 factors, prioritized by impact
- Keep analysis professional and data-driven — no urgency hype or alarming language
- Use CAD currency throughout

IMPORTANT — Market range context:
- The "MARKET PRICE RANGE" section shows the spread of prices from DIFFERENT airlines on the SAME date
- This is NOT historical pricing over time — it's today's market snapshot across carriers
- A price near the bottom of this range means it's competitively priced TODAY, not "historically exceptional"
- Small differences from the range minimum (<10%) are normal fare variation, not remarkable
- Google Flights' own assessment (LOW/TYPICAL/HIGH) is the most reliable signal — it is backed by Google's actual historical data. TRUST this assessment over computed percentiles
- If Google says TYPICAL but our percentile says 0th, trust Google — the price is normal
- Do NOT manufacture urgency from minor price differences between data sources
- Seats remaining refers to the cheapest fare only; other fares may have plenty of seats

Respond with ONLY the JSON, no markdown formatting, no preamble."""


class PriceAdvisorService:
    """Orchestrates all pricing signals and produces LLM-powered advice."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

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
        google_assessment = None

        try:
            # Check cache first
            cached_metrics = await cache_service.get_price_metrics(
                origin, destination, departure_date.isoformat(), cabin_class
            )
            if cached_metrics and cached_metrics.get("available"):
                price_metrics = cached_metrics.get("historical")
                price_percentile = cached_metrics.get("percentile")
                price_percentile_label = cached_metrics.get("percentile_label")
                google_assessment = cached_metrics.get("google_assessment")
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
            "google_assessment": google_assessment,
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
    ) -> dict:
        """Call Claude to synthesize signals into natural-language advice."""
        prompt = self._build_prompt(
            signals, origin, destination, departure_date,
            cabin_class, origin_city, destination_city,
        )

        try:
            message = await self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=800,
                temperature=0.2,
                system=ADVISOR_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = message.content[0].text.strip()
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
    ) -> str:
        """Build the structured prompt for Claude."""
        ps = signals["price_stats"]
        forecast = signals["forecast"]
        seasonality = signals["seasonality"]
        bw = forecast["booking_window"]

        route_display = f"{origin_city or origin} ({origin}) → {destination_city or destination} ({destination})"

        sections = [
            f"Route: {route_display}",
            f"Departure: {departure_date.isoformat()} ({departure_date.strftime('%A')})",
            f"Cabin: {cabin_class}",
            f"",
            f"=== CURRENT PRICES ===",
            f"Cheapest: ${ps['cheapest']:.0f} CAD",
            f"Most expensive: ${ps['most_expensive']:.0f} CAD",
            f"Average: ${ps['average']:.0f} CAD",
            f"Total options: {ps['option_count']}",
            f"Direct flights: {ps['direct_count']}",
            f"Connecting flights: {ps['connecting_count']}",
        ]

        if ps.get("cheapest_direct"):
            sections.append(f"Cheapest direct: ${ps['cheapest_direct']:.0f} CAD")
        if ps.get("cheapest_connecting"):
            sections.append(f"Cheapest connecting: ${ps['cheapest_connecting']:.0f} CAD")
        if ps.get("min_seats_remaining") is not None:
            sections.append(f"Seats remaining at cheapest fare: {ps['min_seats_remaining']}")

        sections.extend([
            f"",
            f"=== BOOKING WINDOW ===",
            f"Days to departure: {bw['days_to_departure']}",
            f"Window position: {bw['position']}",
            f"Sweet spot: {bw['sweet_spot_starts']} to {bw['sweet_spot_ends']}",
        ])

        sections.extend([
            f"",
            f"=== FORECAST MODEL ===",
            f"Predicted price: ${forecast['predicted_price']:.0f} CAD",
            f"Confidence band: ${forecast['confidence_band']['low']:.0f}–${forecast['confidence_band']['high']:.0f} CAD",
            f"Confidence level: {forecast['confidence_level']}",
            f"Price direction: {forecast['price_direction']}",
            f"Urgency score: {forecast['urgency_score']:.2f} (0=no rush, 1=book immediately)",
        ])

        if seasonality.get("data_available"):
            sections.extend([
                f"",
                f"=== SEASONALITY ===",
                f"Season: {seasonality.get('season_label', 'unknown')}",
                f"Month percentile: {seasonality.get('current_month_percentile', 0.5):.0%} (higher = busier)",
                f"Peak months: {', '.join(str(m) for m in seasonality.get('peak_months', []))}",
                f"Off-peak months: {', '.join(str(m) for m in seasonality.get('off_peak_months', []))}",
            ])

        if signals.get("event_details"):
            sections.extend([
                f"",
                f"=== EVENTS NEAR DESTINATION ===",
            ])
            for evt in signals["event_details"]:
                sections.append(f"- {evt['name']} (impact: {evt['impact']}, category: {evt.get('category', 'N/A')})")

        if signals.get("price_metrics"):
            pm = signals["price_metrics"]
            sections.extend([
                f"",
                f"=== MARKET PRICE RANGE (same-day, across airlines) ===",
                f"Cheapest available: ${pm.get('min', 0):.0f} CAD",
                f"25th percentile: ${pm.get('q1', 0):.0f} CAD",
                f"Median: ${pm.get('median', 0):.0f} CAD",
                f"75th percentile: ${pm.get('q3', 0):.0f} CAD",
                f"Most expensive: ${pm.get('max', 0):.0f} CAD",
            ])
            if signals.get("price_percentile") is not None:
                sections.append(
                    f"Current cheapest (${ps['cheapest']:.0f}) falls at the "
                    f"{signals['price_percentile']}th percentile of today's market range "
                    f"({signals['price_percentile_label']})"
                )
            if signals.get("google_assessment"):
                sections.append(
                    f"Google Flights assessment (based on real historical data): {signals['google_assessment'].upper()} price"
                )

        if forecast.get("factors"):
            sections.extend([
                f"",
                f"=== MODEL FACTORS ===",
            ])
            for f in forecast["factors"]:
                sections.append(f"- {f['name']} ({f['impact']}): {f['detail']}")

        return "\n".join(sections)

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
            pct_label = signals["price_percentile_label"]
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
