from typing import Optional
import asyncio
import csv
import io
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth_legacy import get_auth_context_with_legacy
from app.database import get_db
from app.config import settings
from app.services.ebird_service import ebird_service
from app.services.taxonomy.taxonomy_service import taxonomy_service

log = structlog.get_logger()
router = APIRouter(prefix="/ebird", tags=["ebird"])


def _require_ebird():
    if not settings.ebird.enabled:
        raise HTTPException(status_code=400, detail="eBird integration is disabled")
    # API key not strictly required for export, but config enabled is.


@router.get("/export")
async def export_ebird_csv(auth=Depends(get_auth_context_with_legacy)):
    """
    Export all non-hidden detections in eBird Record Format CSV.
    """
    _require_ebird()
    
    async def iter_csv():
        f = io.StringIO()
        writer = csv.writer(f)
        
        # eBird Record Format Headers
        # https://support.ebird.org/en/support/solutions/articles/48000950570-ebird-import-formatting-csv-files
        header = [
            "Common Name", "Scientific Name", "Count", "Observation Date", "Time", 
            "Location Name", "Latitude", "Longitude", 
            "Protocol", "Duration (min)", "All Obs Reported", "Comments"
        ]
        writer.writerow(header)
        f.seek(0)
        yield f.read()
        f.truncate(0)
        f.seek(0)
        
        async with get_db() as db:
            async with db.execute("""
                SELECT 
                    display_name, scientific_name, detection_time, 
                    score, camera_name
                FROM detections
                WHERE is_hidden = 0 
                ORDER BY detection_time DESC
            """) as cursor:
                async for row in cursor:
                    display_name, scientific_name, detection_time, score, camera_name = row
                    
                    # Handle date parsing if string
                    dt = detection_time
                    if isinstance(dt, str):
                        try:
                            # Try ISO format
                            dt = datetime.fromisoformat(dt)
                        except ValueError:
                            # Fallback
                            try:
                                dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S.%f")
                            except ValueError:
                                continue # Skip invalid dates
                    
                    date_str = dt.strftime("%m/%d/%Y")
                    time_str = dt.strftime("%H:%M")
                    
                    lat = settings.location.latitude
                    lon = settings.location.longitude
                    
                    writer.writerow([
                        display_name,
                        scientific_name,
                        1,
                        date_str,
                        time_str,
                        f"Home ({camera_name})",
                        lat if lat else "",
                        lon if lon else "",
                        "Incidental",
                        0,
                        "N",
                        f"Confidence: {score:.2f} | YA-WAMF"
                    ])
                    
                    f.seek(0)
                    data = f.read()
                    if data:
                        yield data
                    f.truncate(0)
                    f.seek(0)

    filename = f"ebird_export_{datetime.now().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/nearby")
async def get_nearby_observations(
    species_name: Optional[str] = Query(None, description="Species common/scientific name"),
    scientific_name: Optional[str] = Query(None, description="Scientific name fallback"),
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
        
    if not species_code and scientific_name:
        species_code = await ebird_service.resolve_species_code(scientific_name)

    if species_name and not species_code:
        warning = "Species code not found for provided name(s); returning general nearby sightings"

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
    
    results = ebird_service.simplify_observations(items)

    async def enrich(item):
        name = item.get("common_name") or item.get("scientific_name")
        if name:
            tax = await taxonomy_service.get_names(name)
            if tax and tax.get("thumbnail_url"):
                item["thumbnail_url"] = tax.get("thumbnail_url")

    # Enrich concurrently (cached lookups are fast, uncached hit iNat)
    await asyncio.gather(*(enrich(item) for item in results))

    return {
        "status": "ok",
        "results": results
    }
