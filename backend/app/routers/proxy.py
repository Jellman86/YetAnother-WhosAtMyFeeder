import asyncio
import json
import re
import hashlib
import secrets
from pathlib import Path as FilePath
from time import perf_counter
from tempfile import NamedTemporaryFile
from urllib.parse import quote_plus
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Response, Path, Request, Depends, Security
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from fastapi.security import HTTPAuthorizationCredentials
import httpx
import sqlite3
import structlog
from prometheus_client import Counter, Histogram
from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.auth import AuthContext, AuthLevel, require_owner, verify_token, security
from app.auth_legacy import get_auth_context_with_legacy, api_key_header, api_key_query
from app.ratelimit import guest_rate_limit, share_create_rate_limit
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.utils.public_access import effective_public_media_days

router = APIRouter()

# Shared HTTP client for better connection pooling
_http_client: httpx.AsyncClient | None = None
_preview_locks: dict[str, asyncio.Lock] = {}

VIDEO_PREVIEW_REQUESTS = Counter(
    "video_preview_requests_total",
    "Total timeline preview endpoint requests",
    ["endpoint", "outcome"],
)
VIDEO_PREVIEW_GENERATION = Counter(
    "video_preview_generation_total",
    "Total timeline preview generation attempts",
    ["outcome"],
)
VIDEO_PREVIEW_GENERATION_SECONDS = Histogram(
    "video_preview_generation_seconds",
    "Duration of timeline preview generation",
    ["outcome"],
)


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
    # Return a path-only URL so WebVTT cues remain valid regardless of
    # reverse-proxy Host header rewriting.
    sprite_url = request.url_for("proxy_clip_thumbnails_sprite", event_id=event_id).path
    params: list[str] = []
    share_token = request.query_params.get("share")
    if share_token:
        params.append(f"share={quote_plus(share_token)}")
    token = request.query_params.get("token")
    if token:
        params.append(f"token={quote_plus(token)}")
    if params:
        sprite_url = f"{sprite_url}?{'&'.join(params)}"
    return sprite_url


SHARE_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{16,256}$')


class VideoShareCreateRequest(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=64)
    expires_in_minutes: int = Field(default=24 * 60, ge=5, le=7 * 24 * 60)
    watermark_label: str | None = Field(default=None, max_length=64)


class VideoShareCreateResponse(BaseModel):
    link_id: int
    event_id: str
    token: str
    share_url: str
    expires_at: str
    expires_in_minutes: int
    watermark_label: str | None = None


class VideoShareInfoResponse(BaseModel):
    event_id: str
    expires_at: str
    watermark_label: str | None = None


class VideoShareLinkItemResponse(BaseModel):
    id: int
    event_id: str
    created_by: str | None = None
    watermark_label: str | None = None
    created_at: str
    expires_at: str
    is_active: bool
    remaining_seconds: int


class VideoShareLinkListResponse(BaseModel):
    event_id: str
    links: list[VideoShareLinkItemResponse]


class VideoShareLinkUpdateRequest(BaseModel):
    expires_in_minutes: int | None = Field(default=None, ge=5, le=7 * 24 * 60)
    watermark_label: str | None = Field(default=None, max_length=64)


class VideoShareRevokeResponse(BaseModel):
    status: str
    event_id: str
    link_id: int


def _iso_or_now(value: datetime | None) -> str:
    return (value or datetime.utcnow()).isoformat()


def _build_video_share_link_item(row: tuple[object, ...], now: datetime | None = None) -> VideoShareLinkItemResponse:
    current = now or datetime.utcnow()
    link_id, event_id, created_by, watermark_label, created_raw, expires_raw, revoked = row
    created_at = _parse_db_timestamp(created_raw)
    expires_at = _parse_db_timestamp(expires_raw)

    if not expires_at:
        expires_at = current

    remaining_seconds = max(0, int((expires_at - current).total_seconds()))
    is_active = (not bool(revoked)) and remaining_seconds > 0

    return VideoShareLinkItemResponse(
        id=int(link_id),
        event_id=str(event_id),
        created_by=str(created_by) if created_by is not None else None,
        watermark_label=str(watermark_label) if watermark_label is not None else None,
        created_at=_iso_or_now(created_at),
        expires_at=_iso_or_now(expires_at),
        is_active=is_active,
        remaining_seconds=remaining_seconds,
    )


