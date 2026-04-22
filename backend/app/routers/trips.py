import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.trip import Trip, TripLeg
from app.models.user import User
from app.schemas.trip import (
    CreateTripNL,
    CreateTripStructured,
    PatchLegRequest,
    TripLegBase,
    TripLegResponse,
    TripResponse,
    UpdateLegsRequest,
)
from pydantic import BaseModel as PydanticBaseModel
from app.services.airport_service import airport_service
from app.services.nlp_parser import nlp_parser

router = APIRouter()


class ChatRequest(PydanticBaseModel):
    message: str
    conversation_history: list[dict] = []
    partial_trip: dict | None = None


class ChatResponse(PydanticBaseModel):
    reply: str
    conversation_history: list[dict]
    partial_trip: dict | None
    trip_ready: bool
    missing_fields: list[str]
    blocks: list[dict] = []


class CompanionPricingRequest(PydanticBaseModel):
    companions: int = 1
    companion_cabin_class: str = "economy"


class CabinBudgetRequest(PydanticBaseModel):
    total_travelers: int  # employee + companions (>= 2)
    anchor_prices: dict[str, float]  # {leg_id: anchor_price}



def _build_title(legs: list[dict]) -> str:
    """Generate trip title from legs, e.g. 'Toronto → New York → Chicago → Toronto'."""
    if not legs:
        return "Untitled Trip"
    cities = [legs[0].get("origin_city", "")]
    for leg in legs:
        dest = leg.get("destination_city", "")
        if dest and dest != cities[-1]:
            cities.append(dest)
    return " → ".join(cities)


@router.post("/chat", response_model=ChatResponse)
async def trip_chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
):
    """Multi-agent conversational trip planning."""
    from app.services.agents.trip_coordinator import TripCoordinator
    from app.services.agents.conversation_state import ConversationState

    state = ConversationState.from_partial_trip(req.partial_trip)

    coordinator = TripCoordinator()
    response = await coordinator.process(
        user_message=req.message,
        state=state,
        conversation_history=req.conversation_history,
    )

    final_state = response.state or state

    updated_history = list(req.conversation_history)
    updated_history.append({"role": "user", "content": req.message})
    updated_history.append({"role": "assistant", "content": response.content})

    return ChatResponse(
        reply=response.content,
        conversation_history=updated_history,
        partial_trip=final_state.to_partial_trip(),
        trip_ready=response.trip_ready,
        missing_fields=final_state.missing_fields,
        blocks=response.blocks,
    )


