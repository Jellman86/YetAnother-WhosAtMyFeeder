import asyncio
import json
import re
from pathlib import Path as FilePath
from tempfile import NamedTemporaryFile
from urllib.parse import quote_plus
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Response, Path, Request, Depends
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
import httpx
import sqlite3
import structlog
from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.auth import AuthContext, AuthLevel, require_owner, verify_token
from app.auth_legacy import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.utils.public_access import effective_public_media_days

router = APIRouter()

# Shared HTTP client for better connection pooling
_http_client: httpx.AsyncClient | None = None
_preview_locks: dict[str, asyncio.Lock] = {}


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client

# Validate event_id format (Frigate uses UUIDs, numeric IDs, or timestamp-based IDs with dots)
EVENT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_.]+$')
CAMERA_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')

def validate_event_id(event_id: str) -> bool:
    return bool(EVENT_ID_PATTERN.match(event_id)) and len(event_id) <= 64

def validate_camera_name(camera: str) -> bool:
    return bool(CAMERA_NAME_PATTERN.match(camera)) and len(camera) <= 64


def _preview_lock(event_id: str) -> asyncio.Lock:
    lock = _preview_locks.get(event_id)
    if lock is None:
        lock = asyncio.Lock()
        _preview_locks[event_id] = lock
    return lock


def _format_vtt_timestamp(seconds: float) -> str:
    whole_ms = max(0, int(round(seconds * 1000)))
    hours = whole_ms // 3_600_000
    minutes = (whole_ms % 3_600_000) // 60_000
    secs = (whole_ms % 60_000) // 1000
    millis = whole_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _build_sprite_url(request: Request, event_id: str) -> str:
    sprite_url = str(request.url_for("proxy_clip_thumbnails_sprite", event_id=event_id))
    token = request.query_params.get("token")
    if token:
        sprite_url = f"{sprite_url}?token={quote_plus(token)}"
    return sprite_url

async def require_event_access(event_id: str, auth: AuthContext, lang: str) -> None:
    """Ensure guests can only access visible, recent events."""
    if auth.is_owner:
        return

    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            detection = await repo.get_by_frigate_event(event_id)
    except sqlite3.OperationalError as exc:
        log = structlog.get_logger()
        log.warning("Failed to check event access; allowing fallback", error=str(exc))
        return

    if not detection or detection.is_hidden or not detection.detection_time:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.event_not_found", lang)
        )

    if settings.public_access.enabled:
        max_days = effective_public_media_days()
        detection_date = detection.detection_time.date()
        if max_days > 0:
            cutoff = date.today() - timedelta(days=max_days)
            if detection_date < cutoff:
                raise HTTPException(
                    status_code=404,
                    detail=i18n_service.translate("errors.proxy.event_not_found", lang)
                )
        else:
            if detection_date != date.today():
                raise HTTPException(
                    status_code=404,
                    detail=i18n_service.translate("errors.proxy.event_not_found", lang)
                )


