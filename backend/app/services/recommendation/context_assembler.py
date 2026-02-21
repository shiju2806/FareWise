"""Context assembler — gathers everything the recommendation agent needs."""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.search_log import FlightOption, SearchLog
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.models.policy import Selection
from app.services.recommendation.hotel_rate_service import HotelRateResult, hotel_rate_service

logger = logging.getLogger(__name__)


# ---------- Data structures ----------

@dataclass
class FlightData:
    """Normalized flight data from any source."""
    id: str
    airline_code: str
    airline_name: str
    flight_numbers: str
    origin_airport: str
    destination_airport: str
    departure_time: str  # ISO format
    arrival_time: str
    duration_minutes: int
    stops: int
    stop_airports: str | None
    price: float
    currency: str
    cabin_class: str
    seats_remaining: int | None = None
    is_alternate_airport: bool = False
    is_alternate_date: bool = False
    within_flexibility: bool = True
    source: str = "unknown"


@dataclass
class LegContext:
    """All context for a single trip leg."""
    leg_id: str
    sequence: int
    origin_airport: str
    origin_city: str
    destination_airport: str
    destination_city: str
    preferred_date: str  # ISO date
    flexibility_days: int
    cabin_class: str
    passengers: int
    needs_hotel: bool
    hotel_check_in: str | None = None
    hotel_check_out: str | None = None

    # Selection
    selected_flight: FlightData | None = None

    # All options from search (for alternatives)
    all_options: list[FlightData] = field(default_factory=list)

    # Search metadata
    cheapest_price: float | None = None
    most_expensive_price: float | None = None

    # Hotel rate at destination
    hotel_rate: HotelRateResult | None = None


@dataclass
class TravelerContext:
    """Traveler profile and preferences."""
    user_id: str
    name: str
    role: str
    department: str | None
    excluded_airlines: set[str] = field(default_factory=set)
    preferred_alliances: list[str] = field(default_factory=list)
    loyalty_programs: list[str] = field(default_factory=list)
    max_stops: int | None = None
    max_layover_minutes: int | None = None


@dataclass
class TripContext:
    """Complete assembled context for the recommendation engine."""
    trip_id: str
    title: str | None
    status: str
    currency: str
    traveler: TravelerContext
    legs: list[LegContext]
    trip_duration_days: int | None = None  # days between first and last leg

    # Trip-window options (for round trips, ±60 day range)
    outbound_options: list[FlightData] = field(default_factory=list)
    return_options: list[FlightData] = field(default_factory=list)

    # Events at destination
    events_context: list[str] = field(default_factory=list)

    @property
    def is_round_trip(self) -> bool:
        return len(self.legs) >= 2

    @property
    def selected_total(self) -> float:
        return sum(
            leg.selected_flight.price * leg.passengers
            for leg in self.legs
            if leg.selected_flight
        )

    @property
    def cheapest_total(self) -> float:
        return sum(
            (leg.cheapest_price or 0) * leg.passengers
            for leg in self.legs
            if leg.cheapest_price
        )


# ---------- Assembler ----------

