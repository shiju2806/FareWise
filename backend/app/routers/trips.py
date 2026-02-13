from fastapi import APIRouter

router = APIRouter()


@router.post("", status_code=201)
async def create_trip():
    return {"detail": "Not implemented yet"}


@router.post("/structured", status_code=201)
async def create_trip_structured():
    return {"detail": "Not implemented yet"}


@router.get("")
async def list_trips():
    return {"detail": "Not implemented yet"}


@router.get("/{trip_id}")
async def get_trip(trip_id: str):
    return {"detail": "Not implemented yet"}


@router.put("/{trip_id}/legs")
async def update_legs(trip_id: str):
    return {"detail": "Not implemented yet"}


@router.delete("/{trip_id}")
async def delete_trip(trip_id: str):
    return {"detail": "Not implemented yet"}