async def _ensure_preview_assets(event_id: str, lang: str) -> None:
    """Ensure preview sprite + manifest exist in media cache."""
    from app.services.media_cache import media_cache
    from app.services.video_preview_service import video_preview_service

    if media_cache.get_preview_sprite_path(event_id) and await media_cache.get_preview_manifest(event_id):
        return

    lock = _preview_lock(event_id)
    async with lock:
        # Another request may have generated assets while waiting.
        if media_cache.get_preview_sprite_path(event_id) and await media_cache.get_preview_manifest(event_id):
            return

        clip_path = media_cache.get_clip_path(event_id)
        temp_clip: FilePath | None = None

        if clip_path is None:
            clip_url = f"{settings.frigate.frigate_url}/api/events/{event_id}/clip.mp4"
            headers = frigate_client._get_headers()
            client = get_http_client()
            try:
                resp = await client.get(clip_url, headers=headers, timeout=60.0)
                if resp.status_code == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
                    )
                resp.raise_for_status()
                if not resp.content:
                    raise HTTPException(
                        status_code=502,
                        detail=i18n_service.translate("errors.proxy.empty_clip", lang)
                    )
                with NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                    tmp.write(resp.content)
                    temp_clip = FilePath(tmp.name)
                clip_path = temp_clip
            except HTTPException:
                raise
            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=504,
                    detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
                )
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
                )
            except httpx.RequestError:
                raise HTTPException(
                    status_code=502,
                    detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
                )

        try:
            sprite_bytes, cues = video_preview_service.generate(clip_path)
            manifest_json = json.dumps({
                "version": 1,
                "event_id": event_id,
                "tile_width": video_preview_service.tile_width,
                "tile_height": video_preview_service.tile_height,
                "cues": [c.__dict__ for c in cues],
            })
            cached = await media_cache.cache_preview_assets(event_id, sprite_bytes, manifest_json)
            if not cached:
                raise HTTPException(
                    status_code=500,
                    detail=i18n_service.translate("errors.proxy.preview_generation_failed", lang)
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=i18n_service.translate("errors.proxy.preview_generation_failed", lang)
            )
        finally:
            if temp_clip is not None:
                try:
                    temp_clip.unlink(missing_ok=True)
                except Exception:
                    pass

@router.get("/frigate/test")
async def test_frigate_connection(
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Test connection to Frigate and return status with details."""
    url = f"{settings.frigate.frigate_url}/api/version"
    client = get_http_client()
    headers = frigate_client._get_headers()
    lang = get_user_language(request)
    try:
        resp = await client.get(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
        version = resp.text.strip().strip('"')
        return {
            "status": "ok",
            "frigate_url": settings.frigate.frigate_url,
            "version": version
        }
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail=i18n_service.translate("errors.proxy.frigate_auth_failed", lang)
            )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
        )

@router.get("/frigate/config")
async def proxy_config(
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    url = f"{settings.frigate.frigate_url}/api/config"
    client = get_http_client()
    headers = frigate_client._get_headers()
    lang = get_user_language(request)
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return Response(content=resp.content, media_type=resp.headers.get("content-type", "application/json"))
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail=i18n_service.translate("errors.proxy.frigate_auth_failed", lang)
            )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
        )

@router.get("/frigate/{event_id}/snapshot.jpg")
@guest_rate_limit()
async def proxy_snapshot(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    await require_event_access(event_id, auth, lang)

    # Check cache first
    if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
        cached = await media_cache.get_snapshot(event_id)
        if cached:
            return Response(content=cached, media_type="image/jpeg")

    # Fetch from Frigate
    url = f"{settings.frigate.frigate_url}/api/events/{event_id}/snapshot.jpg"
    client = get_http_client()
    headers = frigate_client._get_headers()
    try:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.snapshot_not_found", lang)
            )
        resp.raise_for_status()

        # Cache the response
        if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
            await media_cache.cache_snapshot(event_id, resp.content)

        return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"))
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
        )


@router.get("/frigate/camera/{camera}/latest.jpg")
async def proxy_latest_camera_snapshot(
    request: Request,
    camera: str = Path(..., min_length=1, max_length=64)
):
    """Proxy latest snapshot for a camera from Frigate."""
    lang = get_user_language(request)

    # Require owner access (query token or Authorization header). Avoid Depends so query token works.
    if settings.auth.enabled and not settings.public_access.enabled:
        token = request.query_params.get("token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            raise HTTPException(status_code=403, detail="Owner privileges required for this operation")
        try:
            token_data = verify_token(token)
            if token_data.auth_level != AuthLevel.OWNER:
                raise HTTPException(status_code=403, detail="Owner privileges required for this operation")
        except HTTPException:
            raise HTTPException(status_code=403, detail="Owner privileges required for this operation")

    if not validate_camera_name(camera):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    url = f"{settings.frigate.frigate_url}/api/{camera}/latest.jpg"
    client = get_http_client()
    headers = frigate_client._get_headers()
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"))
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
        )

@router.head("/frigate/{event_id}/clip.mp4")
@guest_rate_limit()
async def check_clip_exists(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Check if a clip exists for an event by checking the event details."""
    lang = get_user_language(request)

    if not settings.frigate.clips_enabled:
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    await require_event_access(event_id, auth, lang)

    # Frigate doesn't support HEAD for clips, so check event exists instead
    url = f"{settings.frigate.frigate_url}/api/events/{event_id}"
    client = get_http_client()
    headers = frigate_client._get_headers()
    try:
        resp = await client.get(url, headers=headers, timeout=10.0)
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.event_not_found", lang)
            )
        resp.raise_for_status()
        # Check if event has a clip
        event_data = resp.json()
        has_clip = event_data.get("has_clip", False)
        if not has_clip:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_available", lang)
            )
        return Response(status_code=200)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
        )


