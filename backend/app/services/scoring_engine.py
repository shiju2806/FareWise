"""Scoring engine — ranks flight options with configurable cost/convenience weights."""

import math
from dataclasses import dataclass


@dataclass
class Weights:
    cost: float = 0.5
    time: float = 0.3
    stops: float = 0.15
    departure: float = 0.05


def slider_to_weights(slider_position: float) -> Weights:
    """
    Map slider position (0=cheapest, 100=most convenient) to weight vector.

    At 0: cost=0.8, time=0.1, stops=0.05, departure=0.05
    At 100: cost=0.1, time=0.5, stops=0.3, departure=0.1
    """
    t = slider_position / 100.0  # normalize to 0-1

    return Weights(
        cost=0.8 - 0.7 * t,       # 0.8 → 0.1
        time=0.1 + 0.4 * t,       # 0.1 → 0.5
        stops=0.05 + 0.25 * t,    # 0.05 → 0.3
        departure=0.05 + 0.05 * t,  # 0.05 → 0.1
    )


def score_flights(flights: list[dict], weights: Weights | None = None) -> list[dict]:
    """
    Score and rank flight options.

    Each flight gets a score 0-100 (higher = better match for given weights).
    Returns flights sorted by score descending with 'score' field added.
    """
    if not flights:
        return []

    if weights is None:
        weights = Weights()

    # Extract min/max for normalization
    prices = [f["price"] for f in flights]
    durations = [f["duration_minutes"] for f in flights]
    stops_list = [f["stops"] for f in flights]

    min_price = min(prices)
    max_price = max(prices) if max(prices) > min_price else min_price + 1
    min_duration = min(durations)
    max_duration = max(durations) if max(durations) > min_duration else min_duration + 1
    max_stops = max(stops_list) if max(stops_list) > 0 else 1

    scored = []
    for flight in flights:
        # Cost score: lower price = higher score (inverted, 0-1)
        cost_score = 1.0 - (flight["price"] - min_price) / (max_price - min_price)

        # Time score: shorter duration = higher score (inverted, 0-1)
        time_score = 1.0 - (flight["duration_minutes"] - min_duration) / (max_duration - min_duration)

        # Stops score: fewer stops = higher score (inverted, 0-1)
        stops_score = 1.0 - (flight["stops"] / max_stops) if max_stops > 0 else 1.0

        # Departure score: gaussian centered on 9am (peak preference)
        dep_hour = _extract_hour(flight.get("departure_time", ""))
        departure_score = math.exp(-0.5 * ((dep_hour - 9) / 3) ** 2)

        # Composite score
        composite = (
            weights.cost * cost_score
            + weights.time * time_score
            + weights.stops * stops_score
            + weights.departure * departure_score
        )

        # Scale to 0-100
        final_score = round(composite * 100, 1)

        scored_flight = {**flight, "score": final_score}
        scored.append(scored_flight)

    scored.sort(key=lambda f: f["score"], reverse=True)
    return scored


def _extract_hour(time_str: str) -> float:
    """Extract hour from ISO datetime string or return 12 (noon) as default."""
    if not time_str:
        return 12.0
    try:
        # Handle ISO format: 2026-03-15T09:30:00+00:00
        if "T" in time_str:
            time_part = time_str.split("T")[1]
            parts = time_part.split(":")
            return float(parts[0]) + float(parts[1]) / 60 if len(parts) >= 2 else float(parts[0])
        return 12.0
    except (ValueError, IndexError):
        return 12.0
