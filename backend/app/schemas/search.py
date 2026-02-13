from pydantic import BaseModel


class SearchRequest(BaseModel):
    flexibility_days: int | None = None
    include_nearby_airports: bool = True
    max_stops: int = 2
    preferred_airlines: list[str] | None = None


class ScoreRequest(BaseModel):
    cost_weight: float = 0.5
    time_weight: float = 0.3
    stops_weight: float = 0.15
    departure_weight: float = 0.05
