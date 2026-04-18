import asyncio
import json
import re
import hashlib
import weakref
import secrets
import io
from pathlib import Path as FilePath
from time import perf_counter
from tempfile import NamedTemporaryFile
from urllib.parse import quote_plus, urlsplit
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
from typing import Literal
from app.config import settings
from app.services.bird_crop_service import bird_crop_service
from app.services.frigate_client import frigate_client
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.utils.frigate_recording import evaluate_recording_clip_capability
from app.auth import (
    AuthContext,
    AuthLevel,
    require_owner,
    verify_token,
    security,
    get_auth_context_with_legacy,
    api_key_header,
    api_key_query,
)
from app.ratelimit import guest_rate_limit, share_create_rate_limit
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.utils.api_datetime import serialize_api_datetime
from app.utils.public_access import effective_public_media_days

router = APIRouter()

# Shared HTTP client for better connection pooling
_http_client: httpx.AsyncClient | None = None
# WeakValueDictionary: entries are automatically removed once no coroutine holds
# a reference to the lock, preventing unbounded growth with unique event IDs.
_preview_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
_recording_clip_fetch_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
_snapshot_generation_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

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
SNAPSHOT_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}
HIGH_QUALITY_SNAPSHOT_SOURCES = {"high_quality_snapshot", "high_quality_bird_crop"}


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def _cached_snapshot_allowed_for_current_settings(media_cache, event_id: str) -> bool:
    """Return False when a cached HQ snapshot should not be served under current settings."""
    if settings.media_cache.high_quality_event_snapshots:
        return True

    metadata = await media_cache.get_snapshot_metadata(event_id)
    source = str((metadata or {}).get("source") or "").strip()
    # Legacy cached snapshots have no metadata. When HQ snapshots are disabled,
    # refresh them once so old full-frame HQ replacements do not keep winning.
    if not source or source in HIGH_QUALITY_SNAPSHOT_SOURCES or source.startswith("hq_candidate_"):
        await media_cache.delete_snapshot(event_id)
        await media_cache.delete_thumbnail(event_id)
        return False
    return True

# Validate event_id format (Frigate uses UUIDs, numeric IDs, or timestamp-based IDs with dots)
EVENT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_.]+$')
CAMERA_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')

def validate_event_id(event_id: str) -> bool:
    return bool(EVENT_ID_PATTERN.match(event_id)) and len(event_id) <= 64

def validate_camera_name(camera: str) -> bool:
    return bool(CAMERA_NAME_PATTERN.match(camera)) and len(camera) <= 64


def _is_probably_thumbnail_sized_snapshot(image_bytes: bytes) -> bool:
    """Detect obviously thumbnail-sized cached "snapshots" from earlier shared-cache behavior."""
    if len(image_bytes) > 16_384:
        return False

    try:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
    except Exception:
        return False

    return max(width, height) <= 256


