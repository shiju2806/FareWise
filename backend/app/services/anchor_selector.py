"""Anchor selector — picks a 'reasonable default' business class flight as the budget envelope."""


def select_anchor_flight(
    flights: list[dict], cabin_class: str = "business", preferred_airline: str | None = None,
) -> dict | None:
    """Pick the reasonable default anchor flight for budget envelope calculations.

    Algorithm:
    0. If preferred_airline is set, prefer that airline's direct flights first
    1. Filter to requested cabin_class
    2. Filter to 6am–10pm departure window
    3. Tier 1: direct flights only
       Tier 2: if no directs, 1-stop at carrier hubs (valid_layover=True)
       Tier 3: if still empty, all 1-stop flights
    4. From qualifying pool, pick P40–P60 by price (median-ish, not cheapest)
    5. Add anchor_reason string explaining the selection
    """
    if not flights:
        return None

    # 1. Filter to requested cabin class
    cabin_flights = [f for f in flights if (f.get("cabin_class") or "").lower() == cabin_class.lower()]
    if not cabin_flights:
        return None

    # 2. Filter to 6am–10pm departure window
    daytime = [f for f in cabin_flights if _is_in_departure_window(f)]
    pool = daytime if daytime else cabin_flights  # fall back to all if no daytime flights

    # 3. Tiered selection
    anchor = None
    reason_tier = ""

    # Tier 0: preferred airline direct flights
    if preferred_airline:
        pref_directs = [f for f in pool if f.get("stops", 0) == 0 and f.get("airline_code") == preferred_airline]
        if pref_directs:
            anchor = _pick_best_value(pref_directs)
            reason_tier = f"preferred airline ({preferred_airline}) direct"

    # Tier 1: direct flights (any airline)
    if anchor is None:
        directs = [f for f in pool if f.get("stops", 0) == 0]
        if directs:
            anchor = _pick_best_value(directs)
            reason_tier = "direct flight"
        else:
            # Tier 2: 1-stop via carrier hubs
            hub_stops = [f for f in pool if f.get("stops", 0) == 1 and f.get("valid_layover") is True]
            if hub_stops:
                anchor = _pick_best_value(hub_stops)
                reason_tier = "1-stop via carrier hub"
            else:
                # Tier 3: any 1-stop
                one_stops = [f for f in pool if f.get("stops", 0) <= 1]
                if one_stops:
                    anchor = _pick_best_value(one_stops)
                    reason_tier = "1-stop connection"

    if anchor is None:
        return None

    # Build reason string
    parts = [f"Smart default: {reason_tier}"]
    if daytime and anchor in daytime:
        dep_hour = _extract_dep_hour(anchor)
        if dep_hour is not None:
            parts.append(f"{int(dep_hour)}:{'00' if dep_hour == int(dep_hour) else f'{int((dep_hour % 1) * 60):02d}'} departure")
    parts.append("best value")
    if anchor.get("airline_name"):
        parts.append(anchor["airline_name"])

    anchor_copy = {**anchor, "anchor_reason": " | ".join(parts)}
    return anchor_copy


def _is_in_departure_window(flight: dict, earliest: int = 6, latest: int = 22) -> bool:
    """Check if flight departs between earliest and latest hours."""
    hour = _extract_dep_hour(flight)
    if hour is None:
        return True  # If we can't parse, don't exclude
    return earliest <= hour < latest


def _extract_dep_hour(flight: dict) -> float | None:
    """Extract departure hour as float from ISO datetime string."""
    dep = flight.get("departure_time", "")
    if not dep or "T" not in dep:
        return None
    try:
        time_part = dep.split("T")[1]
        parts = time_part.split(":")
        return float(parts[0]) + float(parts[1]) / 60 if len(parts) >= 2 else float(parts[0])
    except (ValueError, IndexError):
        return None


