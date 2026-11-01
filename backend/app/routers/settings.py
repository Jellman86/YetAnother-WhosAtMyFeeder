import platform
import re
import asyncio
import httpx
from typing import Any, List, Optional, Literal, TypeVar
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, field_validator
import structlog

from app.services.settings_update import apply_update, prepare_update, run_settings_writer
from app.services.cache_stats_measurements import CacheStatsMeasurements
from app.config import CONFIG_PATH, Settings as AppSettings, settings
from app.config_loader import migrate_imported_media_controls
from app.auth import (
    AuthContext,
    require_owner,
    validate_bcrypt_password_length,
)
from app.database import get_db
from app.models.public_settings import PublicSettings, build_public_settings
from app.repositories.detection_repository import DetectionRepository

from app.services.canonical_identity_repair_service import canonical_identity_repair_service
from app.services.telemetry_service import collect_runtime_telemetry_payload, telemetry_service
from app.services.notification_service import notification_service
from app.services.garden_domestic_birds import DomesticBirdKey, normalize_domestic_birds
from app.services.notification_links import instance_base, notification_link
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.birdweather_service import birdweather_service
from app.services.inaturalist_service import inaturalist_service
from app.services.frigate_client import frigate_client
from app.services.timezone_repair_service import timezone_repair_service
from app.services.media_cache import media_cache
from app.services.maintenance_coordinator import maintenance_coordinator
from app.services.media_integrity_scan import MEDIA_INTEGRITY_SCAN_KIND, evaluate_media_presence
from app.services.ai_service import AIService
from app.services.frigate_missing_policy import apply_missing_policy, clear_missing_state_if_present
from app.services.smtp_service import smtp_service
from app.config_models import (
    BlockedSpeciesEntry,
    DEFAULT_LLM_MODEL,
    ExplorerView,
    FrigateMissingBehavior,
    MediaIntegrityScanMedia,
)
from app.utils.enrichment import get_effective_enrichment_settings, is_ebird_active
from app.utils.frigate_recording import get_camera_retention_days
from app.utils.api_datetime import utc_naive_now  # noqa: F401 - compatibility for tests and maintenance helpers
from app.utils.integration_url import validated_http_base_url

from fastapi import BackgroundTasks

router = APIRouter()


def _validated_birdnet_base_url(value: str | None) -> str:
    """Return a safe HTTP(S) base URL for the owner-configured BirdNET-Go host.

    Private addresses and Docker service names are intentionally supported because
    this is a server-to-server integration. Credentials, query strings, fragments,
    and non-HTTP schemes are not valid for a base URL.
    """
    return validated_http_base_url(value, integration_name="BirdNET-Go")


log = structlog.get_logger()
PURGE_CHECK_CONCURRENCY = 8
BATCH_ANALYSIS_CHECK_CONCURRENCY = 8
BATCH_ANALYSIS_MAX_QUEUE_PER_RUN = 50
BATCH_ANALYSIS_MAX_SCAN_PER_RUN = 200
BATCH_ANALYSIS_RETRY_AFTER_SECONDS = 120
AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE = "Password is required when enabling authentication"
CONFIG_BACKUP_FORMAT = "yawamf.config.backup"
CONFIG_BACKUP_FORMAT_VERSION = 1


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


def _maintenance_busy_message(status: dict | None = None) -> str:
    guard = status or _maintenance_guardrail_status()
    message = str(guard.get("maintenance_status_message") or "").strip()
    if message:
        return message
    return "Maintenance work is already in progress."


def _maintenance_holder_id(kind: str) -> str:
    return f"{kind}:{uuid4()}"


class TaxonomySyncStatusResponse(BaseModel):
    is_running: bool
    total: int
    processed: int
    current_item: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    progress_state: Optional[str] = None
    last_progress_at: Optional[str] = None
    seconds_since_progress: Optional[float] = None


class TaxonomySyncStartResponse(BaseModel):
    status: str


class ActionStatusResponse(BaseModel):
    status: Literal["ok", "error"]
    message: str


class SettingsUpdateResponse(BaseModel):
    status: Literal["updated"]


class SettingsImportResponse(BaseModel):
    status: Literal["imported"]
    changed_fields: list[str]


class VideoCircuitResetResponse(BaseModel):
    status: Literal["ok"]
    message: str
    live_circuit: dict[str, Any]
    maintenance_circuit: dict[str, Any]


@router.get("/maintenance/taxonomy/status", response_model=TaxonomySyncStatusResponse)
async def get_taxonomy_status(auth: AuthContext = Depends(require_owner)):
    """Get status of the taxonomy synchronization process. Owner only."""
    return canonical_identity_repair_service.get_status()


@router.post("/maintenance/taxonomy/sync", response_model=TaxonomySyncStartResponse)
async def start_taxonomy_sync(background_tasks: BackgroundTasks, auth: AuthContext = Depends(require_owner)):
    """Start the background process to normalize all detection names. Owner only."""
    guard = _maintenance_guardrail_status()
    if bool(guard.get("reject_new_work")):
        raise HTTPException(status_code=409, detail=_maintenance_busy_message(guard))

    holder_id = "taxonomy_sync"
    acquired = await maintenance_coordinator.try_acquire(holder_id, kind="taxonomy_sync")
    if not acquired:
        # Coordinator rejected — either already running or maintenance lane is busy.
        raise HTTPException(status_code=409, detail=_maintenance_busy_message(guard))

    async def _run_with_slot() -> None:
        try:
            await canonical_identity_repair_service.run()
        finally:
            await maintenance_coordinator.release(holder_id)

    try:
        background_tasks.add_task(_run_with_slot)
    except Exception:
        await maintenance_coordinator.release(holder_id)
        raise
    return {"status": "started"}


@router.post("/settings/birdnet/test", response_model=ActionStatusResponse)
async def test_birdnet(_auth: AuthContext = Depends(require_owner)) -> ActionStatusResponse | JSONResponse:
    """Test local BirdNET ingestion by synchronously persisting a mock detection."""
    from app.services.audio.audio_service import audio_service

    mock_data = {
        "timestamp": datetime.now(timezone.utc).timestamp(),
        "species": "Cyanistes caeruleus",
        "ScientificName": "Cyanistes caeruleus",
        "common_name": "Eurasian Blue Tit (BirdNET Test)",
        "confidence": 0.95,
        "sensor_id": "test_mic",
    }

    # Await the same ingest path used by MQTT. A queued background task would only
    # prove that the request was accepted, not that buffer and database writes work.
    if not await audio_service.add_detection(mock_data, diagnostic=True):
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "The mock detection could not be stored. Check backend and database diagnostics.",
            },
        )

    return ActionStatusResponse(
        status="ok",
        message="Detection ingest and database write passed; the synthetic test record was removed.",
    )


@router.get("/settings/birdnet/reachability", response_model=ActionStatusResponse)
async def test_birdnet_reachability(
    url: Optional[str] = Query(default=None, max_length=2048),
    _auth: AuthContext = Depends(require_owner),
) -> ActionStatusResponse | JSONResponse:
    """Verify the configured BirdNET-Go instance answers over HTTP. Owner only.

    BirdNET-Go detections arrive over MQTT, so the URL is optional (it powers
    spectrograms). When it is set, an HTTP response — any status — proves the
    BirdNET-Go server itself is up and reachable from the backend.
    """
    try:
        base_url = _validated_birdnet_base_url(url if url is not None else settings.frigate.birdnet_url)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "No BirdNET-Go URL is set. It is optional (detections arrive over MQTT), but set it to enable spectrograms and this check.",
            },
        )

    try:
        # Redirects are unnecessary for a reachability probe and could escape the
        # validated origin. The URL is owner-configured and validated immediately
        # above; private hosts are a required Docker/home-network use case.
        async with httpx.AsyncClient(follow_redirects=False) as http_client:
            resp = await http_client.get(base_url, timeout=10.0)  # lgtm[py/full-ssrf]
        return ActionStatusResponse(
            status="ok",
            message=f"BirdNET-Go answered (HTTP {resp.status_code}) at {base_url}.",
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": f"BirdNET-Go timed out at {base_url}."},
        )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": f"Could not reach BirdNET-Go at {base_url} ({type(e).__name__})."},
        )


class MQTTTestRequest(BaseModel):
    server: Optional[str] = Field(default=None, min_length=1, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    auth: Optional[bool] = None
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=512)


@router.post("/settings/mqtt/test-publish", response_model=ActionStatusResponse)
async def test_mqtt_publish(
    request: MQTTTestRequest,
    _auth: AuthContext = Depends(require_owner),
) -> ActionStatusResponse | JSONResponse:
    """Connect independently and publish using saved or on-screen MQTT values. Owner only."""
    from app.services.mqtt_service import mqtt_service

    server = request.server or settings.frigate.mqtt_server
    port = request.port or settings.frigate.mqtt_port
    use_auth = settings.frigate.mqtt_auth if request.auth is None else request.auth
    username = (
        (request.username if request.username is not None else settings.frigate.mqtt_username) if use_auth else None
    )
    supplied_password = request.password if request.password not in (None, "", "***REDACTED***") else None
    password = (supplied_password or settings.frigate.mqtt_password) if use_auth else None

    try:
        success = await mqtt_service.test_connection(
            server=server,
            port=port,
            username=username,
            password=password,
        )
        if success:
            return ActionStatusResponse(status="ok", message="Test message published to 'yawamf/test'")
        else:
            return JSONResponse(
                status_code=502, content={"status": "error", "message": "Failed to publish MQTT message. Check logs."}
            )
    except Exception as exc:
        log.error("MQTT Test Publish Failed", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "Could not connect to the MQTT broker. Check the host, port, and credentials.",
            },
        )


class NotificationTestRequest(BaseModel):
    platform: str = Field(..., max_length=32)  # discord, pushover, telegram
    # Optional overrides for testing uncommitted settings
    webhook_url: Optional[str] = Field(None, max_length=2048)
    user_key: Optional[str] = Field(None, max_length=256)
    api_token: Optional[str] = Field(None, max_length=512)
    bot_token: Optional[str] = Field(None, max_length=512)
    chat_id: Optional[str] = Field(None, max_length=128)


class TimezoneRepairApplyRequest(BaseModel):
    confirm: bool = False


class TimezoneRepairSummary(BaseModel):
    scanned_count: int
    repair_candidate_count: int
    ok_count: int
    missing_frigate_event_count: int
    lookup_error_count: int = 0
    unsupported_delta_count: int
    total_rows_in_scope: Optional[int] = None
    scan_limit: Optional[int] = None
    scan_truncated: Optional[bool] = None


class TimezoneRepairCandidateResponse(BaseModel):
    detection_id: int
    frigate_event: str
    camera_name: str
    display_name: str
    status: str
    stored_detection_time: str
    frigate_start_time: Optional[str] = None
    repaired_detection_time: Optional[str] = None
    delta_hours: Optional[int] = None
    error: Optional[str] = None


class TimezoneRepairPreviewResponse(BaseModel):
    summary: TimezoneRepairSummary
    candidates: list[TimezoneRepairCandidateResponse]


class TimezoneRepairApplyResponse(BaseModel):
    status: str
    repaired_count: int
    skipped_count: int
    preview: TimezoneRepairPreviewResponse


class MaintenanceStatsResponse(BaseModel):
    total_detections: int
    oldest_detection: Optional[str] = None
    retention_days: int = Field(description="The saved history retention in days (0 keeps everything).")
    detections_to_cleanup: int = Field(description="Detections the saved retention deletes at the next cleanup.")
    kept_newest_per_species: int = Field(
        0, description="The newest detections of each species kept regardless of age (0 = none)."
    )
    automatic_cleanup: bool = Field(
        True, description="Whether the scheduled cleanup runs (on start, then every 24 hours)."
    )
    preview_retention_days: Optional[int] = Field(
        None, description="The retention window asked for in `retention_days`, echoed back."
    )
    preview_detections_to_cleanup: Optional[int] = Field(
        None, description="Detections that window would delete under the same rules. Nothing is deleted."
    )


class CleanupResponse(BaseModel):
    status: str
    deleted_count: int
    audio_deleted_count: Optional[int] = None
    message: Optional[str] = None
    cutoff_date: Optional[str] = None


class PurgeMissingMediaResponse(BaseModel):
    status: str
    deleted_count: int
    marked_missing_count: int
    kept_count: int
    cleared_missing_count: int
    checked: int
    missing: int
    errors: int = 0
    message: Optional[str] = None


class AnalyzeUnknownsResponse(BaseModel):
    status: str
    count: int
    message: str
    accepted: Optional[int] = None
    skipped_duplicate: Optional[int] = None
    dropped_full: Optional[int] = None
    skipped_no_clip: Optional[int] = None
    skipped_missing_event: Optional[int] = None
    skipped_outside_retention: Optional[int] = None
    precheck_errors: Optional[int] = None
    total_candidates: Optional[int] = None
    remaining_candidates: Optional[int] = None
    queue_limit: Optional[int] = None
    scan_limit: Optional[int] = None
    scan_truncated: Optional[bool] = None
    pending_maintenance: Optional[int] = None
    active_maintenance: Optional[int] = None
    retry_after_seconds: Optional[int] = None


class AnalysisStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    pending: int
    active: int
    circuit_open: bool
    open_until: Optional[str] = None
    failure_count: Optional[int] = None
    pending_capacity: Optional[int] = None
    pending_available: Optional[int] = None
    max_concurrent_configured: Optional[int] = None
    max_concurrent_effective: Optional[int] = None
    mqtt_pressure_level: Optional[str] = None
    throttled_for_mqtt_pressure: Optional[bool] = None
    throttled_for_live_pressure: Optional[bool] = None
    maintenance_starvation_relief_active: Optional[bool] = None
    live_pressure_active: Optional[bool] = None
    live_in_flight: Optional[int] = None
    live_queued: Optional[int] = None
    mqtt_in_flight: Optional[int] = None
    mqtt_in_flight_capacity: Optional[int] = None
    oldest_maintenance_pending_age_seconds: Optional[float] = None
    pending_maintenance: Optional[int] = None
    active_maintenance: Optional[int] = None
    queue_limit: Optional[int] = None
    scan_limit: Optional[int] = None
    scan_truncated: Optional[bool] = None
    remaining_candidates: Optional[int] = None
    maintenance_state: Optional[str] = None
    maintenance_status_message: Optional[str] = None
    maintenance_seconds_since_progress: Optional[float] = None


class CacheStatsResponse(BaseModel):
    snapshot_count: int
    snapshot_size_bytes: int
    snapshot_size_mb: float
    clip_count: int
    clip_size_bytes: int
    clip_size_mb: float
    preview_count: int
    preview_size_bytes: int
    preview_size_mb: float
    film_count: int = 0
    film_size_bytes: int = 0
    film_size_mb: float = 0.0
    garden_count: int = Field(0, description="Kept photographs and clips of confirmed Garden animals")
    garden_size_bytes: int = 0
    garden_size_mb: float = 0.0
    total_size_bytes: int
    total_size_mb: float
    oldest_file: Optional[str] = None
    newest_file: Optional[str] = None
    storage_available: bool = Field(
        ..., description="False when the media folder cannot be written: photographs and visit media are then not kept"
    )
    cache_clips: bool
    archive_count: int = 0
    archive_size_bytes: int = 0
    archive_size_mb: float = 0.0
    archive_favorites: int = 0
    archive_durable: int = 0
    archive_pending: int = 0
    archive_failed: int = 0
    archive_unavailable: int = 0
    retention_days: int
    retention_source: str


class CacheStatsMeasurementResponse(BaseModel):
    id: str
    status: Literal["running", "completed", "failed"]
    started_at: datetime
    completed_at: Optional[datetime] = None
    stats: Optional[CacheStatsResponse] = None
    error: Optional[str] = None


class CacheCleanupResponse(BaseModel):
    status: str
    snapshots_deleted: int
    clips_deleted: int
    previews_deleted: int = 0
    bytes_freed: int
    protected_skipped: int = 0
    retention_days: int
    message: Optional[str] = None


class ClearFeedbackResponse(BaseModel):
    status: str
    message: str
    deleted_count: int


_Channel = TypeVar("_Channel", bound=BaseModel)


def _with_typed_credentials(saved: _Channel, **typed: Optional[str]) -> _Channel:
    """Overlay unapplied credentials on a private copy of a saved channel.

    Writing them onto the live settings, even for the length of one test send, let a
    concurrent settings save persist credentials the owner never applied.
    """
    overrides = {field: value for field, value in typed.items() if value and value != "***REDACTED***"}
    return saved.model_copy(update=overrides)


@router.post("/settings/notifications/test", response_model=ActionStatusResponse)
async def test_notification(
    request: NotificationTestRequest, _auth: AuthContext = Depends(require_owner)
) -> ActionStatusResponse | JSONResponse:
    """Test notification platform with optional credential overrides. Owner only."""

    # Create mock detection data
    common_name = "Eurasian Blue Tit (Test)"
    confidence = 0.95
    camera = "test_camera"
    timestamp = datetime.now(timezone.utc)
    snapshot_url = "https://placehold.co/600x400.jpg"
    detection_url = notification_link(settings.notifications, settings.frigate.frigate_external_url, None)

    try:
        if request.platform == "discord":
            await notification_service._send_discord(
                common_name,
                confidence,
                camera,
                timestamp,
                snapshot_url,
                True,
                settings.notifications.notification_language,
                None,
                detection_url=detection_url,
                config=_with_typed_credentials(settings.notifications.discord, webhook_url=request.webhook_url),
            )

        elif request.platform == "pushover":
            await notification_service._send_pushover(
                common_name,
                confidence,
                camera,
                timestamp,
                snapshot_url,
                None,
                settings.notifications.notification_language,
                detection_url=detection_url,
                config=_with_typed_credentials(
                    settings.notifications.pushover, user_key=request.user_key, api_token=request.api_token
                ),
            )

        elif request.platform == "telegram":
            await notification_service._send_telegram(
                common_name,
                confidence,
                camera,
                timestamp,
                snapshot_url,
                None,
                settings.notifications.notification_language,
                detection_url=detection_url,
                config=_with_typed_credentials(
                    settings.notifications.telegram, bot_token=request.bot_token, chat_id=request.chat_id
                ),
            )

        else:
            return JSONResponse(
                status_code=400, content={"status": "error", "message": f"Unknown platform: {request.platform}"}
            )

        return ActionStatusResponse(status="ok", message=f"Test notification sent to {request.platform}")
    except Exception as e:
        log.error("Notification test failed", error=str(e))
        return JSONResponse(status_code=502, content={"status": "error", "message": str(e)})


class BirdWeatherTestRequest(BaseModel):
    token: Optional[str] = None


@router.post("/settings/birdweather/test", response_model=ActionStatusResponse)
async def test_birdweather(
    request: BirdWeatherTestRequest, _auth: AuthContext = Depends(require_owner)
) -> ActionStatusResponse | JSONResponse:
    """Test BirdWeather integration with an optional token override. Owner only."""
    token = request.token if request.token and request.token != "***REDACTED***" else None
    if not token and not settings.birdweather.station_token:
        return JSONResponse(
            status_code=400, content={"status": "error", "message": "Missing BirdWeather station token"}
        )
    if token is None and not settings.birdweather.enabled:
        return JSONResponse(status_code=400, content={"status": "error", "message": "BirdWeather is disabled"})

    success = await birdweather_service.report_detection(
        scientific_name="Cyanistes caeruleus",
        common_name="Eurasian Blue Tit (Test)",
        confidence=0.95,
        timestamp=datetime.now(),
        token=token,
    )

    if success:
        return ActionStatusResponse(status="ok", message="BirdWeather test succeeded")
    return JSONResponse(
        status_code=502,
        content={"status": "error", "message": "BirdWeather test failed. Check token and station permissions."},
    )


class HaWeatherTestRequest(BaseModel):
    base_url: Optional[str] = None
    access_token: Optional[str] = None
    weather_entity: Optional[str] = None


class HaWeatherTestResponse(BaseModel):
    status: Literal["ok", "error"]
    message: str
    readings: dict[str, Any] = Field(default_factory=dict)


@router.post("/settings/ha-weather/test", response_model=HaWeatherTestResponse)
async def test_ha_weather(
    request: HaWeatherTestRequest, _auth: AuthContext = Depends(require_owner)
) -> HaWeatherTestResponse | JSONResponse:
    """Fetch a live reading from Home Assistant with the given or stored config. Owner only."""
    from app.services.ha_weather import HomeAssistantWeatherSource

    base_url = (request.base_url or settings.ha_weather.base_url or "").strip()
    token = request.access_token if request.access_token not in (None, "", "***REDACTED***") else None
    token = token or settings.ha_weather.access_token or ""
    weather_entity = (request.weather_entity or settings.ha_weather.weather_entity or "").strip() or None
    if not base_url or not token:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "A base URL and access token are required.", "readings": {}},
        )

    override_entities = settings.ha_weather.override_entities()
    if not weather_entity and not override_entities:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Nothing to read yet: set a weather entity (e.g. weather.home) or at least one sensor override.",
                "readings": {},
            },
        )

    source = HomeAssistantWeatherSource(
        base_url=base_url,
        access_token=token,
        weather_entity=weather_entity,
        override_entities=override_entities,
    )
    readings = await source.get_current_weather()
    if not readings:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "No readings came back. Check the URL, the token, and the entity ids.",
                "readings": {},
            },
        )
    return HaWeatherTestResponse(
        status="ok",
        message=f"{len(readings)} reading(s) received from Home Assistant.",
        readings=readings,
    )


class LlmTestRequest(BaseModel):
    llm_enabled: Optional[bool] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None


class LlmTestResponse(ActionStatusResponse):
    provider: str
    model: str
    frame_count: int
    failure_stage: Optional[Literal["configuration", "provider", "vision", "multi_frame", "response"]] = None
    retryable: bool = False
    retry_after_seconds: Optional[int] = None


@router.post("/settings/llm/test", response_model=LlmTestResponse)
async def test_llm(
    request: LlmTestRequest, _auth: AuthContext = Depends(require_owner)
) -> LlmTestResponse | JSONResponse:
    """Test configuration, provider availability, vision, and multi-frame admission. Owner only."""
    enabled = request.llm_enabled if request.llm_enabled is not None else settings.llm.enabled
    provider = request.llm_provider or settings.llm.provider
    model = request.llm_model or settings.llm.model
    if not enabled:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "AI insights are disabled.",
                "provider": provider,
                "model": model,
                "frame_count": AIService.TEST_PROBE_FRAME_COUNT,
                "failure_stage": "configuration",
                "retryable": False,
                "retry_after_seconds": None,
            },
        )

    api_key = request.llm_api_key
    if not api_key or api_key == "***REDACTED***":
        api_key = settings.llm.api_key

    if not api_key:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "AI API key is missing.",
                "provider": provider,
                "model": model,
                "frame_count": AIService.TEST_PROBE_FRAME_COUNT,
                "failure_stage": "configuration",
                "retryable": False,
                "retry_after_seconds": None,
            },
        )

    service = AIService()
    result = await service.test_connection(provider, model, api_key)
    payload = {
        "status": "ok" if result.ok else "error",
        "message": result.message,
        "provider": provider,
        "model": model,
        "frame_count": service.TEST_PROBE_FRAME_COUNT,
        "failure_stage": result.failure_stage,
        "retryable": result.retryable,
        "retry_after_seconds": result.retry_after_seconds,
    }
    if result.ok:
        return LlmTestResponse(**payload)
    return JSONResponse(status_code=result.http_status_hint, content=payload)