def _build_display_thumbnail_from_snapshot(image_bytes: bytes) -> bytes:
    """Build a card-sized JPEG thumbnail from the canonical snapshot."""
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as img:
        rendered = img.convert("RGB")
        rendered.thumbnail((960, 720), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        rendered.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue()


def _cached_thumbnail_allowed_for_current_snapshot(metadata: dict | None, *, has_snapshot: bool) -> bool:
    """Return whether a cached thumbnail still matches the configured snapshot source."""
    source = str((metadata or {}).get("source") or "").strip()
    if has_snapshot:
        # Legacy thumbnails had no source metadata. Once a canonical snapshot is
        # available, regenerate from it so cards follow the current snapshot config.
        return source == "snapshot_derived"
    # Without a canonical snapshot, keep old cached thumbnails for compatibility
    # unless metadata proves they were derived from a now-missing snapshot.
    if not source:
        return True
    return source == "frigate_thumbnail"


def _preview_lock(event_id: str) -> asyncio.Lock:
    lock = _preview_locks.get(event_id)
    if lock is None:
        lock = asyncio.Lock()
        _preview_locks[event_id] = lock
    return lock


def _recording_clip_fetch_lock(event_id: str) -> asyncio.Lock:
    lock = _recording_clip_fetch_locks.get(event_id)
    if lock is None:
        lock = asyncio.Lock()
        _recording_clip_fetch_locks[event_id] = lock
    return lock


def _snapshot_generation_lock(event_id: str) -> asyncio.Lock:
    lock = _snapshot_generation_locks.get(event_id)
    if lock is None:
        lock = asyncio.Lock()
        _snapshot_generation_locks[event_id] = lock
    return lock


def _hq_bird_crop_feature_enabled() -> bool:
    return bool(
        settings.media_cache.enabled
        and settings.media_cache.cache_snapshots
        and settings.media_cache.high_quality_event_snapshots
        and settings.media_cache.high_quality_event_snapshot_bird_crop
    )


def _bird_crop_runtime_available() -> bool:
    get_status = getattr(bird_crop_service, "get_status", None)
    if not callable(get_status):
        return True
    try:
        status = get_status() or {}
    except Exception:
        return True
    if not isinstance(status, dict):
        return True
    if status.get("installed") is False:
        return False
    if status.get("enabled_for_runtime") is False:
        return False
    return True


async def _build_snapshot_status(event_id: str):
    from app.services.media_cache import media_cache

    cached = False
    source: str | None = None

    if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
        cached = await media_cache.get_snapshot(event_id) is not None
        if cached:
            metadata = await media_cache.get_snapshot_metadata(event_id)
            source = str((metadata or {}).get("source") or "").strip() or None

    already_hq_bird_crop = source == "high_quality_bird_crop"
    can_generate_hq_bird_crop = bool(
        _hq_bird_crop_feature_enabled()
        and _bird_crop_runtime_available()
        and not already_hq_bird_crop
    )

    return SnapshotStatusResponse(
        event_id=event_id,
        cached=cached,
        source=source,
        high_quality_event_snapshots_enabled=bool(settings.media_cache.high_quality_event_snapshots),
        high_quality_bird_crop_enabled=bool(settings.media_cache.high_quality_event_snapshot_bird_crop),
        already_hq_bird_crop=already_hq_bird_crop,
        can_generate_hq_bird_crop=can_generate_hq_bird_crop,
    )


async def _list_snapshot_candidates(event_id: str) -> list[dict]:
    async with get_db() as db:
        repo = DetectionRepository(db)
        return await repo.list_snapshot_candidates(event_id)


def _candidate_thumbnail_url(request: Request, event_id: str, candidate_id: str) -> str:
    return request.url_for(
        "get_snapshot_candidate_thumbnail",
        event_id=event_id,
        candidate_id=candidate_id,
    ).path


async def _build_snapshot_candidates_response(request: Request, event_id: str) -> "SnapshotCandidateListResponse":
    status = await _build_snapshot_status(event_id)
    candidates = await _list_snapshot_candidates(event_id)
    current_source = status.source
    current_candidate_id = None
    if current_source and current_source.startswith("hq_candidate_"):
        for candidate in candidates:
            if str(candidate.get("snapshot_source") or "") == current_source:
                current_candidate_id = str(candidate.get("candidate_id") or "")
                break
    return SnapshotCandidateListResponse(
        event_id=event_id,
        current_source=current_source,
        current_candidate_id=current_candidate_id,
        candidates=[
            SnapshotCandidateResponse(
                candidate_id=str(candidate.get("candidate_id") or ""),
                frame_index=int(candidate.get("frame_index") or 0),
                frame_offset_seconds=(
                    float(candidate["frame_offset_seconds"])
                    if candidate.get("frame_offset_seconds") is not None
                    else None
                ),
                source_mode=str(candidate.get("source_mode") or "full_frame"),
                clip_variant=str(candidate.get("clip_variant") or "event"),
                crop_box=[float(value) for value in (candidate.get("crop_box") or [])] or None,
                crop_confidence=(
                    float(candidate["crop_confidence"])
                    if candidate.get("crop_confidence") is not None
                    else None
                ),
                classifier_label=(
                    str(candidate.get("classifier_label"))
                    if candidate.get("classifier_label") is not None
                    else None
                ),
                classifier_score=(
                    float(candidate["classifier_score"])
                    if candidate.get("classifier_score") is not None
                    else None
                ),
                ranking_score=float(candidate.get("ranking_score") or 0.0),
                selected=bool(candidate.get("selected")),
                snapshot_source=(
                    str(candidate.get("snapshot_source"))
                    if candidate.get("snapshot_source") is not None
                    else None
                ),
                thumbnail_url=_candidate_thumbnail_url(
                    request,
                    event_id,
                    str(candidate.get("candidate_id") or ""),
                ),
            )
            for candidate in candidates
        ],
    )


def _pick_snapshot_candidate(candidates: list[dict], request: "SnapshotApplyRequest") -> dict | None:
    if request.mode == "candidate":
        target_id = str(request.candidate_id or "").strip()
        return next((item for item in candidates if str(item.get("candidate_id") or "") == target_id), None)
    if request.mode == "auto_best":
        return next((item for item in candidates if bool(item.get("selected"))), candidates[0] if candidates else None)
    mode_to_source = {
        "full_frame": "full_frame",
        "frigate_hint_crop": "frigate_hint_crop",
        "model_crop": "model_crop",
    }
    target_source = mode_to_source.get(request.mode)
    if not target_source:
        return None
    return next((item for item in candidates if str(item.get("source_mode") or "") == target_source), None)


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


def _share_base_url(request: Request) -> str:
    """Resolve the base URL used for externally shared links."""
    configured = (settings.public_access.external_base_url or "").strip()
    if configured:
        parsed = urlsplit(configured)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return configured.rstrip("/")
        structlog.get_logger().warning(
            "Invalid PUBLIC_ACCESS__EXTERNAL_BASE_URL; falling back to request base",
            configured_value=configured,
        )
    return str(request.base_url).rstrip("/")


SHARE_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{16,256}$')


class VideoShareCreateRequest(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=64)
    expires_in_minutes: int = Field(default=24 * 60, ge=5, le=7 * 24 * 60)
    watermark_label: str | None = Field(default=None, max_length=64)
    clip_variant: Literal["event", "recording"] = Field(default="event")


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


class RecordingClipFetchResponse(BaseModel):
    event_id: str
    status: Literal["ready"]
    clip_variant: Literal["recording"] = "recording"
    cached: bool


class SnapshotStatusResponse(BaseModel):
    event_id: str
    cached: bool
    source: str | None = None
    high_quality_event_snapshots_enabled: bool
    high_quality_bird_crop_enabled: bool
    already_hq_bird_crop: bool
    can_generate_hq_bird_crop: bool


class SnapshotGenerateResponse(SnapshotStatusResponse):
    status: Literal["already_hq_bird_crop", "generated_hq_bird_crop", "generated_hq_snapshot"]
    result: str


class SnapshotCandidateResponse(BaseModel):
    candidate_id: str
    frame_index: int
    frame_offset_seconds: float | None = None
    source_mode: str
    clip_variant: str
    crop_box: list[float] | None = None
    crop_confidence: float | None = None
    classifier_label: str | None = None
    classifier_score: float | None = None
    ranking_score: float
    selected: bool
    snapshot_source: str | None = None
    thumbnail_url: str | None = None


class SnapshotCandidateListResponse(BaseModel):
    event_id: str
    current_source: str | None = None
    current_candidate_id: str | None = None
    candidates: list[SnapshotCandidateResponse]


class SnapshotApplyRequest(BaseModel):
    mode: Literal[
        "candidate",
        "auto_best",
        "full_frame",
        "frigate_hint_crop",
        "model_crop",
        "revert_original",
    ] = "candidate"
    candidate_id: str | None = None


class SnapshotApplyResponse(SnapshotStatusResponse):
    status: Literal["applied"]
    applied_mode: str
    applied_candidate_id: str | None = None


def _iso_or_now(value: datetime | None) -> str:
    normalized = _normalize_utc_naive(value) or datetime.now(timezone.utc).replace(tzinfo=None)
    serialized = serialize_api_datetime(normalized)
    return serialized or ""


def _normalize_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _build_video_share_link_item(row: tuple[object, ...], now: datetime | None = None) -> VideoShareLinkItemResponse:
    current = _normalize_utc_naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    link_id, event_id, created_by, watermark_label, created_raw, expires_raw, revoked = row
    created_at = _normalize_utc_naive(_parse_db_timestamp(created_raw))
    expires_at = _normalize_utc_naive(_parse_db_timestamp(expires_raw))

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
    if expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
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
    now = datetime.now(timezone.utc)
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


def _normalize_detection_timestamp(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        # Detection rows have historically been stored as naive local wall time.
        # Treat naive values as local time here so full-visit clip windows line up
        # with the detection shown in Explorer instead of being shifted as UTC.
        value = value.astimezone()
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


def _timestamp_from_event_id(event_id: str) -> int | None:
    raw = (event_id or "").strip()
    if not raw:
        return None

    prefix = raw.split("-", 1)[0]
    try:
        parsed = float(prefix)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return int(parsed)


async def _resolve_recording_clip_detection_timestamp(
    event_id: str,
    detection_time: datetime | None,
) -> int | None:
    # Frigate's timestamp-prefixed event ids are the cheapest reliable source.
    # Prefer them so clip probes do not trigger an extra Frigate API lookup.
    event_id_timestamp = _timestamp_from_event_id(event_id)
    if event_id_timestamp is not None:
        return event_id_timestamp

    # Explicit timezone data is already unambiguous, so prefer it before
    # incurring a Frigate API lookup. The network fallback is mainly for
    # legacy naive rows or nonstandard event ids.
    if detection_time is not None and detection_time.tzinfo is not None:
        return _normalize_detection_timestamp(detection_time)

    try:
        event_data = await frigate_client.get_event(event_id)
    except Exception as exc:
        structlog.get_logger().warning(
            "Failed to fetch Frigate event while resolving recording clip timestamp",
            event_id=event_id,
            error=str(exc),
        )
        event_data = None

    if isinstance(event_data, dict):
        start_time = event_data.get("start_time")
        try:
            if start_time is not None:
                parsed = float(start_time)
                if parsed > 0:
                    return int(parsed)
        except (TypeError, ValueError):
            pass

    return _normalize_detection_timestamp(detection_time)


async def _get_recording_clip_context(event_id: str, lang: str) -> tuple[str, int, int]:
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

    if not detection or not detection.detection_time or not detection.camera_name:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.event_not_found", lang)
        )

    detected_at = await _resolve_recording_clip_detection_timestamp(
        event_id,
        detection.detection_time,
    )
    if detected_at is None:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.event_not_found", lang)
        )

    start_ts = max(0, detected_at - settings.frigate.recording_clip_before_seconds)
    end_ts = detected_at + settings.frigate.recording_clip_after_seconds
    if end_ts <= start_ts:
        end_ts = start_ts + 1

    return detection.camera_name, start_ts, end_ts


