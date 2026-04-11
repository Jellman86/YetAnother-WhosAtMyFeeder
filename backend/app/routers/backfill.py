from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
import structlog
import asyncio
from uuid import uuid4

from app.services.backfill_service import BackfillService
from app.services.classifier_service import get_classifier
from app.services.i18n_service import i18n_service
from app.services.media_cache import media_cache
from app.services.weather_service import weather_service
from app.repositories.detection_repository import DetectionRepository
from app.database import get_db
from app.utils.language import get_user_language
from app.auth import require_owner, AuthContext
from app.services.broadcaster import broadcaster
from app.services.mqtt_service import mqtt_service
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.canonical_identity_repair_service import canonical_identity_repair_service
from app.services.error_diagnostics import error_diagnostics_history
from app.services.maintenance_coordinator import maintenance_coordinator
from app.utils.tasks import create_background_task

router = APIRouter()
log = structlog.get_logger()

# Use shared classifier instance
backfill_service = BackfillService(get_classifier())

class BackfillJobStatus(BaseModel):
    id: str
    kind: str
    status: str
    processed: int = 0
    total: int = 0
    new_detections: int = 0
    updated: int = 0
    skipped: int = 0
    skipped_reasons: dict[str, int] = Field(default_factory=dict)
    errors: int = 0
    error_reasons: dict[str, int] = Field(default_factory=dict)
    message: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

_JOB_STORE: dict[str, BackfillJobStatus] = {}
_LATEST_JOB_BY_KIND: dict[str, str] = {}
_JOB_TASKS: dict[str, asyncio.Task] = {}
_JOB_LOCK = asyncio.Lock()
BACKFILL_DEPRIORITIZED_AGE_SECONDS = 15.0
BACKFILL_STALLED_AGE_SECONDS = 90.0


def _maintenance_holder_id(kind: str, job_id: str) -> str:
    return f"{kind}:{job_id}"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _track_job(job: BackfillJobStatus):
    _JOB_STORE[job.id] = job
    _LATEST_JOB_BY_KIND[job.kind] = job.id

def _job_payload(job: BackfillJobStatus) -> dict:
    return job.model_dump()

async def _get_running_job(kind: str) -> Optional[BackfillJobStatus]:
    job_id = _LATEST_JOB_BY_KIND.get(kind)
    if not job_id:
        return None
    job = _JOB_STORE.get(job_id)
    if job and job.status == "running":
        return job
    return None


def _maintenance_busy_message() -> str:
    guard = _maintenance_guardrail_status()
    message = str(guard.get("maintenance_status_message") or "").strip()
    return message or "Maintenance work is already in progress."


def _maintenance_guardrail_status() -> dict:
    def _derive(status: dict) -> dict:
        pending_maintenance = int(status.get("pending_maintenance") or 0)
        active_maintenance = int(status.get("active_maintenance") or 0)
        oldest_pending_age = status.get("oldest_maintenance_pending_age_seconds")
        maintenance_state = str(status.get("maintenance_state") or "idle")
        return {
            **status,
            "reject_new_work": bool(
                status.get("maintenance_circuit_open")
                or maintenance_state == "stalled"
                or pending_maintenance >= 25
                or (isinstance(oldest_pending_age, (int, float)) and oldest_pending_age >= 45.0)
            ),
            "coalesce_analyze_unknowns": bool(pending_maintenance > 0 or active_maintenance > 0),
        }

    guard_getter = getattr(auto_video_classifier, "get_maintenance_guardrail_status", None)
    if callable(guard_getter):
        guard = guard_getter()
        if isinstance(guard, dict):
            if "reject_new_work" in guard and "coalesce_analyze_unknowns" in guard:
                return guard
            return _derive(guard)

    status_getter = getattr(auto_video_classifier, "get_status", None)
    if callable(status_getter):
        status = status_getter()
        if isinstance(status, dict):
            return _derive(status)
    return {}

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
    error_reasons: dict[str, int] = Field(default_factory=dict)
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
    error_reasons: dict[str, int] = Field(default_factory=dict)
    message: str