class SettingsUpdate(BaseModel):
    frigate_url: Optional[str] = Field(None, min_length=1, description="Frigate instance URL")
    frigate_ingest_labels: Optional[List[str]] = Field(None, description="Frigate event labels YA-WAMF acts on")
    frigate_external_url: Optional[str] = Field("", description="External Frigate base URL (browser→Frigate)")
    mqtt_server: Optional[str] = Field(None, min_length=1, description="MQTT server hostname")
    mqtt_port: int = Field(1883, ge=1, le=65535, description="MQTT server port")
    mqtt_auth: bool = Field(False, description="Enable MQTT authentication")
    mqtt_username: Optional[str] = Field(None, description="MQTT username")
    mqtt_password: Optional[str] = Field(None, description="MQTT password")
    birdnet_enabled: Optional[bool] = Field(True, description="Enable BirdNET-Go integration")
    birdnet_url: Optional[str] = Field("", description="Internal BirdNET-Go base URL (server→BirdNET-Go)")
    birdnet_external_url: Optional[str] = Field("", description="External BirdNET-Go base URL (browser→BirdNET-Go)")
    audio_topic: str = Field("birdnet/text", description="MQTT topic for audio detections")
    camera_audio_mapping: dict[str, str] = Field(default_factory=dict, description="Map Frigate camera to BirdNET ID")
    camera_roles: dict[str, Literal["feeder", "nest"]] = Field(default_factory=dict, description="Per-camera role")
    garden_cameras: list[str] = Field(
        default_factory=list, description="Cameras opted in to owner-reviewed garden captures"
    )
    garden_labels: list[str] = Field(
        default_factory=lambda: ["cat", "dog"], description="Animal labels for garden review"
    )
    garden_motion_cameras: list[str] = Field(
        default_factory=list, description="Garden cameras opted in to bounded motion review scans"
    )

    garden_motion_confidence: float = Field(
        0.5,
        ge=0.5,
        le=0.95,
        allow_inf_nan=False,
        strict=True,
        description="Minimum Cedar animal score for new motion proposals; does not change bird or person thresholds",
    )
    garden_notifications_enabled: bool = Field(
        False, description="Opt in to Garden alerts independently of bird notifications"
    )
    garden_notifications_use_bird_channels: bool = Field(
        True,
        description="Send Garden alerts on whichever bird channels are switched on and configured; "
        "off uses garden_notification_channels",
    )
    garden_notification_channels: list[Literal["discord", "telegram", "pushover", "email"]] = Field(
        default_factory=list,
        max_length=4,
        description="Explicit Garden delivery channels using saved notification credentials, "
        "used while garden_notifications_use_bird_channels is off",
    )
    garden_notifications_include_photo: bool = Field(
        True, description="Attach the saved animal crop, or the capture photo, to Garden alerts"
    )

    garden_automatic_naming: bool = Field(
        True, description="Confirm and name a Garden animal automatically at or above the naming threshold"
    )
    garden_naming_threshold: float = Field(
        0.8,
        ge=0.7,
        le=0.99,
        allow_inf_nan=False,
        strict=True,
        description="Minimum SpeciesNet score to name a Garden animal automatically; does not change bird thresholds",
    )
    garden_domestic_birds: list[DomesticBirdKey] = Field(
        default_factory=list,
        description="Domestic birds this install keeps, recorded as Garden animals instead of bird detections",
    )

    @field_validator("garden_motion_cameras", mode="before")
    @classmethod
    def validate_motion_cameras(cls, value: object) -> list[str]:
        from app.services.garden_motion_policy import normalize_motion_cameras

        return normalize_motion_cameras(value)

    @field_validator("garden_cameras", mode="before")
    @classmethod
    def validate_garden_cameras(cls, value: object) -> list[str]:
        from app.services.garden_capture_policy import normalize_garden_cameras

        return normalize_garden_cameras(value)

    @field_validator("garden_labels", mode="before")
    @classmethod
    def validate_garden_labels(cls, value: object) -> list[str]:
        from app.services.garden_capture_policy import normalize_garden_labels

        return normalize_garden_labels(value)

    @field_validator("garden_domestic_birds", mode="before")
    @classmethod
    def validate_garden_domestic_birds(cls, value: object) -> list[str]:
        return normalize_domestic_birds(value)

    nest_dedupe_minutes: int = Field(30, ge=1, le=720, description="Dedupe window for nest cameras")
    audio_buffer_hours: int = Field(
        24, ge=1, le=168, description="Hours to keep audio detections in buffer for correlation (1-168)"
    )
    audio_correlation_window_seconds: int = Field(
        300,
        ge=5,
        le=3600,
        description="Time window in seconds for audio-visual correlation (±N seconds from detection)",
    )
    audio_min_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Ignore BirdNET-Go audio detections below this confidence (0.0 stores everything)",
    )
    classification_image_source: Literal["frigate_snapshot", "recording_snapshot"] = Field(
        "frigate_snapshot",
        description="Initial classification image source; recordings fall back to the detection snapshot",
    )
    recording_frame_delay_seconds: float = Field(
        12,
        ge=1,
        le=120,
        description="Initial recording-frame identification delay in seconds",
    )
    clips_enabled: bool = Field(True, description="Enable fetching of video clips from Frigate")
    recording_clip_enabled: bool = Field(False, description="Enable full-visit recording clips")
    recording_clip_before_seconds: int = Field(
        30, ge=0, le=3600, description="Seconds before detection for full-visit clip"
    )
    recording_clip_after_seconds: int = Field(
        90, ge=0, le=3600, description="Seconds after detection for full-visit clip"
    )
    classification_threshold: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Classification confidence threshold (0-1)"
    )
    classification_min_confidence: float = Field(0.4, ge=0.0, le=1.0, description="Minimum confidence floor (0-1)")
    live_worker_count: Optional[int] = Field(
        None, ge=1, le=8, description="Live classifier worker processes; null follows the default (one)"
    )
    background_worker_count: Optional[int] = Field(
        None, ge=1, le=4, description="Background classifier worker processes; null follows the default (one)"
    )
    cameras: List[str] = Field(default_factory=list, description="List of cameras to monitor")
    retention_days: int = Field(0, ge=0, description="Days to keep detections (0 = unlimited)")
    maintenance_max_concurrent: Optional[int] = Field(
        1, ge=1, le=8, description="Maximum concurrent maintenance workflows"
    )
    auto_delete_missing_clips: bool = Field(False, description="Auto-delete detections when event/clip is missing")
    frigate_missing_behavior: FrigateMissingBehavior = Field(
        "mark_missing",
        description="How YA-WAMF should react when Frigate no longer has the event or retained media",
    )
    auto_purge_missing_clips: bool = Field(
        False, description="Deprecated: use media_integrity_scan_enabled with media='clip'"
    )
    auto_purge_missing_snapshots: bool = Field(
        False, description="Deprecated: use media_integrity_scan_enabled with media='snapshot'"
    )
    media_integrity_scan_enabled: bool = Field(
        False, description="Periodically re-check detections against Frigate and apply the missing-media behaviour"
    )
    media_integrity_scan_media: MediaIntegrityScanMedia = Field(
        "any", description="Which media must be absent upstream for a detection to count as missing"
    )
    media_integrity_scan_interval_hours: int = Field(6, ge=1, le=168, description="Hours between media integrity scans")
    media_integrity_scan_batch_size: int = Field(
        1000, ge=1, le=20000, description="Maximum detections re-checked against Frigate in one scan"
    )
    auto_analyze_unknowns: bool = Field(False, description="Analyze unknown detections during scheduled cleanup")
    blocked_labels: List[str] = Field(default_factory=list, description="Labels to filter out from detections")
    blocked_species: List[BlockedSpeciesEntry] = Field(
        default_factory=list, description="Structured blocked species entries"
    )
    trust_frigate_sublabel: bool = Field(True, description="Trust Frigate sublabels when available")
    write_frigate_sublabel: bool = Field(True, description="Write YA-WAMF labels back to Frigate sublabels")
    display_common_names: bool = Field(True, description="Display common names instead of scientific")
    scientific_name_primary: bool = Field(False, description="Show scientific name as the primary label in UI")
    personalized_rerank_enabled: Optional[bool] = Field(
        False, description="Enable personalized reranking using manual tag feedback"
    )
    range_filter_enabled: Optional[bool] = Field(
        False, description="Set aside automatic identifications of species eBird has never recorded in this region"
    )
    range_filter_region_level: Optional[Literal["county", "state", "country"]] = Field(
        "county", description="Finest eBird region the range filter uses"
    )
    # Auto Video Classification
    auto_video_classification: Optional[bool] = Field(False, description="Automatically classify video clips")
    video_classification_delay: Optional[int] = Field(30, ge=0, description="Seconds to wait before checking for clip")
    video_classification_max_retries: Optional[int] = Field(3, ge=0, description="Max retries for clip availability")
    video_classification_frames: Optional[int] = Field(
        15, ge=5, le=100, description="Number of frames to sample for video classification"
    )
    image_execution_mode: Optional[str] = Field(
        "subprocess",
        description="Image inference execution mode: subprocess|in_process",
    )
    strict_non_finite_output: Optional[bool] = Field(
        True,
        description="Reject all-non-finite inference outputs and trigger runtime recovery/fallback",
    )
    inference_provider: Optional[str] = Field(
        "auto", description="Preferred inference provider: auto|cpu|cuda|intel_gpu|intel_cpu|intel_npu"
    )
    bird_crop_detector_tier: Optional[Literal["fast", "accurate"]] = Field(
        "fast",
        description="Deprecated compatibility field; crop generation automatically tries accurate then fast",
    )
    bird_crop_accurate_detector: Optional[Literal["yolox_tiny", "rfdetr_nano"]] = Field(
        "yolox_tiny",
        description="Which accurate bird detector finds birds in full frames before identification",
    )
    bird_crop_inference_provider: Optional[Literal["auto", "cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"]] = (
        Field(
            None,
            description="Accurate bird finder device; explicit accelerators require current validation for this finder",
        )
    )
    bird_crop_source_priority: Optional[
        Literal["frigate_hints_first", "crop_model_first", "crop_model_only", "frigate_hints_only"]
    ] = Field(
        "frigate_hints_first",
        description="Deprecated compatibility field; HQ snapshots choose the best available crop automatically",
    )
    bird_model_region_override: Optional[str] = Field("auto", description="Bird model region override: auto|eu|na")
    crop_model_overrides: dict[str, str] = Field(
        default_factory=dict, description="Deprecated compatibility field; ignored by the runtime"
    )
    crop_source_overrides: dict[str, str] = Field(
        default_factory=dict, description="Deprecated compatibility field; ignored by the runtime"
    )
    # Media cache settings
    media_cache_clips: bool = Field(False, description="Cache video clips locally (may cause initial playback delay)")
    media_cache_high_quality_event_snapshots: bool = Field(
        False,
        description="Replace cached event snapshots with a frame derived from the Frigate clip when available",
    )
    media_cache_high_quality_event_snapshot_bird_crop: bool = Field(
        False,
        description="Deprecated compatibility field; HQ snapshots automatically attempt every available crop source",
    )
    media_cache_high_quality_event_snapshot_jpeg_quality: int = Field(
        90,
        ge=70,
        le=100,
        description="JPEG quality for derived high-quality event snapshots",
    )
    media_cache_retention_days: int = Field(0, ge=0, description="Days to keep cached media (0 = follow detection)")
    media_cache_per_species_minimum: int = Field(
        0, ge=0, le=10000, description="Newest detections per species kept out of age cleanup (0 = off)"
    )
    media_cache_per_species_maximum: int = Field(
        0, ge=0, le=10000, description="Maximum cached visits per species, excluding favourites; 0 is unlimited"
    )
    media_cache_max_size_mb: int = Field(
        0, ge=0, le=1048576, description="Ordinary media budget in MiB, excluding archived favourites; 0 is unlimited"
    )
    media_cache_automatic_multi_bird_scan: bool = Field(
        False, description="Automatically scan visit photos for additional birds; manual scans remain available"
    )
    media_cache_bird_scan_mode: Literal["standard", "intensive"] = Field(
        "intensive", description="Bird scan effort; standard is lighter, intensive scans high-resolution tiles"
    )
    # Location settings
    location_latitude: Optional[float] = Field(None, description="Latitude")
    location_longitude: Optional[float] = Field(None, description="Longitude")
    location_state: Optional[str] = Field(None, description="State/region")
    location_country: Optional[str] = Field(None, description="Country")
    location_automatic: Optional[bool] = Field(True, description="Auto-detect location")
    location_weather_unit_system: Optional[str] = Field(
        "metric",
        description="Weather unit system: 'metric', 'imperial', or 'british'",
    )
    location_temperature_unit: Optional[str] = Field(
        "celsius", description="Temperature unit: 'celsius' or 'fahrenheit'"
    )
    # BirdWeather settings
    birdweather_enabled: Optional[bool] = Field(False, description="Enable BirdWeather reporting")
    birdweather_station_token: Optional[str] = Field(None, description="BirdWeather Station Token")
    # Home Assistant weather source (#277)
    ha_weather_enabled: Optional[bool] = Field(None, description="Source live weather from Home Assistant")
    ha_weather_base_url: Optional[str] = Field(None, description="Home Assistant base URL")
    ha_weather_access_token: Optional[str] = Field(None, description="Home Assistant long-lived access token")
    ha_weather_entity: Optional[str] = Field(None, description="Weather entity used as the general source")
    ha_weather_temperature_entity: Optional[str] = Field(None, description="Sensor overriding temperature")
    ha_weather_wind_speed_entity: Optional[str] = Field(None, description="Sensor overriding wind speed")
    ha_weather_wind_direction_entity: Optional[str] = Field(None, description="Sensor overriding wind direction")
    ha_weather_cloud_cover_entity: Optional[str] = Field(None, description="Sensor overriding cloud cover")
    ha_weather_precipitation_entity: Optional[str] = Field(None, description="Sensor overriding precipitation")
    ha_weather_rain_entity: Optional[str] = Field(None, description="Sensor overriding rainfall")
    ha_weather_snowfall_entity: Optional[str] = Field(None, description="Sensor overriding snowfall")
    # eBird settings
    ebird_enabled: Optional[bool] = Field(False, description="Enable eBird enrichment")
    ebird_api_key: Optional[str] = Field(None, description="eBird API key")
    ebird_default_radius_km: Optional[int] = Field(
        25, ge=1, le=50, description="Default radius in km for eBird queries"
    )
    ebird_default_days_back: Optional[int] = Field(14, ge=1, le=30, description="Days back for eBird queries")
    ebird_max_results: Optional[int] = Field(25, ge=1, le=200, description="Max eBird results to return")
    ebird_locale: Optional[str] = Field("en", description="eBird locale for common names")
    # iNaturalist settings
    inaturalist_enabled: Optional[bool] = Field(False, description="Enable iNaturalist submissions")
    inaturalist_client_id: Optional[str] = Field(None, description="iNaturalist OAuth Client ID")
    inaturalist_client_secret: Optional[str] = Field(None, description="iNaturalist OAuth Client Secret")
    inaturalist_default_latitude: Optional[float] = Field(
        None, description="Default latitude for iNaturalist submissions"
    )
    inaturalist_default_longitude: Optional[float] = Field(
        None, description="Default longitude for iNaturalist submissions"
    )
    inaturalist_default_place_guess: Optional[str] = Field(
        None, description="Default place guess for iNaturalist submissions"
    )
    # Enrichment settings
    enrichment_mode: Optional[str] = Field(
        "per_enrichment", description="Enrichment source mode: single or per_enrichment"
    )
    enrichment_single_provider: Optional[str] = Field("wikipedia", description="Provider used when mode=single")
    enrichment_summary_source: Optional[str] = Field("wikipedia", description="Provider for summaries/description")
    enrichment_taxonomy_source: Optional[str] = Field("inaturalist", description="Provider for taxonomy/common names")
    enrichment_sightings_source: Optional[str] = Field("disabled", description="Provider for nearby sightings")
    enrichment_seasonality_source: Optional[str] = Field("disabled", description="Provider for seasonality")
    enrichment_rarity_source: Optional[str] = Field("disabled", description="Provider for rarity indicators")
    enrichment_links_sources: Optional[List[str]] = Field(
        default_factory=list, description="Providers for external links"
    )
    # LLM settings
    llm_enabled: Optional[bool] = Field(False, description="Enable AI behavior analysis")
    llm_provider: Optional[str] = Field("gemini", description="AI provider")
    llm_api_key: Optional[str] = Field(None, description="API key")
    llm_model: Optional[str] = Field(DEFAULT_LLM_MODEL, description="AI model")
    llm_analysis_prompt_template: Optional[str] = Field(None, description="Prompt template for detection analysis")
    llm_conversation_prompt_template: Optional[str] = Field(
        None, description="Prompt template for follow-up conversation"
    )
    llm_chart_prompt_template: Optional[str] = Field(None, description="Prompt template for chart analysis")
    ai_pricing_json: Optional[str] = Field(None, description="JSON string containing AI pricing overrides")

    # Telemetry
    telemetry_enabled: Optional[bool] = Field(False, description="Enable anonymous usage statistics")
    telemetry_health_enabled: Optional[bool] = Field(False, description="Enable anonymous health issue diagnostics")

    # Notifications
    notifications_discord_enabled: Optional[bool] = False
    notifications_discord_webhook_url: Optional[str] = None
    notifications_discord_username: Optional[str] = "YA-WAMF"

    notifications_pushover_enabled: Optional[bool] = False
    notifications_pushover_user_key: Optional[str] = None
    notifications_pushover_api_token: Optional[str] = None
    notifications_pushover_priority: Optional[int] = 0
    notifications_pushover_device: Optional[str] = None

    notifications_telegram_enabled: Optional[bool] = False
    notifications_telegram_bot_token: Optional[str] = None
    notifications_telegram_chat_id: Optional[str] = None

    notifications_email_enabled: Optional[bool] = False
    notifications_email_only_on_end: Optional[bool] = False
    notifications_email_use_oauth: Optional[bool] = False
    notifications_email_oauth_provider: Optional[str] = None
    notifications_email_gmail_client_id: Optional[str] = None
    notifications_email_gmail_client_secret: Optional[str] = None
    notifications_email_outlook_client_id: Optional[str] = None
    notifications_email_outlook_client_secret: Optional[str] = None
    notifications_email_smtp_host: Optional[str] = None
    notifications_email_smtp_port: Optional[int] = 587
    notifications_email_smtp_username: Optional[str] = None
    notifications_email_smtp_password: Optional[str] = None
    notifications_email_smtp_use_tls: Optional[bool] = True
    notifications_email_from_email: Optional[str] = None
    notifications_email_to_email: Optional[str] = None
    notifications_email_include_snapshot: Optional[bool] = True
    notifications_email_dashboard_url: Optional[str] = None
    notifications_instance_url: Optional[str] = None
    notifications_link_target: Optional[Literal["yawamf", "frigate"]] = None

    notifications_filter_species_mode: Optional[Literal["none", "blacklist", "whitelist"]] = "none"
    notifications_filter_species_whitelist: Optional[List[str]] = []
    notifications_filter_species_whitelist_structured: List[BlockedSpeciesEntry] = Field(default_factory=list)
    notifications_filter_species_blacklist_structured: List[BlockedSpeciesEntry] = Field(default_factory=list)
    notifications_filter_min_confidence: Optional[float] = 0.7
    notifications_filter_audio_confirmed_only: Optional[bool] = False
    notification_language: Optional[str] = "en"
    notifications_mode: Optional[str] = "standard"
    notifications_notify_on_insert: Optional[bool] = True
    notifications_notify_on_update: Optional[bool] = False
    notifications_delay_until_video: Optional[bool] = False
    notifications_video_fallback_timeout: Optional[int] = 45
    notifications_notification_cooldown_minutes: Optional[int] = 0

    # Accessibility
    accessibility_high_contrast: Optional[bool] = False
    accessibility_dyslexia_font: Optional[bool] = False
    accessibility_reduced_motion: Optional[bool] = False
    accessibility_live_announcements: Optional[bool] = True

    # Authentication
    auth_enabled: Optional[bool] = None
    auth_username: Optional[str] = Field(None, min_length=1, max_length=50)
    auth_password: Optional[str] = Field(
        None,
        min_length=8,
        max_length=128,
        description="New passwords must use 72 UTF-8 bytes or fewer",
    )
    auth_session_expiry_hours: Optional[int] = Field(None, ge=1, le=720)
    trusted_proxy_hosts: Optional[List[str]] = None
    beta_garden_animals: Optional[bool] = None

    @field_validator("auth_username")
    @classmethod
    def validate_auth_username(cls, v: Optional[str]) -> Optional[str]:
        """Validate username contains only safe characters."""
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("Username must contain only letters, numbers, underscore, hyphen, and period")
        return v.strip()

    @field_validator("auth_password")
    @classmethod
    def validate_auth_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength."""
        if v is None or not v:  # Allow empty string to mean "don't change"
            return v

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        validate_bcrypt_password_length(v)

        # Check for basic complexity (at least one letter and one number)
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number")

        return v

    # Public access
    public_access_enabled: Optional[bool] = None
    public_access_show_camera_names: Optional[bool] = None
    public_access_show_ai_conversation: Optional[bool] = None
    public_access_allow_clip_downloads: Optional[bool] = None
    public_access_historical_days_mode: Optional[str] = None
    public_access_historical_days: Optional[int] = Field(None, ge=0, le=365)
    public_access_media_days_mode: Optional[str] = None
    public_access_media_historical_days: Optional[int] = Field(None, ge=0, le=365)
    public_access_rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=100)
    public_access_external_base_url: Optional[str] = Field(None, max_length=512)
    public_access_show_audio: Optional[bool] = Field(None, description="Show BirdNET audio to public visitors")
    public_access_show_snapshots: Optional[bool] = Field(None, description="Show snapshots to public visitors")
    public_access_show_clips: Optional[bool] = Field(None, description="Show clips to public visitors")
    public_access_location_precision: Optional[Literal["approximate", "exact"]] = Field(
        None, description="Location precision for guest-facing features"
    )

    species_info_source: Optional[str] = "auto"
    date_format: Optional[str] = None
    time_format: Optional[str] = None
    appearance_explorer_view: Optional[ExplorerView] = None
    appearance_font_theme: Optional[str] = None
    appearance_color_theme: Optional[str] = None

    @field_validator("location_weather_unit_system")
    @classmethod
    def validate_location_weather_unit_system(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        if normalized not in ("metric", "imperial", "british"):
            raise ValueError("location_weather_unit_system must be 'metric', 'imperial', or 'british'")
        return normalized

    @field_validator("location_temperature_unit")
    @classmethod
    def validate_location_temperature_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        if normalized not in ("celsius", "fahrenheit"):
            raise ValueError("location_temperature_unit must be 'celsius' or 'fahrenheit'")
        return normalized

    @field_validator("notifications_mode")
    @classmethod
    def validate_notifications_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        allowed = {"silent", "final", "standard", "realtime", "custom"}
        if normalized not in allowed:
            raise ValueError("notifications_mode must be one of: silent, final, standard, realtime, custom")
        return normalized

    @field_validator("enrichment_mode")
    @classmethod
    def validate_enrichment_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        allowed = {"single", "per_enrichment"}
        if normalized not in allowed:
            raise ValueError("enrichment_mode must be 'single' or 'per_enrichment'")
        return normalized

    @field_validator("inference_provider")
    @classmethod
    def validate_inference_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        allowed = {"auto", "cpu", "cuda", "intel_gpu", "intel_cpu", "intel_npu"}
        if normalized not in allowed:
            raise ValueError("inference_provider must be one of: auto, cpu, cuda, intel_gpu, intel_cpu, intel_npu")
        return normalized

    @field_validator("frigate_url")
    @classmethod
    def validate_frigate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("frigate_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("birdnet_url")
    @classmethod
    def validate_birdnet_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return "" if v is not None else None
        return _validated_birdnet_base_url(v)

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        allowed = {"locale", "mdy", "dmy", "ymd"}
        if normalized not in allowed:
            raise ValueError("date_format must be one of: locale, mdy, dmy, ymd")
        return normalized

    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        allowed = {"locale", "12h", "24h"}
        if normalized not in allowed:
            raise ValueError("time_format must be one of: locale, 12h, 24h")
        return normalized


_settings_response_fields = {
    name: (
        field.annotation,
        field.default if not field.is_required() else ...,
    )
    for name, field in SettingsUpdate.model_fields.items()
    if name != "auth_password"
}
_settings_response_fields.update(
    {
        "video_classification_circuit_open": (bool, False),
        "video_classification_circuit_until": (Optional[str], None),
        "video_classification_circuit_failures": (int, 0),
        "video_classification_maintenance_circuit_open": (bool, False),
        "video_classification_maintenance_circuit_until": (Optional[str], None),
        "video_classification_maintenance_circuit_failures": (int, 0),
        "inaturalist_connected_user": (Optional[str], None),
        "llm_ready": (bool, False),
        "telemetry_installation_id": (Optional[str], None),
        "telemetry_platform": (Optional[str], None),
        "telemetry_payload_preview": (Optional[dict], None),
        "notifications_email_connected_email": (Optional[str], None),
        "auth_has_password": (bool, False),
        "debug_ui_enabled": (bool, False),
        "beta_garden_animals": (bool, False),
        "update_check_enabled": (bool, True),
    }
)
SettingsResponse = create_model("SettingsResponse", **_settings_response_fields)


def _config_backup_payload() -> dict[str, Any]:
    return {
        "format": CONFIG_BACKUP_FORMAT,
        "format_version": CONFIG_BACKUP_FORMAT_VERSION,
        "app": "YA-WAMF",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "includes_secrets": True,
        "config_path": str(CONFIG_PATH),
        "config": settings.model_dump(mode="json"),
    }


def _extract_import_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config")
    if isinstance(config, dict):
        return config
    if "frigate" in payload and "classification" in payload:
        return payload
    raise HTTPException(status_code=422, detail="Invalid YA-WAMF config backup")


async def _broadcast_settings_imported(changed_fields: list[str], username: str) -> None:
    try:
        from app.services.broadcaster import broadcaster

        await broadcaster.broadcast(
            {
                "type": "settings_updated",
                "data": {
                    "changed_fields": sorted(changed_fields),
                    "updated_by": username,
                    "source": "config_import",
                },
            }
        )
    except Exception as e:
        log.warning("Failed to broadcast settings import", error=str(e))


@router.get("/settings/export", response_class=JSONResponse)
async def export_settings(auth: AuthContext = Depends(require_owner)):
    """Export the full persisted configuration, including secrets. Owner only."""
    payload = _config_backup_payload()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="yawamf-config-backup-{timestamp}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/settings/import", response_model=SettingsImportResponse)
async def import_settings(
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] = Body(...),
    auth: AuthContext = Depends(require_owner),
) -> SettingsImportResponse:
    """Import a full configuration backup. Owner only."""

    async def write() -> SettingsImportResponse:
        return await _import_settings(background_tasks, payload, auth)

    return await run_settings_writer(write)


async def _import_settings(
    background_tasks: BackgroundTasks, payload: dict[str, Any], auth: AuthContext
) -> SettingsImportResponse:
    config = _extract_import_config(payload)
    migrate_imported_media_controls(config)
    try:
        imported = AppSettings.model_validate(config)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e

    if imported.auth.enabled and not imported.auth.password_hash:
        raise HTTPException(status_code=422, detail=AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE)

    # These keys belong to this installation, not to its configuration: the session
    # secret signs the owner's current login, and the OAuth key decrypts tokens stored
    # in this database. Taking them from a backup signed the importer out, could
    # reinstate a secret rotated after a leak, and stranded the stored OAuth tokens.
    imported.auth.session_secret = settings.auth.session_secret
    imported.auth.oauth_token_secret = settings.auth.oauth_token_secret

    previous_classifier = (
        settings.classification.model,
        settings.classification.inference_provider,
        settings.classification.image_execution_mode,
        settings.classification.bird_crop_accurate_detector,
        settings.classification.bird_crop_inference_provider,
        settings.location.latitude,
        settings.location.longitude,
    )
    previous_ebird_naming = (settings.ebird.api_key, settings.ebird.locale, settings.ebird.enabled)
    telemetry_was_enabled = settings.telemetry.enabled or settings.telemetry.health_enabled
    telemetry_installation_id = settings.telemetry.installation_id

    changed_fields = [
        field for field in AppSettings.model_fields if getattr(settings, field) != getattr(imported, field)
    ]
    await apply_update(settings, imported)
    await _broadcast_settings_imported(changed_fields, auth.username)

    # The same follow-up a settings save does, so an import takes effect without a restart.
    if settings.telemetry.enabled:
        background_tasks.add_task(telemetry_service.force_heartbeat)
    if settings.telemetry.health_enabled:
        background_tasks.add_task(telemetry_service.force_health_report)
    if (
        telemetry_was_enabled
        and not settings.telemetry.enabled
        and not settings.telemetry.health_enabled
        and telemetry_installation_id
    ):
        background_tasks.add_task(telemetry_service.forget_installation, telemetry_installation_id)

    if (settings.ebird.api_key, settings.ebird.locale, settings.ebird.enabled) != previous_ebird_naming:
        from app.services.localized_names import start_background_refresh

        background_tasks.add_task(start_background_refresh)

    current_classifier = (
        settings.classification.model,
        settings.classification.inference_provider,
        settings.classification.image_execution_mode,
        settings.classification.bird_crop_accurate_detector,
        settings.classification.bird_crop_inference_provider,
        settings.location.latitude,
        settings.location.longitude,
    )
    if current_classifier != previous_classifier:
        from app.services.classifier_service import reload_classifier_out_of_band

        execution_mode_changed = current_classifier[2] != previous_classifier[2]
        background_tasks.add_task(reload_classifier_out_of_band, full_restart=execution_mode_changed)

    log.info(
        "AUTH_AUDIT: Config backup imported",
        event_type="config_imported",
        username=auth.username,
        changed_fields=changed_fields,
    )
    return SettingsImportResponse(status="imported", changed_fields=changed_fields)


@router.get("/settings/public", response_model=PublicSettings)
async def get_public_settings() -> PublicSettings:
    """The display preferences a viewer needs, served to guest and owner alike.

    Deliberately unauthenticated. `/api/settings` is owner-only, so a guest could
    read no display preference at all and every one that shaped their view had to
    be copied onto the auth status payload by hand. The projection names its
    fields, so what is public is a decision rather than an oversight.
    """
    return build_public_settings()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(auth: AuthContext = Depends(require_owner)):
    """
    Get application settings with secrets redacted. Owner only.
    Secrets are never returned via API for security reasons.
    """
    oauth_status = await smtp_service.get_oauth_status(settings.notifications.email.oauth_provider)
    if not oauth_status:
        oauth_status = await smtp_service.get_oauth_status()
    connected_email = oauth_status["email"] if oauth_status else None
    connected_provider = oauth_status["provider"] if oauth_status else settings.notifications.email.oauth_provider

    inat_user = await inaturalist_service.refresh_connected_user()

    circuit_status = auto_video_classifier.get_circuit_status("live")
    maintenance_circuit_status = auto_video_classifier.get_circuit_status("maintenance")
    effective_enrichment = get_effective_enrichment_settings()
    ebird_active = is_ebird_active()

    return {
        "frigate_url": settings.frigate.frigate_url,
        "frigate_ingest_labels": settings.frigate.ingest_labels,
        "frigate_external_url": settings.frigate.frigate_external_url,
        "mqtt_server": settings.frigate.mqtt_server,
        "mqtt_port": settings.frigate.mqtt_port,
        "mqtt_auth": settings.frigate.mqtt_auth,
        "mqtt_username": settings.frigate.mqtt_username,
        # SECURITY: Never expose passwords via API
        "mqtt_password": "***REDACTED***" if settings.frigate.mqtt_password else None,
        "birdnet_enabled": settings.frigate.birdnet_enabled,
        "birdnet_url": settings.frigate.birdnet_url,
        "birdnet_external_url": settings.frigate.birdnet_external_url,
        "audio_topic": settings.frigate.audio_topic,
        "camera_audio_mapping": settings.frigate.camera_audio_mapping,
        "camera_roles": settings.frigate.camera_roles,
        "garden_cameras": settings.frigate.garden_cameras,
        "garden_labels": settings.frigate.garden_labels,
        "garden_motion_cameras": settings.frigate.garden_motion_cameras,
        "garden_motion_confidence": settings.frigate.garden_motion_confidence,
        "garden_notifications_enabled": settings.frigate.garden_notifications_enabled,
        "garden_notifications_use_bird_channels": settings.frigate.garden_notifications_use_bird_channels,
        "garden_notification_channels": settings.frigate.garden_notification_channels,
        "garden_notifications_include_photo": settings.frigate.garden_notifications_include_photo,
        "garden_automatic_naming": settings.frigate.garden_automatic_naming,
        "garden_naming_threshold": settings.frigate.garden_naming_threshold,
        "garden_domestic_birds": settings.frigate.garden_domestic_birds,
        "nest_dedupe_minutes": settings.frigate.nest_dedupe_minutes,
        "audio_buffer_hours": settings.frigate.audio_buffer_hours,
        "audio_correlation_window_seconds": settings.frigate.audio_correlation_window_seconds,
        "audio_min_confidence": settings.frigate.audio_min_confidence,
        "classification_image_source": settings.frigate.classification_image_source,
        "recording_frame_delay_seconds": settings.frigate.recording_frame_delay_seconds,
        "clips_enabled": settings.frigate.clips_enabled,
        "recording_clip_enabled": settings.frigate.recording_clip_enabled,
        "recording_clip_before_seconds": settings.frigate.recording_clip_before_seconds,
        "recording_clip_after_seconds": settings.frigate.recording_clip_after_seconds,
        "classification_threshold": settings.classification.threshold,
        "classification_min_confidence": settings.classification.min_confidence,
        "live_worker_count": settings.classification.live_worker_count,
        "background_worker_count": settings.classification.background_worker_count,
        "cameras": settings.frigate.camera,
        "retention_days": settings.maintenance.retention_days,
        "maintenance_max_concurrent": settings.maintenance.max_concurrent,
        "auto_delete_missing_clips": settings.maintenance.auto_delete_missing_clips,
        "frigate_missing_behavior": settings.maintenance.frigate_missing_behavior,
        "auto_purge_missing_clips": settings.maintenance.auto_purge_missing_clips,
        "auto_purge_missing_snapshots": settings.maintenance.auto_purge_missing_snapshots,
        "media_integrity_scan_enabled": settings.maintenance.media_integrity_scan_enabled,
        "media_integrity_scan_media": settings.maintenance.media_integrity_scan_media,
        "media_integrity_scan_interval_hours": settings.maintenance.media_integrity_scan_interval_hours,
        "media_integrity_scan_batch_size": settings.maintenance.media_integrity_scan_batch_size,
        "auto_analyze_unknowns": settings.maintenance.auto_analyze_unknowns,
        "blocked_labels": settings.classification.blocked_labels,
        "blocked_species": settings.classification.blocked_species,
        "trust_frigate_sublabel": settings.classification.trust_frigate_sublabel,
        "write_frigate_sublabel": settings.classification.write_frigate_sublabel,
        "display_common_names": settings.classification.display_common_names,
        "scientific_name_primary": settings.classification.scientific_name_primary,
        "personalized_rerank_enabled": settings.classification.personalized_rerank_enabled,
        "range_filter_enabled": settings.classification.range_filter_enabled,
        "range_filter_region_level": settings.classification.range_filter_region_level,
        "auto_video_classification": settings.classification.auto_video_classification,
        "video_classification_delay": settings.classification.video_classification_delay,
        "video_classification_max_retries": settings.classification.video_classification_max_retries,
        "video_classification_frames": settings.classification.video_classification_frames,
        "image_execution_mode": settings.classification.image_execution_mode,
        "strict_non_finite_output": settings.classification.strict_non_finite_output,
        "inference_provider": settings.classification.inference_provider,
        "bird_crop_detector_tier": settings.classification.bird_crop_detector_tier,
        "bird_crop_accurate_detector": settings.classification.bird_crop_accurate_detector,
        "bird_crop_inference_provider": settings.classification.bird_crop_inference_provider,
        "bird_crop_source_priority": settings.classification.bird_crop_source_priority,
        "bird_model_region_override": settings.classification.bird_model_region_override,
        "crop_model_overrides": settings.classification.crop_model_overrides,
        "crop_source_overrides": settings.classification.crop_source_overrides,
        "video_classification_circuit_open": circuit_status.get("open", False),
        "video_classification_circuit_until": circuit_status.get("open_until"),
        "video_classification_circuit_failures": circuit_status.get("failure_count", 0),
        "video_classification_maintenance_circuit_open": maintenance_circuit_status.get("open", False),
        "video_classification_maintenance_circuit_until": maintenance_circuit_status.get("open_until"),
        "video_classification_maintenance_circuit_failures": maintenance_circuit_status.get("failure_count", 0),
        # Media cache settings
        "media_cache_clips": settings.media_cache.cache_clips,
        "media_cache_high_quality_event_snapshots": settings.media_cache.high_quality_event_snapshots,
        "media_cache_high_quality_event_snapshot_bird_crop": settings.media_cache.high_quality_event_snapshot_bird_crop,
        "media_cache_high_quality_event_snapshot_jpeg_quality": settings.media_cache.high_quality_event_snapshot_jpeg_quality,
        "media_cache_retention_days": settings.media_cache.retention_days,
        "media_cache_per_species_maximum": settings.media_cache.per_species_maximum,
        "media_cache_max_size_mb": settings.media_cache.max_size_mb,
        "media_cache_automatic_multi_bird_scan": settings.media_cache.automatic_multi_bird_scan,
        "media_cache_bird_scan_mode": settings.media_cache.bird_scan_mode,
        "media_cache_per_species_minimum": settings.media_cache.per_species_minimum,
        # Location settings
        "location_latitude": settings.location.latitude,
        "location_longitude": settings.location.longitude,
        "location_state": settings.location.state,
        "location_country": settings.location.country,
        "location_automatic": settings.location.automatic,
        "location_weather_unit_system": settings.location.weather_unit_system,
        "location_temperature_unit": settings.location.temperature_unit,
        # BirdWeather settings
        "birdweather_enabled": settings.birdweather.enabled,
        # SECURITY: Never expose station tokens via API
        "birdweather_station_token": "***REDACTED***" if settings.birdweather.station_token else None,
        # Home Assistant weather source (#277)
        "ha_weather_enabled": settings.ha_weather.enabled,
        "ha_weather_base_url": settings.ha_weather.base_url,
        "ha_weather_access_token": "***REDACTED***" if settings.ha_weather.access_token else None,
        "ha_weather_entity": settings.ha_weather.weather_entity,
        "ha_weather_temperature_entity": settings.ha_weather.temperature_entity,
        "ha_weather_wind_speed_entity": settings.ha_weather.wind_speed_entity,
        "ha_weather_wind_direction_entity": settings.ha_weather.wind_direction_entity,
        "ha_weather_cloud_cover_entity": settings.ha_weather.cloud_cover_entity,
        "ha_weather_precipitation_entity": settings.ha_weather.precipitation_entity,
        "ha_weather_rain_entity": settings.ha_weather.rain_entity,
        "ha_weather_snowfall_entity": settings.ha_weather.snowfall_entity,
        # eBird settings
        "ebird_enabled": ebird_active,
        "ebird_api_key": "***REDACTED***" if settings.ebird.api_key else None,
        "ebird_default_radius_km": settings.ebird.default_radius_km,
        "ebird_default_days_back": settings.ebird.default_days_back,
        "ebird_max_results": settings.ebird.max_results,
        "ebird_locale": settings.ebird.locale,
        # iNaturalist settings
        "inaturalist_enabled": settings.inaturalist.enabled,
        "inaturalist_client_id": "***REDACTED***" if settings.inaturalist.client_id else None,
        "inaturalist_client_secret": "***REDACTED***" if settings.inaturalist.client_secret else None,
        "inaturalist_default_latitude": settings.inaturalist.default_latitude,
        "inaturalist_default_longitude": settings.inaturalist.default_longitude,
        "inaturalist_default_place_guess": settings.inaturalist.default_place_guess,
        "inaturalist_connected_user": inat_user,
        # Enrichment settings
        "enrichment_mode": effective_enrichment["mode"],
        "enrichment_single_provider": effective_enrichment["single_provider"],
        "enrichment_summary_source": effective_enrichment["summary_source"],
        "enrichment_taxonomy_source": effective_enrichment["taxonomy_source"],
        "enrichment_sightings_source": effective_enrichment["sightings_source"],
        "enrichment_seasonality_source": effective_enrichment["seasonality_source"],
        "enrichment_rarity_source": effective_enrichment["rarity_source"],
        "enrichment_links_sources": effective_enrichment["links_sources"],
        # LLM settings
        "llm_enabled": settings.llm.enabled,
        "llm_ready": settings.llm.enabled and bool(settings.llm.api_key),
        "llm_provider": settings.llm.provider,
        # SECURITY: Never expose API keys via API
        "llm_api_key": "***REDACTED***" if settings.llm.api_key else None,
        "llm_model": settings.llm.model,
        "llm_analysis_prompt_template": settings.llm.analysis_prompt_template,
        "llm_conversation_prompt_template": settings.llm.conversation_prompt_template,
        "llm_chart_prompt_template": settings.llm.chart_prompt_template,
        "ai_pricing_json": settings.classification.ai_pricing_json,
        # Telemetry
        "telemetry_enabled": settings.telemetry.enabled,
        "telemetry_health_enabled": settings.telemetry.health_enabled,
        "telemetry_installation_id": settings.telemetry.installation_id,
        "telemetry_platform": f"{platform.system()} {platform.machine()}",
        "telemetry_payload_preview": collect_runtime_telemetry_payload(),
        # Notifications
        "notifications_discord_enabled": settings.notifications.discord.enabled,
        "notifications_discord_webhook_url": "***REDACTED***" if settings.notifications.discord.webhook_url else None,
        "notifications_discord_username": settings.notifications.discord.username,
        "notifications_pushover_enabled": settings.notifications.pushover.enabled,
        "notifications_pushover_user_key": "***REDACTED***" if settings.notifications.pushover.user_key else None,
        "notifications_pushover_api_token": "***REDACTED***" if settings.notifications.pushover.api_token else None,
        "notifications_pushover_priority": settings.notifications.pushover.priority,
        "notifications_pushover_device": settings.notifications.pushover.device,
        "notifications_telegram_enabled": settings.notifications.telegram.enabled,
        "notifications_telegram_bot_token": "***REDACTED***" if settings.notifications.telegram.bot_token else None,
        "notifications_telegram_chat_id": "***REDACTED***" if settings.notifications.telegram.chat_id else None,
        "notifications_email_enabled": settings.notifications.email.enabled,
        "notifications_email_only_on_end": settings.notifications.email.only_on_end,
        "notifications_email_use_oauth": settings.notifications.email.use_oauth,
        "notifications_email_oauth_provider": connected_provider,
        "notifications_email_connected_email": connected_email,
        "notifications_email_gmail_client_id": settings.notifications.email.gmail_client_id,
        "notifications_email_gmail_client_secret": "***REDACTED***"
        if settings.notifications.email.gmail_client_secret
        else None,
        "notifications_email_outlook_client_id": settings.notifications.email.outlook_client_id,
        "notifications_email_outlook_client_secret": "***REDACTED***"
        if settings.notifications.email.outlook_client_secret
        else None,
        "notifications_email_smtp_host": settings.notifications.email.smtp_host,
        "notifications_email_smtp_port": settings.notifications.email.smtp_port,
        "notifications_email_smtp_username": settings.notifications.email.smtp_username,
        "notifications_email_smtp_password": "***REDACTED***" if settings.notifications.email.smtp_password else None,
        "notifications_email_smtp_use_tls": settings.notifications.email.smtp_use_tls,
        "notifications_email_from_email": settings.notifications.email.from_email,
        "notifications_email_to_email": settings.notifications.email.to_email,
        "notifications_email_include_snapshot": settings.notifications.email.include_snapshot,
        "notifications_email_dashboard_url": settings.notifications.email.dashboard_url,
        "notifications_instance_url": instance_base(settings.notifications),
        "notifications_link_target": settings.notifications.link_target,
        "notifications_filter_species_whitelist": settings.notifications.filters.species_whitelist,
        "notifications_filter_species_mode": settings.notifications.filters.species_mode,
        "notifications_filter_species_whitelist_structured": settings.notifications.filters.species_whitelist_structured,
        "notifications_filter_species_blacklist_structured": settings.notifications.filters.species_blacklist_structured,
        "notifications_filter_min_confidence": settings.notifications.filters.min_confidence,
        "notifications_filter_audio_confirmed_only": settings.notifications.filters.audio_confirmed_only,
        "notification_language": settings.notifications.notification_language,
        "notifications_mode": settings.notifications.mode,
        "notifications_notify_on_insert": settings.notifications.notify_on_insert,
        "notifications_notify_on_update": settings.notifications.notify_on_update,
        "notifications_delay_until_video": settings.notifications.delay_until_video,
        "notifications_video_fallback_timeout": settings.notifications.video_fallback_timeout,
        "notifications_notification_cooldown_minutes": settings.notifications.notification_cooldown_minutes,
        # Accessibility
        "accessibility_high_contrast": settings.accessibility.high_contrast,
        "accessibility_dyslexia_font": settings.accessibility.dyslexia_font,
        "accessibility_reduced_motion": settings.accessibility.reduced_motion,
        "accessibility_live_announcements": settings.accessibility.live_announcements,
        # Appearance
        "appearance_explorer_view": settings.appearance.explorer_view,
        "appearance_font_theme": settings.appearance.font_theme,
        "appearance_color_theme": settings.appearance.color_theme,
        # Authentication
        "auth_enabled": settings.auth.enabled,
        "auth_username": settings.auth.username,
        "auth_has_password": settings.auth.password_hash is not None,
        "auth_session_expiry_hours": settings.auth.session_expiry_hours,
        "trusted_proxy_hosts": settings.system.trusted_proxy_hosts,
        "debug_ui_enabled": settings.system.debug_ui_enabled,
        "beta_garden_animals": settings.system.beta_garden_animals,
        "update_check_enabled": settings.system.update_check_enabled,
        # Public access
        "public_access_enabled": settings.public_access.enabled,
        "public_access_show_camera_names": settings.public_access.show_camera_names,
        "public_access_show_ai_conversation": settings.public_access.show_ai_conversation,
        "public_access_allow_clip_downloads": settings.public_access.allow_clip_downloads,
        "public_access_show_audio": settings.public_access.show_audio,
        "public_access_show_snapshots": settings.public_access.show_snapshots,
        "public_access_show_clips": settings.public_access.show_clips,
        "public_access_location_precision": settings.public_access.location_precision,
        "public_access_historical_days_mode": settings.public_access.historical_days_mode,
        "public_access_historical_days": settings.public_access.show_historical_days,
        "public_access_media_days_mode": settings.public_access.media_days_mode,
        "public_access_media_historical_days": settings.public_access.media_historical_days,
        "public_access_rate_limit_per_minute": settings.public_access.rate_limit_per_minute,
        "public_access_external_base_url": settings.public_access.external_base_url,
        "species_info_source": settings.species_info_source,
        "date_format": settings.date_format,
        "time_format": settings.time_format,
    }


@router.post("/settings", response_model=SettingsUpdateResponse)
async def update_settings(
    update: SettingsUpdate, background_tasks: BackgroundTasks, auth: AuthContext = Depends(require_owner)
) -> SettingsUpdateResponse:
    """Update application settings. Owner only."""

    async def write() -> SettingsUpdateResponse:
        return await _update_settings(update, background_tasks, auth)

    return await run_settings_writer(write)


async def _update_settings(
    update: SettingsUpdate, background_tasks: BackgroundTasks, auth: AuthContext
) -> SettingsUpdateResponse:
    previous_classifier_location = (settings.location.latitude, settings.location.longitude)
    previous_finder = (
        settings.classification.bird_crop_accurate_detector,
        settings.classification.bird_crop_inference_provider,
    )
    telemetry_was_enabled = settings.telemetry.enabled or settings.telemetry.health_enabled
    telemetry_installation_id = settings.telemetry.installation_id
    prepared = prepare_update(settings, update, auth.username)
    await apply_update(settings, prepared.candidate)
    for message, fields in prepared.audit_events:
        log.info(message, **fields)
    fields_set = update.model_fields_set
    execution_mode_changed = prepared.execution_mode_changed
    if settings.telemetry.enabled:
        background_tasks.add_task(telemetry_service.force_heartbeat)
    if settings.telemetry.health_enabled:
        background_tasks.add_task(telemetry_service.force_health_report)
    if (
        telemetry_was_enabled
        and not settings.telemetry.enabled
        and not settings.telemetry.health_enabled
        and telemetry_installation_id
    ):
        background_tasks.add_task(telemetry_service.forget_installation, telemetry_installation_id)

    if prepared.ebird_naming_changed:
        from app.services.localized_names import start_background_refresh

        background_tasks.add_task(start_background_refresh)

    # The filter, the region level, the location or the eBird key may have changed;
    # a list for a different place or level is fetched in the background, never here.
    from app.services.range_filter_service import range_filter_service

    background_tasks.add_task(range_filter_service.settings_changed)

    if (
        prepared.inference_provider_changed
        or execution_mode_changed
        or previous_finder
        != (settings.classification.bird_crop_accurate_detector, settings.classification.bird_crop_inference_provider)
        or previous_classifier_location != (settings.location.latitude, settings.location.longitude)
    ):
        from app.services.classifier_service import reload_classifier_out_of_band

        async def full_reload():
            if execution_mode_changed:
                log.info("Execution mode changed, performing full classifier service restart")
            await reload_classifier_out_of_band(full_restart=execution_mode_changed)

        background_tasks.add_task(full_reload)

    try:
        from app.services.broadcaster import broadcaster

        await broadcaster.broadcast(
            {
                "type": "settings_updated",
                "data": {
                    "changed_fields": sorted(list(fields_set)),
                    "updated_by": auth.username,
                },
            }
        )
    except Exception as e:
        log.warning("Failed to broadcast settings_updated event", error=str(e))
    return SettingsUpdateResponse(status="updated")


@router.get("/maintenance/stats", response_model=MaintenanceStatsResponse)
async def get_maintenance_stats(
    retention_days: Optional[int] = Query(
        None,
        ge=0,
        # A century; far larger windows overflow the cutoff date arithmetic.
        le=36500,
        description="Preview how many detections this retention window would delete. Read-only.",
    ),
    auth: AuthContext = Depends(require_owner),
):
    """Get database maintenance statistics. Owner only."""
    species_floor = settings.media_cache.per_species_minimum

    async def count_due(repo: DetectionRepository, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return await repo.count_older_than(cutoff, preserve_favorites=True, species_floor=species_floor)

    async with get_db() as db:
        repo = DetectionRepository(db)
        total_count = await repo.get_count()
        oldest_date = await repo.get_oldest_detection_date()
        to_delete = await count_due(repo, settings.maintenance.retention_days)
        preview_to_delete = await count_due(repo, retention_days) if retention_days is not None else None

        return {
            "total_detections": total_count,
            "oldest_detection": oldest_date.isoformat() if oldest_date else None,
            "retention_days": settings.maintenance.retention_days,
            "detections_to_cleanup": to_delete,
            "kept_newest_per_species": species_floor,
            "automatic_cleanup": settings.maintenance.cleanup_enabled,
            "preview_retention_days": retention_days,
            "preview_detections_to_cleanup": preview_to_delete,
        }


@router.get("/maintenance/timezone-repair/preview", response_model=TimezoneRepairPreviewResponse)
async def preview_timezone_repair(auth: AuthContext = Depends(require_owner)):
    """Preview legacy detection timestamp repairs validated against Frigate. Owner only."""
    holder_id = _maintenance_holder_id("timezone_repair_preview")
    acquired = await maintenance_coordinator.try_acquire(holder_id, kind="timezone_repair")
    if not acquired:
        raise HTTPException(status_code=409, detail=_maintenance_busy_message())
    try:
        return await timezone_repair_service.preview()
    finally:
        await maintenance_coordinator.release(holder_id)


@router.post("/maintenance/timezone-repair/apply", response_model=TimezoneRepairApplyResponse)
async def apply_timezone_repair(
    request: TimezoneRepairApplyRequest,
    auth: AuthContext = Depends(require_owner),
):
    """Apply legacy detection timestamp repairs validated against Frigate. Owner only."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Timezone repair requires explicit confirmation.")
    holder_id = _maintenance_holder_id("timezone_repair_apply")
    acquired = await maintenance_coordinator.try_acquire(holder_id, kind="timezone_repair")
    if not acquired:
        raise HTTPException(status_code=409, detail=_maintenance_busy_message())
    try:
        return await timezone_repair_service.apply(confirm=True)
    finally:
        await maintenance_coordinator.release(holder_id)