class ContextAssembler:
    """Gathers all context needed for recommendation reasoning."""

    async def assemble(
        self,
        db: AsyncSession,
        trip_id: str,
        user: User,
        selected_flights: dict[str, str] | None = None,
    ) -> TripContext:
        """Build complete TripContext from DB state.

        Args:
            db: Database session
            trip_id: Trip UUID
            user: Authenticated user
            selected_flights: Optional override — leg_id → flight_option_id mapping.
                If not provided, reads from Selection records.
        """
        # 1. Load trip with legs
        trip = await self._load_trip(db, trip_id, user)
        legs_sorted = sorted(trip.legs, key=lambda l: l.sequence)

        # 2. Build traveler context
        traveler = self._build_traveler_context(user)

        # 3. Compute trip duration
        trip_duration = None
        if len(legs_sorted) >= 2:
            first_date = legs_sorted[0].preferred_date
            last_date = legs_sorted[-1].preferred_date
            if first_date and last_date:
                trip_duration = (last_date - first_date).days

        # 4. Build per-leg context (parallel: flight data + hotel rates)
        leg_contexts = []
        for leg in legs_sorted:
            leg_ctx = await self._build_leg_context(
                db, leg, selected_flights, traveler,
            )
            leg_contexts.append(leg_ctx)

        # 5. Load events context
        events = await self._load_events(db, legs_sorted)

        return TripContext(
            trip_id=str(trip.id),
            title=trip.title,
            status=trip.status,
            currency=trip.currency or "CAD",
            traveler=traveler,
            legs=leg_contexts,
            trip_duration_days=trip_duration,
            events_context=events,
        )

    async def _load_trip(
        self, db: AsyncSession, trip_id: str, user: User,
    ) -> Trip:
        """Load trip with legs, verify ownership."""
        from uuid import UUID
        result = await db.execute(
            select(Trip)
            .options(selectinload(Trip.legs))
            .where(Trip.id == UUID(trip_id), Trip.traveler_id == user.id)
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError(f"Trip {trip_id} not found for user {user.id}")
        return trip

    def _build_traveler_context(self, user: User) -> TravelerContext:
        """Extract traveler profile from user record."""
        prefs = user.travel_preferences or {}

        return TravelerContext(
            user_id=str(user.id),
            name=f"{user.first_name} {user.last_name}",
            role=user.role,
            department=user.department,
            excluded_airlines=set(prefs.get("excluded_airlines", [])),
            preferred_alliances=prefs.get("preferred_alliances", []),
            loyalty_programs=prefs.get("loyalty_programs", []),
            max_stops=prefs.get("max_stops"),
            max_layover_minutes=prefs.get("max_layover_minutes"),
        )

    async def _build_leg_context(
        self,
        db: AsyncSession,
        leg: TripLeg,
        selected_flights: dict[str, str] | None,
        traveler: TravelerContext,
    ) -> LegContext:
        """Build context for a single leg: search results, selection, hotel rate."""
        leg_ctx = LegContext(
            leg_id=str(leg.id),
            sequence=leg.sequence,
            origin_airport=leg.origin_airport,
            origin_city=leg.origin_city,
            destination_airport=leg.destination_airport,
            destination_city=leg.destination_city,
            preferred_date=leg.preferred_date.isoformat() if leg.preferred_date else "",
            flexibility_days=leg.flexibility_days,
            cabin_class=leg.cabin_class or "economy",
            passengers=leg.passengers,
            needs_hotel=leg.needs_hotel,
            hotel_check_in=leg.hotel_check_in.isoformat() if leg.hotel_check_in else None,
            hotel_check_out=leg.hotel_check_out.isoformat() if leg.hotel_check_out else None,
        )

        # Load latest search results
        search_result = await db.execute(
            select(SearchLog)
            .where(
                SearchLog.trip_leg_id == leg.id,
                SearchLog.is_synthetic == False,
            )
            .order_by(SearchLog.searched_at.desc())
            .limit(1)
        )
        search_log = search_result.scalar_one_or_none()

        if search_log:
            leg_ctx.cheapest_price = float(search_log.cheapest_price) if search_log.cheapest_price else None
            leg_ctx.most_expensive_price = float(search_log.most_expensive_price) if search_log.most_expensive_price else None

            # Load all flight options
            opts_result = await db.execute(
                select(FlightOption).where(FlightOption.search_log_id == search_log.id)
            )
            all_opts = opts_result.scalars().all()
            source = search_log.api_provider or "unknown"
            leg_ctx.all_options = [self._flight_to_data(opt, source) for opt in all_opts]

        # Load selected flight (from override or DB)
        selected_id = (selected_flights or {}).get(str(leg.id))
        if selected_id:
            leg_ctx.selected_flight = self._find_selected(leg_ctx.all_options, selected_id)
        else:
            # Check Selection record
            sel_result = await db.execute(
                select(Selection).where(Selection.trip_leg_id == leg.id)
            )
            sel = sel_result.scalar_one_or_none()
            if sel:
                leg_ctx.selected_flight = self._find_selected(
                    leg_ctx.all_options, str(sel.flight_option_id)
                )

        # Lookup corporate hotel rate at destination
        leg_ctx.hotel_rate = await hotel_rate_service.get_preferred_rate(
            db, leg.destination_airport, leg.preferred_date,
        )

        return leg_ctx

    async def _load_events(
        self, db: AsyncSession, legs: list[TripLeg],
    ) -> list[str]:
        """Load relevant events at destination cities."""
        events: list[str] = []
        for leg in legs:
            search_result = await db.execute(
                select(SearchLog)
                .where(SearchLog.trip_leg_id == leg.id)
                .order_by(SearchLog.searched_at.desc())
                .limit(1)
            )
            search = search_result.scalar_one_or_none()
            if search and search.events_during_travel and isinstance(search.events_during_travel, list):
                for ev in search.events_during_travel[:2]:
                    if isinstance(ev, dict) and ev.get("title"):
                        events.append(
                            f"{ev['title']} in {leg.destination_city} "
                            f"({ev.get('impact_level', 'unknown')} impact)"
                        )
        return events

    @staticmethod
    def _flight_to_data(opt: FlightOption, source: str = "unknown") -> FlightData:
        """Convert a DB FlightOption to a FlightData dataclass."""
        return FlightData(
            id=str(opt.id),
            airline_code=opt.airline_code or "",
            airline_name=opt.airline_name or "",
            flight_numbers=opt.flight_numbers or "",
            origin_airport=opt.origin_airport or "",
            destination_airport=opt.destination_airport or "",
            departure_time=opt.departure_time.isoformat() if opt.departure_time else "",
            arrival_time=opt.arrival_time.isoformat() if opt.arrival_time else "",
            duration_minutes=opt.duration_minutes or 0,
            stops=opt.stops or 0,
            stop_airports=opt.stop_airports,
            price=float(opt.price) if opt.price else 0.0,
            currency=opt.currency or "CAD",
            cabin_class=opt.cabin_class or "economy",
            seats_remaining=opt.seats_remaining,
            is_alternate_airport=bool(opt.is_alternate_airport),
            is_alternate_date=bool(opt.is_alternate_date),
            source=source,
        )

    async def load_trip_window_options(
        self,
        db: AsyncSession,
        context: TripContext,
    ) -> None:
        """Load ±60 day flight data for trip-window generation.

        Queries DB1B for broad date range. Falls back to per-leg saved
        search results (already loaded in context.legs[].all_options).
        Only applies to round trips (2+ legs).
        """
        if not context.is_round_trip:
            return

        from datetime import timedelta

        outbound = context.legs[0]
        return_leg = context.legs[-1]
        cabin = outbound.cabin_class

        out_date = _safe_parse_date(outbound.preferred_date)
        ret_date = _safe_parse_date(return_leg.preferred_date)

        if out_date and ret_date:
            try:
                from app.services.db1b_client import db1b_client

                if db1b_client.pool:
                    import asyncio
                    out_range, ret_range = await asyncio.gather(
                        db1b_client.search_flights_date_range(
                            outbound.origin_airport, outbound.destination_airport,
                            out_date - timedelta(days=60), out_date + timedelta(days=60), cabin,
                        ),
                        db1b_client.search_flights_date_range(
                            return_leg.origin_airport, return_leg.destination_airport,
                            ret_date - timedelta(days=60), ret_date + timedelta(days=60), cabin,
                        ),
                    )
                    for flights in out_range.values():
                        context.outbound_options.extend(
                            self._dict_to_flight_data(f) for f in flights
                        )
                    for flights in ret_range.values():
                        context.return_options.extend(
                            self._dict_to_flight_data(f) for f in flights
                        )
                    logger.info(
                        f"Trip-window: DB1B loaded out={len(context.outbound_options)}, "
                        f"ret={len(context.return_options)}"
                    )
            except Exception as e:
                logger.warning(f"DB1B trip-window query failed: {e}")

        # Fallback: use saved search results already loaded per-leg
        if not context.outbound_options:
            context.outbound_options = list(outbound.all_options)
            logger.info(f"Trip-window: Fell back to saved search for outbound: {len(context.outbound_options)}")
        if not context.return_options:
            context.return_options = list(return_leg.all_options)
            logger.info(f"Trip-window: Fell back to saved search for return: {len(context.return_options)}")

    @staticmethod
    def _dict_to_flight_data(d: dict) -> FlightData:
        """Convert a DB1B/search dict to FlightData."""
        return FlightData(
            id=d.get("id", ""),
            airline_code=d.get("airline_code", ""),
            airline_name=d.get("airline_name", ""),
            flight_numbers=d.get("flight_numbers", ""),
            origin_airport=d.get("origin_airport", ""),
            destination_airport=d.get("destination_airport", ""),
            departure_time=d.get("departure_time", ""),
            arrival_time=d.get("arrival_time", ""),
            duration_minutes=d.get("duration_minutes", 0),
            stops=d.get("stops", 0),
            stop_airports=d.get("stop_airports"),
            price=float(d.get("price", 0)),
            currency=d.get("currency", "USD"),
            cabin_class=d.get("cabin_class", "economy"),
            source="db1b",
        )

    @staticmethod
    def _find_selected(options: list[FlightData], flight_id: str) -> FlightData | None:
        """Find a flight by ID in the options list."""
        for opt in options:
            if opt.id == flight_id:
                return opt
        return None


def _safe_parse_date(date_str: str | None) -> date | None:
    """Safely parse an ISO date string, returning None on failure."""
    if not date_str or not date_str.strip():
        return None
    try:
        return date.fromisoformat(date_str.strip())
    except (ValueError, TypeError):
        logger.warning(f"Invalid date string: {date_str!r}")
        return None


context_assembler = ContextAssembler()