def _minimum_acceptable_recording_clip_duration_seconds(start_ts: int, end_ts: int) -> float:
    expected = max(1.0, float(end_ts - start_ts))
    tolerance = max(expected - 2.0, expected * 0.9)
    return max(1.0, min(expected, tolerance))


async def _get_valid_cached_recording_clip_path(event_id: str, lang: str):
    from app.services.media_cache import media_cache

    raw_cached_path = None
    if settings.media_cache.enabled:
        raw_cached_path = media_cache.get_recording_clip_path(event_id)
    if not raw_cached_path:
        camera_name, start_ts, end_ts = await _get_recording_clip_context(event_id, lang)
        return None, camera_name, start_ts, end_ts

    try:
        camera_name, start_ts, end_ts = await _get_recording_clip_context(event_id, lang)
    except HTTPException:
        return raw_cached_path, None, None, None

    cached_path = media_cache.get_recording_clip_path(
        event_id,
        min_duration_seconds=_minimum_acceptable_recording_clip_duration_seconds(start_ts, end_ts),
    )
    return cached_path, camera_name, start_ts, end_ts


async def _is_no_recordings_response(response: httpx.Response) -> bool:
    if response.status_code not in {400, 404}:
        return False
    try:
        payload = response.json()
    except Exception:
        payload = None
    if payload is None:
        try:
            await response.aread()
        except Exception:
            return False
        try:
            payload = response.json()
        except Exception:
            payload = None
    message = str((payload or {}).get("message") or response.text or "")
    return "No recordings found for the specified time range" in message


