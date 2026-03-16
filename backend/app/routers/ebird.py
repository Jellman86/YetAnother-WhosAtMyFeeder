import asyncio
from typing import Optional
import csv
import io
import math
from datetime import date, datetime, time, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.auth import get_auth_context_with_legacy
from app.database import get_db
from app.config import settings
from app.services.ebird_service import ebird_service
from app.services.taxonomy.taxonomy_service import taxonomy_service
log = structlog.get_logger()
router = APIRouter(prefix="/ebird", tags=["ebird"])


def _require_ebird_api():
    if not settings.ebird.enabled or not settings.ebird.api_key:
        raise HTTPException(status_code=400, detail="eBird integration is disabled")


def _format_ebird_row(
    *,
    display_name: str,
    scientific_name: str | None,
    detection_time: datetime,
    score: float,
    camera_name: str | None,
    common_name: str | None,
    english_common_name: str | None,
    duration_minutes: int,
    video_classification_provider: str | None,
    video_classification_backend: str | None,
) -> list[str]:
    date_str = detection_time.strftime("%m/%d/%Y")
    time_str = detection_time.strftime("%H:%M")

    genus = ""
    species = ""
    if scientific_name:
        parts = scientific_name.strip().split(" ", 1)
        if len(parts) > 0:
            genus = parts[0]
        if len(parts) > 1:
            species = parts[1]

    export_common_name = _resolve_export_common_name(
        display_name=display_name,
        common_name=common_name,
        english_common_name=english_common_name,
    )
    location_name = f"Home ({camera_name})" if camera_name else "Home"
    lat = settings.location.latitude
    lon = settings.location.longitude
    state = str(getattr(settings.location, "state", "") or "").strip()
    country = str(getattr(settings.location, "country", "") or "").strip()
    submission_parts = ["Exported from YA-WAMF"]

    provider = str(video_classification_provider or "").strip()
    backend = str(video_classification_backend or "").strip()
    if provider:
        submission_parts.append(f"provider {provider}")
    if backend:
        submission_parts.append(f"backend {backend}")

    try:
        confidence = float(score)
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None and math.isfinite(confidence):
        submission_parts.append(f"confidence {confidence:.2f}")

    submission_comment = "; ".join(submission_parts)

    return [
        export_common_name,
        genus,
        species,
        "1",
        "",
        location_name,
        f"{lat:.6f}" if lat is not None else "",
        f"{lon:.6f}" if lon is not None else "",
        date_str,
        time_str,
        state,
        country,
        "Stationary",
        "1",
        str(max(0, int(duration_minutes))),
        "N",
        "",
        "",
        submission_comment,
    ]


def _is_english_safe_name(value: str | None) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    if candidate.lower() == "unknown bird":
        return False
    return candidate.isascii()


def _resolve_export_common_name(
    *,
    display_name: str | None,
    common_name: str | None,
    english_common_name: str | None,
) -> str:
    for candidate in (english_common_name, common_name, display_name):
        if _is_english_safe_name(candidate):
            return str(candidate).strip()
    return ""


def _is_exportable_ebird_detection(
    *,
    display_name: str | None,
    common_name: str | None,
    english_common_name: str | None,
) -> bool:
    normalized_display = str(display_name or "").strip().lower()
    normalized_common = str(common_name or "").strip().lower()

    if normalized_display == "unknown bird" or normalized_common == "unknown bird":
        return False
    if not _resolve_export_common_name(
        display_name=display_name,
        common_name=common_name,
        english_common_name=english_common_name,
    ):
        return False
    return True


def _parse_detection_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                return None
    return None


