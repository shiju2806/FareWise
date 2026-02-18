"""Trip Analysis router — trip-level cost analysis, date optimization, and LLM insights."""

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.search_log import FlightOption, SearchLog
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.services.trip_intelligence_service import trip_intelligence

logger = logging.getLogger(__name__)

router = APIRouter()


class AnalyzeTripRequest(BaseModel):
    """Selected flight IDs for each leg, keyed by leg_id."""
    selected_flights: dict[str, str]  # leg_id → flight_option_id


class AnalyzeSelectionsRequest(BaseModel):
    """Selected flight IDs for each leg — for trip-level justification analysis."""
    selected_flights: dict[str, str]  # leg_id → flight_option_id


class OptimizeDatesRequest(BaseModel):
    """Optional: specify which two legs to optimize."""
    outbound_leg_id: str | None = None
    return_leg_id: str | None = None


async def _get_user_trip(
    trip_id: uuid.UUID,
    db: AsyncSession,
    user: User,
) -> Trip:
    """Fetch a trip with legs, ensuring it belongs to the current user."""
    result = await db.execute(
        select(Trip)
        .options(selectinload(Trip.legs))
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


async def _get_leg_flights(
    leg: TripLeg,
    db: AsyncSession,
) -> list[dict]:
    """Get all flight options from the most recent search for a leg."""
    search_result = await db.execute(
        select(SearchLog)
        .where(SearchLog.trip_leg_id == leg.id)
        .order_by(SearchLog.searched_at.desc())
        .limit(1)
    )
    search_log = search_result.scalar_one_or_none()
    if not search_log:
        return []

    opts_result = await db.execute(
        select(FlightOption).where(FlightOption.search_log_id == search_log.id)
    )
    all_options = opts_result.scalars().all()

    return [
        {
            "id": str(o.id),
            "airline_name": o.airline_name,
            "airline_code": o.airline_code,
            "flight_numbers": o.flight_numbers,
            "origin_airport": o.origin_airport,
            "destination_airport": o.destination_airport,
            "departure_time": o.departure_time.isoformat() if o.departure_time else "",
            "arrival_time": o.arrival_time.isoformat() if o.arrival_time else "",
            "duration_minutes": o.duration_minutes,
            "stops": o.stops,
            "price": float(o.price),
            "currency": o.currency or "CAD",
            "cabin_class": o.cabin_class,
        }
        for o in all_options
        if o.price and float(o.price) > 0
    ]


@router.post("/{trip_id}/analyze-trip")
async def analyze_trip(
    trip_id: uuid.UUID,
    req: AnalyzeTripRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Analyze entire trip cost with LLM-powered insights.

    Compares selected flights across all legs against:
    - Cheapest alternatives (different airlines, with stops, different dates)
    - Company policy budgets per cabin class
    - Routing alternatives

    Returns LLM-generated trip-level recommendation and justification prompt.
    """
    trip = await _get_user_trip(trip_id, db, user)

    # Sort legs by sequence
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    legs_info = []
    selected_flights = []
    all_options_per_leg = []

    for leg in legs_sorted:
        # Get all flight options for this leg
        options = await _get_leg_flights(leg, db)
        all_options_per_leg.append(options)

        legs_info.append({
            "origin_airport": leg.origin_airport,
            "destination_airport": leg.destination_airport,
            "origin_city": leg.origin_city,
            "destination_city": leg.destination_city,
            "preferred_date": leg.preferred_date.isoformat() if leg.preferred_date else "",
            "cabin_class": leg.cabin_class or "economy",
        })

        # Find the selected flight
        flight_id = req.selected_flights.get(str(leg.id))
        if flight_id:
            matching = [o for o in options if o["id"] == flight_id]
            selected_flights.append(matching[0] if matching else None)
        else:
            selected_flights.append(None)

    # Get LLM analysis
    analysis = await trip_intelligence.analyze_trip(
        legs=legs_info,
        selected_flights=selected_flights,
        all_options_per_leg=all_options_per_leg,
    )

    # Also include cost summary (non-LLM structured data)
    cost_summary = trip_intelligence.get_cost_summary(
        legs=legs_info,
        selected_flights=selected_flights,
        all_options_per_leg=all_options_per_leg,
    )

    return {
        "analysis": analysis,
        "cost_summary": cost_summary,
    }


@router.get("/{trip_id}/cost-summary")
async def get_cost_summary(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get structured cost summary for the trip (no LLM, fast).

    Returns per-leg breakdown with cheapest alternatives, policy budgets,
    and total comparisons. Used by the Trip Cost Bar component.
    """
    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    legs_info = []
    all_options_per_leg = []

    for leg in legs_sorted:
        options = await _get_leg_flights(leg, db)
        all_options_per_leg.append(options)

        legs_info.append({
            "origin_airport": leg.origin_airport,
            "destination_airport": leg.destination_airport,
            "cabin_class": leg.cabin_class or "economy",
        })

    cost_summary = trip_intelligence.get_cost_summary(
        legs=legs_info,
        selected_flights=None,
        all_options_per_leg=all_options_per_leg,
    )

    return cost_summary


@router.post("/{trip_id}/optimize-dates")
async def optimize_dates(
    trip_id: uuid.UUID,
    req: OptimizeDatesRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cross-reference outbound × return prices for optimal date combinations.

    Uses LLM to analyze date patterns and recommend the best round-trip
    date combinations considering price, convenience, and trip duration.

    Only works for round trips (2 legs where leg 2 is reverse of leg 1).
    """
    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    if len(legs_sorted) < 2:
        raise HTTPException(
            status_code=400,
            detail="Date optimization requires at least 2 legs (round trip)",
        )

    # Identify outbound and return legs
    if req and req.outbound_leg_id and req.return_leg_id:
        outbound_leg = next((l for l in legs_sorted if str(l.id) == req.outbound_leg_id), None)
        return_leg = next((l for l in legs_sorted if str(l.id) == req.return_leg_id), None)
    else:
        # Default: first leg = outbound, second = return
        outbound_leg = legs_sorted[0]
        return_leg = legs_sorted[1]

    if not outbound_leg or not return_leg:
        raise HTTPException(status_code=400, detail="Could not identify outbound/return legs")

    # Verify it's a round trip
    if outbound_leg.origin_city != return_leg.destination_city:
        raise HTTPException(
            status_code=400,
            detail="Legs do not form a round trip",
        )

    # Get flight options for both legs
    outbound_options = await _get_leg_flights(outbound_leg, db)
    return_options = await _get_leg_flights(return_leg, db)

    if not outbound_options or not return_options:
        raise HTTPException(
            status_code=400,
            detail="Both legs must have search results before optimizing dates",
        )

    outbound_info = {
        "origin_airport": outbound_leg.origin_airport,
        "destination_airport": outbound_leg.destination_airport,
        "cabin_class": outbound_leg.cabin_class or "economy",
    }
    return_info = {
        "origin_airport": return_leg.origin_airport,
        "destination_airport": return_leg.destination_airport,
        "cabin_class": return_leg.cabin_class or "economy",
    }

    result = await trip_intelligence.optimize_dates(
        outbound_leg=outbound_info,
        return_leg=return_info,
        outbound_options=outbound_options,
        return_options=return_options,
        preferred_outbound=outbound_leg.preferred_date.isoformat() if outbound_leg.preferred_date else "",
        preferred_return=return_leg.preferred_date.isoformat() if return_leg.preferred_date else "",
    )

    return result


@router.post("/{trip_id}/trip-window-alternatives")
async def trip_window_alternatives(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Compute trip-window alternatives that preserve trip duration.

    Shifts the entire trip window (outbound + return) to find cheaper
    date pairs while maintaining the same trip length.
    """
    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    if len(legs_sorted) < 2:
        raise HTTPException(status_code=400, detail="Trip window requires 2 legs (round trip)")

    outbound_leg = legs_sorted[0]
    return_leg = legs_sorted[1]

    outbound_options = await _get_leg_flights(outbound_leg, db)
    return_options = await _get_leg_flights(return_leg, db)

    if not outbound_options or not return_options:
        return {"original_trip_duration": 0, "original_total_price": 0, "proposals": []}

    result = trip_intelligence.compute_trip_window_alternatives(
        outbound_options=outbound_options,
        return_options=return_options,
        preferred_outbound=outbound_leg.preferred_date.isoformat() if outbound_leg.preferred_date else "",
        preferred_return=return_leg.preferred_date.isoformat() if return_leg.preferred_date else "",
    )

    return result


@router.post("/{trip_id}/analyze-selections")
async def analyze_selections(
    trip_id: uuid.UUID,
    req: AnalyzeSelectionsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trip-level justification analysis with smart date filtering.

    Analyzes ALL legs together: per-leg alternatives with cross-leg date
    constraints, trip-level totals, and an LLM-generated justification prompt.
    Replaces the per-leg analyze-selection call during trip confirmation.
    """
    from app.services.justification_service import justification_service
    from app.services.selection_analysis_service import (
        analyze_leg_selection,
        apply_smart_date_filter,
    )

    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    # Get user excluded airlines and full preferences
    excluded_airlines: set[str] = set()
    user_preferences: dict | None = None
    if user.travel_preferences and isinstance(user.travel_preferences, dict):
        user_preferences = user.travel_preferences
        excluded_airlines = set(user_preferences.get("excluded_airlines", []))

    # Compute original trip duration (days between first and last leg preferred dates)
    original_trip_duration = None
    if len(legs_sorted) >= 2:
        try:
            first_date = legs_sorted[0].preferred_date
            last_date = legs_sorted[-1].preferred_date
            if first_date and last_date:
                original_trip_duration = (last_date - first_date).days
        except (TypeError, AttributeError):
            pass

    # Analyze each leg
    per_leg_analyses = []
    selected_dates: dict[str, str] = {}  # leg_id -> selected departure date string

    for leg in legs_sorted:
        flight_id_str = req.selected_flights.get(str(leg.id))
        if not flight_id_str:
            per_leg_analyses.append(None)
            continue

        analysis = await analyze_leg_selection(
            db=db,
            leg_id=leg.id,
            flight_option_id=uuid.UUID(flight_id_str),
            excluded_airlines=excluded_airlines,
            user_preferences=user_preferences,
        )
        per_leg_analyses.append(analysis)

        if analysis and analysis.selected.departure_time:
            selected_dates[str(leg.id)] = (
                analysis.selected.departure_time.date().isoformat()
            )

    # Cross-leg date context for smart filtering
    outbound_date = selected_dates.get(str(legs_sorted[0].id)) if legs_sorted else None
    return_date = (
        selected_dates.get(str(legs_sorted[-1].id))
        if len(legs_sorted) >= 2
        else None
    )

    legs_result = []
    total_selected = 0.0
    total_cheapest = 0.0

    for i, leg in enumerate(legs_sorted):
        analysis = per_leg_analyses[i]
        if not analysis:
            legs_result.append({
                "leg_id": str(leg.id),
                "sequence": leg.sequence,
                "route": f"{leg.origin_airport} → {leg.destination_airport}",
                "justification_required": False,
                "selected": None,
                "savings": {"amount": 0, "percent": 0},
                "alternatives": [],
            })
            continue

        sel_price = float(analysis.selected.price)
        cheapest_price = float(analysis.overall_cheapest.price)
        total_selected += sel_price
        total_cheapest += cheapest_price

        # Apply smart date filter
        filtered_alternatives = apply_smart_date_filter(
            alternatives=analysis.alternatives,
            leg_sequence=leg.sequence,
            total_legs=len(legs_sorted),
            outbound_selected_date=outbound_date,
            return_selected_date=return_date,
            original_trip_duration_days=original_trip_duration,
        )

        sel_date = (
            analysis.selected.departure_time.date().isoformat()
            if analysis.selected.departure_time
            else ""
        )

        legs_result.append({
            "leg_id": str(leg.id),
            "sequence": leg.sequence,
            "route": f"{leg.origin_airport} → {leg.destination_airport}",
            "preferred_date": (
                leg.preferred_date.isoformat() if leg.preferred_date else None
            ),
            "justification_required": (
                analysis.savings_amount >= 100 or analysis.savings_percent >= 10
            ),
            "selected": {
                "airline": analysis.selected.airline_name,
                "date": sel_date,
                "price": sel_price,
                "stops": analysis.selected.stops,
                "duration_minutes": analysis.selected.duration_minutes,
                "flight_option_id": str(analysis.selected.id),
            },
            "savings": {
                "amount": analysis.savings_amount,
                "percent": analysis.savings_percent,
            },
            "alternatives": filtered_alternatives,
        })

    # Cross-leg consistency: ensure return-leg alternatives don't conflict
    # with outbound-leg alternatives for the same airline
    if len(legs_result) >= 2:
        outbound_alt_dates: dict[str, str] = {}  # airline_name → latest alt date
        for alt in legs_result[0].get("alternatives", []):
            if alt.get("type") == "same_airline" and alt.get("airline") and alt.get("date"):
                airline = alt["airline"]
                if airline not in outbound_alt_dates or alt["date"] > outbound_alt_dates[airline]:
                    outbound_alt_dates[airline] = alt["date"]
        for leg_data in legs_result[1:]:
            filtered = []
            for alt in leg_data.get("alternatives", []):
                if alt.get("type") == "same_airline" and alt.get("airline") and alt.get("date"):
                    outbound_alt_date = outbound_alt_dates.get(alt["airline"])
                    if outbound_alt_date and alt["date"] <= outbound_alt_date:
                        continue  # return before or on outbound alt date — skip
                filtered.append(alt)
            leg_data["alternatives"] = filtered

    # Trip-level totals
    trip_savings_amount = round(total_selected - total_cheapest, 2)
    trip_savings_percent = (
        round((trip_savings_amount / total_selected) * 100, 1)
        if total_selected > 0
        else 0
    )
    trip_justification_required = (
        trip_savings_amount >= 100 or trip_savings_percent >= 10
    )

    # Generate trip-level LLM justification prompt
    justification_prompt = None
    if trip_justification_required:
        try:
            justification_prompt = await justification_service.generate_trip_prompt(
                legs=legs_result,
                trip_total_selected=total_selected,
                trip_total_cheapest=total_cheapest,
                trip_savings_amount=trip_savings_amount,
                trip_savings_percent=trip_savings_percent,
            )
        except Exception as e:
            logger.warning(f"Trip justification prompt failed: {e}")

    # Compute trip-window alternatives for round trips (both legs shift together)
    trip_window_alternatives = None
    if len(legs_sorted) >= 2:
        try:
            outbound_leg = legs_sorted[0]
            return_leg = legs_sorted[-1]
            outbound_options = await _get_leg_flights(outbound_leg, db)
            return_options = await _get_leg_flights(return_leg, db)
            if outbound_options and return_options:
                # Collect airline codes from user's selected flights
                selected_codes = []
                for analysis in per_leg_analyses:
                    if analysis and analysis.selected and analysis.selected.airline_code:
                        selected_codes.append(analysis.selected.airline_code)
                trip_window_alternatives = trip_intelligence.compute_trip_window_alternatives(
                    outbound_options=outbound_options,
                    return_options=return_options,
                    preferred_outbound=outbound_leg.preferred_date.isoformat() if outbound_leg.preferred_date else "",
                    preferred_return=return_leg.preferred_date.isoformat() if return_leg.preferred_date else "",
                    selected_airline_codes=selected_codes if selected_codes else None,
                )
        except Exception as e:
            logger.warning(f"Trip window alternatives failed: {e}")

    # Compute cheaper-month suggestions for the user's selected airline
    cheaper_month_suggestions = []
    if legs_sorted and legs_sorted[0].preferred_date:
        try:
            from app.services.db1b_client import db1b_client
            import asyncio as _asyncio

            selected_codes = set()
            for analysis in per_leg_analyses:
                if analysis and analysis.selected and analysis.selected.airline_code:
                    selected_codes.add(analysis.selected.airline_code)

            if selected_codes:
                outbound_leg = legs_sorted[0]
                pref_date = outbound_leg.preferred_date
                cabin = outbound_leg.cabin_class or "economy"

                months_to_check = []
                for offset in [-1, 0, 1, 2]:
                    m = pref_date.month + offset
                    y = pref_date.year
                    if m < 1:
                        m += 12
                        y -= 1
                    elif m > 12:
                        m -= 12
                        y += 1
                    months_to_check.append((y, m))

                month_tasks = [
                    db1b_client.search_month_matrix(
                        outbound_leg.origin_airport,
                        outbound_leg.destination_airport,
                        y, m, cabin,
                    )
                    for y, m in months_to_check
                ]
                month_results = await _asyncio.gather(*month_tasks, return_exceptions=True)

                airline_month_prices: dict[tuple[int, int], list[float]] = {}
                for i, (y, m) in enumerate(months_to_check):
                    data = month_results[i]
                    if isinstance(data, Exception) or not data:
                        continue
                    for entry in data:
                        if entry["airline_code"] in selected_codes:
                            airline_month_prices.setdefault((y, m), []).append(entry["price"])

                current_key = (pref_date.year, pref_date.month)
                current_prices = airline_month_prices.get(current_key, [])
                current_avg = sum(current_prices) / len(current_prices) if current_prices else None

                if current_avg:
                    for (y, m), prices in sorted(airline_month_prices.items()):
                        if (y, m) == current_key:
                            continue
                        avg_price = sum(prices) / len(prices)
                        min_price = min(prices)
                        if avg_price < current_avg * 0.85:  # 15%+ cheaper
                            savings_pct = round((1 - avg_price / current_avg) * 100, 1)
                            month_name = date(y, m, 1).strftime("%B %Y")
                            cheaper_month_suggestions.append({
                                "month": month_name,
                                "year": y,
                                "month_num": m,
                                "avg_price": round(avg_price, 2),
                                "min_price": round(min_price, 2),
                                "current_month_avg": round(current_avg, 2),
                                "savings_percent": savings_pct,
                                "data_points": len(prices),
                            })
                    cheaper_month_suggestions.sort(key=lambda s: s["savings_percent"], reverse=True)
                    cheaper_month_suggestions = cheaper_month_suggestions[:3]
        except Exception as e:
            logger.warning(f"Cheaper month suggestions failed: {e}")

    return {
        "justification_required": trip_justification_required,
        "legs": legs_result,
        "trip_totals": {
            "selected": round(total_selected, 2),
            "cheapest": round(total_cheapest, 2),
            "savings_amount": trip_savings_amount,
            "savings_percent": trip_savings_percent,
        },
        "justification_prompt": justification_prompt,
        "trip_window_alternatives": trip_window_alternatives,
        "cheaper_month_suggestions": cheaper_month_suggestions,
    }


class CheaperMonthRequest(BaseModel):
    """Airline codes to check for cheaper months."""
    airline_codes: list[str]


@router.post("/{trip_id}/cheaper-months")
async def cheaper_months(
    trip_id: uuid.UUID,
    req: CheaperMonthRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find cheaper months for the user's selected airline on this route.

    Queries DB1B data for the selected airline across adjacent months
    and returns suggestions if a significantly cheaper month exists.
    """
    from app.services.db1b_client import db1b_client

    trip = await _get_user_trip(trip_id, db, user)
    legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

    if not legs_sorted:
        return {"suggestions": []}

    outbound_leg = legs_sorted[0]
    if not outbound_leg.preferred_date:
        return {"suggestions": []}

    pref_date = outbound_leg.preferred_date
    cabin = outbound_leg.cabin_class or "economy"
    origin = outbound_leg.origin_airport
    destination = outbound_leg.destination_airport
    airline_codes = set(req.airline_codes)

    # Query 3 months: prev, current, next
    months_to_check = []
    for offset in [-1, 0, 1, 2]:
        m = pref_date.month + offset
        y = pref_date.year
        if m < 1:
            m += 12
            y -= 1
        elif m > 12:
            m -= 12
            y += 1
        months_to_check.append((y, m))

    # Fetch matrix data for each month (per-airline per-date)
    import asyncio
    month_tasks = [
        db1b_client.search_month_matrix(origin, destination, y, m, cabin)
        for y, m in months_to_check
    ]
    month_results = await asyncio.gather(*month_tasks, return_exceptions=True)

    # Compute per-month average for selected airline(s)
    airline_month_prices: dict[tuple[int, int], list[float]] = {}
    for i, (y, m) in enumerate(months_to_check):
        data = month_results[i]
        if isinstance(data, Exception) or not data:
            continue
        for entry in data:
            if entry["airline_code"] in airline_codes:
                airline_month_prices.setdefault((y, m), []).append(entry["price"])

    if not airline_month_prices:
        return {"suggestions": []}

    # Current month average
    current_key = (pref_date.year, pref_date.month)
    current_prices = airline_month_prices.get(current_key, [])
    current_avg = sum(current_prices) / len(current_prices) if current_prices else None

    suggestions = []
    for (y, m), prices in sorted(airline_month_prices.items()):
        if (y, m) == current_key:
            continue
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)

        if current_avg and avg_price < current_avg * 0.8:  # 20%+ cheaper
            savings_pct = round((1 - avg_price / current_avg) * 100, 1)
            month_name = date(y, m, 1).strftime("%B %Y")
            suggestions.append({
                "month": month_name,
                "year": y,
                "month_num": m,
                "avg_price": round(avg_price, 2),
                "min_price": round(min_price, 2),
                "current_month_avg": round(current_avg, 2),
                "savings_percent": savings_pct,
                "data_points": len(prices),
            })

    suggestions.sort(key=lambda s: s["savings_percent"], reverse=True)

    return {"suggestions": suggestions[:3]}