async def _probe_recording_clip_response(
    clip_url: str,
    headers: dict[str, str],
    *,
    timeout: float,
) -> tuple[httpx.AsyncClient, httpx.Response]:
    client = get_http_client()
    req = client.build_request("GET", clip_url, headers=headers, timeout=timeout)
    response = await client.send(req, stream=True)
    return client, response


async def _recording_clip_exists_for_share(event_id: str, lang: str) -> bool:
    if not settings.frigate.clips_enabled or not settings.frigate.recording_clip_enabled:
        raise HTTPException(
            status_code=403,
            detail=i18n_service.translate("errors.clip_disabled", lang)
        )

    cached_path, camera_name, start_ts, end_ts = await _get_valid_cached_recording_clip_path(event_id, lang)
    if cached_path:
        return True

    clip_url = frigate_client.get_camera_recording_clip_url(camera_name, start_ts, end_ts)
    headers = frigate_client._get_headers()
    _client, response = await _probe_recording_clip_response(clip_url, headers, timeout=10.0)
    try:
        if await _is_no_recordings_response(response) or response.status_code == 404:
            return False
        response.raise_for_status()
        return True
    finally:
        await response.aclose()


async def _fetch_recording_clip_ready(event_id: str, lang: str) -> bool:
    from app.services.media_cache import media_cache, _MIN_VALID_CLIP_BYTES

    cached_path, camera_name, start_ts, end_ts = await _get_valid_cached_recording_clip_path(event_id, lang)
    if cached_path:
        return True

    lock = _recording_clip_fetch_lock(event_id)
    async with lock:
        cached_path = media_cache.get_recording_clip_path(
            event_id,
            min_duration_seconds=_minimum_acceptable_recording_clip_duration_seconds(start_ts, end_ts),
        )
        if cached_path:
            return True

        clip_url = frigate_client.get_camera_recording_clip_url(camera_name, start_ts, end_ts)
        headers = frigate_client._get_headers()

        client = httpx.AsyncClient(timeout=120.0)
        req = client.build_request("GET", clip_url, headers=headers)
        response = await client.send(req, stream=True)
        try:
            if await _is_no_recordings_response(response) or response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
                )
            response.raise_for_status()

            should_cache = settings.media_cache.enabled
            if should_cache:
                cached = await media_cache.cache_recording_clip_streaming(event_id, response.aiter_bytes())
                if not cached:
                    raise HTTPException(
                        status_code=404,
                        detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
                    )
                return True

            total_size = 0
            async for chunk in response.aiter_bytes():
                if chunk:
                    total_size += len(chunk)
            if total_size < _MIN_VALID_CLIP_BYTES:
                raise HTTPException(
                    status_code=404,
                    detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
                )
            return True
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
        finally:
            await response.aclose()
            await client.aclose()


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
                # Reject Frigate stub responses (clip not retained).
                # Frigate returns ~78 bytes for expired clips; no valid MP4 is
                # this small, so treat anything under the same threshold used by
                # the media cache as a missing clip rather than crashing OpenCV.
                from app.services.media_cache import _MIN_VALID_CLIP_BYTES
                if len(resp.content) < _MIN_VALID_CLIP_BYTES:
                    raise HTTPException(
                        status_code=404,
                        detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
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

    clip_variant = payload.clip_variant or "event"
    if clip_variant == "event":
        try:
            event_data = await frigate_client.get_event(event_id)
        except Exception:
            event_data = None

        if not event_data or not event_data.get("has_clip", False):
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_available", lang)
            )
    else:
        recording_exists = await _recording_clip_exists_for_share(event_id, lang)
        if not recording_exists:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
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

    base = _share_base_url(request)
    share_url = f"{base}/events?event={quote_plus(event_id)}&video=1&share={quote_plus(token)}"
    if clip_variant == "recording":
        share_url = f"{share_url}&clip=recording"

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