@router.post("", status_code=201, response_model=TripResponse)
async def create_trip_nl(
    req: CreateTripNL,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a trip from natural language input using Claude API."""
    parsed = await nlp_parser.parse(req.natural_language_input)

    trip = Trip(
        company_id=user.company_id,
        traveler_id=user.id,
        natural_language_input=req.natural_language_input,
        parsed_input=parsed,
        status="draft",
    )

    # Create legs from parsed data
    legs_data = parsed.get("legs", [])
    for leg_data in legs_data:
        # Resolve airports if needed
        origin_airport = leg_data.get("origin_airport", "")
        dest_airport = leg_data.get("destination_airport", "")

        if not origin_airport and leg_data.get("origin_city"):
            primary = await airport_service.get_primary_airport(db, leg_data["origin_city"])
            if primary:
                origin_airport = primary["iata"]

        if not dest_airport and leg_data.get("destination_city"):
            primary = await airport_service.get_primary_airport(db, leg_data["destination_city"])
            if primary:
                dest_airport = primary["iata"]

        # Parse preferred_date string to date object
        pref_date_raw = leg_data.get("preferred_date")
        if isinstance(pref_date_raw, str):
            pref_date = date_type.fromisoformat(pref_date_raw)
        elif isinstance(pref_date_raw, date_type):
            pref_date = pref_date_raw
        else:
            pref_date = date_type.today()

        leg = TripLeg(
            sequence=leg_data.get("sequence", len(trip.legs) + 1),
            origin_airport=origin_airport,
            origin_city=leg_data.get("origin_city", ""),
            destination_airport=dest_airport,
            destination_city=leg_data.get("destination_city", ""),
            preferred_date=pref_date,
            flexibility_days=leg_data.get("flexibility_days", 3),
            cabin_class=leg_data.get("cabin_class", "economy"),
            passengers=leg_data.get("passengers", 1),
        )
        trip.legs.append(leg)

    trip.title = _build_title(legs_data)
    db.add(trip)
    await db.commit()
    await db.refresh(trip, ["legs"])

    return TripResponse.model_validate(trip)


@router.post("/structured", status_code=201, response_model=TripResponse)
async def create_trip_structured(
    req: CreateTripStructured,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a trip from structured form input."""
    trip = Trip(company_id=user.company_id, traveler_id=user.id, status="draft")

    for i, leg_data in enumerate(req.legs):
        # Resolve city → airport
        origin_airport = ""
        dest_airport = ""

        origin_primary = await airport_service.get_primary_airport(db, leg_data.origin_city)
        if origin_primary:
            origin_airport = origin_primary["iata"]

        dest_primary = await airport_service.get_primary_airport(db, leg_data.destination_city)
        if dest_primary:
            dest_airport = dest_primary["iata"]

        leg = TripLeg(
            sequence=i + 1,
            origin_airport=origin_airport,
            origin_city=leg_data.origin_city,
            destination_airport=dest_airport,
            destination_city=leg_data.destination_city,
            preferred_date=leg_data.preferred_date,
            flexibility_days=leg_data.flexibility_days,
            cabin_class=leg_data.cabin_class,
            passengers=leg_data.passengers,
        )
        trip.legs.append(leg)

    legs_as_dicts = [
        {"origin_city": l.origin_city, "destination_city": l.destination_city}
        for l in trip.legs
    ]
    trip.title = _build_title(legs_as_dicts)
    db.add(trip)
    await db.commit()
    await db.refresh(trip, ["legs"])

    return TripResponse.model_validate(trip)


@router.get("", response_model=list[TripResponse])
async def list_trips(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List current user's trips."""
    query = (
        select(Trip)
        .where(Trip.traveler_id == user.id)
        .options(selectinload(Trip.legs))
        .order_by(Trip.updated_at.desc())
    )

    if status:
        query = query.where(Trip.status == status)

    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    trips = result.scalars().unique().all()

    return [TripResponse.model_validate(t) for t in trips]


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a single trip with legs."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
        .options(selectinload(Trip.legs))
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    return TripResponse.model_validate(trip)


@router.put("/{trip_id}/legs", response_model=TripResponse)
async def update_legs(
    trip_id: uuid.UUID,
    req: UpdateLegsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update trip legs — replace all legs with the provided set."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
        .options(selectinload(Trip.legs))
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.status not in ("draft", "searching"):
        raise HTTPException(status_code=400, detail="Can only edit draft or searching trips")

    # Remove existing legs
    for leg in trip.legs:
        await db.delete(leg)

    # Add new legs
    for i, leg_data in enumerate(req.legs):
        origin_city = leg_data.get("origin_city", "")
        dest_city = leg_data.get("destination_city", "")
        origin_airport = leg_data.get("origin_airport", "")
        dest_airport = leg_data.get("destination_airport", "")

        if not origin_airport and origin_city:
            primary = await airport_service.get_primary_airport(db, origin_city)
            if primary:
                origin_airport = primary["iata"]

        if not dest_airport and dest_city:
            primary = await airport_service.get_primary_airport(db, dest_city)
            if primary:
                dest_airport = primary["iata"]

        new_leg = TripLeg(
            trip_id=trip.id,
            sequence=i + 1,
            origin_airport=origin_airport,
            origin_city=origin_city,
            destination_airport=dest_airport,
            destination_city=dest_city,
            preferred_date=leg_data.get("preferred_date"),
            flexibility_days=leg_data.get("flexibility_days", 3),
            cabin_class=leg_data.get("cabin_class", "economy"),
            passengers=leg_data.get("passengers", 1),
        )
        db.add(new_leg)

    legs_dicts = [
        {"origin_city": l.get("origin_city", ""), "destination_city": l.get("destination_city", "")}
        for l in req.legs
    ]
    trip.title = _build_title(legs_dicts)
    await db.commit()
    await db.refresh(trip, ["legs"])

    return TripResponse.model_validate(trip)


@router.post("/{trip_id}/add-leg", response_model=TripResponse)
async def add_leg(
    trip_id: uuid.UUID,
    req: TripLegBase,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a single leg to an existing trip (e.g., return flight)."""
    result = await db.execute(
        select(Trip)
        .where(Trip.id == trip_id, Trip.traveler_id == user.id)
        .options(selectinload(Trip.legs))
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.status not in ("draft", "searching"):
        raise HTTPException(status_code=400, detail="Can only edit draft or searching trips")

    # Resolve airports
    origin_airport = ""
    dest_airport = ""
    if req.origin_city:
        primary = await airport_service.get_primary_airport(db, req.origin_city)
        if primary:
            origin_airport = primary["iata"]
    if req.destination_city:
        primary = await airport_service.get_primary_airport(db, req.destination_city)
        if primary:
            dest_airport = primary["iata"]

    next_seq = max((l.sequence for l in trip.legs), default=0) + 1
    new_leg = TripLeg(
        trip_id=trip.id,
        sequence=next_seq,
        origin_airport=origin_airport,
        origin_city=req.origin_city,
        destination_airport=dest_airport,
        destination_city=req.destination_city,
        preferred_date=req.preferred_date,
        flexibility_days=req.flexibility_days,
        cabin_class=req.cabin_class,
        passengers=req.passengers,
    )
    db.add(new_leg)

    # Update title
    legs_dicts = [
        {"origin_city": l.origin_city, "destination_city": l.destination_city}
        for l in trip.legs
    ] + [{"origin_city": req.origin_city, "destination_city": req.destination_city}]
    trip.title = _build_title(legs_dicts)

    await db.commit()
    await db.refresh(trip, ["legs"])
    return TripResponse.model_validate(trip)


@router.patch("/legs/{leg_id}", response_model=TripLegResponse)
async def patch_leg(
    leg_id: uuid.UUID,
    req: PatchLegRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update individual fields on a trip leg (cabin class, passengers, etc.)."""
    result = await db.execute(
        select(TripLeg)
        .join(Trip, TripLeg.trip_id == Trip.id)
        .where(TripLeg.id == leg_id, Trip.traveler_id == user.id)
    )
    leg = result.scalar_one_or_none()

    if not leg:
        raise HTTPException(status_code=404, detail="Leg not found")

    if req.cabin_class is not None:
        valid = {"economy", "premium_economy", "business", "first"}
        if req.cabin_class not in valid:
            raise HTTPException(status_code=400, detail=f"Invalid cabin class. Must be one of: {', '.join(sorted(valid))}")
        leg.cabin_class = req.cabin_class

    if req.passengers is not None:
        if req.passengers < 1:
            raise HTTPException(status_code=400, detail="Passengers must be at least 1")
        leg.passengers = req.passengers

    if req.flexibility_days is not None:
        if req.flexibility_days < 0:
            raise HTTPException(status_code=400, detail="Flexibility days must be non-negative")
        leg.flexibility_days = req.flexibility_days

    if "companion_preferred_date" in req.model_fields_set:
        leg.companion_preferred_date = req.companion_preferred_date

    await db.commit()
    await db.refresh(leg)

    return TripLegResponse.model_validate(leg)


@router.post("/{trip_id}/companion-pricing")
async def companion_pricing(
    trip_id: uuid.UUID,
    req: CompanionPricingRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get companion/family pricing for an existing trip's selected flights."""
    from app.services.companion_pricing_service import companion_pricing_service
    from dataclasses import asdict

    # Verify ownership
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.traveler_id == user.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if req.companions < 1:
        raise HTTPException(status_code=400, detail="Companions must be at least 1")

    valid_cabins = {"economy", "premium_economy"}
    if req.companion_cabin_class not in valid_cabins:
        raise HTTPException(
            status_code=400,
            detail=f"Companion cabin must be one of: {', '.join(sorted(valid_cabins))}",
        )

    # Update trip companion fields
    trip.companions = req.companions
    trip.companion_cabin_class = req.companion_cabin_class
    await db.commit()

    pricing = await companion_pricing_service.get_companion_pricing(
        str(trip_id), req.companions, req.companion_cabin_class, db,
    )
    return asdict(pricing)


@router.post("/{trip_id}/cabin-budget")
async def cabin_budget_recommendation(
    trip_id: uuid.UUID,
    req: CabinBudgetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recommend which cabin class fits all travelers within the anchor budget."""
    from app.services.companion_pricing_service import companion_pricing_service
    from dataclasses import asdict

    # Verify ownership
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.traveler_id == user.id)
    )
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if req.total_travelers < 2:
        raise HTTPException(status_code=400, detail="Total travelers must be at least 2")

    if not req.anchor_prices:
        raise HTTPException(status_code=400, detail="Anchor prices required")

    result = await companion_pricing_service.get_cabin_budget_recommendation(
        str(trip_id), req.total_travelers, req.anchor_prices, db,
    )
    return asdict(result)


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a draft trip."""
    result = await db.execute(
        select(Trip).where(Trip.id == trip_id, Trip.traveler_id == user.id)
    )
    trip = result.scalar_one_or_none()

    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip.status not in ("draft", "searching"):
        raise HTTPException(status_code=400, detail="Can only delete unsubmitted trips")

    # Clean up records that lack ON DELETE CASCADE
    from app.models.policy import Selection
    from app.models.events import HotelSelection

    leg_ids = [l.id for l in trip.legs] if trip.legs else []
    if not leg_ids:
        leg_result = await db.execute(select(TripLeg.id).where(TripLeg.trip_id == trip.id))
        leg_ids = [r[0] for r in leg_result.all()]

    if leg_ids:
        await db.execute(sa_delete(Selection).where(Selection.trip_leg_id.in_(leg_ids)))
        await db.execute(sa_delete(HotelSelection).where(HotelSelection.trip_leg_id.in_(leg_ids)))

    await db.delete(trip)
    await db.commit()
