from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog
import asyncio
import os
import json
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
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.frigate_client import frigate_client
from app.repositories.detection_repository import DetectionRepository
from app.routers import events, proxy, settings as settings_router, species, backfill, classifier, models, ai, stats, debug, audio, email, inaturalist, ebird, auth as auth_router
from app.config import settings, _expand_trusted_hosts
from app.middleware.language import LanguageMiddleware
from app.services.i18n_service import i18n_service
from app.utils.tasks import create_background_task
from app.ratelimit import limiter
from app.auth import get_auth_context, AuthContext, AuthLevel
from app.auth_legacy import get_auth_context_with_legacy

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

def get_app_branch() -> str:
    """Get app branch from environment or by running git."""
    # First check environment variable (set during Docker build)
    branch = os.environ.get('APP_BRANCH', '').strip()
    if branch:
        return branch

    # Try to get from git command (for development)
    try:
        import subprocess
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
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
APP_BRANCH = get_app_branch()

# Format: version-branch+hash (omit branch if main or unknown)
if APP_BRANCH and APP_BRANCH not in ["main", "unknown"]:
    APP_VERSION = f"{BASE_VERSION}-{APP_BRANCH}+{GIT_HASH}"
else:
    APP_VERSION = f"{BASE_VERSION}+{GIT_HASH}"

os.environ["APP_VERSION"] = APP_VERSION # Make available to other services

# Metrics
EVENTS_PROCESSED = Counter('events_processed_total', 'Total number of events processed')
DETECTIONS_TOTAL = Counter('detections_total', 'Total number of bird detections')
API_REQUESTS = Counter('api_requests_total', 'Total API requests')
RATE_LIMIT_EXCEEDED = Counter('rate_limit_exceeded_total', 'Total rate limit violations')

# Test mode: keep app startup lightweight so TestClient doesn't hang on external/background services.
IS_TESTING = bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("YA_WAMF_TESTING") == "1"

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
    if not IS_TESTING:
        create_background_task(mqtt_service.start(event_processor), name="mqtt_service_start")
        await telemetry_service.start()
        await auto_video_classifier.start()
        cleanup_task = create_background_task(cleanup_scheduler(), name="cleanup_scheduler")
        log.info("Background cleanup scheduler started",
                 interval_hours=CLEANUP_INTERVAL_HOURS,
                 retention_days=settings.maintenance.retention_days,
                 enabled=settings.maintenance.cleanup_enabled)
    else:
        log.info("Test mode enabled: skipping background services startup")
    yield
    # Shutdown
    cleanup_running = False
    if cleanup_task and not IS_TESTING:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    if not IS_TESTING:
        await auto_video_classifier.stop()
        await telemetry_service.stop()
        await mqtt_service.stop()
        await frigate_client.close()
    await close_db()  # Close database connection pool

app = FastAPI(title="Yet Another WhosAtMyFeeder API", version=APP_VERSION, lifespan=lifespan)

# Trust proxy headers (X-Forwarded-Proto, X-Forwarded-For) for correct scheme/IP detection
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
trusted_proxy_hosts = settings.system.trusted_proxy_hosts
if "*" in trusted_proxy_hosts:
    trusted_proxy_hosts = ["*"]
else:
    # Expand DNS names to IPs so ProxyHeadersMiddleware can match client IPs.
    trusted_proxy_hosts = _expand_trusted_hosts(trusted_proxy_hosts)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_proxy_hosts)

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

# Global exception handler for unexpected 500s
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

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
app.include_router(inaturalist.router, prefix="/api", tags=["inaturalist"], dependencies=[Depends(get_auth_context_with_legacy)])
app.include_router(ebird.router, prefix="/api", tags=["ebird"], dependencies=[Depends(get_auth_context_with_legacy)])

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

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
        "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self' https://cloudflareinsights.com https://static.cloudflareinsights.com; "
        "frame-ancestors 'none';"
    )
    response.headers["Content-Security-Policy"] = csp_policy

    # Referrer Policy - don't leak URLs to external sites
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy - disable unnecessary browser features
    response.headers["Permissions-Policy"] = (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=(), "
        "usb=(), "
        "magnetometer=(), "
        "gyroscope=(), "
        "accelerometer=()"
    )

    return response

@app.middleware("http")
async def check_https_warning(request: Request, call_next):
    """Log warning if authentication is enabled over HTTP."""
    # Only check on non-health endpoints to avoid log spam
    if request.url.path not in ["/health", "/metrics"]:
        if settings.auth.enabled and request.url.scheme != "https":
            # Log warning once per minute to avoid spam
            if not hasattr(app.state, "_last_https_warning"):
                app.state._last_https_warning = datetime.now()
                log.warning(
                    "Authentication enabled over HTTP - credentials may be exposed",
                    path=request.url.path,
                    recommendation="Use HTTPS in production for secure authentication"
                )
            else:
                # Log at most once per minute
                if (datetime.now() - app.state._last_https_warning).total_seconds() > 60:
                    app.state._last_https_warning = datetime.now()
                    log.warning(
                        "Authentication enabled over HTTP - credentials may be exposed",
                        recommendation="Use HTTPS in production for secure authentication"
                    )
            # Warn if proxy trust is wide open
            if settings.system.trusted_proxy_hosts == ["*"]:
                if not hasattr(app.state, "_last_proxy_warning"):
                    app.state._last_proxy_warning = datetime.now()
                    log.warning(
                        "Proxy headers trust all hosts",
                        recommendation="Configure SYSTEM__TRUSTED_PROXY_HOSTS to restrict trusted proxies"
                    )
                else:
                    if (datetime.now() - app.state._last_proxy_warning).total_seconds() > 60:
                        app.state._last_proxy_warning = datetime.now()
                        log.warning(
                            "Proxy headers trust all hosts",
                            recommendation="Configure SYSTEM__TRUSTED_PROXY_HOSTS to restrict trusted proxies"
                        )

    response = await call_next(request)
    return response

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

    hide_camera_names = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
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
                        if event_type in ['settings_updated', 'backfill_started', 'backfill_progress', 'backfill_complete', 'backfill_failed']:
                            continue

                    if not auth.is_owner:
                        message = sanitize_message_for_guest(message)

                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send a heartbeat comment (ignored by clients but keeps connection alive)
                    yield ": heartbeat\n\n"
        finally:
            await broadcaster.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/version")
async def get_version():
    """Return the application version info."""
    return {
        "version": APP_VERSION,
        "base_version": BASE_VERSION,
        "git_hash": GIT_HASH,
        "branch": APP_BRANCH
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
