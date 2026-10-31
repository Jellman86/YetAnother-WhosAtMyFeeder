"""Keep a confirmed Garden animal's full photograph and Frigate clip after Frigate lets them go.

The database row in garden_kept_media is the authority. A file is only ever served
when its row says it is kept, its capture is confirmed and its bytes still match the
recorded checksum; any other file in the garden folder is swept. Paths come from
validated capture IDs, never from Frigate event IDs.
"""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Literal
import uuid

import aiofiles
import aiofiles.os
from fastapi import HTTPException
import httpx
import structlog

from app.config import settings
from app.database import get_db
from app.models.garden_media import ClipState, KeptMediaEntry, KeptMediaRecord, PhotoSource, PhotoState
from app.repositories.garden_repository import GardenCapture, GardenRepository
from app.services import garden_motion_privacy
from app.services import media_cache as cache_module
from app.services.garden_capture_policy import garden_collection_cameras, safe_event_id
from app.services.garden_media_policy import (
    MIN_CLIP_BYTES,
    RETRY_AFTER,
    decision_image_sha256,
    frigate_clip_error_state,
    frigate_photo_error_state,
    keep_plan,
    kept_media_retention_days,
    photo_outcome,
    valid_capture_id,
    within_retention,
)
from app.utils.api_datetime import utc_naive_now

log = structlog.get_logger()

MediaKind = Literal["photo", "clip"]
_SUFFIX: dict[MediaKind, str] = {"photo": ".jpg", "clip": ".mp4"}
_KEPT_FILE = re.compile(r"([a-f0-9]{32})\.(jpg|mp4)")
_STALE_TEMPORARY_SECONDS = 3600


def media_dir() -> Path:
    return cache_module.GARDEN_DIR


def kept_path(capture_id: str, kind: MediaKind) -> Path:
    """The only way a Garden media path is built: a validated capture ID, proven inside the folder."""
    if not valid_capture_id(capture_id):
        raise ValueError("Invalid Garden capture ID")
    base = os.path.normpath(str(media_dir()))
    candidate = os.path.normpath(os.path.join(base, capture_id + _SUFFIX[kind]))
    if not candidate.startswith(base + os.sep):
        raise ValueError("Garden media path escapes its folder")
    return Path(candidate)


def _temporary_path(capture_id: str, kind: MediaKind) -> Path:
    final = kept_path(capture_id, kind)
    return final.with_name(f".{final.stem}.{uuid.uuid4().hex}.tmp")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sweep_sync(directory: Path, keep: set[tuple[str, str]], now: float) -> int:
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.iterdir():
        try:
            if not path.is_file():
                continue
            if path.name.startswith(".") and path.name.endswith(".tmp"):
                if now - path.stat().st_mtime > _STALE_TEMPORARY_SECONDS:
                    path.unlink(missing_ok=True)
                continue
            match = _KEPT_FILE.fullmatch(path.name)
            if match and (match.group(1), "photo" if match.group(2) == "jpg" else "clip") not in keep:
                path.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    return removed


