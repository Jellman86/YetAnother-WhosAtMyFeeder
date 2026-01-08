from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
import structlog
import asyncio
import os
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter

from app.database import init_db, get_db
from app.services.mqtt_service import mqtt_service
from app.services.classifier_service import get_classifier
from app.services.event_processor import EventProcessor
from app.services.media_cache import media_cache
from app.services.broadcaster import broadcaster
from app.services.telemetry_service import telemetry_service
from app.repositories.detection_repository import DetectionRepository
from app.routers import events, stream, proxy, settings as settings_router, species, backfill, classifier, models, ai, stats, debug, audio
from app.config import settings

# Authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

async def verify_api_key(
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query)
):
    """Validate API Key if configured (via Header or Query param)."""
    if settings.api_key:
        api_key = header_key or query_key
        if not api_key:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API Key",
            )
        if api_key != settings.api_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API Key",
            )
    return header_key or query_key

# Version management
def get_base_version() -> str:
    """Read base version from VERSION file."""
    version_file = os.path.join(os.path.dirname(__file__), '..', '..', 'VERSION')
    try:
        with open(version_file, 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, IOError):
        # Fallback if VERSION file doesn't exist
        return "2.2.0"

def get_git_hash() -> str:
    """Get git commit hash from environment or by running git."""
    # First check environment variable (set during Docker build)
    git_hash = os.environ.get('GIT_HASH', '').strip()
    if git_hash:
        return git_hash

    # Try to get from git command (for development)
    try:
        import subprocess
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

BASE_VERSION = get_base_version()
GIT_HASH = get_git_hash()
APP_VERSION = f"{BASE_VERSION}+{GIT_HASH}"
os.environ["APP_VERSION"] = APP_VERSION # Make available to other services

# Metrics
EVENTS_PROCESSED = Counter('events_processed_total', 'Total number of events processed')
DETECTIONS_TOTAL = Counter('detections_total', 'Total number of bird detections')
API_REQUESTS = Counter('api_requests_total', 'Total API requests')

# Use shared classifier instance
classifier_service = get_classifier()
event_processor = EventProcessor(classifier_service)
log = structlog.get_logger()

# Cleanup task control
cleanup_task = None
cleanup_running = True
CLEANUP_INTERVAL_HOURS = 24  # Run cleanup every 24 hours


async def run_cleanup():
    """Execute cleanup of old detections and media cache."""
    try:
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
                 await asyncio.sleep(3600) # check every hour

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cleanup_task, cleanup_running
    # Startup
    await init_db()
    asyncio.create_task(mqtt_service.start(event_processor))
    await telemetry_service.start()
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
    await telemetry_service.stop()
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

app.include_router(events.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(stream.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(proxy.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(settings_router.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(species.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(backfill.router, prefix="/api", tags=["backfill"], dependencies=[Depends(verify_api_key)])
app.include_router(classifier.router, prefix="/api", dependencies=[Depends(verify_api_key)])
app.include_router(models.router, prefix="/api", tags=["models"], dependencies=[Depends(verify_api_key)])
app.include_router(ai.router, prefix="/api", tags=["ai"], dependencies=[Depends(verify_api_key)])
app.include_router(stats.router, prefix="/api", tags=["stats"], dependencies=[Depends(verify_api_key)])
app.include_router(debug.router, prefix="/api", tags=["debug"], dependencies=[Depends(verify_api_key)])
app.include_router(audio.router, prefix="/api", tags=["audio"], dependencies=[Depends(verify_api_key)])

@app.middleware("http")
async def count_requests(request, call_next):
    API_REQUESTS.inc()
    response = await call_next(request)
    return response

@app.get("/health")
async def health_check():
    health = {
        "status": "ok", 
        "service": "ya-wamf-backend", 
        "version": APP_VERSION,
        "ml": classifier_service.check_health()
    }
    
    # If ML is in error state, top-level status should reflect it
    if health["ml"]["status"] != "ok":
        health["status"] = "degraded"
        
    return health

@app.get("/api/sse", dependencies=[Depends(verify_api_key)])
async def sse_endpoint():
    """Server-Sent Events endpoint for real-time updates."""
    async def event_generator():
        queue = await broadcaster.subscribe()
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'SSE Connected'})}\n\n"
            
            while True:
                try:
                    # Wait for a message or a timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send a heartbeat comment (ignored by clients but keeps connection alive)
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            await broadcaster.unsubscribe(queue)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

