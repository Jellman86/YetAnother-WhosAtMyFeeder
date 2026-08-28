from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog
import asyncio
import ipaddress
import os
import json
import re
from datetime import datetime, timedelta, timezone
import sys  # Trigger CI rebuild
from time import monotonic
from contextlib import asynccontextmanager
from typing import Awaitable, Callable
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter
from pydantic import BaseModel
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.database import (
    init_db,
    close_db,
    get_db,
    get_db_path_diagnostics,
    is_db_pool_initialized,
    get_db_pool_status,
    DatabasePoolTimeout,
)
from app.services.media_integrity_scan import (
    get_media_integrity_scan_status,
    run_media_integrity_scan,
)
from app.services.mqtt_service import mqtt_service
from app.services.classifier_service import (
    CLASSIFIER_ACCEL_PROBE_TTL_SECONDS,
    get_classifier,
    refresh_accel_caps_if_running,
    shutdown_classifier,
)
from app.services.event_processor import EventProcessor
from app.services.media_cache import media_cache
from app.services.full_visit_clip_service import full_visit_clip_service
from app.services.broadcaster import broadcaster
from app.services.telemetry_service import telemetry_service
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services.notification_dispatcher import notification_dispatcher
from app.services.frigate_client import frigate_client
from app.repositories.detection_repository import DetectionRepository
from app.repositories.health_repository import HealthRepository
from app.services.uptime import HEARTBEAT_INTERVAL_MINUTES
from app.routers import (
    events,
    proxy,
    settings as settings_router,
    species,
    backfill,
    classifier,
    models,
    ai,
    stats,
    stats_ai,
    debug,
    audio,
    email,
    inaturalist,
    ebird,
    diagnostics,
    geocoding,
    model_eval,
    setup as setup_router,
    auth as auth_router,
    jobs as jobs_router,
    manual_observations,
)
from app.config import settings, _expand_trusted_hosts
from app.middleware.language import LanguageMiddleware
from app.utils.tasks import create_background_task
from app.utils.runtime_flavor import get_image_flavor
from app.services.label_enrichment import start_background_map_refresh
from app.services.localized_names import start_background_refresh
from app.services.startup_status import startup_status
from app.ratelimit import limiter
from app.auth import AuthContext
from app.auth import get_auth_context_with_legacy


# Version management
def get_base_version() -> str:
    """Read base version from VERSION file or environment."""
    # Check environment variable first
    if os.environ.get("APP_VERSION_BASE"):
        return os.environ.get("APP_VERSION_BASE")

    version_file = os.path.join(os.path.dirname(__file__), "..", "..", "VERSION")
    try:
        with open(version_file, "r") as f:
            return f.read().strip()
    except (FileNotFoundError, IOError):
        # Fallback if VERSION file doesn't exist
        return "2.2.0"


def get_git_hash() -> str:
    """Get git commit hash from environment or by running git."""
    # First check environment variable (set during Docker build)
    git_hash = os.environ.get("GIT_HASH", "").strip()
    if git_hash:
        return git_hash

    # Try to get from git command (for development)
    try:
        import subprocess

        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return "unknown"


def get_app_branch() -> str:
    """Get app branch from environment or by running git."""
    # First check environment variable (set during Docker build)
    branch = os.environ.get("APP_BRANCH", "").strip()
    if branch:
        return branch

    # Try to get from git command (for development)
    try:
        import subprocess

        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return "unknown"


BASE_VERSION = get_base_version()
GIT_HASH = get_git_hash()

# How often the scheduler wakes to check whether hardware capabilities have
# expired, away from any request path. A wake is a monotonic comparison; a
# probe — child processes with five second timeouts — runs only once the
# reading is older than CLASSIFIER_ACCEL_PROBE_TTL_SECONDS (#313).
ACCEL_CAPS_REFRESH_SECONDS = min(60.0, CLASSIFIER_ACCEL_PROBE_TTL_SECONDS)
APP_BRANCH = get_app_branch()

# Treat semver-like tags (e.g. v2.7.9.1) as releases, not branches.
if re.fullmatch(r"v\\d+\\.\\d+\\.\\d+(?:\\.\\d+)?", APP_BRANCH or ""):
    APP_BRANCH = "main"

# Format: version-branch+hash (omit branch for release-like channels)
if APP_BRANCH and APP_BRANCH not in ["main", "stable", "unknown"]:
    APP_VERSION = f"{BASE_VERSION}-{APP_BRANCH}+{GIT_HASH}"
else:
    APP_VERSION = f"{BASE_VERSION}+{GIT_HASH}"

os.environ["APP_VERSION"] = APP_VERSION  # Make available to other services
os.environ["APP_BRANCH"] = APP_BRANCH


class VersionResponse(BaseModel):
    version: str
    base_version: str


class ReadinessResponse(BaseModel):
    ready: bool
    db_pool_initialized: bool
    startup_warnings: list[dict[str, object]]
    startup_instance_id: str
    startup_started_at: str | None