@router.post("/maintenance/cleanup", response_model=CleanupResponse)
async def run_cleanup(auth: AuthContext = Depends(require_owner)):
    """Manually trigger cleanup of old detections. Owner only."""
    if settings.maintenance.retention_days <= 0:
        return {"status": "skipped", "message": "Retention is set to unlimited (0 days)", "deleted_count": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.maintenance.retention_days)

    async with get_db() as db:
        repo = DetectionRepository(db)
        deleted_count = await repo.delete_older_than(
            cutoff, preserve_favorites=True, species_floor=settings.media_cache.per_species_minimum
        )
        # The same pass the scheduled cleanup runs: "Purge Old Records" is documented as running
        # it now, and old BirdNET-Go audio used to survive until the next automatic run.
        audio_deleted_count = await repo.delete_audio_detections_older_than(cutoff)

    log.info(
        "Manual cleanup completed",
        deleted_count=deleted_count,
        audio_deleted_count=audio_deleted_count,
        cutoff=cutoff.isoformat(),
    )

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "audio_deleted_count": audio_deleted_count,
        "cutoff_date": cutoff.isoformat(),
    }


@router.post("/maintenance/favorites/clear", response_model=CleanupResponse)
async def clear_favorites(auth: AuthContext = Depends(require_owner)):
    """Remove all favorite markers from detections. Owner only."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        deleted_count = await repo.clear_all_favorites()

    from app.services.archive_service import archive_service

    await archive_service.remove_all()
    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "message": "All favorites removed" if deleted_count > 0 else "No favorites to remove",
    }


def _busy_purge_response() -> dict:
    """The shape a purge endpoint returns when a scan is already running."""
    return {
        "status": "busy",
        "deleted_count": 0,
        "marked_missing_count": 0,
        "kept_count": 0,
        "cleared_missing_count": 0,
        "checked": 0,
        "missing": 0,
        "message": "A media integrity scan is already running.",
    }


async def _purge_missing_media(kind: Literal["clip", "snapshot"]) -> dict:
    if kind == "clip" and not settings.frigate.clips_enabled:
        return {
            "status": "skipped",
            "deleted_count": 0,
            "marked_missing_count": 0,
            "kept_count": 0,
            "cleared_missing_count": 0,
            "checked": 0,
            "missing": 0,
            "message": "Clip fetching is disabled in settings.",
        }

    async with get_db() as db:
        repo = DetectionRepository(db)
        event_ids = await repo.get_all_frigate_event_ids()

    if not event_ids:
        return {
            "status": "completed",
            "deleted_count": 0,
            "marked_missing_count": 0,
            "kept_count": 0,
            "cleared_missing_count": 0,
            "checked": 0,
            "missing": 0,
            "message": "No detections found",
        }

    # Check Frigate availability before performing mass purge.
    try:
        version = await frigate_client.get_version()
    except Exception:
        version = None
    if not version:
        return {
            "status": "failed",
            "deleted_count": 0,
            "marked_missing_count": 0,
            "kept_count": 0,
            "cleared_missing_count": 0,
            "checked": 0,
            "missing": 0,
            "message": "Frigate is not reachable. Aborting purge.",
        }

    semaphore = asyncio.Semaphore(PURGE_CHECK_CONCURRENCY)

    async def check(event_id: str) -> tuple[str, bool | None, str | None]:
        async with semaphore:
            try:
                event_data, error = await frigate_client.get_event_with_error(event_id)
            except Exception:
                return event_id, None, "event_request_error"
            missing, reason = evaluate_media_presence(
                event_data, error, media=kind, clips_enabled=settings.frigate.clips_enabled
            )
            return event_id, missing, reason

    results = await asyncio.gather(*(check(event_id) for event_id in event_ids))
    missing_count = sum(1 for _event_id, missing, _error in results if missing)
    deleted_count = 0
    marked_missing_count = 0
    kept_count = 0
    cleared_missing_count = 0
    async with get_db() as db:
        repo = DetectionRepository(db)
        for event_id, missing, error in results:
            if missing is None:
                continue
            if missing:
                counts = await apply_missing_policy(
                    repo=repo,
                    frigate_event=event_id,
                    error=error or f"{kind}_unavailable",
                    source="maintenance_scan",
                    media_kind=kind,
                )
                deleted_count += counts["deleted_count"]
                marked_missing_count += counts["marked_missing_count"]
                kept_count += counts["kept_count"]
                continue
            if await clear_missing_state_if_present(
                repo=repo,
                frigate_event=event_id,
                source="maintenance_scan",
                media_kind=kind,
            ):
                cleared_missing_count += 1

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "marked_missing_count": marked_missing_count,
        "kept_count": kept_count,
        "cleared_missing_count": cleared_missing_count,
        "checked": len(event_ids),
        "missing": missing_count,
        "errors": sum(missing is None for _event_id, missing, _error in results),
    }


async def _purge_missing_all_media() -> dict:
    async with get_db() as db:
        repo = DetectionRepository(db)
        event_ids = await repo.get_all_frigate_event_ids()

    if not event_ids:
        return {
            "status": "completed",
            "deleted_count": 0,
            "marked_missing_count": 0,
            "kept_count": 0,
            "cleared_missing_count": 0,
            "checked": 0,
            "missing": 0,
            "message": "No detections found",
        }

    try:
        version = await frigate_client.get_version()
    except Exception:
        version = None
    if not version:
        return {
            "status": "failed",
            "deleted_count": 0,
            "marked_missing_count": 0,
            "kept_count": 0,
            "cleared_missing_count": 0,
            "checked": 0,
            "missing": 0,
            "message": "Frigate is not reachable. Aborting purge.",
        }

    semaphore = asyncio.Semaphore(PURGE_CHECK_CONCURRENCY)

    async def check(event_id: str) -> tuple[str, bool | None, str | None]:
        async with semaphore:
            try:
                event_data, error = await frigate_client.get_event_with_error(event_id)
            except Exception:
                return event_id, None, "event_request_error"
            missing, reason = evaluate_media_presence(
                event_data, error, media="any", clips_enabled=settings.frigate.clips_enabled
            )
            return event_id, missing, reason

    results = await asyncio.gather(*(check(event_id) for event_id in event_ids))
    missing_count = sum(1 for _event_id, missing, _error in results if missing)
    deleted_count = 0
    marked_missing_count = 0
    kept_count = 0
    cleared_missing_count = 0

    async with get_db() as db:
        repo = DetectionRepository(db)
        for event_id, missing, error in results:
            if missing is None:
                continue
            if missing:
                counts = await apply_missing_policy(
                    repo=repo,
                    frigate_event=event_id,
                    error=error or "media_unavailable",
                    source="maintenance_scan",
                    media_kind="media",
                )
                deleted_count += counts["deleted_count"]
                marked_missing_count += counts["marked_missing_count"]
                kept_count += counts["kept_count"]
                continue
            if await clear_missing_state_if_present(
                repo=repo,
                frigate_event=event_id,
                source="maintenance_scan",
                media_kind="media",
            ):
                cleared_missing_count += 1

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "marked_missing_count": marked_missing_count,
        "kept_count": kept_count,
        "cleared_missing_count": cleared_missing_count,
        "checked": len(event_ids),
        "missing": missing_count,
        "errors": sum(missing is None for _event_id, missing, _error in results),
    }


def _get_camera_retention_days(frigate_config: object, camera_name: str) -> float | None:
    return get_camera_retention_days(frigate_config, camera_name)


async def _run_guarded_media_scan(runner) -> dict:
    """Run a manual scan under the scheduled scan's maintenance slot.

    They walk the same detections and ask the same Frigate. Running both at once
    doubles the request rate against it and puts two writers on one row, so
    whichever asks second is told the scan is already running.
    """
    holder_id = "manual_media_integrity_scan"
    if not await maintenance_coordinator.try_acquire(holder_id, kind=MEDIA_INTEGRITY_SCAN_KIND):
        return _busy_purge_response()
    try:
        return await runner()
    finally:
        await maintenance_coordinator.release(holder_id)


@router.post("/maintenance/purge-missing-clips", response_model=PurgeMissingMediaResponse)
async def purge_missing_clips(auth: AuthContext = Depends(require_owner)):
    """Remove detections without clips (or missing events). Owner only."""
    result = await _run_guarded_media_scan(lambda: _purge_missing_media("clip"))
    log.info("Purge missing clips completed", **result)
    return result


@router.post("/maintenance/purge-missing-media", response_model=PurgeMissingMediaResponse)
async def purge_missing_media(auth: AuthContext = Depends(require_owner)):
    """Apply the configured missing-media policy when any Frigate event/media is missing. Owner only."""
    result = await _run_guarded_media_scan(_purge_missing_all_media)
    log.info("Purge missing media completed", **result)
    return result


@router.post("/maintenance/purge-missing-snapshots", response_model=PurgeMissingMediaResponse)
async def purge_missing_snapshots(auth: AuthContext = Depends(require_owner)):
    """Remove detections without snapshots (or missing events). Owner only."""
    result = await _run_guarded_media_scan(lambda: _purge_missing_media("snapshot"))
    log.info("Purge missing snapshots completed", **result)
    return result


async def _run_analyze_unknowns() -> dict:
    """Core logic for analyzing unknown detections. Used by endpoint and scheduler."""
    guard = _maintenance_guardrail_status()
    pending_maintenance = int(guard.get("pending_maintenance") or 0)
    active_maintenance = int(guard.get("active_maintenance") or 0)
    if pending_maintenance > 0 or active_maintenance > 0:
        return {
            "status": "deferred",
            "count": pending_maintenance + active_maintenance,
            "accepted": 0,
            "skipped_duplicate": 0,
            "dropped_full": 0,
            "skipped_no_clip": 0,
            "skipped_missing_event": 0,
            "skipped_outside_retention": 0,
            "precheck_errors": 0,
            "total_candidates": 0,
            "remaining_candidates": 0,
            "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
            "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
            "scan_truncated": False,
            "pending_maintenance": pending_maintenance,
            "active_maintenance": active_maintenance,
            "retry_after_seconds": BATCH_ANALYSIS_RETRY_AFTER_SECONDS,
            "message": f"{_maintenance_busy_message(guard)} Batch analysis deferred until queued maintenance work drains.",
        }

    holder_id = "analyze_unknowns"
    acquired = await maintenance_coordinator.try_acquire(holder_id, kind="analyze_unknowns")
    if not acquired:
        status = await maintenance_coordinator.get_status()
        active_total = int(status.get("active_total") or 0)
        return {
            "status": "in_progress",
            "count": active_total,
            "accepted": 0,
            "skipped_duplicate": 0,
            "dropped_full": 0,
            "skipped_no_clip": 0,
            "skipped_missing_event": 0,
            "skipped_outside_retention": 0,
            "precheck_errors": 0,
            "total_candidates": 0,
            "remaining_candidates": 0,
            "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
            "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
            "scan_truncated": False,
            "pending_maintenance": pending_maintenance,
            "active_maintenance": active_maintenance,
            "retry_after_seconds": BATCH_ANALYSIS_RETRY_AFTER_SECONDS,
            "message": "Maintenance work is already in progress. Batch analysis is already in progress.",
        }
    accepted = 0
    skipped_duplicate = 0
    dropped_full = 0
    skipped_no_clip = 0
    skipped_missing_event = 0
    skipped_outside_retention = 0
    precheck_errors = 0
    total_candidates = 0
    processed_candidates = 0
    precheck_outage = False
    try:
        frigate_cfg = await frigate_client.get_config()
        if frigate_cfg is None:
            log.info("Batch analysis deferred until Frigate config is available")
            return {
                "status": "deferred",
                "reason": "frigate_unavailable",
                "count": 0,
                "accepted": 0,
                "skipped_duplicate": 0,
                "dropped_full": 0,
                "skipped_no_clip": 0,
                "skipped_missing_event": 0,
                "skipped_outside_retention": 0,
                "precheck_errors": 0,
                "total_candidates": 0,
                "remaining_candidates": 0,
                "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
                "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
                "scan_truncated": False,
                "pending_maintenance": pending_maintenance,
                "active_maintenance": active_maintenance,
                "retry_after_seconds": BATCH_ANALYSIS_RETRY_AFTER_SECONDS,
                "message": "Frigate is unavailable. Batch analysis will retry after it is ready.",
            }

        # Read the candidates, then let the connection go. The pre-check calls
        # Frigate once per detection, in rounds, and the whole loop can run for
        # minutes on a large backlog. The writes re-acquire, one round at a time.
        async with get_db() as db:
            unknowns = await DetectionRepository(db).get_unknown_detections(limit=BATCH_ANALYSIS_MAX_SCAN_PER_RUN)
            total_candidates = len(unknowns)
            scan_truncated = total_candidates >= BATCH_ANALYSIS_MAX_SCAN_PER_RUN

        log.info(
            "Batch analysis triggered",
            total_unknowns=total_candidates,
            queue_limit=BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
            scan_limit=BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
            scan_truncated=scan_truncated,
        )

        # Pre-check availability before queueing to avoid failure storms when
        # detections are older than Frigate media retention or clips are missing.
        retention_by_camera: dict[str, int | None] = {}
        for d in unknowns:
            if d.camera_name not in retention_by_camera:
                retention_by_camera[d.camera_name] = _get_camera_retention_days(frigate_cfg, d.camera_name)

        now = datetime.now()
        semaphore = asyncio.Semaphore(BATCH_ANALYSIS_CHECK_CONCURRENCY)

        async def precheck_detection(detection):
            retention_days = retention_by_camera.get(detection.camera_name)
            if retention_days is not None:
                cutoff = now - timedelta(days=retention_days)
                if detection.detection_time < cutoff:
                    return ("outside_retention", detection)

            async with semaphore:
                event_data, event_error = await frigate_client.get_event_with_error(
                    detection.frigate_event, timeout=8.0
                )

            if not event_data:
                if event_error == "event_not_found":
                    return ("missing_event", detection)
                # Transient precheck issues should not suppress classification;
                # keep these in the queue path and let worker retries handle it.
                return ("precheck_error", detection)

            if not bool(event_data.get("has_clip", False)):
                return ("no_clip", detection)

            return ("eligible", detection)

        for offset in range(0, len(unknowns), BATCH_ANALYSIS_CHECK_CONCURRENCY):
            if accepted >= BATCH_ANALYSIS_MAX_QUEUE_PER_RUN:
                break
            batch = unknowns[offset : offset + BATCH_ANALYSIS_CHECK_CONCURRENCY]
            prechecked = await asyncio.gather(*(precheck_detection(d) for d in batch))
            if all(state == "precheck_error" for state, _ in prechecked):
                precheck_errors += len(batch)
                processed_candidates += len(batch)
                precheck_outage = True
                log.warning("Batch analysis deferred after Frigate precheck outage", checked=len(batch))
                break

            async with get_db() as db:
                repo = DetectionRepository(db)
                for state, d in prechecked:
                    processed_candidates += 1
                    if state == "outside_retention":
                        skipped_outside_retention += 1
                        await repo.update_video_status(d.frigate_event, "failed", error="frigate_retention_expired")
                        continue
                    if state == "missing_event":
                        skipped_missing_event += 1
                        await repo.update_video_status(d.frigate_event, "failed", error="event_not_found")
                        continue
                    if state == "no_clip":
                        skipped_no_clip += 1
                        await repo.update_video_status(d.frigate_event, "failed", error="clip_not_retained")
                        continue
                    if state == "precheck_error":
                        precheck_errors += 1
                        continue

                    result = await auto_video_classifier.queue_classification(
                        d.frigate_event,
                        d.camera_name,
                        fallback_to_snapshot=True,
                        source="maintenance",
                    )
                    if result in {"queued", "deferred"}:
                        accepted += 1
                        if accepted >= BATCH_ANALYSIS_MAX_QUEUE_PER_RUN:
                            break
                    elif result == "duplicate":
                        skipped_duplicate += 1
                    elif result == "full":
                        dropped_full += 1
                        break
            if dropped_full > 0:
                break
    finally:
        await maintenance_coordinator.release(holder_id)

    count = accepted  # Backward-compatible field expected by current UI.
    remaining_candidates = max(0, total_candidates - processed_candidates + precheck_errors)
    msg = (
        f"Queued {accepted} unknown detections for video analysis "
        f"(batch limit {BATCH_ANALYSIS_MAX_QUEUE_PER_RUN}, scanned {processed_candidates}/{total_candidates}, "
        f"scan limit {BATCH_ANALYSIS_MAX_SCAN_PER_RUN}, remaining scanned candidates {remaining_candidates}). "
        f"Skipped duplicates: {skipped_duplicate}. "
        f"Queue full drops: {dropped_full}. "
        f"Skipped no clip: {skipped_no_clip}. "
        f"Skipped missing event: {skipped_missing_event}. "
        f"Skipped outside retention: {skipped_outside_retention}. "
        f"Transient precheck errors deferred: {precheck_errors}."
    )
    if precheck_outage:
        msg = (
            f"Frigate event prechecks are unavailable. Batch analysis deferred after checking "
            f"{processed_candidates} of {total_candidates} candidates; retry after "
            f"{BATCH_ANALYSIS_RETRY_AFTER_SECONDS} seconds."
        )
    log.info(
        "Batch analysis precheck summary",
        total_candidates=total_candidates,
        processed_candidates=processed_candidates,
        remaining_candidates=remaining_candidates,
        queue_limit=BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
        scan_limit=BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
        scan_truncated=scan_truncated,
        accepted=accepted,
        skipped_duplicate=skipped_duplicate,
        dropped_full=dropped_full,
        skipped_no_clip=skipped_no_clip,
        skipped_missing_event=skipped_missing_event,
        skipped_outside_retention=skipped_outside_retention,
        precheck_errors=precheck_errors,
    )
    return {
        "status": "deferred" if precheck_outage else "queued",
        **({"reason": "frigate_unavailable"} if precheck_outage else {}),
        "count": count,
        "accepted": accepted,
        "skipped_duplicate": skipped_duplicate,
        "dropped_full": dropped_full,
        "skipped_no_clip": skipped_no_clip,
        "skipped_missing_event": skipped_missing_event,
        "skipped_outside_retention": skipped_outside_retention,
        "precheck_errors": precheck_errors,
        "total_candidates": total_candidates,
        "remaining_candidates": remaining_candidates,
        "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
        "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
        "scan_truncated": scan_truncated,
        "pending_maintenance": pending_maintenance,
        "active_maintenance": active_maintenance,
        "retry_after_seconds": BATCH_ANALYSIS_RETRY_AFTER_SECONDS if remaining_candidates > 0 else 0,
        "message": msg,
    }


@router.post("/maintenance/analyze-unknowns", response_model=AnalyzeUnknownsResponse)
async def analyze_unknowns(auth: AuthContext = Depends(require_owner)):
    """Queue video analysis for all 'Unknown Bird' detections. Owner only."""
    guard = _maintenance_guardrail_status()
    if bool(guard.get("coalesce_analyze_unknowns")):
        pending_maintenance = int(guard.get("pending_maintenance") or 0)
        active_maintenance = int(guard.get("active_maintenance") or 0)
        return {
            "status": "in_progress",
            "count": pending_maintenance + active_maintenance,
            "accepted": 0,
            "skipped_duplicate": 0,
            "dropped_full": 0,
            "skipped_no_clip": 0,
            "skipped_missing_event": 0,
            "skipped_outside_retention": 0,
            "precheck_errors": 0,
            "total_candidates": 0,
            "remaining_candidates": 0,
            "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
            "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
            "scan_truncated": False,
            "pending_maintenance": pending_maintenance,
            "active_maintenance": active_maintenance,
            "retry_after_seconds": BATCH_ANALYSIS_RETRY_AFTER_SECONDS,
            "message": f"{_maintenance_busy_message(guard)} Batch analysis is already in progress.",
        }
    return await _run_analyze_unknowns()


@router.get("/maintenance/analysis/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(response: Response, auth: AuthContext = Depends(require_owner)):
    """Get status of auto video classification queue. Owner only."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return {
        **auto_video_classifier.get_status(),
        "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
        "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
    }


