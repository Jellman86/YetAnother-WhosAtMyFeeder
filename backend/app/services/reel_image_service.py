"""Resized photographs for the About portrait, species spotlight, and Leaderboard wall.

Local files (the media cache, favourite archive, manual upload preview, and eligible
cached thumbnails) are always preferred so newly chosen crops win immediately. When a
visit's local snapshot was evicted by a cache budget (`per_species_maximum`, `max_size_mb`,
or retention) while Frigate still retains the event, this service fetches a cropped
snapshot read-only from Frigate, resizes it off the event loop, and holds only the small
resized JPEG in a bounded in-memory LRU cache.

Unlike `proxy_snapshot` and `proxy_thumbnail`, fallback bytes are deliberately NEVER
written back to disk `media_cache`: expanding a 300-visit Leaderboard wall would otherwise
re-populate hundreds of evicted snapshots on disk only for the next storage sweep to delete
them again.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
import time
from typing import Literal, Optional
import weakref

import aiofiles
import aiofiles.os
from PIL import Image, ImageOps
import structlog

from app.services.frigate_client import frigate_client

log = structlog.get_logger()

# The stored photograph can be a full-resolution frame of several megabytes; a card wants a
# few hundred pixels. The reel serves a resized copy, kept in memory, keyed on the file so
# a re-chosen frame is picked up immediately.
REEL_IMAGE_MAX_EDGE = 480
# A leaderboard wall draws up to 24 rows (300+ visits on wide displays) in cells under ninety
# pixels wide. A card-sized copy of each is megabytes of photograph the screen cannot show,
# so the wall asks for a tile.
REEL_TILE_MAX_EDGE = 240
REEL_IMAGE_QUALITY = 82
# Room for a full expanded wall of tiles beside card previews without thrashing the cache.
REEL_IMAGE_CACHE_ENTRIES = 512
REEL_FALLBACK_CACHE_ENTRIES = 512
REEL_FALLBACK_MISSING_ENTRIES = 512
REEL_FALLBACK_POSITIVE_TTL_SECONDS = 600.0
REEL_FALLBACK_NEGATIVE_TTL_SECONDS = 300.0
REEL_UPSTREAM_CONCURRENCY = 6
REEL_UPSTREAM_QUEUE_TIMEOUT_SECONDS = 5.0
REEL_UPSTREAM_FETCH_TIMEOUT_SECONDS = 5.0
REEL_UPSTREAM_BREAKER_SECONDS = 20.0
REEL_UPSTREAM_MAX_BYTES = 16 * 1024 * 1024
REEL_MAX_IMAGE_PIXELS = 40_000_000

ReelImageSize = Literal["card", "tile"]
_REEL_MAX_EDGE: dict[ReelImageSize, int] = {"card": REEL_IMAGE_MAX_EDGE, "tile": REEL_TILE_MAX_EDGE}


class ReelImageUnavailableError(RuntimeError):
    """Raised when an upstream fallback fetch cannot complete right now (transient failure)."""


def resize_for_reel(image_bytes: bytes, max_edge: int = REEL_IMAGE_MAX_EDGE) -> bytes:
    """A card- or tile-sized JPEG of the photograph; the crop is kept, only the size changes."""
    if not image_bytes:
        raise ValueError("Empty image payload")
    with Image.open(BytesIO(image_bytes)) as opened:
        width, height = opened.size
        if width <= 0 or height <= 0 or width * height > REEL_MAX_IMAGE_PIXELS:
            raise ValueError(f"Image dimensions out of bounds: {width}x{height}")
        image = (ImageOps.exif_transpose(opened) or opened).convert("RGB")
        image.thumbnail((max_edge, max_edge))
        out = BytesIO()
        image.save(out, format="JPEG", quality=REEL_IMAGE_QUALITY, optimize=True)
        return out.getvalue()


def _is_transient_frigate_error(error: Optional[str]) -> bool:
    if not error:
        return False
    if error in {"snapshot_timeout", "snapshot_request_error", "snapshot_unknown_error"}:
        return True
    if error.startswith("snapshot_http_"):
        try:
            code = int(error.removeprefix("snapshot_http_"))
        except ValueError:
            return True
        return code >= 500 or code in {408, 429}
    return False


class ReelImageService:
    """Bounded resizing and read-only Frigate fallback cache for reel/wall photographs."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_local_entries: int = REEL_IMAGE_CACHE_ENTRIES,
        max_fallback_entries: int = REEL_FALLBACK_CACHE_ENTRIES,
        max_missing_entries: int = REEL_FALLBACK_MISSING_ENTRIES,
        positive_ttl_seconds: float = REEL_FALLBACK_POSITIVE_TTL_SECONDS,
        negative_ttl_seconds: float = REEL_FALLBACK_NEGATIVE_TTL_SECONDS,
        upstream_concurrency: int = REEL_UPSTREAM_CONCURRENCY,
        upstream_queue_timeout_seconds: float = REEL_UPSTREAM_QUEUE_TIMEOUT_SECONDS,
        upstream_fetch_timeout_seconds: float = REEL_UPSTREAM_FETCH_TIMEOUT_SECONDS,
        breaker_seconds: float = REEL_UPSTREAM_BREAKER_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_local_entries = max(1, max_local_entries)
        self._max_fallback_entries = max(1, max_fallback_entries)
        self._max_missing_entries = max(1, max_missing_entries)
        self._positive_ttl_seconds = positive_ttl_seconds
        self._negative_ttl_seconds = negative_ttl_seconds
        self._upstream_concurrency = max(1, upstream_concurrency)
        self._upstream_queue_timeout_seconds = upstream_queue_timeout_seconds
        self._upstream_fetch_timeout_seconds = upstream_fetch_timeout_seconds
        self._breaker_seconds = breaker_seconds

        self._local_images: OrderedDict[tuple[str, int, int, ReelImageSize], bytes] = OrderedDict()
        self._fallback_images: OrderedDict[tuple[str, ReelImageSize], tuple[float, bytes]] = OrderedDict()
        self._fallback_missing: OrderedDict[str, float] = OrderedDict()
        self._event_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._pending_sizes: dict[str, dict[ReelImageSize, int]] = {}
        self._breaker_until: float = 0.0
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_loop: Optional[asyncio.AbstractEventLoop] = None

    def reset(self) -> None:
        """Clear all in-memory caches, locks, and breaker state (used in tests)."""
        self._local_images.clear()
        self._fallback_images.clear()
        self._fallback_missing.clear()
        self._event_locks.clear()
        self._pending_sizes.clear()
        self._breaker_until = 0.0
        self._semaphore = None
        self._semaphore_loop = None

    def _get_upstream_semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._semaphore is None or self._semaphore_loop is not loop:
            self._semaphore = asyncio.Semaphore(self._upstream_concurrency)
            self._semaphore_loop = loop
        return self._semaphore

    def _event_lock(self, event_id: str) -> asyncio.Lock:
        lock = self._event_locks.get(event_id)
        if lock is None:
            lock = asyncio.Lock()
            self._event_locks[event_id] = lock
        return lock

    def _get_warm_fallback(self, event_id: str, size: ReelImageSize) -> Optional[bytes]:
        key = (event_id, size)
        entry = self._fallback_images.get(key)
        if entry is None:
            return None
        expires_at, data = entry
        if self._clock() >= expires_at:
            self._fallback_images.pop(key, None)
            return None
        self._fallback_images.move_to_end(key)
        return data

    def _store_fallback(self, event_id: str, size: ReelImageSize, data: bytes) -> None:
        key = (event_id, size)
        self._fallback_images[key] = (self._clock() + self._positive_ttl_seconds, data)
        self._fallback_images.move_to_end(key)
        while len(self._fallback_images) > self._max_fallback_entries:
            self._fallback_images.popitem(last=False)

    def _is_known_missing(self, event_id: str) -> bool:
        expires_at = self._fallback_missing.get(event_id)
        if expires_at is None:
            return False
        if self._clock() >= expires_at:
            self._fallback_missing.pop(event_id, None)
            return False
        self._fallback_missing.move_to_end(event_id)
        return True

    def _store_missing(self, event_id: str) -> None:
        self._fallback_missing[event_id] = self._clock() + self._negative_ttl_seconds
        self._fallback_missing.move_to_end(event_id)
        while len(self._fallback_missing) > self._max_missing_entries:
            self._fallback_missing.popitem(last=False)

    def _register_pending_size(self, event_id: str, size: ReelImageSize) -> None:
        counts = self._pending_sizes.setdefault(event_id, {})
        counts[size] = counts.get(size, 0) + 1

    def _unregister_pending_size(self, event_id: str, size: ReelImageSize) -> None:
        counts = self._pending_sizes.get(event_id)
        if not counts:
            return
        remaining = counts.get(size, 0) - 1
        if remaining > 0:
            counts[size] = remaining
        else:
            counts.pop(size, None)
        if not counts:
            self._pending_sizes.pop(event_id, None)

    async def from_file(self, path: Path, size: ReelImageSize = "card") -> bytes:
        """Read and resize a local image file, caching the resized JPEG by file stat."""
        stat = await aiofiles.os.stat(path)
        key = (str(path), int(stat.st_mtime), int(stat.st_size), size)
        cached = self._local_images.get(key)
        if cached is not None:
            self._local_images.move_to_end(key)
            return cached
        async with aiofiles.open(path, "rb") as handle:
            raw = await handle.read()
        resized = await asyncio.to_thread(resize_for_reel, raw, _REEL_MAX_EDGE[size])
        self._local_images[key] = resized
        self._local_images.move_to_end(key)
        while len(self._local_images) > self._max_local_entries:
            self._local_images.popitem(last=False)
        return resized

    async def from_frigate(self, event_id: str, size: ReelImageSize = "card") -> Optional[bytes]:
        """Fetch a cropped snapshot read-only from Frigate and cache only the resized JPEG in memory.

        Returns resized JPEG bytes, or None when Frigate confirms the snapshot is absent or
        the payload is unusable. Raises ReelImageUnavailableError on transient upstream
        outages, timeouts, open circuit breaker, or queue saturation.
        """
        warm = self._get_warm_fallback(event_id, size)
        if warm is not None:
            return warm
        if self._is_known_missing(event_id):
            return None

        self._register_pending_size(event_id, size)
        try:
            lock = self._event_lock(event_id)
            async with lock:
                warm = self._get_warm_fallback(event_id, size)
                if warm is not None:
                    return warm
                if self._is_known_missing(event_id):
                    return None

                if self._clock() < self._breaker_until:
                    raise ReelImageUnavailableError("Frigate snapshot fallback breaker open")

                if not await frigate_client.readiness.admit():
                    frigate_client.readiness.note_deferred()
                    raise ReelImageUnavailableError("Frigate not ready")

                semaphore = self._get_upstream_semaphore()
                try:
                    await asyncio.wait_for(semaphore.acquire(), timeout=self._upstream_queue_timeout_seconds)
                except TimeoutError as exc:
                    raise ReelImageUnavailableError("Frigate snapshot fallback busy") from exc

                try:
                    raw, error = await frigate_client.get_snapshot_with_error(
                        event_id,
                        crop=True,
                        quality=95,
                        timeout=self._upstream_fetch_timeout_seconds,
                    )
                    if error == "snapshot_not_found":
                        self._store_missing(event_id)
                        return None
                    if _is_transient_frigate_error(error):
                        self._breaker_until = self._clock() + self._breaker_seconds
                        raise ReelImageUnavailableError(f"Frigate snapshot fallback failed: {error}")
                    if error is not None or not raw:
                        return None
                    if len(raw) > REEL_UPSTREAM_MAX_BYTES:
                        log.warning(
                            "Upstream snapshot exceeded reel size limit",
                            event_id=event_id,
                            size_bytes=len(raw),
                            max_bytes=REEL_UPSTREAM_MAX_BYTES,
                        )
                        return None

                    # Resize every size currently awaited for this event (e.g. concurrent tile + card)
                    # from the single upstream download so a hover during expansion makes one call.
                    requested_sizes = set(self._pending_sizes.get(event_id, {}).keys())
                    requested_sizes.add(size)
                    resized_by_size: dict[ReelImageSize, bytes] = {}
                    try:
                        for target_size in requested_sizes:
                            resized_by_size[target_size] = await asyncio.to_thread(
                                resize_for_reel, raw, _REEL_MAX_EDGE[target_size]
                            )
                    except Exception:
                        return None

                    for target_size, jpeg_bytes in resized_by_size.items():
                        self._store_fallback(event_id, target_size, jpeg_bytes)
                    return resized_by_size[size]
                finally:
                    semaphore.release()
        finally:
            self._unregister_pending_size(event_id, size)


reel_image_service = ReelImageService()