def _pick_best_value(flights: list[dict], low: float = 0.40, high: float = 0.60) -> dict | None:
    """Pick the best-value flight from a pool.

    Strategy:
    - Small pools (≤5 flights): pick the cheapest — with few options,
      "median" skews expensive and a smart travel manager would pick
      the best value (e.g. AC $3,694 direct over BA $4,882 direct).
    - Large pools (>5 flights): pick P40-P60 median to avoid outlier
      cheapest fares that may have bad schedules or connections.
    """
    if not flights:
        return None
    if len(flights) == 1:
        return flights[0]

    sorted_flights = sorted(flights, key=lambda f: f.get("price", 0))
    n = len(sorted_flights)

    # Small pool: best value = cheapest
    if n <= 5:
        return sorted_flights[0]

    # Large pool: P40-P60 median
    low_idx = max(0, int(n * low))
    high_idx = min(n - 1, int(n * high))

    median_idx = n // 2
    best_idx = low_idx
    best_dist = abs(low_idx - median_idx)
    for i in range(low_idx, high_idx + 1):
        dist = abs(i - median_idx)
        if dist < best_dist:
            best_dist = dist
            best_idx = i

    return sorted_flights[best_idx]


def build_anchor_alternatives(
    flights: list[dict],
    anchor: dict,
    cabin_class: str = "business",
    preferred_airline: str | None = None,
    max_alternatives: int = 6,
) -> list[dict]:
    """Build top alternatives to the anchor flight.

    Groups by:
    1. Same airline (preferred or anchor airline, different times) — up to 2
    2. Same alliance (full-service partners) — up to 2
    3. Best value (cheapest full-service) — fill to max
    """
    from app.services.recommendation.airline_tiers import get_alliance, get_tier, same_alliance

    if not flights or not anchor:
        return []

    anchor_price = anchor.get("price", 0)
    anchor_code = anchor.get("airline_code", "")
    anchor_id = (anchor.get("flight_number", ""), anchor.get("departure_time", ""))

    # Filter to same cabin, exclude the anchor itself
    cabin_flights = [
        f for f in flights
        if (f.get("cabin_class") or "").lower() == cabin_class.lower()
        and (f.get("flight_number", ""), f.get("departure_time", "")) != anchor_id
    ]

    if not cabin_flights:
        return []

    def _make_alt(f: dict, group: str) -> dict:
        price = f.get("price", 0)
        savings = ((anchor_price - price) / anchor_price * 100) if anchor_price > 0 else 0
        code = f.get("airline_code", "")
        return {
            "airline_code": code,
            "airline_name": f.get("airline_name", ""),
            "alliance": get_alliance(code) or "unaffiliated",
            "tier": get_tier(code),
            "price": round(price),
            "stops": f.get("stops", 0),
            "departure_time": f.get("departure_time", ""),
            "duration_minutes": f.get("duration_minutes"),
            "savings_vs_anchor": round(savings, 1),
            "group": group,
        }

    seen_flights: set[tuple] = set()
    alternatives: list[dict] = []

    def _add(f: dict, group: str) -> bool:
        fid = (f.get("flight_number", ""), f.get("departure_time", ""))
        if fid in seen_flights:
            return False
        seen_flights.add(fid)
        alternatives.append(_make_alt(f, group))
        return True

    sorted_flights = sorted(cabin_flights, key=lambda f: f.get("price", 0))

    # Group 1: same airline (up to 2)
    same_airline_code = preferred_airline or anchor_code
    for f in sorted_flights:
        if len([a for a in alternatives if a["group"] == "same_airline"]) >= 2:
            break
        if f.get("airline_code") == same_airline_code:
            _add(f, "same_airline")

    # Group 2: same alliance, full-service only (up to 2)
    if same_airline_code:
        for f in sorted_flights:
            if len([a for a in alternatives if a["group"] == "same_alliance"]) >= 2:
                break
            code = f.get("airline_code", "")
            if (code != same_airline_code
                    and same_alliance(same_airline_code, code)
                    and get_tier(code) == "full_service"):
                _add(f, "same_alliance")

    # Group 3: direct competitors (full-service, different alliance)
    if same_airline_code:
        for f in sorted_flights:
            if len([a for a in alternatives if a["group"] == "direct_competitor"]) >= 2:
                break
            code = f.get("airline_code", "")
            if (code != same_airline_code
                    and not same_alliance(same_airline_code, code)
                    and get_tier(code) == "full_service"):
                _add(f, "direct_competitor")

    # Group 4: best value full-service (fill to max)
    for f in sorted_flights:
        if len(alternatives) >= max_alternatives:
            break
        if get_tier(f.get("airline_code", "")) == "full_service":
            _add(f, "best_value")

    return alternatives[:max_alternatives]