@router.get("/frigate/recording-clip-capability")
async def get_recording_clip_capability(
    auth: AuthContext = Depends(require_owner)
):
    try:
        frigate_config = await frigate_client.get_config()
    except Exception:
        frigate_config = None

    return evaluate_recording_clip_capability(
        frigate_config=frigate_config,
        selected_cameras=settings.frigate.camera,
    )


@router.get("/frigate/{event_id}/snapshot/status", response_model=SnapshotStatusResponse)
async def get_snapshot_status(
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(require_owner),
):
    del auth
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    return await _build_snapshot_status(event_id)


@router.post("/frigate/{event_id}/snapshot/hq-bird-crop", response_model=SnapshotGenerateResponse)
async def generate_hq_bird_crop_snapshot(
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(require_owner),
):
    del auth
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    if not _hq_bird_crop_feature_enabled():
        raise HTTPException(status_code=409, detail="HQ bird crop snapshots are not enabled")
    if not _bird_crop_runtime_available():
        raise HTTPException(status_code=409, detail="Bird crop detector is not available")

    async with _snapshot_generation_lock(event_id):
        before = await _build_snapshot_status(event_id)
        if before.already_hq_bird_crop:
            return SnapshotGenerateResponse(
                **before.model_dump(),
                status="already_hq_bird_crop",
                result="already_hq_bird_crop",
            )

        result = await high_quality_snapshot_service.process_event(event_id)
        after = await _build_snapshot_status(event_id)
        if result == "bird_crop_replaced" or after.already_hq_bird_crop:
            status = "generated_hq_bird_crop"
        elif result == "replaced":
            status = "generated_hq_snapshot"
        else:
            raise HTTPException(status_code=409, detail=f"HQ bird crop generation unavailable: {result}")

        return SnapshotGenerateResponse(
            **after.model_dump(),
            status=status,
            result=result,
        )