@router.get("/export")
async def export_ebird_csv(
    from_date: Optional[str] = Query(None, alias="from", description="Optional inclusive export start date in YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, alias="to", description="Optional inclusive export end date in YYYY-MM-DD"),
    auth=Depends(get_auth_context_with_legacy),
):
    """
    Export all non-hidden detections in eBird Record Format CSV.
    """
    params: list[object] = []
    date_clauses: list[str] = []

    try:
        requested_from = date.fromisoformat(from_date) if from_date else None
        requested_to = date.fromisoformat(to_date) if to_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date; expected YYYY-MM-DD") from exc

    if requested_from and requested_to and requested_from > requested_to:
        raise HTTPException(status_code=400, detail="Invalid date range; expected from <= to")

    if requested_from:
        date_clauses.append("d.detection_time >= ?")
        params.append(datetime.combine(requested_from, time.min))
    if requested_to:
        date_clauses.append("d.detection_time < ?")
        params.append(datetime.combine(requested_to + timedelta(days=1), time.min))

    date_clause = f" AND {' AND '.join(date_clauses)}" if date_clauses else ""

    async def iter_csv():
        f = io.StringIO()
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        parsed_rows: list[tuple[str, str | None, datetime, float, str | None, str | None, str | None, str | None, str | None, date]] = []

        # eBird spreadsheet import is strict about column order and often treats headers as data,
        # so this endpoint emits headerless rows in the standard 19-column record format.
        
        async with get_db() as db:
            async with db.execute(
                f"""
                SELECT 
                    d.display_name,
                    d.scientific_name,
                    d.detection_time, 
                    d.score,
                    d.camera_name,
                    d.common_name,
                    d.video_classification_provider,
                    d.video_classification_backend,
                    COALESCE(
                        (
                            SELECT tc_by_name.common_name
                            FROM taxonomy_cache tc_by_name
                            WHERE d.scientific_name IS NOT NULL
                              AND LOWER(tc_by_name.scientific_name) = LOWER(d.scientific_name)
                            ORDER BY tc_by_name.id ASC
                            LIMIT 1
                        ),
                        (
                            SELECT tc_by_taxa.common_name
                            FROM taxonomy_cache tc_by_taxa
                            WHERE d.taxa_id IS NOT NULL
                              AND tc_by_taxa.taxa_id = d.taxa_id
                            ORDER BY tc_by_taxa.id ASC
                            LIMIT 1
                        )
                    ) AS english_common_name
                FROM detections d
                WHERE d.is_hidden = 0
                {date_clause}
                ORDER BY d.detection_time DESC
                """,
                params,
            ) as cursor:
                async for row in cursor:
                    (
                        display_name,
                        scientific_name,
                        detection_time,
                        score,
                        camera_name,
                        common_name,
                        video_classification_provider,
                        video_classification_backend,
                        english_common_name,
                    ) = row
                    if not _is_exportable_ebird_detection(
                        display_name=display_name,
                        common_name=common_name,
                        english_common_name=english_common_name,
                    ):
                        continue
                    dt = _parse_detection_time(detection_time)
                    if dt is None:
                        continue
                    bucket = dt.date()
                    parsed_rows.append(
                        (
                            display_name,
                            scientific_name,
                            dt,
                            score,
                            camera_name,
                            common_name,
                            video_classification_provider,
                            video_classification_backend,
                            english_common_name,
                            bucket,
                        )
                    )

            durations_by_date: dict[date, int] = {}
            for row in parsed_rows:
                bucket = row[9]
                existing = durations_by_date.get(bucket)
                if existing is None:
                    durations_by_date[bucket] = 0

            min_max_by_date: dict[date, tuple[datetime, datetime]] = {}
            for row in parsed_rows:
                bucket = row[9]
                dt = row[2]
                current = min_max_by_date.get(bucket)
                if current is None:
                    min_max_by_date[bucket] = (dt, dt)
                else:
                    min_dt, max_dt = current
                    min_max_by_date[bucket] = (min(min_dt, dt), max(max_dt, dt))

            for bucket, (min_dt, max_dt) in min_max_by_date.items():
                durations_by_date[bucket] = max(0, int((max_dt - min_dt).total_seconds() // 60))

            for (
                display_name,
                scientific_name,
                dt,
                score,
                camera_name,
                common_name,
                video_classification_provider,
                video_classification_backend,
                english_common_name,
                bucket,
            ) in parsed_rows:
                writer.writerow(
                    _format_ebird_row(
                        display_name=display_name,
                        scientific_name=scientific_name,
                        detection_time=dt,
                        score=score,
                        camera_name=camera_name,
                        common_name=common_name,
                        english_common_name=english_common_name,
                        duration_minutes=durations_by_date.get(bucket, 0),
                        video_classification_provider=video_classification_provider,
                        video_classification_backend=video_classification_backend,
                    )
                )

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
    _require_ebird_api()
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

    try:
        items = await ebird_service.get_recent_observations(
            lat=lat,
            lng=lng,
            dist_km=dist,
            back_days=back,
            max_results=max_results,
            species_code=species_code
        )
    except Exception as e:
        log.error("eBird nearby search failed", error=str(e))
        return {
            "status": "error",
            "message": str(e),
            "results": []
        }

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
    _require_ebird_api()
    if lat is None or lng is None:
        if settings.location.latitude is None or settings.location.longitude is None:
            raise HTTPException(status_code=400, detail="Location is not configured")
        lat = settings.location.latitude
        lng = settings.location.longitude

    dist = dist_km or settings.ebird.default_radius_km
    back = days_back or settings.ebird.default_days_back
    max_results = max_results or settings.ebird.max_results

    try:
        items = await ebird_service.get_recent_observations(
            lat=lat,
            lng=lng,
            dist_km=dist,
            back_days=back,
            max_results=max_results,
            notable=True
        )
    except Exception as e:
        log.error("eBird notable search failed", error=str(e))
        return {
            "status": "error",
            "message": str(e),
            "results": []
        }
    
    results = ebird_service.simplify_observations(items)

    async def enrich(item):
        name = item.get("common_name") or item.get("scientific_name")
        if not name:
            return
        try:
            tax = await taxonomy_service.get_names(name)
        except Exception as exc:
            log.warning("eBird notable enrichment failed", species=name, error=str(exc))
            return
        if tax and tax.get("thumbnail_url"):
            item["thumbnail_url"] = tax.get("thumbnail_url")

    # Enrich concurrently (cached lookups are fast, uncached hit iNat)
    await asyncio.gather(*(enrich(item) for item in results))

    return {
        "status": "ok",
        "results": results
    }