# Metrics
EVENTS_PROCESSED = Counter("events_processed_total", "Total number of events processed")
DETECTIONS_TOTAL = Counter("detections_total", "Total number of bird detections")
API_REQUESTS = Counter("api_requests_total", "Total API requests")
RATE_LIMIT_EXCEEDED = Counter("rate_limit_exceeded_total", "Total rate limit violations")


def _is_testing() -> bool:
    """
    Detect test runs (pytest sets PYTEST_CURRENT_TEST only while a test is executing).
    This must be evaluated at runtime (inside lifespan), not just at import time.
    """
    return "pytest" in sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("YA_WAMF_TESTING") == "1"


log = structlog.get_logger()
event_processor: EventProcessor | None = None

# Cleanup task control
cleanup_task = None
media_integrity_task = None
cleanup_running = True
heartbeat_task = None
accel_caps_task = None
heartbeat_running = True
CLEANUP_INTERVAL_HOURS = 24  # Run cleanup every 24 hours


async def run_cleanup():
    """Execute cleanup of old detections and media cache."""
    try:
        now = datetime.now(timezone.utc)
        favorite_event_ids: set[str] = set()

        # Detection cleanup
        if settings.maintenance.retention_days > 0 and settings.maintenance.cleanup_enabled:
            cutoff = now - timedelta(days=settings.maintenance.retention_days)
            async with get_db() as db:
                repo = DetectionRepository(db)
                favorite_event_ids = await repo.get_favorite_frigate_event_ids()
                deleted_count = await repo.delete_older_than(cutoff, preserve_favorites=True)
                deleted_audio_count = await repo.delete_audio_detections_older_than(cutoff)
            if deleted_count > 0:
                log.info(
                    "Automatic cleanup completed",
                    deleted_count=deleted_count,
                    retention_days=settings.maintenance.retention_days,
                    cutoff=cutoff.isoformat(),
                )
            if deleted_audio_count > 0:
                log.info(
                    "Automatic audio cleanup completed",
                    deleted_count=deleted_audio_count,
                    retention_days=settings.maintenance.retention_days,
                    cutoff=cutoff.isoformat(),
                )

        # Media cache cleanup
        if settings.media_cache.enabled:
            cache_retention = settings.media_cache.retention_days
            if cache_retention == 0:
                cache_retention = settings.maintenance.retention_days
            if cache_retention > 0:
                if not favorite_event_ids:
                    async with get_db() as db:
                        repo = DetectionRepository(db)
                        favorite_event_ids = await repo.get_favorite_frigate_event_ids()
                cache_stats = await media_cache.cleanup_old_media(
                    cache_retention,
                    protected_event_ids=favorite_event_ids,
                )
                if cache_stats["snapshots_deleted"] > 0 or cache_stats["clips_deleted"] > 0:
                    log.info("Media cache cleanup completed", **cache_stats)

        # Video share-link cleanup
        deleted_share_links = await proxy.cleanup_expired_video_share_links()
        if deleted_share_links > 0:
            log.info("Video share-link cleanup completed", deleted_count=deleted_share_links)

        # Scheduled analyze unknowns
        if settings.maintenance.auto_analyze_unknowns:
            try:
                from app.routers.settings import _run_analyze_unknowns

                result = await _run_analyze_unknowns()
                if result.get("accepted", 0) > 0:
                    log.info("Scheduled analyze unknowns completed", **result)
            except Exception as e:
                log.error("Scheduled analyze unknowns failed", error=str(e))

    except Exception as e:
        log.error("Error during cleanup execution", error=str(e))


async def cleanup_scheduler():
    """Background task that runs cleanup on a fixed interval."""
    global cleanup_running

    # Run cleanup once on startup (handles missed cleanups from downtime)
    log.info("Running startup cleanup...")
    await run_cleanup()

    # Then run on fixed interval
    while cleanup_running:
        try:
            # Sleep for the interval, checking for cancellation periodically
            for _ in range(CLEANUP_INTERVAL_HOURS):
                if not cleanup_running:
                    break
                await asyncio.sleep(3600)  # check every hour

            if cleanup_running:
                await run_cleanup()

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Cleanup task error", error=str(e))
            # On error, wait 1 hour before retrying
            await asyncio.sleep(3600)
        except BaseException as e:
            # Catch-all for anything else (unlikely but safe)
            log.critical("Cleanup task critical failure", error=str(e))
            await asyncio.sleep(3600)