def _build_skipped_message(skipped: int, skipped_reasons: Optional[dict[str, int]] = None) -> str:
    """Build a human-readable skipped summary from reason counters."""
    if skipped <= 0:
        return ""

    reasons = {
        str(k): int(v)
        for k, v in (skipped_reasons or {}).items()
        if k and int(v) > 0
    }
    if not reasons:
        return f"{skipped} skipped"

    already_exists = reasons.pop("already_exists", 0)
    invalid_scores = reasons.pop("invalid_score", 0)
    other_skips = sum(reasons.values())

    parts: list[str] = []
    if already_exists > 0:
        parts.append(f"{already_exists} already existed")
    if invalid_scores > 0:
        parts.append(f"{invalid_scores} had invalid classifier scores")
    if other_skips > 0:
        parts.append(f"{other_skips} skipped by filters/validation")

    if not parts:
        return f"{skipped} skipped"
    return ", ".join(parts)


def _build_running_message(job: BackfillJobStatus, classifier_status: Optional[dict] = None) -> str:
    classifier_status = classifier_status or {}
    total = max(0, int(job.total or 0))
    processed = max(0, int(job.processed or 0))
    worker_pools = classifier_status.get("worker_pools") or {}
    live_worker = worker_pools.get("live") or {}
    background_worker = worker_pools.get("background") or {}
    worker_recovery_active = bool(live_worker.get("circuit_open")) or bool(background_worker.get("circuit_open"))

    if job.kind == "weather":
        if total <= 0:
            return "Scanning detections for missing weather"
        return "Filling weather history"

    background_status = classifier_status.get("background") or {}
    oldest_queued_age = background_status.get("oldest_queued_age_seconds")
    if (
        classifier_status.get("background_throttled")
        and processed <= 0
        and isinstance(oldest_queued_age, (int, float))
        and oldest_queued_age >= BACKFILL_STALLED_AGE_SECONDS
    ):
        return "Stalled while waiting for maintenance classifier capacity"
    if (
        classifier_status.get("background_throttled")
        and processed <= 0
        and isinstance(oldest_queued_age, (int, float))
        and oldest_queued_age >= BACKFILL_DEPRIORITIZED_AGE_SECONDS
    ):
        return "Deprioritized while live detections keep classifier capacity"
    if total <= 0:
        return "Scanning historical events"
    if worker_recovery_active and processed <= 0:
        return "Paused while classifier workers recover"
    if worker_recovery_active:
        return "Waiting for classifier workers to recover"
    if classifier_status.get("background_throttled") and processed <= 0:
        return "Paused while live detections use classifier capacity"
    if classifier_status.get("background_throttled"):
        return "Throttled by live detections"
    if processed <= 0:
        return f"Queued {total} historical event(s)"
    return "Processing historical events"