# =============================================================================
# Media Cache Endpoints
# =============================================================================


async def _collect_cache_stats() -> dict:
    """Collect the completed measurement outside the polling request's lifetime."""
    # Archive use comes from the favourite rows, which record bytes as they are written: this
    # endpoint is polled every minute by every owner page and must not walk a directory tree.
    async with get_db() as db:
        counts = await DetectionRepository(db).favorite_archive_totals()
    archive_totals = {
        "archive_count": counts["durable"],
        "archive_size_bytes": counts["bytes"],
        "archive_size_mb": round(counts["bytes"] / (1024 * 1024), 2),
        "archive_favorites": counts["favorites"],
        "archive_durable": counts["durable"],
        "archive_pending": counts["pending"],
        "archive_failed": counts["failed"],
        "archive_unavailable": counts["unavailable"],
    }
    stats = await media_cache.get_cache_stats()

    # Add retention info
    retention = settings.media_cache.retention_days
    if retention == 0:
        retention = settings.maintenance.retention_days

    return {
        **stats,
        "storage_available": media_cache.available,
        "cache_clips": settings.media_cache.cache_clips,
        **archive_totals,
        "retention_days": retention,
        "retention_source": "media_cache" if settings.media_cache.retention_days > 0 else "detection",
    }


cache_stats_measurements = CacheStatsMeasurements(_collect_cache_stats)


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(auth: AuthContext = Depends(require_owner)):
    """Get media cache statistics. Owner only; waits for the filesystem walk."""
    return await _collect_cache_stats()


