from fastapi import FastAPI, Depends, HTTPException, status, Security, Request
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog
import asyncio
import os
import json
import secrets
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter

from app.database import init_db, close_db, get_db
from app.services.mqtt_service import mqtt_service
from app.services.classifier_service import get_classifier
from app.services.event_processor import EventProcessor
from app.services.media_cache import media_cache
from app.services.broadcaster import broadcaster
from app.services.telemetry_service import telemetry_service
from app.repositories.detection_repository import DetectionRepository
from app.routers import events, stream, proxy, settings as settings_router, species, backfill, classifier, models, ai, stats, debug, audio, email, auth as auth_router
from app.config import settings
from app.middleware.language import LanguageMiddleware
from app.services.i18n_service import i18n_service
from app.auth import get_auth_context, AuthContext, AuthLevel

# Legacy API key authentication (DEPRECATED - will be removed in v2.9.0)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

async def verify_api_key_legacy(
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query)
) -> bool:
    """
    DEPRECATED: Legacy API key authentication.

    This function is maintained for backward compatibility.
    New installations should use the JWT auth system.

    Will be removed in v2.9.0 (approximately 3 months).

    Returns:
        True if legacy API key is valid, False otherwise
    """
    legacy_api_key = settings.api_key

    if not legacy_api_key:
        return False  # No legacy key configured

    api_key = header_key or query_key
    if not api_key:
        return False

    if secrets.compare_digest(api_key, legacy_api_key):
        log.warning(
            "Using deprecated API key authentication",
            notice="Migrate to password-based auth in Settings. "
                   "API key support will be removed in v2.9.0"
        )
        return True

    return False

async def get_auth_context_with_legacy(
    request: Request,
    credentials = Depends(get_auth_context.__wrapped__)  # Get the actual dependency
) -> AuthContext:
    """
    Get auth context with legacy API key fallback.

    Priority:
    1. New JWT token authentication
    2. Legacy API key (deprecated)
    3. Public access (if enabled)
    4. Deny
    """
    # Try new auth first
    try:
        return await get_auth_context(request, credentials)
    except HTTPException as e:
        # New auth failed - try legacy
        if await verify_api_key_legacy():
            return AuthContext(auth_level=AuthLevel.OWNER, username="legacy_api_key")

        # Both failed - re-raise original exception
        raise e

# Version management
def get_base_version() -> str:
    """Read base version from VERSION file or environment."""
    # Check environment variable first
    if os.environ.get("APP_VERSION_BASE"):
        return os.environ.get("APP_VERSION_BASE")

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

# Rate limiting configuration
# Use a more permissive rate limit: 100 requests per minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Metrics
EVENTS_PROCESSED = Counter('events_processed_total', 'Total number of events processed')
DETECTIONS_TOTAL = Counter('detections_total', 'Total number of bird detections')
API_REQUESTS = Counter('api_requests_total', 'Total API requests')
RATE_LIMIT_EXCEEDED = Counter('rate_limit_exceeded_total', 'Total rate limit violations')

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
    await close_db()  # Close database connection pool

app = FastAPI(title="Yet Another WhosAtMyFeeder API", version=APP_VERSION, lifespan=lifespan)

# Setup structured logging
log = structlog.get_logger()

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Custom rate limit exceeded handler with metrics
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    RATE_LIMIT_EXCEEDED.inc()
    log.warning("Rate limit exceeded",
                ip=get_remote_address(request),
                path=request.url.path)
    return Response(
        content='{"detail":"Rate limit exceeded. Please try again later."}',
        status_code=429,
        headers={"Retry-After": str(exc.detail)},
        media_type="application/json"
    )

app.add_middleware(LanguageMiddleware)

# CORS configuration - Note: wildcard origins cannot be used with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth router - no auth required (provides login endpoint)
app.include_router(auth_router.router, prefix="/api", tags=["auth"])

# Public/mixed access routers - use new auth system with legacy fallback
app.include_router(events.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(stream.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(proxy.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(species.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(classifier.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(ai.router, prefix="/api", tags=["ai"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(stats.router, prefix="/api", tags=["stats"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(audio.router, prefix="/api", tags=["audio"], dependencies=[Depends(get_auth_context_with_legacy)])

# Owner-only routers - require authentication
app.include_router(settings_router.router, prefix="/api", dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(backfill.router, prefix="/api", tags=["backfill"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(models.router, prefix="/api", tags=["models"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(debug.router, prefix="/api", tags=["debug"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(email.router, prefix="/api", tags=["email"], dependencies=[Depends(get_auth_context_with_legacy)])

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

@app.get("/api/sse")
async def sse_endpoint(
    request: Request,
    token: str = None  # Optional token via query param for EventSource
):
    """Server-Sent Events endpoint for real-time updates.

    Supports authentication via:
    - Bearer token in Authorization header
    - Token in query parameter (?token=...)
    - Public access if enabled
    """
    from app.auth import verify_token
    from fastapi.security import HTTPAuthorizationCredentials

    # Get auth context with token support
    auth: AuthContext = None

    # Try query parameter token first (for EventSource compatibility)
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

    async def event_generator():
        queue = await broadcaster.subscribe()
        try:
            # Send initial connection message with auth level
            yield f"data: {json.dumps({'type': 'connected', 'message': 'SSE Connected', 'auth_level': auth.auth_level})}\n\n"

            while True:
                try:
                    # Wait for a message or a timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=20.0)

                    # Filter sensitive events for guests
                    if not auth.is_owner:
                        event_type = message.get('type', '')
                        # Block owner-only events from public users
                        if event_type in ['settings_updated', 'backfill_progress', 'backfill_complete']:
                            continue

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