def _unlink(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


class GardenMediaCache:
    def __init__(self) -> None:
        # One capture at a time; sweeps and commits share a short lock so a sweep
        # never removes a file between its rename and its database row.
        self._collect_lock = asyncio.Lock()
        self._commit_lock = asyncio.Lock()

    @staticmethod
    def clips_wanted() -> bool:
        return bool(settings.frigate.clips_enabled and settings.media_cache.cache_clips)

    @staticmethod
    def retention_days() -> int:
        return kept_media_retention_days(settings.media_cache.retention_days, settings.maintenance.retention_days)

    async def collect_one(self) -> None:
        """Backfill: keep one confirmed capture whose media is still due, newest first."""
        from app.services.classifier_service import garden_inference_pressure
        from app.services.garden_identification import bird_work_pending

        cameras = garden_collection_cameras()
        if (
            not cameras
            or not cache_module.media_cache.available
            or self._collect_lock.locked()
            or bird_work_pending(garden_inference_pressure())
        ):
            return
        now = utc_naive_now()
        days = self.retention_days()
        since = (now - timedelta(days=days)).isoformat() if days > 0 else None
        async with get_db() as db:
            capture = await GardenRepository(db).next_media_to_keep(
                cameras, since=since, clips=self.clips_wanted(), now=now.isoformat()
            )
        if capture is not None:
            await self.collect(capture.id)

    async def collect(self, capture_id: str) -> None:
        """Keep what a confirmed capture still has upstream. Failures never touch the review."""
        if not valid_capture_id(capture_id) or not cache_module.media_cache.available:
            return
        async with self._collect_lock:
            try:
                await self._collect(capture_id)
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                TimeoutError,
                HTTPException,
                httpx.HTTPError,
                sqlite3.Error,
            ) as error:
                log.info("garden_media_keep_unavailable", capture_id=capture_id, reason=type(error).__name__)
                await self._defer(capture_id)

    async def _defer(self, capture_id: str) -> None:
        """A failed attempt waits an hour, so one stubborn capture cannot hold up the backfill."""
        try:
            async with get_db() as db:
                repo = GardenRepository(db)
                original = await repo.get(capture_id)
                if original is None or original.status != "confirmed":
                    return
                previous = await repo.kept_media_record(capture_id) or KeptMediaRecord(photo_state="retry")
                await repo.save_kept_media(
                    original, replace(previous, retry_after=(utc_naive_now() + RETRY_AFTER).isoformat())
                )
        except sqlite3.Error as error:
            log.warning("garden_media_defer_failed", capture_id=capture_id, reason=type(error).__name__)

    async def _collect(self, capture_id: str) -> None:
        generation = garden_motion_privacy.generation
        async with get_db() as db:
            repo = GardenRepository(db)
            original = await repo.get(capture_id)
            previous = await repo.kept_media_record(capture_id) if original else None
        if original is None:
            return
        now = utc_naive_now()
        plan = keep_plan(
            status=original.status,
            motion=bool(original.motion_source),
            camera_enabled=original.camera in garden_collection_cameras(),
            within_window=within_retention(datetime.fromisoformat(original.observed_at), now, self.retention_days()),
            clips_wanted=self.clips_wanted(),
            state=previous,
            now_iso=now.isoformat(),
        )
        if not plan.anything:
            return
        await aiofiles.os.makedirs(media_dir(), exist_ok=True)
        staged: dict[MediaKind, Path] = {}
        try:
            window = None
            if original.motion_source:
                window = (original.motion_source.clip_start, original.motion_source.clip_end)
            else:
                revoked, window = await self._frigate_event(original)
                if revoked:
                    return
            record = previous or KeptMediaRecord(photo_state="retry")
            if plan.photo:
                state, source, image = await self._fetch_photo(original)
                record = replace(record, photo_state=state, photo_source=source, photo_sha256=None, photo_bytes=None)
                if state == "kept" and image is not None:
                    staged["photo"] = _temporary_path(capture_id, "photo")
                    async with aiofiles.open(staged["photo"], "wb") as output:
                        await output.write(image)
                    record = replace(record, photo_sha256=hashlib.sha256(image).hexdigest(), photo_bytes=len(image))
            if plan.clip:
                clip_state, clip_path = await self._fetch_clip(original, window is not None)
                record = replace(record, clip_state=clip_state, clip_sha256=None, clip_bytes=None)
                if clip_path is not None:
                    staged["clip"] = clip_path
                    size = (await aiofiles.os.stat(clip_path)).st_size
                    record = replace(
                        record,
                        clip_sha256=await asyncio.to_thread(_sha256_file, clip_path),
                        clip_bytes=size,
                    )
            if window is None:
                observed = datetime.fromisoformat(original.observed_at + "+00:00").timestamp()
                window = (observed, observed)
            retry = "retry" in (record.photo_state, record.clip_state)
            record = replace(
                record,
                source_start=window[0],
                source_end=window[1],
                retry_after=(now + RETRY_AFTER).isoformat() if retry else None,
            )
            await self._commit(original, record, staged, generation)
        finally:
            await asyncio.to_thread(_unlink, list(staged.values()))

    async def _frigate_event(self, original: GardenCapture) -> tuple[bool, tuple[float, float] | None]:
        """Whether Frigate has since revoked the event, and its recording window when Frigate has one."""
        from app.services.broadcaster import broadcaster
        from app.services.frigate_client import frigate_client

        if not safe_event_id(original.frigate_event):
            return False, None
        event = await frigate_client.get_event(original.frigate_event)
        if not isinstance(event, dict):
            return False, None
        label = str(event.get("label", "")).lower()
        if event.get("false_positive") or label in {"person", "human"}:
            # The same veto the crop collector applies: a revoked event keeps nothing.
            async with garden_motion_privacy.lock:
                garden_motion_privacy.invalidate()
                async with get_db() as db:
                    await GardenRepository(db).block_capture(original.id)
            await broadcaster.broadcast({"type": "garden_history_changed"})
            await self.sweep()
            return True, None
        if event.get("camera") != original.camera:
            raise ValueError("Garden event camera differs from its capture")
        start, end = event.get("start_time"), event.get("end_time")
        if all(type(value) in (int, float) and math.isfinite(value) for value in (start, end)) and start <= end:
            return False, (float(start), float(end))
        return False, None

    async def _fetch_photo(self, original: GardenCapture) -> tuple[PhotoState, PhotoSource, bytes | None]:
        if original.motion_source:
            async with get_db() as db:
                image = await GardenRepository(db).motion_photo(original.id)
            sha = hashlib.sha256(image).hexdigest() if image else None
            return (
                photo_outcome(image, expected_sha256=original.motion_source.image_sha256, sha256=sha),
                "motion_photo",
                image,
            )
        from app.services.frigate_client import frigate_client

        if not original.has_snapshot or not safe_event_id(original.frigate_event):
            return "missing", "frigate_snapshot", None
        # The same request the record and the automatic check read, so the checksum compares.
        image, error = await frigate_client.get_snapshot_with_error(original.frigate_event, crop=False)
        if not image:
            return frigate_photo_error_state(error), "frigate_snapshot", None
        expected = decision_image_sha256(
            original.automatic_check.image_sha256 if original.automatic_check else None,
            original.identification.image_sha256 if original.identification else None,
        )
        outcome = photo_outcome(image, expected_sha256=expected, sha256=hashlib.sha256(image).hexdigest())
        if outcome == "changed":
            log.warning("garden_media_photo_differs_from_decision", capture_id=original.id)
        return outcome, "frigate_snapshot", image

    async def _fetch_clip(self, original: GardenCapture, has_event: bool) -> tuple[ClipState, Path | None]:
        from app.services.frigate_client import frigate_client

        event_id = original.frigate_event
        # The clip proxy serves event IDs of at most 64 characters; a longer one could never play.
        if not safe_event_id(event_id) or len(event_id) > 64:
            return "missing", None
        destination = _temporary_path(original.id, "clip")
        downloaded, error = await frigate_client.download_clip_to_file(event_id, str(destination))
        if not downloaded:
            await asyncio.to_thread(_unlink, [destination])
            # Without event metadata a failed clip is most likely gone with it.
            return ("missing" if not has_event else frigate_clip_error_state(error)), None
        if (await aiofiles.os.stat(destination)).st_size < MIN_CLIP_BYTES:
            await asyncio.to_thread(_unlink, [destination])
            return "missing", None
        return "kept", destination

    async def _commit(
        self,
        original: GardenCapture,
        record: KeptMediaRecord,
        staged: dict[MediaKind, Path],
        generation: int,
    ) -> None:
        async with garden_motion_privacy.lock:
            if generation != garden_motion_privacy.generation:
                return
            async with self._commit_lock:
                async with get_db() as db:
                    repo = GardenRepository(db)
                    current = await repo.get(original.id)
                    if current is None or current.status != "confirmed" or current != original:
                        return
                    promoted = []
                    for kind, path in list(staged.items()):
                        final = kept_path(original.id, kind)
                        await aiofiles.os.replace(path, final)
                        staged.pop(kind)
                        promoted.append(final)
                    try:
                        saved = await repo.save_kept_media(original, record)
                    except BaseException:
                        await asyncio.to_thread(_unlink, promoted)
                        raise
                    if not saved:
                        await asyncio.to_thread(_unlink, promoted)
                        return
        log.info(
            "garden_media_kept",
            capture_id=original.id,
            photo=record.photo_state,
            clip=record.clip_state,
        )

    async def photo(self, capture: GardenCapture) -> bytes | None:
        """The kept photograph, only while it is confirmed and still the recorded evidence."""
        if capture.status != "confirmed" or not capture.kept_photo_sha256:
            return None
        try:
            async with aiofiles.open(kept_path(capture.id, "photo"), "rb") as source:
                image = await source.read()
        except (OSError, ValueError) as error:
            log.warning("garden_kept_photo_unreadable", capture_id=capture.id, reason=type(error).__name__)
            return None
        if hashlib.sha256(image).hexdigest() != capture.kept_photo_sha256:
            log.warning("garden_kept_photo_differs", capture_id=capture.id)
            return None
        return image

    async def event_clip(self, event_id: str) -> tuple[bool, Path | None]:
        """Whether a Frigate event is a Garden capture's, and its kept clip when one may be served."""
        try:
            async with get_db() as db:
                garden, capture_id, size = await GardenRepository(db).garden_clip(event_id)
        except sqlite3.Error as error:
            log.warning("garden_kept_clip_lookup_failed", reason=type(error).__name__)
            return False, None
        if capture_id is None:
            return garden, None
        path = kept_path(capture_id, "clip")
        try:
            info = await aiofiles.os.stat(path)
        except OSError:
            return True, None
        return True, (path if info.st_size == size else None)

    async def sweep(self) -> int:
        """Delete every file the database no longer keeps: dismissed, revoked, expired or evicted."""
        async with self._commit_lock:
            async with get_db() as db:
                keep = await GardenRepository(db).kept_media_files()
            removed = await asyncio.to_thread(_sweep_sync, media_dir(), keep, time.time())
        if removed:
            log.info("garden_media_swept", removed=removed)
        return removed

    async def apply_retention(self, now: datetime | None = None) -> int:
        """Age kept media out with the bird media setting; the capture's history follows its own rule."""
        days = self.retention_days()
        if days > 0:
            cutoff = (now or utc_naive_now()) - timedelta(days=days)
            async with get_db() as db:
                repo = GardenRepository(db)
                await repo.evict_kept_media(await repo.kept_media_observed_before(cutoff))
        return await self.sweep()

    async def entries(self) -> list[KeptMediaEntry]:
        async with get_db() as db:
            return await GardenRepository(db).kept_media_entries()

    async def evict(self, capture_ids: list[str]) -> None:
        async with get_db() as db:
            await GardenRepository(db).evict_kept_media([value for value in capture_ids if valid_capture_id(value)])
        await self.sweep()


garden_media_cache = GardenMediaCache()