@router.get("/cache/measurement", response_model=CacheStatsMeasurementResponse)
async def get_cache_measurement(
    response: Response,
    measurement_id: Optional[str] = Query(None, max_length=36),
    auth: AuthContext = Depends(require_owner),
) -> dict:
    """Start or poll a shared storage measurement without waiting for the walk."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return cache_stats_measurements.get(measurement_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Storage measurement expired. Start a new measurement.") from None


@router.post("/cache/cleanup", response_model=CacheCleanupResponse)
async def run_cache_cleanup(auth: AuthContext = Depends(require_owner)):
    """Manually trigger cleanup of old cached media. Owner only."""
    # Determine retention period
    retention = settings.media_cache.retention_days
    if retention == 0:
        retention = settings.maintenance.retention_days

    # Favorites are exempt from retention cleanup and media cleanup.
    async with get_db() as db:
        repo = DetectionRepository(db)
        protected_ids = await repo.get_favorite_frigate_event_ids()
        # The per-species floor keeps photographs only (#178); favourites keep everything.
        floor_ids = await repo.get_species_floor_frigate_event_ids(settings.media_cache.per_species_minimum)

    # Even if retention is 0, we still run cleanup to remove empty files
    stats = await media_cache.cleanup_old_media(
        retention, protected_event_ids=protected_ids, protected_snapshot_event_ids=floor_ids
    )

    # Also run orphaned media cleanup (files not in DB)
    async with get_db() as db:
        repo = DetectionRepository(db)
        valid_ids = set(await repo.get_all_frigate_event_ids())
    valid_ids.update(protected_ids)
    valid_ids.update(floor_ids)

    orphan_stats = await media_cache.cleanup_orphaned_media(valid_ids)

    # Merge stats
    stats["snapshots_deleted"] += orphan_stats["snapshots_deleted"]
    stats["clips_deleted"] += orphan_stats["clips_deleted"]
    stats["bytes_freed"] += orphan_stats["bytes_freed"]

    from app.services.media_storage_service import media_storage_service

    limit_stats = await media_storage_service.enforce_limits()
    stats["bytes_freed"] += limit_stats["bytes_freed"]
    from app.services.garden_media_cache import garden_media_cache

    await garden_media_cache.apply_retention()
    return {"status": "completed", **stats, "retention_days": retention}


@router.post("/maintenance/video-classification/reset-circuit", response_model=VideoCircuitResetResponse)
async def reset_video_circuit(
    _auth: AuthContext = Depends(require_owner),
) -> VideoCircuitResetResponse:
    """Reset the live and maintenance video classification breakers without discarding queued jobs. Owner only.

    Use this to manually recover from a false-positive open circuit caused by
    a transient Frigate outage or maintenance timeout burst. Queued and active
    jobs are preserved.
    """
    auto_video_classifier.reset_circuit()
    live_status = auto_video_classifier.get_circuit_status("live")
    maintenance_status = auto_video_classifier.get_circuit_status("maintenance")
    return VideoCircuitResetResponse(
        status="ok",
        message="Video classification circuit breakers reset.",
        live_circuit=live_status,
        maintenance_circuit=maintenance_status,
    )


@router.delete("/maintenance/feedback/clear", response_model=ClearFeedbackResponse)
async def clear_classification_feedback(background_tasks: BackgroundTasks, auth: AuthContext = Depends(require_owner)):
    """Clear all personalized re-ranking classification feedback. Owner only."""
    from app.services.classifier_service import reload_classifier_out_of_band

    async with get_db() as db:
        repo = DetectionRepository(db)
        deleted_count = await repo.clear_all_classification_feedback()

    background_tasks.add_task(reload_classifier_out_of_band, full_restart=False)

    return {
        "status": "success",
        "message": f"Cleared {deleted_count} feedback records.",
        "deleted_count": deleted_count,
    }
