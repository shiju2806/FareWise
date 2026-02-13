from fastapi import APIRouter

router = APIRouter()


@router.post("/{trip_leg_id}")
async def search_flights(trip_leg_id: str):
    return {"detail": "Not implemented yet"}


@router.get("/{trip_leg_id}/options")
async def get_flight_options(trip_leg_id: str, date: str | None = None, sort: str = "price"):
    return {"detail": "Not implemented yet"}


@router.post("/{trip_leg_id}/score")
async def rescore_flights(trip_leg_id: str):
    return {"detail": "Not implemented yet"}
