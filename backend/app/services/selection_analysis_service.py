"""Selection analysis service — computes alternatives and savings for flight selections.

Shared by:
- Per-leg analyze-selection endpoint (search.py)
- Trip-level analyze-selections endpoint (trip_analysis.py)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_log import FlightOption, SearchLog

logger = logging.getLogger(__name__)


@dataclass
class LegAnalysis:
    """Result of analyzing a single leg's selection against alternatives."""

    selected: FlightOption
    alternatives: list[dict] = field(default_factory=list)
    savings_amount: float = 0.0
    savings_percent: float = 0.0
    overall_cheapest: FlightOption | None = None
    cheapest_same_date: FlightOption | None = None
    cheapest_same_airline: FlightOption | None = None


async def analyze_leg_selection(
    db: AsyncSession,
    leg_id: uuid.UUID,
    flight_option_id: uuid.UUID,
    excluded_airlines: set[str] | None = None,
    user_preferences: dict | None = None,
) -> LegAnalysis | None:
    """Analyze a flight selection for a single leg.

    Finds cheaper alternatives: same date/different airline, any date,
    same airline/different date, nearby airport, same tier. Computes savings vs cheapest.

    Returns LegAnalysis or None if no data available.
    """
    # Get the selected flight
    result = await db.execute(
        select(FlightOption).where(FlightOption.id == flight_option_id)
    )
    selected = result.scalar_one_or_none()
    if not selected:
        return None

    # Get all options from the most recent search
    search_result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg_id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = search_result.scalar_one_or_none()
    if not search_log:
        return None

    opts_result = await db.execute(
        select(FlightOption).where(FlightOption.search_log_id == search_log.id)
    )
    all_options = opts_result.scalars().all()

    # Filter to allowed airlines
    if excluded_airlines:
        allowed_options = [
            o for o in all_options if o.airline_name not in excluded_airlines
        ]
    else:
        allowed_options = list(all_options)

    if not allowed_options:
        return None

    selected_date = (
        selected.departure_time.date().isoformat() if selected.departure_time else ""
    )
    selected_price = float(selected.price)

    # Find cheapest overall
    overall_cheapest = min(allowed_options, key=lambda o: float(o.price))
    overall_cheapest_price = float(overall_cheapest.price)

    # Find cheapest on same date (different airline)
    same_date_options = [
        o
        for o in allowed_options
        if o.departure_time
        and o.departure_time.date().isoformat() == selected_date
        and o.airline_name != selected.airline_name
    ]
    cheapest_same_date = (
        min(same_date_options, key=lambda o: float(o.price))
        if same_date_options
        else None
    )

    # Find cheapest same airline, different date (only if cheaper)
    same_airline_options = [
        o
        for o in allowed_options
        if o.airline_name == selected.airline_name
        and o.departure_time
        and o.departure_time.date().isoformat() != selected_date
        and float(o.price) < selected_price
    ]
    cheapest_same_airline = (
        min(same_airline_options, key=lambda o: float(o.price))
        if same_airline_options
        else None
    )

    # Calculate savings
    savings_amount = round(selected_price - overall_cheapest_price, 2)
    savings_percent = (
        round((savings_amount / selected_price) * 100, 1) if selected_price > 0 else 0
    )

    # Build alternatives list
    alternatives: list[dict] = []

    if cheapest_same_date:
        sd_price = float(cheapest_same_date.price)
        alternatives.append(
            {
                "type": "same_date",
                "label": "Same date, different airline",
                "airline": cheapest_same_date.airline_name,
                "date": selected_date,
                "price": sd_price,
                "savings": round(selected_price - sd_price, 2),
                "stops": cheapest_same_date.stops,
                "duration_minutes": cheapest_same_date.duration_minutes,
                "flight_option_id": str(cheapest_same_date.id),
            }
        )

    if overall_cheapest.id != selected.id:
        cheapest_any_date_info = {
            "type": "any_date",
            "label": "Different date",
            "airline": overall_cheapest.airline_name,
            "date": (
                overall_cheapest.departure_time.date().isoformat()
                if overall_cheapest.departure_time
                else ""
            ),
            "price": overall_cheapest_price,
            "savings": round(selected_price - overall_cheapest_price, 2),
            "stops": overall_cheapest.stops,
            "duration_minutes": overall_cheapest.duration_minutes,
            "flight_option_id": str(overall_cheapest.id),
        }
        if not cheapest_same_date or overall_cheapest.id != cheapest_same_date.id:
            alternatives.append(cheapest_any_date_info)

    if cheapest_same_airline:
        sa_price = float(cheapest_same_airline.price)
        alternatives.append(
            {
                "type": "same_airline",
                "label": f"Same airline ({selected.airline_name}), different date",
                "airline": selected.airline_name,
                "date": (
                    cheapest_same_airline.departure_time.date().isoformat()
                    if cheapest_same_airline.departure_time
                    else ""
                ),
                "price": sa_price,
                "savings": round(selected_price - sa_price, 2),
                "stops": cheapest_same_airline.stops,
                "duration_minutes": cheapest_same_airline.duration_minutes,
                "flight_option_id": str(cheapest_same_airline.id),
            }
        )

    # Nearby airport alternative — cheapest flight from/to a nearby airport
    nearby_options = [
        o for o in allowed_options
        if o.is_alternate_airport and float(o.price) < selected_price
    ]
    if nearby_options:
        cheapest_nearby = min(nearby_options, key=lambda o: float(o.price))
        existing_ids = {a["flight_option_id"] for a in alternatives}
        if str(cheapest_nearby.id) not in existing_ids:
            np_price = float(cheapest_nearby.price)
            alternatives.append({
                "type": "nearby_airport",
                "label": f"Nearby airport ({cheapest_nearby.origin_airport} \u2192 {cheapest_nearby.destination_airport})",
                "airline": cheapest_nearby.airline_name,
                "date": (
                    cheapest_nearby.departure_time.date().isoformat()
                    if cheapest_nearby.departure_time else ""
                ),
                "price": np_price,
                "savings": round(selected_price - np_price, 2),
                "stops": cheapest_nearby.stops,
                "duration_minutes": cheapest_nearby.duration_minutes,
                "flight_option_id": str(cheapest_nearby.id),
            })

    # Same-tier alternative — cheapest flight from a similar-quality airline
    if user_preferences and user_preferences.get("prefer_same_tier"):
        from app.data.airline_tiers import get_tier, TIER_LABELS

        selected_tier = get_tier(selected.airline_code or "")
        if selected_tier != "unknown":
            same_tier_options = [
                o for o in allowed_options
                if get_tier(o.airline_code or "") == selected_tier
                and o.airline_name != selected.airline_name
                and float(o.price) < selected_price
            ]
            if same_tier_options:
                cheapest_same_tier = min(same_tier_options, key=lambda o: float(o.price))
                existing_ids = {a["flight_option_id"] for a in alternatives}
                if str(cheapest_same_tier.id) not in existing_ids:
                    st_price = float(cheapest_same_tier.price)
                    tier_label = TIER_LABELS.get(selected_tier, selected_tier)
                    alternatives.append({
                        "type": "same_tier",
                        "label": f"Similar quality ({tier_label}) airline",
                        "airline": cheapest_same_tier.airline_name,
                        "date": (
                            cheapest_same_tier.departure_time.date().isoformat()
                            if cheapest_same_tier.departure_time else ""
                        ),
                        "price": st_price,
                        "savings": round(selected_price - st_price, 2),
                        "stops": cheapest_same_tier.stops,
                        "duration_minutes": cheapest_same_tier.duration_minutes,
                        "flight_option_id": str(cheapest_same_tier.id),
                    })

    return LegAnalysis(
        selected=selected,
        alternatives=alternatives,
        savings_amount=savings_amount,
        savings_percent=savings_percent,
        overall_cheapest=overall_cheapest,
        cheapest_same_date=cheapest_same_date,
        cheapest_same_airline=cheapest_same_airline,
    )