async def media_integrity_scheduler():
    """Background task that runs the media integrity scan on its own interval.

    Deliberately sleeps before its first run rather than scanning at startup:
    the scan asks Frigate about a batch of events, and startup is when Frigate,
    the model and the migrations are already competing for the box. An owner who
    wants it now has the button in Settings.
    """
    while cleanup_running:
        try:
            # Re-read the interval every hour rather than once per cycle:
            # otherwise an owner shortening it from a week to an hour waits the
            # old week to find out whether the change worked.
            elapsed_hours = 0
            while cleanup_running:
                await asyncio.sleep(3600)
                elapsed_hours += 1
                if elapsed_hours >= max(1, int(settings.maintenance.media_integrity_scan_interval_hours)):
                    break

            if cleanup_running and settings.maintenance.media_integrity_scan_enabled:
                result = await run_media_integrity_scan()
                if result.status not in ("disabled", "nothing_to_check"):
                    log.info("Scheduled media integrity scan finished", **result.as_dict())
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Media integrity scan task error", error=str(e))
            await asyncio.sleep(3600)


def _record_startup_warning(app: FastAPI, phase: str, error: str) -> None:
    warnings = getattr(app.state, "startup_warnings", [])
    warnings.append({"phase": phase, "error": error})
    app.state.startup_warnings = warnings


async def _run_lifecycle_phase(
    app: FastAPI,
    phase: str,
    action: Callable[[], Awaitable[None]],
    fatal: bool,
    startup_phase: str | None = None,
    startup_progress: int | None = None,
) -> None:
    """Run startup/shutdown phase with explicit timing and failure context."""
    if startup_phase is not None and startup_progress is not None:
        await asyncio.to_thread(startup_status.publish, startup_phase, startup_progress)
    started_at = monotonic()
    log.info("Lifecycle phase starting", phase=phase, fatal=fatal)
    try:
        await action()
    except Exception as e:
        duration_ms = round((monotonic() - started_at) * 1000, 2)
        log.error(
            "Lifecycle phase failed",
            phase=phase,
            fatal=fatal,
            duration_ms=duration_ms,
            error=str(e),
            exc_info=True,
        )
        if fatal:
            await asyncio.to_thread(startup_status.mark_failed, startup_phase or phase)
            raise RuntimeError(f"Lifecycle phase failed: {phase}") from e
        _record_startup_warning(app, phase, str(e))
    else:
        duration_ms = round((monotonic() - started_at) * 1000, 2)
        log.info("Lifecycle phase completed", phase=phase, duration_ms=duration_ms)


def _log_startup_diagnostics(test_mode: bool) -> None:
    """Emit startup diagnostics once so permission/config issues are obvious."""
    log.info(
        "Startup diagnostics",
        test_mode=test_mode,
        app_version=APP_VERSION,
        image_flavor=get_image_flavor(),
        db=get_db_path_diagnostics(),
        media_cache=media_cache.get_status(),
        mqtt_server=settings.frigate.mqtt_server,
        telemetry_enabled=settings.telemetry.enabled,
        auto_video_classification=settings.classification.auto_video_classification,
    )


async def _start_mqtt_service_task() -> None:
    global event_processor
    if event_processor is None:
        event_processor = EventProcessor()
    create_background_task(mqtt_service.start(event_processor), name="mqtt_service_start")


async def heartbeat_scheduler(instance_id: str):
    """Record that the application is alive, on a fixed interval.

    Gaps between heartbeats are the only honest uptime signal available without an
    external monitor, so this loop is deliberately dull and failure-tolerant.
    """
    global heartbeat_running

    while heartbeat_running:
        try:
            async with get_db() as db:
                repo = HealthRepository(db)
                await repo.record_heartbeat(instance_id)
                if (
                    datetime.now(timezone.utc).hour == 4
                    and datetime.now(timezone.utc).minute < HEARTBEAT_INTERVAL_MINUTES
                ):
                    await repo.prune()
        except asyncio.CancelledError:
            break
        except Exception as e:
            # A missed heartbeat reads as a short gap, which is honest enough.
            log.warning("heartbeat_write_failed", error=str(e))

        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL_MINUTES * 60)
        except asyncio.CancelledError:
            break


async def _start_heartbeat_scheduler_task(instance_id: str) -> None:
    global heartbeat_task, accel_caps_task

    async def accel_caps_scheduler() -> None:
        """Keep hardware capabilities current away from any request.

        Detection spawns child processes that import an inference runtime. It
        used to happen inline on a status request, stalling every concurrent
        request behind it (#313).
        """
        while True:
            try:
                await refresh_accel_caps_if_running()
            except Exception as error:  # noqa: BLE001 - a probe failure must not end the loop
                log.warning("Acceleration capability refresh failed", error=str(error))
            await asyncio.sleep(ACCEL_CAPS_REFRESH_SECONDS)

    accel_caps_task = create_background_task(accel_caps_scheduler(), name="accel_caps_scheduler")
    heartbeat_task = create_background_task(heartbeat_scheduler(instance_id), name="heartbeat_scheduler")


