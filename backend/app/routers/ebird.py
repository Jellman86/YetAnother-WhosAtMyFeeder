from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth_legacy import get_auth_context_with_legacy
from app.config import settings
from app.services.ebird_service import ebird_service

log = structlog.get_logger()
router = APIRouter(prefix="/ebird", tags=["ebird"])


def _require_ebird():
    if not settings.ebird.enabled:
        raise HTTPException(status_code=400, detail="eBird integration is disabled")
    if not settings.ebird.api_key:
        raise HTTPException(status_code=400, detail="eBird API key is not configured")


@router.get("/nearby")
async def get_nearby_observations(
    species_name: Optional[str] = Query(None, description="Species common/scientific name"),
    lat: Optional[float] = Query(None, description="Latitude override"),
    lng: Optional[float] = Query(None, description="Longitude override"),
    dist_km: Optional[int] = Query(None, ge=1, le=50, description="Search radius in km"),
    days_back: Optional[int] = Query(None, ge=1, le=30, description="Days back to search"),
    max_results: Optional[int] = Query(None, ge=1, le=200, description="Max results"),
    auth=Depends(get_auth_context_with_legacy)
):
    _require_ebird()
    if lat is None or lng is None:
        if settings.location.latitude is None or settings.location.longitude is None:
            raise HTTPException(status_code=400, detail="Location is not configured")
        lat = settings.location.latitude
        lng = settings.location.longitude

    dist = dist_km or settings.ebird.default_radius_km
    back = days_back or settings.ebird.default_days_back
    max_results = max_results or settings.ebird.max_results

    species_code = None
    warning = None
    if species_name:
        species_code = await ebird_service.resolve_species_code(species_name)
        if not species_code:
            warning = "Species code not found for provided name; returning general nearby sightings"

    items = await ebird_service.get_recent_observations(
        lat=lat,
        lng=lng,
        dist_km=dist,
        back_days=back,
        max_results=max_results,
        species_code=species_code
    )
    return {
        "status": "ok",
        "species_name": species_name,
        "species_code": species_code,
        "warning": warning,
        "results": ebird_service.simplify_observations(items)
    }


@router.get("/notable")
async def get_notable_observations(
    lat: Optional[float] = Query(None, description="Latitude override"),
    lng: Optional[float] = Query(None, description="Longitude override"),
    dist_km: Optional[int] = Query(None, ge=1, le=50, description="Search radius in km"),
    days_back: Optional[int] = Query(None, ge=1, le=30, description="Days back to search"),
    max_results: Optional[int] = Query(None, ge=1, le=200, description="Max results"),
    auth=Depends(get_auth_context_with_legacy)
):
    _require_ebird()
    if lat is None or lng is None:
        if settings.location.latitude is None or settings.location.longitude is None:
            raise HTTPException(status_code=400, detail="Location is not configured")
        lat = settings.location.latitude
        lng = settings.location.longitude

    dist = dist_km or settings.ebird.default_radius_km
    back = days_back or settings.ebird.default_days_back
    max_results = max_results or settings.ebird.max_results

    items = await ebird_service.get_recent_observations(
        lat=lat,
        lng=lng,
        dist_km=dist,
        back_days=back,
        max_results=max_results,
        notable=True
    )
    return {
        "status": "ok",
        "results": ebird_service.simplify_observations(items)
    }