@router.get("/frigate/{event_id}/clip.mp4")
@guest_rate_limit()
async def proxy_clip(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Proxy video clip from Frigate with Range support and streaming."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not settings.frigate.clips_enabled:
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    await require_event_access(event_id, auth, lang)

    # Check cache first
    if settings.media_cache.enabled and settings.media_cache.cache_clips:
        cached_path = media_cache.get_clip_path(event_id)
        if cached_path:
            # Serve from cache - FileResponse handles Range requests automatically
            return FileResponse(
                path=cached_path,
                media_type="video/mp4",
                filename=f"{event_id}.mp4"
            )

    # Verify clip exists in Frigate before attempting download
    try:
        event_data = await frigate_client.get_event(event_id)
        if not event_data:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.event_not_found", lang)
            )
        if not event_data.get("has_clip", False):
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_available", lang)
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        # If checking fails, proceed cautiously (maybe Frigate API is weird) but log it
        # Or better, just fail here to prevent empty downloads
        pass

    clip_url = f"{settings.frigate.frigate_url}/api/events/{event_id}/clip.mp4"
    headers = frigate_client._get_headers()

    # Forward Range header if present (only when not caching)
    range_header = request.headers.get("range")
    should_cache = settings.media_cache.enabled and settings.media_cache.cache_clips
    
    if range_header and not should_cache:
        headers["Range"] = range_header

    # We need to maintain the client context for the duration of the streaming response
    client = httpx.AsyncClient(timeout=120.0)
    req = client.build_request("GET", clip_url, headers=headers)
    
    # Manually handle the request to inspect status before streaming
    r = await client.send(req, stream=True)
    
    if r.status_code == 404:
        await r.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
        )

    # If caching is enabled, download and cache the clip first (blocking operation)
    if should_cache:
        try:
            cached_path = await media_cache.cache_clip_streaming(event_id, r.aiter_bytes())
            await r.aclose()
            await client.aclose()

            if cached_path:
                return FileResponse(
                    path=cached_path,
                    media_type="video/mp4",
                    filename=f"{event_id}.mp4"
                )
            
            # If caching returned None, it means the file was empty (0 bytes) or failed.
            # Do NOT fallback to streaming the broken content.
            raise HTTPException(
                status_code=502,
                detail=i18n_service.translate("errors.proxy.empty_clip", lang)
            )

        except HTTPException:
            raise
        except Exception:
            # Ensure cleanup if something goes wrong during caching attempt
            await r.aclose()
            await client.aclose()
            # If it was a generic exception (not our empty file check), we might try direct streaming
            # but usually it's safer to fail.
            raise HTTPException(
                status_code=502,
                detail=i18n_service.translate("errors.proxy.media_fetch_failed", lang)
            )

    # Stream directly from Frigate
    response_headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename={event_id}.mp4",
    }

    # If we are here, we are proxying directly.
    # Check if we got valid content length from Frigate to ensure it's not empty
    content_len = r.headers.get("content-length")
    if content_len and int(content_len) == 0:
        await r.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.empty_clip", lang)
        )

    if "content-length" in r.headers:
        response_headers["Content-Length"] = r.headers["content-length"]
    if "content-range" in r.headers:
        response_headers["Content-Range"] = r.headers["content-range"]
    if "content-type" in r.headers:
        response_headers["Content-Type"] = r.headers["content-type"]
    else:
        response_headers["Content-Type"] = "video/mp4"

    async def cleanup():
        await r.aclose()
        await client.aclose()

    return StreamingResponse(
        r.aiter_bytes(),
        status_code=r.status_code,
        headers=response_headers,
        background=BackgroundTask(cleanup)
    )