@router.get("/frigate/{event_id}/snapshot/candidates", response_model=SnapshotCandidateListResponse)
async def get_snapshot_candidates(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(require_owner),
):
    del auth
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    return await _build_snapshot_candidates_response(request, event_id)


@router.get("/frigate/{event_id}/snapshot/candidates/{candidate_id}/thumbnail.jpg")
async def get_snapshot_candidate_thumbnail(
    event_id: str = Path(..., min_length=1, max_length=64),
    candidate_id: str = Path(..., min_length=1, max_length=160),
    auth: AuthContext = Depends(require_owner),
):
    del auth
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    candidates = await _list_snapshot_candidates(event_id)
    candidate = next((item for item in candidates if str(item.get("candidate_id") or "") == candidate_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Snapshot candidate not found")
    from app.services.media_cache import media_cache

    thumbnail_ref = str(candidate.get("thumbnail_ref") or "").strip()
    if not thumbnail_ref:
        raise HTTPException(status_code=404, detail="Snapshot candidate thumbnail unavailable")
    thumbnail_bytes = await media_cache.get_thumbnail(thumbnail_ref)
    if not thumbnail_bytes:
        raise HTTPException(status_code=404, detail="Snapshot candidate thumbnail unavailable")
    return Response(content=thumbnail_bytes, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)


@router.post("/frigate/{event_id}/snapshot/apply", response_model=SnapshotApplyResponse)
async def apply_snapshot_candidate(
    request_body: SnapshotApplyRequest,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(require_owner),
):
    del auth
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    from app.services.media_cache import media_cache

    if request_body.mode == "revert_original":
        snapshot_bytes = await frigate_client.get_snapshot(event_id, crop=True, quality=95)
        if not snapshot_bytes:
            raise HTTPException(status_code=404, detail="Original Frigate snapshot unavailable")
        replaced = await media_cache.replace_snapshot(event_id, snapshot_bytes, source="frigate_snapshot")
        if not replaced:
            raise HTTPException(status_code=409, detail="Snapshot apply failed")
        after = await _build_snapshot_status(event_id)
        return SnapshotApplyResponse(
            **after.model_dump(),
            status="applied",
            applied_mode=request_body.mode,
            applied_candidate_id=None,
        )

    candidates = await _list_snapshot_candidates(event_id)
    candidate = _pick_snapshot_candidate(candidates, request_body)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Snapshot candidate unavailable")

    image_ref = str(candidate.get("image_ref") or "").strip()
    if not image_ref:
        raise HTTPException(status_code=409, detail="Snapshot candidate image unavailable")
    image_bytes = await media_cache.get_snapshot(image_ref)
    if not image_bytes:
        raise HTTPException(status_code=409, detail="Snapshot candidate image unavailable")
    snapshot_source = str(candidate.get("snapshot_source") or "high_quality_snapshot")
    replaced = await media_cache.replace_snapshot(event_id, image_bytes, source=snapshot_source)
    if not replaced:
        raise HTTPException(status_code=409, detail="Snapshot apply failed")
    after = await _build_snapshot_status(event_id)
    return SnapshotApplyResponse(
        **after.model_dump(),
        status="applied",
        applied_mode=request_body.mode,
        applied_candidate_id=str(candidate.get("candidate_id") or ""),
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
            cache_allowed = await _cached_snapshot_allowed_for_current_settings(media_cache, event_id)
            if cache_allowed and not _is_probably_thumbnail_sized_snapshot(cached):
                return Response(content=cached, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)
            if cache_allowed:
                await media_cache.delete_snapshot(event_id)

    # Fetch from Frigate
    url = f"{settings.frigate.frigate_url}/api/events/{event_id}/snapshot.jpg"
    client = get_http_client()
    headers = frigate_client._get_headers()
    try:
        resp = await client.get(
            url,
            headers=headers,
            params={"crop": 1, "quality": 95},
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.snapshot_not_found", lang)
            )
        resp.raise_for_status()

        # Cache the response
        if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
            await media_cache.cache_snapshot(event_id, resp.content)

        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers=SNAPSHOT_NO_STORE_HEADERS,
        )
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
    from app.services.media_cache import media_cache

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

    if settings.media_cache.enabled:
        recording_cached_path = media_cache.get_recording_clip_path(event_id)
        if recording_cached_path:
            try:
                _validated_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(event_id, lang)
                recording_cached_path = _validated_path
            except HTTPException:
                pass
        if recording_cached_path:
            return Response(status_code=200)
        if settings.media_cache.cache_clips and media_cache.get_clip_path(event_id):
            return Response(status_code=200)

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


@router.head("/frigate/{event_id}/recording-clip.mp4")
@guest_rate_limit()
async def check_recording_clip_exists(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)

    if not settings.frigate.clips_enabled or not settings.frigate.recording_clip_enabled:
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

    if settings.media_cache.enabled:
        cached_path, camera_name, start_ts, end_ts = await _get_valid_cached_recording_clip_path(event_id, lang)
        if cached_path:
            return Response(status_code=200, headers={"X-YAWAMF-Recording-Clip-Ready": "cached"})
    else:
        camera_name, start_ts, end_ts = await _get_recording_clip_context(event_id, lang)
    clip_url = frigate_client.get_camera_recording_clip_url(camera_name, start_ts, end_ts)
    headers = frigate_client._get_headers()

    try:
        _client, resp = await _probe_recording_clip_response(clip_url, headers, timeout=10.0)
        if await _is_no_recordings_response(resp):
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
            )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
            )
        resp.raise_for_status()
        return Response(status_code=200, headers={"X-YAWAMF-Recording-Clip-Ready": "available"})
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
    finally:
        if 'resp' in locals():
            await resp.aclose()


