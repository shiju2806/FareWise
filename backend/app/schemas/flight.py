import uuid
from datetime import datetime

from pydantic import BaseModel


class FlightOptionResponse(BaseModel):
    id: uuid.UUID
    airline_code: str
    airline_name: str
    flight_numbers: str
    origin_airport: str
    destination_airport: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    stops: int
    stop_airports: str | None
    price: float
    currency: str
    cabin_class: str | None
    seats_remaining: int | None
    is_alternate_airport: bool
    is_alternate_date: bool
    score: float | None = None

    model_config = {"from_attributes": True}
