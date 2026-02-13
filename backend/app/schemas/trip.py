import uuid
from datetime import date, datetime

from pydantic import BaseModel


class TripLegBase(BaseModel):
    origin_city: str
    destination_city: str
    preferred_date: date
    flexibility_days: int = 3
    cabin_class: str = "economy"
    passengers: int = 1


class TripLegResponse(BaseModel):
    id: uuid.UUID
    sequence: int
    origin_airport: str
    origin_city: str
    destination_airport: str
    destination_city: str
    preferred_date: date
    flexibility_days: int
    cabin_class: str
    passengers: int

    model_config = {"from_attributes": True}


class CreateTripNL(BaseModel):
    natural_language_input: str


class CreateTripStructured(BaseModel):
    legs: list[TripLegBase]


class TripResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    natural_language_input: str | None
    parsed_input: dict | None
    total_estimated_cost: float | None
    currency: str
    legs: list[TripLegResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateLegsRequest(BaseModel):
    legs: list[dict]


class PatchLegRequest(BaseModel):
    cabin_class: str | None = None
    passengers: int | None = None
    flexibility_days: int | None = None