@router.post("/frigate/{event_id}/recording-clip/fetch", response_model=RecordingClipFetchResponse)
@guest_rate_limit()
async def fetch_recording_clip(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    lang = get_user_language(request)

    if not settings.frigate.clips_enabled or not settings.frigate.recording_clip_enabled:
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

    ready = await _fetch_recording_clip_ready(event_id, lang)
    return RecordingClipFetchResponse(
        event_id=event_id,
        status="ready",
        clip_variant="recording",
        cached=bool(ready and settings.media_cache.enabled),
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
    if settings.media_cache.enabled:
        recording_cached_path = media_cache.get_recording_clip_path(event_id)
        if recording_cached_path:
            try:
                _validated_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(event_id, lang)
                recording_cached_path = _validated_path
            except HTTPException:
                pass
        if recording_cached_path:
            log.info(
                "proxy_clip_recording_cache_hit",
                event_id=event_id,
                download=download_requested,
                duration_ms=round((perf_counter() - request_started) * 1000, 2),
            )
            return FileResponse(
                path=recording_cached_path,
                media_type="video/mp4",
                filename=f"{event_id}.mp4",
                headers={
                    "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}.mp4"
                }
            )
        if settings.media_cache.cache_clips:
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


@router.get("/frigate/{event_id}/recording-clip.mp4")
@guest_rate_limit()
async def proxy_recording_clip(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_proxy_auth_context),
):
    """Proxy a full-visit clip from Frigate camera recordings."""
    from app.services.media_cache import media_cache

    lang = get_user_language(request)
    download_requested = request.query_params.get("download") == "1"
    request_started = perf_counter()
    log = structlog.get_logger()

    if not settings.frigate.clips_enabled or not settings.frigate.recording_clip_enabled:
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

    if settings.media_cache.enabled:
        cached_path, camera_name, start_ts, end_ts = await _get_valid_cached_recording_clip_path(event_id, lang)
        if cached_path:
            log.info(
                "proxy_recording_clip_cache_hit",
                event_id=event_id,
                download=download_requested,
                duration_ms=round((perf_counter() - request_started) * 1000, 2),
            )
            return FileResponse(
                path=cached_path,
                media_type="video/mp4",
                filename=f"{event_id}_recording.mp4",
                headers={
                    "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}_recording.mp4"
                }
            )

    else:
        camera_name, start_ts, end_ts = await _get_recording_clip_context(event_id, lang)
    clip_url = frigate_client.get_camera_recording_clip_url(camera_name, start_ts, end_ts)
    headers = frigate_client._get_headers()

    range_header = request.headers.get("range")
    should_cache = settings.media_cache.enabled
    log.debug(
        "proxy_recording_clip_start",
        event_id=event_id,
        camera_name=camera_name,
        download=download_requested,
        has_range=bool(range_header),
        should_cache=should_cache,
    )

    if range_header and not should_cache:
        headers["Range"] = range_header

    client = httpx.AsyncClient(timeout=120.0)
    req = client.build_request("GET", clip_url, headers=headers)
    r = await client.send(req, stream=True)

    if await _is_no_recordings_response(r) or r.status_code == 404:
        await r.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
        )

    if should_cache:
        try:
            cached_path = await media_cache.cache_recording_clip_streaming(event_id, r.aiter_bytes())
            await r.aclose()
            await client.aclose()

            if cached_path:
                log.info(
                    "proxy_recording_clip_cached_from_frigate",
                    event_id=event_id,
                    camera_name=camera_name,
                    download=download_requested,
                    duration_ms=round((perf_counter() - request_started) * 1000, 2),
                )
                return FileResponse(
                    path=cached_path,
                    media_type="video/mp4",
                    filename=f"{event_id}_recording.mp4",
                    headers={
                        "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}_recording.mp4"
                    }
                )

            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.proxy.clip_not_found", lang)
            )
        except HTTPException:
            raise
        except Exception:
            await r.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail=i18n_service.translate("errors.proxy.media_fetch_failed", lang)
            )

    response_headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"{'attachment' if download_requested else 'inline'}; filename={event_id}_recording.mp4",
    }

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
    response_headers["Content-Type"] = r.headers.get("content-type", "video/mp4")

    log.info(
        "proxy_recording_clip_streaming_from_frigate",
        event_id=event_id,
        camera_name=camera_name,
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

    if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
        cached = await media_cache.get_thumbnail(event_id)
        snapshot_cached = await media_cache.get_snapshot(event_id)
        thumbnail_metadata = await media_cache.get_thumbnail_metadata(event_id)
        if snapshot_cached and not await _cached_snapshot_allowed_for_current_settings(media_cache, event_id):
            snapshot_cached = None
            cached = None
        if snapshot_cached:
            if (
                cached
                and _cached_thumbnail_allowed_for_current_snapshot(thumbnail_metadata, has_snapshot=True)
                and not _is_probably_thumbnail_sized_snapshot(cached)
            ):
                return Response(content=cached, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)
            try:
                derived = await asyncio.to_thread(_build_display_thumbnail_from_snapshot, snapshot_cached)
                await media_cache.cache_thumbnail(event_id, derived, source="snapshot_derived")
                return Response(content=derived, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)
            except Exception:
                # Fall back to any cached thumbnail or Frigate thumbnail fetch below.
                if cached and _cached_thumbnail_allowed_for_current_snapshot(thumbnail_metadata, has_snapshot=True):
                    return Response(content=cached, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)
        elif cached and _cached_thumbnail_allowed_for_current_snapshot(thumbnail_metadata, has_snapshot=False):
            return Response(content=cached, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)

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

        # Cache the response using a dedicated thumbnail key.
        if settings.media_cache.enabled and settings.media_cache.cache_snapshots:
            await media_cache.cache_thumbnail(event_id, resp.content, source="frigate_thumbnail")

        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers=SNAPSHOT_NO_STORE_HEADERS,
        )
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
