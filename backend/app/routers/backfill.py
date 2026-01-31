from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
import structlog

from app.services.backfill_service import BackfillService
from app.services.classifier_service import get_classifier
from app.services.i18n_service import i18n_service
from app.services.media_cache import media_cache
from app.services.weather_service import weather_service
from app.repositories.detection_repository import DetectionRepository
from app.database import get_db
from app.utils.language import get_user_language
from app.auth import require_owner, AuthContext

router = APIRouter()
log = structlog.get_logger()

# Use shared classifier instance
backfill_service = BackfillService(get_classifier())


class BackfillRequest(BaseModel):
    date_range: str = Field(
        default="week",
        description="Date range preset: 'day', 'week', 'month', or 'custom'"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date for custom range (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date for custom range (YYYY-MM-DD)"
    )
    cameras: Optional[List[str]] = Field(
        default=None,
        description="Optional list of cameras to backfill (defaults to configured cameras)"
    )


class BackfillResponse(BaseModel):
    status: str
    processed: int
    new_detections: int
    skipped: int
    errors: int
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    message: str


class WeatherBackfillRequest(BaseModel):
    date_range: str = Field(
        default="week",
        description="Date range preset: 'day', 'week', 'month', or 'custom'"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date for custom range (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date for custom range (YYYY-MM-DD)"
    )
    only_missing: bool = Field(
        default=True,
        description="Only fill detections missing weather fields"
    )


class WeatherBackfillResponse(BaseModel):
    status: str
    processed: int
    updated: int
    skipped: int
    errors: int
    message: str


def _resolve_date_range(date_range: str, start_date: Optional[str], end_date: Optional[str], lang: str) -> tuple[datetime, datetime]:
    now = datetime.now()
    if date_range == "day":
        return now - timedelta(days=1), now
    if date_range == "week":
        return now - timedelta(weeks=1), now
    if date_range == "month":
        return now - timedelta(days=30), now
    if date_range == "custom":
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail=i18n_service.translate("errors.backfill.invalid_time_range", lang)
            )
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            end = end.replace(hour=23, minute=59, second=59)
            return start, end
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=i18n_service.translate("errors.backfill.invalid_time_range", lang)
            )
    raise HTTPException(
        status_code=400,
        detail=i18n_service.translate("errors.backfill.invalid_time_range", lang)
    )


@router.delete("/backfill/reset")
async def reset_database(
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Reset the database: Delete ALL detections and clear media cache. Owner only.
    """
    try:
        # Clear detections
        async with get_db() as db:
            repo = DetectionRepository(db)
            deleted_count = await repo.delete_all()
            
        # Clear media cache
        cache_stats = await media_cache.clear_all()
        
        log.warning("Database reset triggered by user", 
                    deleted_detections=deleted_count, 
                    cache_stats=cache_stats)
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} detections and cleared cache ({cache_stats['snapshots_deleted']} snapshots, {cache_stats['clips_deleted']} clips).",
            "deleted_count": deleted_count,
            "cache_stats": cache_stats
        }
    except Exception as e:
        log.error("Database reset failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_detections(
    backfill_request: BackfillRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Fetch historical bird detections from Frigate and process them. Owner only.

    This endpoint queries Frigate's event API for past bird detections,
    classifies them using the ML model, and saves new detections to the database.
    Existing detections (by frigate_event ID) are skipped to avoid duplicates.

    Date range options:
    - 'day': Last 24 hours
    - 'week': Last 7 days
    - 'month': Last 30 days
    - 'custom': Use start_date and end_date parameters
    """
    lang = get_user_language(request)
    try:
        start, end = _resolve_date_range(
            backfill_request.date_range,
            backfill_request.start_date,
            backfill_request.end_date,
            lang
        )

        # Validate date range
        if start > end:
            raise HTTPException(
                status_code=400,
                detail=i18n_service.translate("errors.backfill.invalid_time_range", lang)
            )

        # Run the backfill
        result = await backfill_service.run_backfill(start, end, backfill_request.cameras)

        # Build message
        if result.new_detections > 0:
            message = f"Added {result.new_detections} new detection(s)"
        else:
            message = "No new detections found"

        if result.skipped > 0:
            message += f", {result.skipped} already existed"

        if result.errors > 0:
            message += f", {result.errors} error(s)"

        return BackfillResponse(
            status="completed",
            processed=result.processed,
            new_detections=result.new_detections,
            skipped=result.skipped,
            errors=result.errors,
            skipped_reasons=result.skipped_reasons,
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error("Backfill failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=i18n_service.translate("errors.backfill.processing_error", lang, error=str(e))
        )


@router.post("/backfill/weather", response_model=WeatherBackfillResponse)
async def backfill_weather(
    backfill_request: WeatherBackfillRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Backfill missing weather fields for detections in a date range."""
    lang = get_user_language(request)
    try:
        start, end = _resolve_date_range(
            backfill_request.date_range,
            backfill_request.start_date,
            backfill_request.end_date,
            lang
        )

        if start > end:
            raise HTTPException(
                status_code=400,
                detail=i18n_service.translate("errors.backfill.invalid_time_range", lang)
            )

        async with get_db() as db:
            repo = DetectionRepository(db)
            detections = await repo.list_for_weather_backfill(
                start.strftime("%Y-%m-%d %H:%M:%S"),
                end.strftime("%Y-%m-%d %H:%M:%S"),
                backfill_request.only_missing
            )

            if not detections:
                return WeatherBackfillResponse(
                    status="completed",
                    processed=0,
                    updated=0,
                    skipped=0,
                    errors=0,
                    message="No detections found in range"
                )

            hourly = await weather_service.get_hourly_weather(start, end)
            if not hourly:
                return WeatherBackfillResponse(
                    status="completed",
                    processed=len(detections),
                    updated=0,
                    skipped=len(detections),
                    errors=0,
                    message="Weather archive unavailable for range"
                )

            updated = 0
            skipped = 0
            errors = 0

            for det in detections:
                try:
                    time_str = det["detection_time"]
                    if time_str.endswith("Z"):
                        time_str = time_str.replace("Z", "+00:00")
                    det_time = datetime.fromisoformat(time_str)
                    if det_time.tzinfo is None:
                        det_time = det_time.replace(tzinfo=timezone.utc)
                    det_time = det_time.astimezone(timezone.utc)

                    base_hour = det_time.replace(minute=0, second=0, microsecond=0)
                    if det_time.minute >= 30:
                        base_hour = base_hour + timedelta(hours=1)
                    hour_key = base_hour.strftime("%Y-%m-%dT%H:00")
                    weather = hourly.get(hour_key)
                    if not weather:
                        skipped += 1
                        continue

                    await repo.update_weather_fields(
                        det["frigate_event"],
                        weather.get("temperature"),
                        weather.get("condition_text"),
                        weather.get("cloud_cover"),
                        weather.get("wind_speed"),
                        weather.get("wind_direction"),
                        weather.get("precipitation"),
                        weather.get("rain"),
                        weather.get("snowfall")
                    )
                    updated += 1
                except Exception as e:
                    errors += 1
                    log.warning("Weather backfill failed", error=str(e), event_id=det.get("frigate_event"))

            message = f"Updated {updated} detection(s)"
            if skipped:
                message += f", {skipped} skipped"
            if errors:
                message += f", {errors} errors"

            return WeatherBackfillResponse(
                status="completed",
                processed=len(detections),
                updated=updated,
                skipped=skipped,
                errors=errors,
                message=message
            )
    except HTTPException:
        raise
    except Exception as e:
        log.error("Weather backfill failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=i18n_service.translate("errors.backfill.processing_error", lang, error=str(e))
        )