async def _start_cleanup_scheduler_task() -> None:
    global cleanup_task, media_integrity_task
    cleanup_task = create_background_task(cleanup_scheduler(), name="cleanup_scheduler")
    media_integrity_task = create_background_task(media_integrity_scheduler(), name="media_integrity_scheduler")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cleanup_task, media_integrity_task, cleanup_running, heartbeat_task, heartbeat_running, accel_caps_task
    test_mode = _is_testing()

    # Startup
    cleanup_running = True
    cleanup_task = None
    media_integrity_task = None
    heartbeat_running = not test_mode
    heartbeat_task = None
    accel_caps_task = None
    app.state.startup_warnings = []
    startup_started_at = datetime.now(timezone.utc)
    app.state.startup_started_at = startup_started_at.isoformat()
    app.state.startup_instance_id = f"{startup_started_at.strftime('%Y%m%dT%H%M%S.%fZ')}-{os.getpid()}"
    _log_startup_diagnostics(test_mode)
    if test_mode:
        # Keep tests fast and deterministic: skip migrations + external/background services.
        log.info("Test mode enabled: skipping DB init and background services startup")
    else:
        await _run_lifecycle_phase(
            app,
            "db_init",
            init_db,
            fatal=True,
            startup_phase="database",
            startup_progress=68,
        )
        from app.services.species_catalog_store import start_species_catalog

        await _run_lifecycle_phase(
            app,
            "species_catalog_init",
            start_species_catalog,
            fatal=False,
            startup_phase="database",
            startup_progress=70,
        )
        from app.services.species_catalog_backfill import start_background_catalog_backfill

        create_background_task(start_background_catalog_backfill(), name="species_catalog_backfill")
        await _run_lifecycle_phase(
            app,
            "notification_dispatcher_start",
            notification_dispatcher.start,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=76,
        )
        from app.services.model_manager import model_manager

        await _run_lifecycle_phase(
            app,
            "retired_model_reconciliation",
            model_manager.reconcile_retired_model_selection,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=72,
        )
        create_background_task(model_manager.ensure_installed_model_configs(), name="model_config_refresh")
        from app.services.species_catalog_compatibility import start_background_local_mapping_import

        create_background_task(start_background_local_mapping_import(), name="local_model_mapping_import")
        await _run_lifecycle_phase(
            app,
            "telemetry_start",
            telemetry_service.start,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=83,
        )
        await _run_lifecycle_phase(
            app,
            "auto_video_classifier_start",
            auto_video_classifier.start,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=86,
        )
        await _run_lifecycle_phase(
            app,
            "model_taxon_map_refresh",
            start_background_map_refresh,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=87,
        )
        await _run_lifecycle_phase(
            app,
            "localized_names_refresh",
            start_background_refresh,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=88,
        )
        await _run_lifecycle_phase(
            app,
            "high_quality_snapshot_start",
            high_quality_snapshot_service.start,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=89,
        )
        await _run_lifecycle_phase(
            app,
            "full_visit_clip_start",
            full_visit_clip_service.start,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=92,
        )
        # Intake opens only after every downstream worker can accept work.
        await _run_lifecycle_phase(
            app,
            "mqtt_service_task_start",
            _start_mqtt_service_task,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=94,
        )
        await _run_lifecycle_phase(
            app,
            "heartbeat_scheduler_task_start",
            lambda: _start_heartbeat_scheduler_task(app.state.startup_instance_id),
            fatal=False,
        )
        await _run_lifecycle_phase(
            app,
            "cleanup_scheduler_task_start",
            _start_cleanup_scheduler_task,
            fatal=False,
            startup_phase="starting_services",
            startup_progress=95,
        )
        backfill.start_watchdog()
        await asyncio.to_thread(startup_status.publish, "finalizing", 97)
        log.info(
            "Background cleanup scheduler started",
            interval_hours=CLEANUP_INTERVAL_HOURS,
            retention_days=settings.maintenance.retention_days,
            enabled=settings.maintenance.cleanup_enabled,
        )
    await asyncio.to_thread(startup_status.mark_ready)
    yield

    # Shutdown
    if accel_caps_task and not test_mode:
        accel_caps_task.cancel()
        try:
            await accel_caps_task
        except asyncio.CancelledError:
            pass

    heartbeat_running = False
    if heartbeat_task and not test_mode:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    cleanup_running = False
    if cleanup_task and not test_mode:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    if media_integrity_task and not test_mode:
        media_integrity_task.cancel()
        try:
            await media_integrity_task
        except asyncio.CancelledError:
            pass
    if not test_mode:
        # Quiesce external intake first. MQTT drains in-flight handlers before
        # downstream queues are stopped, preventing late work from being
        # accepted into a service that has already shut down.
        await _run_lifecycle_phase(app, "mqtt_service_stop", mqtt_service.stop, fatal=False)
        await _run_lifecycle_phase(app, "notification_dispatcher_stop", notification_dispatcher.stop, fatal=False)
        await _run_lifecycle_phase(app, "high_quality_snapshot_stop", high_quality_snapshot_service.stop, fatal=False)
        await _run_lifecycle_phase(app, "auto_video_classifier_stop", auto_video_classifier.stop, fatal=False)
        await _run_lifecycle_phase(app, "full_visit_clip_stop", full_visit_clip_service.stop, fatal=False)
        await _run_lifecycle_phase(app, "telemetry_stop", telemetry_service.stop, fatal=False)
        await _run_lifecycle_phase(app, "frigate_client_close", frigate_client.close, fatal=False)
        await _run_lifecycle_phase(app, "classifier_shutdown", shutdown_classifier, fatal=False)
    await close_db()  # Close database connection pool


