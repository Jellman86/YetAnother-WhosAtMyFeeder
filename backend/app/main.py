from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import asyncio
import os
import subprocess
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from app.database import init_db, get_db
from app.services.mqtt_service import MQTTService
from app.services.classifier_service import get_classifier
from app.services.event_processor import EventProcessor
from app.services.media_cache import media_cache
from app.repositories.detection_repository import DetectionRepository
from app.routers import events, stream, proxy, settings as settings_router, species, backfill, classifier
from app.config import settings

# Use shared classifier instance
classifier_service = get_classifier()
event_processor = EventProcessor(classifier_service)
mqtt_service = MQTTService()
log = structlog.get_logger()

# Version management
# Reload triggered by agent
BASE_VERSION = "2.0.0"

def get_git_hash() -> str:
    """Get git commit hash from environment or by running git."""
    # First check environment variable (set during Docker build)
    git_hash = os.environ.get('GIT_HASH', '').strip()
    if git_hash:
        return git_hash

    # Try to get from git command (for development)
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return "unknown"

GIT_HASH = get_git_hash()
APP_VERSION = f"{BASE_VERSION}+{GIT_HASH}"

# Cleanup task control
cleanup_task = None
cleanup_running = True
CLEANUP_INTERVAL_HOURS = 24  # Run cleanup every 24 hours


async def run_cleanup():
    """Execute cleanup of old detections and media cache."""
    now = datetime.now()

    # Detection cleanup
    if settings.maintenance.retention_days > 0 and settings.maintenance.cleanup_enabled:
        cutoff = now - timedelta(days=settings.maintenance.retention_days)
        async with get_db() as db:
            repo = DetectionRepository(db)
            deleted_count = await repo.delete_older_than(cutoff)
        if deleted_count > 0:
            log.info("Automatic cleanup completed",
                     deleted_count=deleted_count,
                     retention_days=settings.maintenance.retention_days,
                     cutoff=cutoff.isoformat())

    # Media cache cleanup
    if settings.media_cache.enabled:
        cache_retention = settings.media_cache.retention_days
        if cache_retention == 0:
            cache_retention = settings.maintenance.retention_days
        if cache_retention > 0:
            cache_stats = await media_cache.cleanup_old_media(cache_retention)
            if cache_stats["snapshots_deleted"] > 0 or cache_stats["clips_deleted"] > 0:
                log.info("Media cache cleanup completed", **cache_stats)


async def cleanup_scheduler():
    """Background task that runs cleanup on a fixed interval.

    Improvements over 3 AM fixed-time approach:
    - Runs cleanup immediately on startup (catches missed intervals)
    - Uses fixed interval (24 hours) instead of polling hourly
    - Handles container restarts gracefully
    """
    global cleanup_running

    # Run cleanup once on startup (handles missed cleanups from downtime)
    try:
        await run_cleanup()
        log.info("Startup cleanup completed")
    except Exception as e:
        log.error("Startup cleanup failed", error=str(e))

    # Then run on fixed interval
    while cleanup_running:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
            await run_cleanup()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Cleanup task error", error=str(e))
            # On error, wait 1 hour before retrying
            await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cleanup_task, cleanup_running
    # Startup
    await init_db()
    asyncio.create_task(mqtt_service.start(event_processor.process_mqtt_message))
    cleanup_task = asyncio.create_task(cleanup_scheduler())
    log.info("Background cleanup scheduler started",
             interval_hours=CLEANUP_INTERVAL_HOURS,
             retention_days=settings.maintenance.retention_days,
             enabled=settings.maintenance.cleanup_enabled)
    yield
    # Shutdown
    cleanup_running = False
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    await mqtt_service.stop()

app = FastAPI(title="Yet Another WhosAtMyFeeder API", version=APP_VERSION, lifespan=lifespan)

# Setup structured logging
log = structlog.get_logger()

# CORS configuration - Note: wildcard origins cannot be used with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(proxy.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(species.router, prefix="/api")
app.include_router(backfill.router, prefix="/api", tags=["backfill"])
app.include_router(classifier.router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "ya-wamf-backend", "version": APP_VERSION}

@app.get("/api/version")
async def get_version():
    """Return the application version info."""
    return {
        "version": APP_VERSION,
        "base_version": BASE_VERSION,
        "git_hash": GIT_HASH
    }


@app.get("/metrics")
async def metrics():
    # Placeholder for Prometheus metrics
    return "events_processed_total 0\n"