def _hash_share_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_db_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                if fmt is None:
                    dt = datetime.fromisoformat(normalized)
                else:
                    dt = datetime.strptime(value, fmt)
                # Normalize any timezone-aware values to naive UTC for comparison/storage consistency.
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                continue
    return None


async def _resolve_video_share_token(share_token: str, event_id: str | None = None) -> dict[str, object] | None:
    if not SHARE_TOKEN_PATTERN.match(share_token):
        return None

    token_hash = _hash_share_token(share_token)
    async with get_db() as db:
        async with db.execute(
            """
            SELECT frigate_event, watermark_label, expires_at, revoked
            FROM video_share_links
            WHERE token_hash = ?
            LIMIT 1
            """,
            (token_hash,),
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        return None

    frigate_event, watermark_label, expires_raw, revoked = row
    expires_at = _parse_db_timestamp(expires_raw)
    if not expires_at:
        return None
    if bool(revoked):
        return None
    if expires_at <= datetime.utcnow():
        return None
    if event_id and frigate_event != event_id:
        return None

    return {
        "frigate_event": frigate_event,
        "watermark_label": watermark_label,
        "expires_at": expires_at,
    }


async def _create_video_share_token(
    event_id: str,
    expires_in_minutes: int,
    created_by: str | None,
    watermark_label: str | None,
) -> tuple[int, str, datetime]:
    expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

    async with get_db() as db:
        for _ in range(5):
            token = secrets.token_urlsafe(24)
            token_hash = _hash_share_token(token)
            try:
                cursor = await db.execute(
                    """
                    INSERT INTO video_share_links
                    (token_hash, frigate_event, created_by, watermark_label, expires_at, revoked)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (token_hash, event_id, created_by, watermark_label, expires_at),
                )
                await db.commit()
                link_id = int(cursor.lastrowid or 0)
                return link_id, token, expires_at
            except sqlite3.IntegrityError:
                # Extremely unlikely hash collision/token replay; retry with a fresh token.
                continue

    raise RuntimeError("Failed to create a unique video share token")


async def _list_active_video_share_links(event_id: str) -> list[VideoShareLinkItemResponse]:
    now = datetime.utcnow()
    async with get_db() as db:
        async with db.execute(
            """
            SELECT id, frigate_event, created_by, watermark_label, created_at, expires_at, revoked
            FROM video_share_links
            WHERE frigate_event = ?
              AND revoked = 0
              AND expires_at > ?
            ORDER BY created_at DESC, id DESC
            """,
            (event_id, now),
        ) as cursor:
            rows = await cursor.fetchall()

    return [_build_video_share_link_item(row, now=now) for row in rows]


async def _update_video_share_link(
    event_id: str,
    link_id: int,
    *,
    expires_in_minutes: int | None,
    watermark_provided: bool,
    watermark_label: str | None,
) -> VideoShareLinkItemResponse | None:
    now = datetime.utcnow()
    updates: list[str] = []
    params: list[object] = []

    if expires_in_minutes is not None:
        updates.append("expires_at = ?")
        params.append(now + timedelta(minutes=expires_in_minutes))
    if watermark_provided:
        updates.append("watermark_label = ?")
        params.append(watermark_label)

    if not updates:
        return None

    async with get_db() as db:
        async with db.execute(
            """
            SELECT id, frigate_event, created_by, watermark_label, created_at, expires_at, revoked
            FROM video_share_links
            WHERE frigate_event = ?
              AND id = ?
              AND revoked = 0
              AND expires_at > ?
            LIMIT 1
            """,
            (event_id, link_id, now),
        ) as cursor:
            existing = await cursor.fetchone()

        if not existing:
            return None

        update_sql = f"UPDATE video_share_links SET {', '.join(updates)} WHERE frigate_event = ? AND id = ?"
        await db.execute(update_sql, (*params, event_id, link_id))
        await db.commit()

        async with db.execute(
            """
            SELECT id, frigate_event, created_by, watermark_label, created_at, expires_at, revoked
            FROM video_share_links
            WHERE frigate_event = ?
              AND id = ?
            LIMIT 1
            """,
            (event_id, link_id),
        ) as cursor:
            updated = await cursor.fetchone()

    if not updated:
        return None

    return _build_video_share_link_item(updated, now=datetime.utcnow())


async def _revoke_video_share_link(event_id: str, link_id: int) -> bool:
    now = datetime.utcnow()
    async with get_db() as db:
        await db.execute(
            """
            UPDATE video_share_links
            SET revoked = 1
            WHERE frigate_event = ?
              AND id = ?
              AND revoked = 0
              AND expires_at > ?
            """,
            (event_id, link_id, now),
        )
        async with db.execute("SELECT changes()") as cursor:
            row = await cursor.fetchone()
            changed = int(row[0]) if row else 0
        await db.commit()
    return changed > 0


async def cleanup_expired_video_share_links() -> int:
    """Delete stale share links (expired and revoked) to keep table size bounded."""
    now = datetime.utcnow()
    async with get_db() as db:
        await db.execute(
            """
            DELETE FROM video_share_links
            WHERE expires_at <= ?
               OR revoked = 1
            """,
            (now,),
        )
        async with db.execute("SELECT changes()") as cursor:
            row = await cursor.fetchone()
            deleted = int(row[0]) if row else 0
        await db.commit()
    return deleted


def _has_valid_share_context(request: Request, event_id: str) -> bool:
    share = getattr(request.state, "video_share", None)
    return bool(share and share.get("frigate_event") == event_id)


async def get_proxy_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query),
) -> AuthContext:
    share_token = request.query_params.get("share")
    event_id = request.path_params.get("event_id")
    if share_token and event_id and validate_event_id(event_id):
        share = await _resolve_video_share_token(share_token, event_id)
        if share:
            request.state.video_share = share
            return AuthContext(auth_level=AuthLevel.GUEST, username="video_share")

    return await get_auth_context_with_legacy(request, credentials, header_key, query_key)


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


async def _ensure_preview_assets(event_id: str, lang: str) -> str:
    """Ensure preview sprite + manifest exist in media cache."""
    from app.services.media_cache import media_cache
    from app.services.video_preview_service import video_preview_service

    if not settings.media_cache.enabled:
        raise HTTPException(
            status_code=503,
            detail=i18n_service.translate("errors.proxy.preview_disabled", lang)
        )

    if media_cache.get_preview_sprite_path(event_id) and await media_cache.get_preview_manifest(event_id):
        return "cache_hit"

    lock = _preview_lock(event_id)
    async with lock:
        # Another request may have generated assets while waiting.
        if media_cache.get_preview_sprite_path(event_id) and await media_cache.get_preview_manifest(event_id):
            return "cache_hit"

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
            started = perf_counter()
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
                VIDEO_PREVIEW_GENERATION.labels(outcome="cache_write_failed").inc()
                VIDEO_PREVIEW_GENERATION_SECONDS.labels(outcome="cache_write_failed").observe(perf_counter() - started)
                raise HTTPException(
                    status_code=500,
                    detail=i18n_service.translate("errors.proxy.preview_generation_failed", lang)
                )
            VIDEO_PREVIEW_GENERATION.labels(outcome="generated").inc()
            VIDEO_PREVIEW_GENERATION_SECONDS.labels(outcome="generated").observe(perf_counter() - started)
            return "generated"
        except HTTPException:
            raise
        except Exception:
            VIDEO_PREVIEW_GENERATION.labels(outcome="error").inc()
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

@router.post("/video-share", response_model=VideoShareCreateResponse)
@share_create_rate_limit()
async def create_video_share_link(
    request: Request,
    payload: VideoShareCreateRequest,
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required for this operation")

    event_id = payload.event_id.strip()
    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    if not settings.frigate.clips_enabled:
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    try:
        event_data = await frigate_client.get_event(event_id)
    except Exception:
        event_data = None

    if not event_data or not event_data.get("has_clip", False):
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.clip_not_available", lang)
        )

    watermark = payload.watermark_label.strip() if payload.watermark_label else None
    if watermark == "":
        watermark = None

    if watermark is None:
        watermark = auth.username or "Shared"

    link_id, token, expires_at = await _create_video_share_token(
        event_id=event_id,
        expires_in_minutes=payload.expires_in_minutes,
        created_by=auth.username,
        watermark_label=watermark,
    )

    base = str(request.base_url).rstrip("/")
    share_url = (
        f"{base}/events?event={quote_plus(event_id)}&video=1&share={quote_plus(token)}"
    )

    structlog.get_logger().info(
        "VIDEO_SHARE_AUDIT: Share link created",
        event_type="video_share_link_created",
        event_id=event_id,
        link_id=link_id,
        created_by=auth.username,
        expires_in_minutes=payload.expires_in_minutes,
        watermark_label=watermark,
    )

    return VideoShareCreateResponse(
        link_id=link_id,
        event_id=event_id,
        token=token,
        share_url=share_url,
        expires_at=expires_at.isoformat(),
        expires_in_minutes=payload.expires_in_minutes,
        watermark_label=watermark,
    )


@router.get("/video-share/{event_id}", response_model=VideoShareInfoResponse)
async def get_video_share_info(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)
    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    share = getattr(request.state, "video_share", None)
    if not share or share.get("frigate_event") != event_id:
        if auth.is_owner:
            share_token = request.query_params.get("share")
            if share_token:
                share = await _resolve_video_share_token(share_token, event_id)
        if not share:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.event_not_found", lang)
            )

    expires_at = share.get("expires_at")
    if not isinstance(expires_at, datetime):
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.event_not_found", lang)
        )

    return VideoShareInfoResponse(
        event_id=event_id,
        expires_at=expires_at.isoformat(),
        watermark_label=share.get("watermark_label"),
    )


@router.get("/video-share/{event_id}/links", response_model=VideoShareLinkListResponse)
async def list_video_share_links(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required for this operation")

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    links = await _list_active_video_share_links(event_id)
    return VideoShareLinkListResponse(event_id=event_id, links=links)


@router.patch("/video-share/{event_id}/links/{link_id}", response_model=VideoShareLinkItemResponse)
async def update_video_share_link(
    request: Request,
    payload: VideoShareLinkUpdateRequest,
    event_id: str = Path(..., min_length=1, max_length=64),
    link_id: int = Path(..., ge=1),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required for this operation")

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    fields_set = set(payload.model_fields_set)
    has_expiry_update = "expires_in_minutes" in fields_set
    has_watermark_update = "watermark_label" in fields_set
    if not has_expiry_update and not has_watermark_update:
        raise HTTPException(status_code=400, detail="At least one update field must be provided")

    watermark: str | None = None
    if has_watermark_update:
        raw_watermark = payload.watermark_label
        if raw_watermark is not None:
            raw_watermark = raw_watermark.strip()
        watermark = raw_watermark or None

    updated = await _update_video_share_link(
        event_id=event_id,
        link_id=link_id,
        expires_in_minutes=payload.expires_in_minutes if has_expiry_update else None,
        watermark_provided=has_watermark_update,
        watermark_label=watermark,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.event_not_found", lang)
        )

    structlog.get_logger().info(
        "VIDEO_SHARE_AUDIT: Share link updated",
        event_type="video_share_link_updated",
        event_id=event_id,
        link_id=link_id,
        updated_by=auth.username,
        expires_in_minutes=payload.expires_in_minutes if has_expiry_update else None,
        watermark_updated=has_watermark_update,
    )
    return updated


@router.post("/video-share/{event_id}/links/{link_id}/revoke", response_model=VideoShareRevokeResponse)
async def revoke_video_share_link(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    link_id: int = Path(..., ge=1),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required for this operation")

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    revoked = await _revoke_video_share_link(event_id=event_id, link_id=link_id)
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.event_not_found", lang)
        )

    structlog.get_logger().info(
        "VIDEO_SHARE_AUDIT: Share link revoked",
        event_type="video_share_link_revoked",
        event_id=event_id,
        link_id=link_id,
        revoked_by=auth.username,
    )
    return VideoShareRevokeResponse(status="revoked", event_id=event_id, link_id=link_id)


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
    auth: AuthContext = Depends(get_proxy_auth_context)
):
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    if not _has_valid_share_context(request, event_id):
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
    auth: AuthContext = Depends(get_proxy_auth_context)
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

    if not _has_valid_share_context(request, event_id):
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
    auth: AuthContext = Depends(get_proxy_auth_context)
):
    """Proxy video clip from Frigate with Range support and streaming."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)
    download_requested = request.query_params.get("download") == "1"
    request_started = perf_counter()
    log = structlog.get_logger()

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

    if not _has_valid_share_context(request, event_id):
        await require_event_access(event_id, auth, lang)

    if download_requested and (not auth.is_owner) and (not settings.public_access.allow_clip_downloads):
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.proxy.download_forbidden", lang)
        )

    # Check cache first
    if settings.media_cache.enabled and settings.media_cache.cache_clips:
        cached_path = media_cache.get_clip_path(event_id)
        if cached_path:
            log.info(
                "proxy_clip_cache_hit",
                event_id=event_id,
                download=download_requested,
                duration_ms=round((perf_counter() - request_started) * 1000, 2),
            )
            # Serve from cache - FileResponse handles Range requests automatically
            return FileResponse(
                path=cached_path,
                media_type="video/mp4",
                filename=f"{event_id}.mp4",
                headers={
                    "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}.mp4"
                }
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
    log.debug(
        "proxy_clip_start",
        event_id=event_id,
        download=download_requested,
        has_range=bool(range_header),
        should_cache=should_cache,
    )
    
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
                log.info(
                    "proxy_clip_cached_from_frigate",
                    event_id=event_id,
                    download=download_requested,
                    duration_ms=round((perf_counter() - request_started) * 1000, 2),
                )
                return FileResponse(
                    path=cached_path,
                    media_type="video/mp4",
                    filename=f"{event_id}.mp4",
                    headers={
                        "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}.mp4"
                    }
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
        "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}.mp4",
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

    log.info(
        "proxy_clip_streaming_from_frigate",
        event_id=event_id,
        download=download_requested,
        status_code=r.status_code,
        has_range=bool(range_header),
        content_length=r.headers.get("content-length"),
        duration_ms=round((perf_counter() - request_started) * 1000, 2),
    )

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
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    """Return WebVTT timeline preview metadata for a clip."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)
    endpoint_name = "vtt"
    request_started = perf_counter()
    log = structlog.get_logger()

    if not settings.frigate.clips_enabled:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_403").inc()
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    if not validate_event_id(event_id):
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_400").inc()
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    if not _has_valid_share_context(request, event_id):
        await require_event_access(event_id, auth, lang)

    try:
        event_data = await frigate_client.get_event(event_id)
        if not event_data:
            VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_404").inc()
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.event_not_found", lang)
            )
        if not event_data.get("has_clip", False):
            VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_404").inc()
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_available", lang)
            )
    except HTTPException:
        raise
    except Exception:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_502").inc()
        raise HTTPException(
            status_code=502,
            detail=i18n_service.translate("errors.proxy.media_fetch_failed", lang)
        )

    try:
        generation_outcome = await _ensure_preview_assets(event_id, lang)
    except HTTPException as exc:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome=f"http_{exc.status_code}").inc()
        raise
    manifest_json = await media_cache.get_preview_manifest(event_id)
    if not manifest_json:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_404").inc()
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.preview_not_found", lang)
        )

    try:
        manifest = json.loads(manifest_json)
        cues = manifest.get("cues", [])
    except Exception:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_500").inc()
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

    VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome=f"ok_{generation_outcome}").inc()
    log.info(
        "proxy_clip_thumbnails_vtt_served",
        event_id=event_id,
        generation_outcome=generation_outcome,
        cue_count=len(cues),
        duration_ms=round((perf_counter() - request_started) * 1000, 2),
    )
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
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    """Return generated sprite image for clip timeline previews."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)
    endpoint_name = "sprite"
    request_started = perf_counter()
    log = structlog.get_logger()

    if not settings.frigate.clips_enabled:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_403").inc()
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    if not validate_event_id(event_id):
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_400").inc()
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    if not _has_valid_share_context(request, event_id):
        await require_event_access(event_id, auth, lang)
    try:
        generation_outcome = await _ensure_preview_assets(event_id, lang)
    except HTTPException as exc:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome=f"http_{exc.status_code}").inc()
        raise

    sprite_path = media_cache.get_preview_sprite_path(event_id)
    if not sprite_path:
        VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome="http_404").inc()
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.preview_not_found", lang)
        )

    VIDEO_PREVIEW_REQUESTS.labels(endpoint=endpoint_name, outcome=f"ok_{generation_outcome}").inc()
    log.info(
        "proxy_clip_thumbnails_sprite_served",
        event_id=event_id,
        generation_outcome=generation_outcome,
        duration_ms=round((perf_counter() - request_started) * 1000, 2),
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
    auth: AuthContext = Depends(get_proxy_auth_context)
):
    from app.services.media_cache import media_cache

    lang = get_user_language(request)

    if not validate_event_id(event_id):
        raise HTTPException(
            status_code=400,
            detail=i18n_service.translate("errors.proxy.invalid_event_id", lang)
        )

    if not _has_valid_share_context(request, event_id):
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