app = FastAPI(title="Yet Another WhosAtMyFeeder API", version=APP_VERSION, lifespan=lifespan)

# Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) for correct scheme/IP detection
configured_trusted_proxy_hosts = list(settings.system.trusted_proxy_hosts)
if "*" in configured_trusted_proxy_hosts:
    resolved_trusted_proxy_hosts = ["*"]
else:
    # Expand DNS names to IPs so ProxyHeadersMiddleware can match client IPs.
    resolved_trusted_proxy_hosts = _expand_trusted_hosts(configured_trusted_proxy_hosts)
app.state.trusted_proxy_hosts_configured = configured_trusted_proxy_hosts
app.state.trusted_proxy_hosts_resolved = resolved_trusted_proxy_hosts
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=resolved_trusted_proxy_hosts)

# Setup structured logging
log = structlog.get_logger()

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Custom rate limit exceeded handler with metrics
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    RATE_LIMIT_EXCEEDED.inc()
    log.warning("Rate limit exceeded", ip=get_remote_address(request), path=request.url.path)
    return Response(
        content='{"detail":"Rate limit exceeded. Please try again later."}',
        status_code=429,
        headers={"Retry-After": str(exc.detail)},
        media_type="application/json",
    )


@app.exception_handler(DatabasePoolTimeout)
async def db_pool_timeout_handler(request: Request, exc: DatabasePoolTimeout):
    """Answer a saturated connection pool honestly.

    This is capacity, not corruption: nothing is wrong with the request and
    retrying it later will work, so it must not be dressed up as a 500. The
    holder named in the exception goes to the log, where an owner can act on
    it, and not to the client, which cannot.
    """
    log.error(
        "Database connection pool exhausted",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "The server is busy waiting for the database. Please try again in a moment."},
        headers={"Retry-After": "5"},
    )


# A queue this long means requests are already being made to wait.
DB_POOL_DEGRADED_WAIT_MS = 5000.0
# A connection held this long is doing something that does not need one. It is
# the earlier signal: waits only start once the pool has already run dry.
DB_POOL_DEGRADED_HOLD_MS = 5000.0


def db_pool_is_degraded(db_pool_health: dict) -> bool:
    """Whether the connection pool is in a state an owner should be told about.

    Both inputs are windowed, so a burst that has passed stops counting. The
    lifetime peaks stay in diagnostics for context but must never drive status,
    or one bad minute would report the install as unhealthy forever.
    """
    return (
        float(db_pool_health.get("acquire_wait_max_ms") or 0.0) >= DB_POOL_DEGRADED_WAIT_MS
        or float(db_pool_health.get("hold_ms_max") or 0.0) >= DB_POOL_DEGRADED_HOLD_MS
    )


# Global exception handler for unexpected 500s
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled exception", path=request.url.path, method=request.method, error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(LanguageMiddleware)

# CORS configuration - Note: wildcard origins cannot be used with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-YAWAMF-Audio-Suppressed-By-Mapping"],
)

# Auth router - no auth required (provides login endpoint)
app.include_router(auth_router.router, prefix="/api", tags=["auth"])