def apply_smart_date_filter(
    alternatives: list[dict],
    leg_sequence: int,
    total_legs: int,
    outbound_selected_date: str | None,
    return_selected_date: str | None,
    original_trip_duration_days: int | None,
) -> list[dict]:
    """Filter alternatives based on cross-leg date constraints.

    Rules:
    - same_date alternatives are always valid (no duration issue)
    - For return leg: don't suggest dates earlier than
      outbound_date + (trip_duration - 1 day)
    - For outbound leg: don't suggest dates later than
      return_date - (trip_duration - 1 day)
    - If total_legs < 2 or trip_duration unknown, return unfiltered

    Example: Trip is Mon Mar 15 → Fri Mar 20 (5 days).
    Return alternatives on Mar 16 or Mar 17 are filtered out.
    Mar 19 or Mar 21 are allowed.
    """
    if not original_trip_duration_days or total_legs < 2:
        return alternatives

    filtered = []
    for alt in alternatives:
        # Same-date and nearby-airport alternatives are not date-dependent
        if alt["type"] in ("same_date", "nearby_airport", "same_tier"):
            filtered.append(alt)
            continue

        alt_date_str = alt.get("date", "")
        if not alt_date_str:
            filtered.append(alt)
            continue

        try:
            alt_date = date_type.fromisoformat(alt_date_str)
        except ValueError:
            filtered.append(alt)
            continue

        valid = True

        # Return leg: must be AFTER outbound and within ±2 days of original duration
        if leg_sequence > 1 and outbound_selected_date:
            try:
                out_date = date_type.fromisoformat(outbound_selected_date)
                # Hard constraint: return must be after outbound
                if alt_date <= out_date:
                    valid = False
                elif original_trip_duration_days and original_trip_duration_days >= 2:
                    actual_duration = (alt_date - out_date).days
                    min_duration = max(2, original_trip_duration_days - 2)
                    max_duration = original_trip_duration_days + 2
                    if actual_duration < min_duration or actual_duration > max_duration:
                        valid = False
            except ValueError:
                pass

        # Outbound leg: must be BEFORE return and within ±2 days of original duration
        if leg_sequence == 1 and return_selected_date:
            try:
                ret_date = date_type.fromisoformat(return_selected_date)
                # Hard constraint: outbound must be before return
                if alt_date >= ret_date:
                    valid = False
                elif original_trip_duration_days and original_trip_duration_days >= 2:
                    actual_duration = (ret_date - alt_date).days
                    min_duration = max(2, original_trip_duration_days - 2)
                    max_duration = original_trip_duration_days + 2
                    if actual_duration < min_duration or actual_duration > max_duration:
                        valid = False
            except ValueError:
                pass

        if valid:
            filtered.append(alt)

    return filtered
