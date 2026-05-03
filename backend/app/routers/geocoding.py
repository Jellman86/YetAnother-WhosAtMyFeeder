"""Reverse-geocoding endpoint used by the Settings UI to derive
state/country/place from a configured latitude/longitude pair.
"""

from fastapi import APIRouter, HTTPException, Query

from app.services.geocoding_service import geocoding_service

router = APIRouter(prefix="/location", tags=["location"])


@router.get("/reverse-geocode")
async def reverse_geocode(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
):
    try:
        result = await geocoding_service.reverse(lat, lon)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "state": result.state,
        "country": result.country,
        "place_guess": result.place_guess,
    }