# Public/mixed access routers - use new auth system with legacy fallback
app.include_router(events.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(proxy.router, prefix="/api", dependencies=[Depends(proxy.get_proxy_auth_context)])
app.include_router(species.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(classifier.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(ai.router, prefix="/api", tags=["ai"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(stats.router, prefix="/api", tags=["stats"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(stats_ai.router, prefix="/api", tags=["stats"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(audio.router, prefix="/api", tags=["audio"], dependencies=[Depends(get_auth_context_with_legacy)])

# Owner-only routers - require authentication
app.include_router(settings_router.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(setup_router.router, prefix="/api", tags=["setup"])
app.include_router(
    backfill.router, prefix="/api", tags=["backfill"], dependencies=[Depends(get_auth_context_with_legacy)]
)
app.include_router(models.router, prefix="/api", tags=["models"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(debug.router, prefix="/api", tags=["debug"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(
    diagnostics.router, prefix="/api", tags=["diagnostics"], dependencies=[Depends(get_auth_context_with_legacy)]
)
app.include_router(
    model_eval.router, prefix="/api", tags=["diagnostics"], dependencies=[Depends(get_auth_context_with_legacy)]
)
app.include_router(jobs_router.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(manual_observations.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(email.router, prefix="/api", tags=["email"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(
    inaturalist.router, prefix="/api", tags=["inaturalist"], dependencies=[Depends(get_auth_context_with_legacy)]
)
app.include_router(ebird.router, prefix="/api", tags=["ebird"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(geocoding.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])


async def _safe_call_next(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Handle disconnect-related middleware errors without surfacing noisy 500s.

    Starlette can raise RuntimeError("No response returned.") when the client disconnects
    while middleware is still awaiting call_next(). Treat that as client-closed.
    """
    try:
        return await call_next(request)
    except asyncio.CancelledError:
        if await request.is_disconnected():
            log.info("Request cancelled after client disconnect", path=request.url.path, method=request.method)
            return Response(status_code=499)
        raise
    except RuntimeError as exc:
        if str(exc) == "No response returned." and await request.is_disconnected():
            log.info("Client disconnected before response was returned", path=request.url.path, method=request.method)
            return Response(status_code=499)
        raise


def _is_trusted_proxy_client(client_host: str | None, trusted_proxy_hosts: list[str]) -> bool:
    """Return true if the immediate client is a trusted proxy."""
    if not client_host:
        return False
    return "*" in trusted_proxy_hosts or client_host in trusted_proxy_hosts


def _classify_https_warning_reason(
    request_scheme: str,
    client_host: str | None,
    forwarded_proto: str | None,
    trusted_proxy_hosts: list[str],
) -> str:
    """Classify why a request resolved to HTTP for actionable warning logs."""
    if request_scheme == "https":
        return "secure_request"

    if forwarded_proto:
        normalized_proto = forwarded_proto.split(",")[0].strip().lower()
        if _is_trusted_proxy_client(client_host, trusted_proxy_hosts):
            if normalized_proto in {"http", "ws"}:
                return "trusted_proxy_forwarded_non_https"
            if normalized_proto in {"https", "wss"}:
                return "trusted_proxy_scheme_mismatch"
            return "trusted_proxy_forwarded_unknown_proto"
        return "untrusted_forwarded_proto_ignored"

    return "direct_http_request"


def _is_internal_client_host(client_host: str | None) -> bool:
    """Return true if the client address is loopback or private (within the trust boundary).

    Such traffic (the monolith's bundled nginx over loopback, or another container on the
    Docker network) never crosses an untrusted network, so a plaintext-HTTP request from it
    does not expose credentials to an outside party.
    """
    if not client_host:
        return False
    try:
        ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _should_warn_auth_over_http(warning_reason: str, client_host: str | None) -> bool:
    """Decide whether an authenticated HTTP request warrants a credential-exposure warning.

    A trusted proxy forwarding a non-HTTPS scheme reflects a real client leg over plaintext,
    so it always warns. Otherwise the request is treated as HTTP based on the direct
    connection, which is only a genuine exposure when that connection comes from outside the
    trust boundary — internal/private clients (e.g. the bundled nginx or Docker-network
    services polling the API) must not raise the alarm.
    """
    if warning_reason in {"untrusted_forwarded_proto_ignored", "direct_http_request"}:
        return not _is_internal_client_host(client_host)
    if warning_reason == "secure_request":
        return False
    return True


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await _safe_call_next(request, call_next)

    # Only add HSTS if using HTTPS
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # General security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy - allow self and inline styles (needed for some UI)
    # Adjust as needed for your specific requirements
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self' https://cloudflareinsights.com https://static.cloudflareinsights.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers["Content-Security-Policy"] = csp_policy

    # Referrer Policy - don't leak URLs to external sites
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy - disable unnecessary browser features
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()"
    )

    return response


@app.middleware("http")
async def check_https_warning(request: Request, call_next):
    """Log warning if authentication is enabled over HTTP."""
    # Only check on non-health endpoints to avoid log spam
    if request.url.path not in ["/health", "/metrics"]:
        if settings.auth.enabled and request.url.scheme != "https":
            resolved_trusted_hosts = getattr(app.state, "trusted_proxy_hosts_resolved", [])
            client_host = request.client.host if request.client else None
            x_forwarded_proto = request.headers.get("x-forwarded-proto")
            warning_reason = _classify_https_warning_reason(
                request_scheme=request.url.scheme,
                client_host=client_host,
                forwarded_proto=x_forwarded_proto,
                trusted_proxy_hosts=resolved_trusted_hosts,
            )

            # Internal/private clients (the bundled nginx, Docker-network services) stay within
            # the trust boundary, so plaintext HTTP from them is not a credential-exposure risk.
            # Log warning once per minute to avoid spam.
            should_log = _should_warn_auth_over_http(warning_reason, client_host) and (
                not hasattr(app.state, "_last_https_warning")
                or (datetime.now() - app.state._last_https_warning).total_seconds() > 60
            )
            if should_log:
                app.state._last_https_warning = datetime.now()
                log.warning(
                    "Authentication enabled over HTTP - credentials may be exposed",
                    path=request.url.path,
                    host=request.headers.get("host"),
                    client=client_host,
                    scheme=request.url.scheme,
                    warning_reason=warning_reason,
                    x_forwarded_proto=x_forwarded_proto,
                    x_forwarded_for=request.headers.get("x-forwarded-for"),
                    x_forwarded_host=request.headers.get("x-forwarded-host"),
                    trusted_proxy_hosts_configured=getattr(app.state, "trusted_proxy_hosts_configured", []),
                    trusted_proxy_hosts_resolved=resolved_trusted_hosts,
                    recommendation="Use HTTPS in production for secure authentication",
                )
            # Warn if proxy trust is wide open
            if "*" in resolved_trusted_hosts:
                if not hasattr(app.state, "_last_proxy_warning"):
                    app.state._last_proxy_warning = datetime.now()
                    log.warning(
                        "Proxy headers trust all hosts",
                        recommendation="Configure SYSTEM__TRUSTED_PROXY_HOSTS to restrict trusted proxies",
                    )
                else:
                    if (datetime.now() - app.state._last_proxy_warning).total_seconds() > 60:
                        app.state._last_proxy_warning = datetime.now()
                        log.warning(
                            "Proxy headers trust all hosts",
                            recommendation="Configure SYSTEM__TRUSTED_PROXY_HOSTS to restrict trusted proxies",
                        )

    response = await _safe_call_next(request, call_next)
    return response


@app.middleware("http")
async def count_requests(request, call_next):
    API_REQUESTS.inc()
    response = await _safe_call_next(request, call_next)
    return response


def _naming_health() -> dict[str, object]:
    """Where bird names come from when the network cannot answer.

    Reported because a reference or a locale that is not there is invisible
    otherwise: naming simply falls back and nobody learns why the names are in
    English or missing.
    """
    from app.services.localized_names import localized_names
    from app.services.species_reference import species_reference
    from app.services import species_catalog_status as catalog_status_module

    try:
        reference = species_reference.status()
    except Exception:  # pragma: no cover - health must never fail
        reference = {"available": False}
    try:
        localized = localized_names.status()
    except Exception:  # pragma: no cover
        localized = {"available": False}
    try:
        catalog = catalog_status_module.species_catalog_status.status()
    except Exception:  # pragma: no cover
        catalog = {"available": False, "species_count": 0, "active_release": None, "artifacts": []}
    try:
        from app.services.species_catalog_resolver import species_catalog_resolver

        catalog["shadow"] = species_catalog_resolver.stats()
    except Exception:  # pragma: no cover
        pass
    try:
        from app.services.species_catalog_backfill import last_backfill_summary

        catalog["backfill"] = last_backfill_summary()
    except Exception:  # pragma: no cover
        pass
    try:
        from app.services.species_catalog_compatibility import last_local_mapping_report

        catalog["local_mapping"] = last_local_mapping_report()
    except Exception:  # pragma: no cover
        pass
    try:
        from app.services.species_catalog_overrides import override_summary

        catalog["owner_renames"] = override_summary()
    except Exception:  # pragma: no cover
        pass
    return {"species_reference": reference, "localized_names": localized, "species_catalog": catalog}


def build_health_payload() -> dict[str, object]:
    from app.services.host_facts import collect_host_facts

    startup_warnings = getattr(app.state, "startup_warnings", [])
    startup_instance_id = getattr(app.state, "startup_instance_id", "unknown")
    startup_started_at = getattr(app.state, "startup_started_at", None)
    classifier_health = get_classifier().check_health()
    mqtt_health = mqtt_service.get_status()
    video_health = auto_video_classifier.get_status()
    high_quality_snapshot_health = high_quality_snapshot_service.get_status()
    notification_dispatch_health = notification_dispatcher.get_status()
    db_pool_health = get_db_pool_status()
    event_pipeline_health = (
        event_processor.get_status()
        if event_processor is not None
        else {
            "status": "unknown",
            "started_events": 0,
            "completed_events": 0,
            "dropped_events": 0,
            "incomplete_events": 0,
            "critical_failures": 0,
            "stage_timeouts": {},
            "stage_failures": {},
            "stage_fallbacks": {},
            "drop_reasons": {},
            "last_stage_timeout": None,
            "last_stage_failure": None,
            "last_drop": None,
            "last_completed": None,
            "recent_outcomes": [],
        }
    )
    health = {
        "status": "ok",
        "service": "ya-wamf-backend",
        "version": APP_VERSION,
        "ml": classifier_health,
        "naming": _naming_health(),
        "db_pool": db_pool_health,
        "media_integrity_scan": get_media_integrity_scan_status(),
        "mqtt": mqtt_health,
        "video_classifier": video_health,
        "high_quality_snapshots": high_quality_snapshot_health,
        "notification_dispatcher": notification_dispatch_health,
        "event_pipeline": event_pipeline_health,
        "startup_warnings": startup_warnings,
        # The machine this is running on. A performance report cannot be sized
        # without it, and two bundles were exchanged on #300 before anyone could
        # say whether the host was a small box or a large one.
        "host": collect_host_facts(),
        "startup_instance_id": startup_instance_id,
        "startup_started_at": startup_started_at,
    }
    live_image_health = health["ml"].get("live_image") or {}
    live_image_status = str(live_image_health.get("status") or "").lower()

    # If startup had degraded phases or ML is unhealthy, top-level status should reflect it
    if (
        health["ml"]["status"] != "ok"
        or (live_image_status not in {"", "ok", "healthy"} or bool(live_image_health.get("recovery_active")))
        or startup_warnings
        or bool(mqtt_health.get("backlog_wait_active"))
        or bool(mqtt_health.get("recent_handler_slot_wait_exhaustion"))
        or bool(mqtt_health.get("stall_recovery_warning_active"))
        or int(notification_dispatch_health.get("dropped_jobs") or 0) > 0
        or event_pipeline_health.get("status") != "ok"
        or db_pool_is_degraded(db_pool_health)
    ):
        health["status"] = "degraded"

    return health


@app.get("/health")
async def health_check(response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return build_health_payload()


@app.get("/ready", response_model=ReadinessResponse)
async def readiness_check(response: Response) -> ReadinessResponse | JSONResponse:
    """Kubernetes/Compose readiness probe endpoint.

    Ready requires:
    - DB pool initialized (or test mode)
    - no non-fatal startup warnings recorded
    """
    startup_warnings = getattr(app.state, "startup_warnings", [])
    db_ready = is_db_pool_initialized() or _is_testing()
    ready = db_ready and not startup_warnings

    payload = ReadinessResponse(
        ready=ready,
        db_pool_initialized=db_ready,
        startup_warnings=startup_warnings,
        startup_instance_id=getattr(app.state, "startup_instance_id", "unknown"),
        startup_started_at=getattr(app.state, "startup_started_at", None),
    )
    if ready:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return payload
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload.model_dump(),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/api/sse")
async def sse_endpoint(
    request: Request,
    token: str = None,  # Optional token via query param for EventSource
):
    """Server-Sent Events endpoint for real-time updates.

    Supports authentication via:
    - Bearer token in Authorization header
    - Token in query parameter (?token=...)
    - Public access if enabled
    """
    from app.auth import verify_token

    # Get auth context with token support
    auth: AuthContext = None

    # Try query parameter token first (for EventSource compatibility)
    token_data = None
    if token:
        try:
            token_data = verify_token(token)
            auth = AuthContext(auth_level=token_data.auth_level, username=token_data.username)
        except HTTPException:
            # Invalid token - fall through to other methods
            pass

    # If no valid token from query param, try normal auth
    if not auth:
        try:
            auth = await get_auth_context_with_legacy(request, None)
        except HTTPException as e:
            # If auth required and none provided, reject connection
            raise e

    hide_camera_names = (
        not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    )

    def sanitize_message_for_guest(message: dict) -> dict:
        if not hide_camera_names:
            return message

        sanitized = dict(message)
        data = sanitized.get("data")
        if isinstance(data, dict):
            data = dict(data)
            if "camera" in data:
                data["camera"] = "Hidden"
            if "camera_name" in data:
                data["camera_name"] = "Hidden"
            sanitized["data"] = data
        return sanitized

    async def event_generator():
        queue = await broadcaster.subscribe()
        message_count = 0
        # Check token expiry every 60 events or heartbeats (~20 minutes idle, or
        # every 60 messages under active traffic — whichever comes first).
        _EXPIRY_CHECK_INTERVAL = 60
        try:
            # Send initial connection message with auth level
            yield f"data: {json.dumps({'type': 'connected', 'message': 'SSE Connected', 'auth_level': auth.auth_level})}\n\n"

            while True:
                try:
                    # Wait for a message or a timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=20.0)

                    # Filter sensitive events for guests
                    if not auth.is_owner:
                        event_type = message.get("type", "")
                        # Block owner-only events from public users
                        if event_type in [
                            "settings_updated",
                            "backfill_started",
                            "backfill_progress",
                            "backfill_complete",
                            "backfill_failed",
                        ]:
                            continue

                    if not auth.is_owner:
                        message = sanitize_message_for_guest(message)

                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send a JSON heartbeat rather than a comment-only frame. Some
                    # browser/proxy combinations are less reliable at keeping SSE
                    # streams alive when idle traffic is only comments.
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                message_count += 1
                # Re-validate token expiry periodically (active traffic and idle both covered)
                if token_data is not None and message_count % _EXPIRY_CHECK_INTERVAL == 0:
                    if datetime.now(timezone.utc) >= token_data.exp:
                        yield f"data: {json.dumps({'type': 'session_expired', 'message': 'Session token has expired'})}\n\n"
                        return
        finally:
            await broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/version", response_model=VersionResponse)
async def get_version():
    """Return the application version info. Git hash and branch are omitted from
    the unauthenticated response to reduce reconnaissance surface; they are
    available in the authenticated /api/health endpoint."""
    return {
        "version": APP_VERSION,
        "base_version": BASE_VERSION,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