def _build_error_message(errors: int, error_reasons: Optional[dict[str, int]] = None) -> str:
    if errors <= 0:
        return ""

    reasons = {
        str(k): int(v)
        for k, v in (error_reasons or {}).items()
        if k and int(v) > 0
    }
    if not reasons:
        return f"{errors} error(s)"

    labels = [
        ("fetch_snapshot_failed", "missing snapshots"),
        ("background_image_worker_unavailable", "classifier worker unavailable"),
        ("background_image_worker_startup_timeout", "classifier startup timeout"),
        ("background_image_worker_timed_out", "classifier worker timeout"),
        ("background_image_lease_expired", "classifier lease expiry"),
        ("background_image_overloaded", "classifier overload"),
        ("background_image_circuit_open", "classifier recovery pause"),
        ("background_image_model_unavailable", "classifier model unavailable"),
        ("classification_failed", "empty classifier result"),
        ("timeout", "timed out"),
        ("exception", "processing exception"),
    ]
    parts: list[str] = []
    for reason_code, label in labels:
        count = reasons.pop(reason_code, 0)
        if count > 0:
            parts.append(f"{count} {label}")
    other_errors = sum(reasons.values())
    if other_errors > 0:
        parts.append(f"{other_errors} other error(s)")
    return ", ".join(parts) if parts else f"{errors} error(s)"


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
        mqtt_service.pause()
        await auto_video_classifier.reset_state()
        for job_id, task in list(_JOB_TASKS.items()):
            task.cancel()
            _JOB_TASKS.pop(job_id, None)
        _JOB_STORE.clear()
        _LATEST_JOB_BY_KIND.clear()

        # Clear detections
        async with get_db() as db:
            repo = DetectionRepository(db)
            deleted_count = await repo.delete_all()
            
        # Clear media cache
        cache_stats = await media_cache.clear_all()
        
        log.warning("Database reset triggered by user", 
                    deleted_detections=deleted_count, 
                    cache_stats=cache_stats)

        mqtt_service.resume()
        
        return {
            "status": "success",
            "message": f"Deleted {deleted_count} detections and cleared cache ({cache_stats['snapshots_deleted']} snapshots, {cache_stats['clips_deleted']} clips).",
            "deleted_count": deleted_count,
            "cache_stats": cache_stats
        }
    except Exception as e:
        mqtt_service.resume()
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
    holder_id = _maintenance_holder_id("backfill_detections_sync", str(uuid4()))
    acquired = await maintenance_coordinator.try_acquire(holder_id, kind="backfill")
    if not acquired:
        raise HTTPException(status_code=409, detail=_maintenance_busy_message())
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
            message += f", {_build_skipped_message(result.skipped, result.skipped_reasons)}"

        if result.errors > 0:
            message += f", {_build_error_message(result.errors, result.error_reasons)}"

        return BackfillResponse(
            status="completed",
            processed=result.processed,
            new_detections=result.new_detections,
            skipped=result.skipped,
            errors=result.errors,
            skipped_reasons=result.skipped_reasons,
            error_reasons=result.error_reasons,
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
    finally:
        await maintenance_coordinator.release(holder_id)


@router.post("/backfill/async", response_model=BackfillJobStatus)
async def backfill_detections_async(
    backfill_request: BackfillRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Run detection backfill in the background and return a job status."""
    lang = get_user_language(request)
    taxonomy_status = canonical_identity_repair_service.get_status()
    if taxonomy_status.get("is_running"):
        raise HTTPException(status_code=409, detail="Taxonomy repair is currently running. Please wait for it to finish.")

    guard = _maintenance_guardrail_status()
    if bool(guard.get("reject_new_work")):
        raise HTTPException(status_code=409, detail=_maintenance_busy_message())

    async with _JOB_LOCK:
        running = await _get_running_job("detections")
        if running:
            return running

        job = BackfillJobStatus(
            id=str(uuid4()),
            kind="detections",
            status="running",
            started_at=_now_iso()
        )
        holder_id = _maintenance_holder_id("backfill_detections", job.id)
        acquired = await maintenance_coordinator.try_acquire(holder_id, kind="backfill")
        if not acquired:
            raise HTTPException(status_code=409, detail=_maintenance_busy_message())
        _track_job(job)

    async def runner():
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

            job.message = "Querying Frigate API for historical events..."
            await broadcaster.broadcast({
                "type": "backfill_started",
                "data": _job_payload(job)
            })
            events = await backfill_service.fetch_frigate_events(
                start.timestamp(),
                end.timestamp(),
                backfill_request.cameras
            )
            job.total = len(events)
            job.processed = 0
            job.message = _build_running_message(job, backfill_service.classifier.get_admission_status())
            last_broadcast = 0
            broadcast_every = max(1, job.total // 20) if job.total else 1
            await broadcaster.broadcast({
                "type": "backfill_progress",
                "data": _job_payload(job)
            })

            for event in events:
                status, reason = await backfill_service.process_historical_event_with_timeout(event)
                job.processed += 1
                if status == "new":
                    job.new_detections += 1
                elif status == "skipped":
                    job.skipped += 1
                    if reason:
                        job.skipped_reasons[reason] = job.skipped_reasons.get(reason, 0) + 1
                else:
                    job.errors += 1
                    if reason:
                        job.error_reasons[reason] = job.error_reasons.get(reason, 0) + 1
                if job.processed - last_broadcast >= broadcast_every or job.processed == job.total:
                    last_broadcast = job.processed
                    job.message = _build_running_message(job, backfill_service.classifier.get_admission_status())
                    await broadcaster.broadcast({
                        "type": "backfill_progress",
                        "data": _job_payload(job)
                    })
            if job.new_detections > 0:
                message = f"Added {job.new_detections} new detection(s)"
            else:
                message = "No new detections found"
            if job.skipped:
                message += f", {_build_skipped_message(job.skipped, job.skipped_reasons)}"
            if job.errors:
                message += f", {_build_error_message(job.errors, job.error_reasons)}"
            job.message = message
            job.status = "completed"
            job.finished_at = _now_iso()
            await broadcaster.broadcast({
                "type": "backfill_complete",
                "data": _job_payload(job)
            })
        except asyncio.CancelledError:
            log.warning("Async backfill cancelled", job_id=job.id)
            if _JOB_STORE.get(job.id) is job:
                job.status = "failed"
                job.message = "Backfill cancelled"
                job.finished_at = _now_iso()
                await broadcaster.broadcast({
                    "type": "backfill_failed",
                    "data": _job_payload(job)
                })
            raise
        except Exception as e:
            log.error("Async backfill failed", error=str(e))
            job.status = "failed"
            job.message = str(e)
            job.finished_at = _now_iso()
            error_diagnostics_history.record(
                source="backfill",
                component="detections",
                stage="job",
                reason_code="job_failed",
                message="Async detection backfill failed",
                severity="error",
                context={"job_id": job.id, "error": str(e) or repr(e)},
            )
            await broadcaster.broadcast({
                "type": "backfill_failed",
                "data": _job_payload(job)
            })
        finally:
            await maintenance_coordinator.release(holder_id)

    try:
        task = create_background_task(runner(), name=f"backfill_job:{job.id}")
    except Exception:
        await maintenance_coordinator.release(holder_id)
        raise
    _JOB_TASKS[job.id] = task
    task.add_done_callback(lambda _: _JOB_TASKS.pop(job.id, None))
    return job


@router.post("/backfill/weather", response_model=WeatherBackfillResponse)
async def backfill_weather(
    backfill_request: WeatherBackfillRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Backfill missing weather fields for detections in a date range."""
    lang = get_user_language(request)
    holder_id = _maintenance_holder_id("backfill_weather_sync", str(uuid4()))
    acquired = await maintenance_coordinator.try_acquire(holder_id, kind="weather_backfill")
    if not acquired:
        raise HTTPException(status_code=409, detail=_maintenance_busy_message())
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
            error_reasons: dict[str, int] = {}

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
                    error_reasons["exception"] = error_reasons.get("exception", 0) + 1
                    log.warning("Weather backfill failed", error=str(e), event_id=det.get("frigate_event"))

            message = f"Updated {updated} detection(s)"
            if skipped:
                message += f", {skipped} skipped"
            if errors:
                message += f", {_build_error_message(errors, error_reasons)}"

            return WeatherBackfillResponse(
                status="completed",
                processed=len(detections),
                updated=updated,
                skipped=skipped,
                errors=errors,
                error_reasons=error_reasons,
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
    finally:
        await maintenance_coordinator.release(holder_id)


@router.post("/backfill/weather/async", response_model=BackfillJobStatus)
async def backfill_weather_async(
    backfill_request: WeatherBackfillRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Run weather backfill in the background and return a job status."""
    lang = get_user_language(request)
    async with _JOB_LOCK:
        running = await _get_running_job("weather")
        if running:
            return running

        job = BackfillJobStatus(
            id=str(uuid4()),
            kind="weather",
            status="running",
            started_at=_now_iso()
        )
        holder_id = _maintenance_holder_id("backfill_weather", job.id)
        acquired = await maintenance_coordinator.try_acquire(holder_id, kind="weather_backfill")
        if not acquired:
            raise HTTPException(status_code=409, detail=_maintenance_busy_message())
        _track_job(job)

    async def runner():
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

                job.total = len(detections)
                last_broadcast = 0
                broadcast_every = max(1, job.total // 20) if job.total else 1
                await broadcaster.broadcast({
                    "type": "backfill_started",
                    "data": _job_payload(job)
                })
                if not detections:
                    job.status = "completed"
                    job.message = "No detections found in range"
                    job.finished_at = _now_iso()
                    await broadcaster.broadcast({
                        "type": "backfill_complete",
                        "data": _job_payload(job)
                    })
                    return

                hourly = await weather_service.get_hourly_weather(start, end)
                if not hourly:
                    job.processed = job.total
                    job.skipped = job.total
                    job.status = "completed"
                    job.message = "Weather archive unavailable for range"
                    job.finished_at = _now_iso()
                    await broadcaster.broadcast({
                        "type": "backfill_complete",
                        "data": _job_payload(job)
                    })
                    return

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
                            job.skipped += 1
                        else:
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
                            job.updated += 1
                    except Exception as e:
                        job.errors += 1
                        job.error_reasons["exception"] = job.error_reasons.get("exception", 0) + 1
                        log.warning("Weather backfill failed", error=str(e), event_id=det.get("frigate_event"))
                    finally:
                        job.processed += 1
                        if job.processed - last_broadcast >= broadcast_every or job.processed == job.total:
                            last_broadcast = job.processed
                            await broadcaster.broadcast({
                                "type": "backfill_progress",
                                "data": _job_payload(job)
                            })

                message = f"Updated {job.updated} detection(s)"
                if job.skipped:
                    message += f", {job.skipped} skipped"
                if job.errors:
                    message += f", {_build_error_message(job.errors, job.error_reasons)}"
                job.message = message
                job.status = "completed"
                job.finished_at = _now_iso()
                await broadcaster.broadcast({
                    "type": "backfill_complete",
                    "data": _job_payload(job)
                })
        except asyncio.CancelledError:
            log.warning("Async weather backfill cancelled", job_id=job.id)
            if _JOB_STORE.get(job.id) is job:
                job.status = "failed"
                job.message = "Weather backfill cancelled"
                job.finished_at = _now_iso()
                await broadcaster.broadcast({
                    "type": "backfill_failed",
                    "data": _job_payload(job)
                })
            raise
        except Exception as e:
            log.error("Async weather backfill failed", error=str(e))
            job.status = "failed"
            job.message = str(e)
            job.finished_at = _now_iso()
            error_diagnostics_history.record(
                source="backfill",
                component="weather",
                stage="job",
                reason_code="job_failed",
                message="Async weather backfill failed",
                severity="error",
                context={"job_id": job.id, "error": str(e) or repr(e)},
            )
            await broadcaster.broadcast({
                "type": "backfill_failed",
                "data": _job_payload(job)
            })
        finally:
            await maintenance_coordinator.release(holder_id)

    try:
        task = create_background_task(runner(), name=f"backfill_weather_job:{job.id}")
    except Exception:
        await maintenance_coordinator.release(holder_id)
        raise
    _JOB_TASKS[job.id] = task
    task.add_done_callback(lambda _: _JOB_TASKS.pop(job.id, None))
    return job


@router.get("/backfill/status")
async def get_backfill_status(
    kind: Optional[str] = None,
    auth: AuthContext = Depends(require_owner)
):
    """Return the latest backfill job status (optionally filtered by kind)."""
    if kind:
        job_id = _LATEST_JOB_BY_KIND.get(kind)
        return _JOB_STORE.get(job_id) if job_id else None
    if not _LATEST_JOB_BY_KIND:
        return None
    latest = max(_JOB_STORE.values(), key=lambda j: j.started_at or "")
    return latest


@router.get("/backfill/status/{job_id}", response_model=BackfillJobStatus)
async def get_backfill_status_by_id(
    job_id: str,
    auth: AuthContext = Depends(require_owner)
):
    job = _JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backfill job not found")
    return job