@router.get("/frigate/{event_id}/clip-thumbnails.vtt")
@guest_rate_limit()
async def proxy_clip_thumbnails_vtt(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Return WebVTT timeline preview metadata for a clip."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not settings.frigate.clips_enabled:
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    await require_event_access(event_id, auth, lang)

    try:
        event_data = await frigate_client.get_event(event_id)
        if not event_data:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.event_not_found", lang)
            )
        if not event_data.get("has_clip", False):
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_available", lang)
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.media_fetch_failed", lang)
        )

    await _ensure_preview_assets(event_id, lang)
    manifest_json = await media_cache.get_preview_manifest(event_id)
    if not manifest_json:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.preview_not_found", lang)
        )

    try:
        manifest = json.loads(manifest_json)
        cues = manifest.get("cues", [])
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=i18n_service.translate("errors.proxy.preview_generation_failed", lang)
        )

    sprite_url = _build_sprite_url(request, event_id)
    lines = ["WEBVTT", ""]
    for cue in cues:
        start = _format_vtt_timestamp(float(cue["start"]))
        end = _format_vtt_timestamp(float(cue["end"]))
        x = int(cue["x"])
        y = int(cue["y"])
        w = int(cue["w"])
        h = int(cue["h"])
        lines.append(f"{start} --> {end}")
        lines.append(f"{sprite_url}#xywh={x},{y},{w},{h}")
        lines.append("")

    return Response(
        content="\n".join(lines),
        media_type="text/vtt; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/frigate/{event_id}/clip-thumbnails.jpg")
@guest_rate_limit()
async def proxy_clip_thumbnails_sprite(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Return generated sprite image for clip timeline previews."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not settings.frigate.clips_enabled:
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    await require_event_access(event_id, auth, lang)
    await _ensure_preview_assets(event_id, lang)

    sprite_path = media_cache.get_preview_sprite_path(event_id)
    if not sprite_path:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.preview_not_found", lang)
        )

    return FileResponse(
        path=sprite_path,
        media_type="image/jpeg",
        filename=f"{event_id}-thumbnails.jpg",
        headers={"Cache-Control": "private, max-age=300"},
    )

@router.get("/frigate/{event_id}/thumbnail.jpg")
@guest_rate_limit()
async def proxy_thumb(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    await require_event_access(event_id, auth, lang)

    # Thumbnails share cache with snapshots (they're the same image in Frigate)
    # Check cache first
    if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
        cached = await media_cache.get_snapshot(event_id)
        if cached:
            return Response(content=cached, media_type="image/jpeg")

    url = f"{settings.frigate.frigate_url}/api/events/{event_id}/thumbnail.jpg"
    client = get_http_client()
    headers = frigate_client._get_headers()
    try:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.thumbnail_not_found", lang)
            )
        resp.raise_for_status()

        # Cache the response (as snapshot since they're interchangeable)
        if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
            await media_cache.cache_snapshot(event_id, resp.content)

        return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"))
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.proxy.frigate_timeout", lang)
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=i18n_service.translate("errors.proxy.frigate_error", lang, status_code=e.response.status_code)
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.connection_failed", lang, url=settings.frigate.frigate_url)
        )
