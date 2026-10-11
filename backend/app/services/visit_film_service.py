"""Short films of a visit, framed on the bird, for the leaderboard's reel.

A stored crop is a few hundred pixels across; the camera's recording is full resolution. So a
film is cut from Frigate's continuous recording around the saved photograph's proven moment,
cropped to a 16:9 window around that photograph's bird, scaled to card size and written as a
silent VP8 WebM loop. The photograph remains
where the browser cannot play VP8 WebM. OpenCV writes it, so the image needs no ffmpeg binary.

Films are made once per photograph revision, one at a time, in the background, and kept beside the media cache. A visit
with no recording for that moment gets no film, and is not retried for a while; the reel shows
its photograph instead.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import math
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Callable

import structlog

from app.services.frigate_client import frigate_client
from app.services.media_cache import CACHE_BASE_DIR, media_cache, validate_film_alignment

log = structlog.get_logger()

FILMS_DIR = Path(os.getenv("VISIT_FILMS_DIR", str(CACHE_BASE_DIR / "films")))
FILM_SIZE = (640, 360)
FILM_FPS = 12
FILM_SECONDS = 4.0
# The window fetched around the snapshot moment; the film starts a little before it.
WINDOW_BEFORE = 1.5
WINDOW_AFTER = 4.5
# The crop is this many times the bird's box: room for the bird to move, and for Frigate's box
# trailing it by a few frames, while the bird stays big enough to read on a card.
CROP_FACTOR = 2.6
MIN_CROP_WIDTH = 480
FAILED_RETRY_SECONDS = 6 * 3600
RECENT_RECORDING_SECONDS = 120
SETTLING_RETRY_SECONDS = 30
FILMS_PENDING_LIMIT = 8
FILM_FAILURES_KEPT = 256
# The reel asks for films of the leading species' newest visits, so the set turns over as the
# leaders do. The media cache's cleanup does not know this folder, so it keeps itself: the
# newest films stay (about a megabyte each) and older ones go, deleted visits' among them.
FILMS_KEPT = 40
# Frigate keeps continuous recordings for days, not weeks: a visit whose recording is gone, or
# which never came from Frigate (an uploaded observation), will never have a film. Asking again
# would only be another request to Frigate on every leaderboard load.
PERMANENT_FAILURES = frozenset({"clip_not_retained", "event_not_found", "no_box_or_moment", "recording_too_short"})
# The file name is built from the event id, so only Frigate's own id characters are accepted.
_EVENT_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class _PhotoUnsupported(ValueError):
    """The current photo has no proven recording moment or has changed during rendering."""


class _RecordingNotReady(ValueError):
    """An active or recent visit can still receive its missing recording."""


def snapshot_matches_photo(metadata: dict, box: list[float], moment: float) -> bool:
    """Require normalized photo localization and agreement of every retained box and time."""
    try:
        if len(box) != 4 or any(isinstance(value, bool) for value in box):
            return False
        values = [float(value) for value in box]
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
            return False
        x, y, width, height = values
        if width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001:
            return False
        if isinstance(moment, bool) or not math.isfinite(float(moment)) or float(moment) <= 0:
            return False
        hints = (metadata.get("snapshot_photo_hints") or {}).get("event_hints") or {}
        snapshot = hints.get("snapshot") or {}
        data = hints.get("data") or {}
        moments = [
            value for value in (snapshot.get("frame_time"), data.get("snapshot_frame_time")) if value is not None
        ]
        if not moments or any(
            isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) <= 0
            or not math.isclose(float(value), float(moment), abs_tol=0.001, rel_tol=0)
            for value in moments
        ):
            return False
        boxes = [value for value in (data.get("box"), snapshot.get("box")) if value is not None]
        # MQTT pixel LTRB boxes need known frame dimensions to normalize; guessing is unsafe.
        if not boxes:
            return False
        for retained in boxes:
            if not isinstance(retained, (list, tuple)) or len(retained) != 4:
                return False
            if any(isinstance(value, bool) for value in retained) or not all(
                math.isclose(float(a), b, abs_tol=0.0001, rel_tol=0) for a, b in zip(retained, values)
            ):
                return False
        return True
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False


def film_window(box: list[float], frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
    """The 16:9 crop (x, y, width, height) around a normalised Frigate box, kept inside the frame."""
    left, top, width, height = (float(value) for value in box)
    centre_x = (left + width / 2) * frame_width
    centre_y = (top + height / 2) * frame_height
    crop_width = max(width * frame_width * CROP_FACTOR, height * frame_height * CROP_FACTOR * 16 / 9, MIN_CROP_WIDTH)
    crop_width = min(crop_width, frame_width, frame_height * 16 / 9)
    crop_height = crop_width * 9 / 16
    x = min(max(centre_x - crop_width / 2, 0), frame_width - crop_width)
    y = min(max(centre_y - crop_height / 2, 0), frame_height - crop_height)
    return round(x), round(y), round(crop_width), round(crop_height)


def prune_films(directory: Path, keep: int = FILMS_KEPT) -> int:
    """Remove all but the newest ``keep`` films; returns how many were removed."""
    films = sorted(
        (path for path in directory.glob("*.webm") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for path in films[keep:]:
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)
        removed += 1
    return removed


def render_film(source: Path, box: list[float], start_seconds: float, destination: Path) -> int:
    """Write the film; returns its frame count. Raises ValueError when the source is unusable."""
    import cv2

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise ValueError("recording_unreadable")
    try:
        source_fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if source_fps <= 0 or frame_width <= 0 or frame_height <= 0:
            raise ValueError("recording_unreadable")
        x, y, width, height = film_window(box, frame_width, frame_height)
        writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"VP80"), FILM_FPS, FILM_SIZE)
        if not writer.isOpened():
            raise ValueError("encoder_unavailable")
        written = 0
        step = source_fps / FILM_FPS
        next_frame = start_seconds * source_fps
        index = 0
        wanted = int(FILM_SECONDS * FILM_FPS)
        try:
            while written < wanted:
                ok, frame = capture.read()
                if not ok:
                    break
                if index >= next_frame:
                    crop = frame[y : y + height, x : x + width]
                    writer.write(cv2.resize(crop, FILM_SIZE, interpolation=cv2.INTER_AREA))
                    written += 1
                    next_frame += step
                index += 1
        finally:
            writer.release()
    finally:
        capture.release()
    if written < FILM_FPS:
        raise ValueError("recording_too_short")
    return written


def write_film(recording: bytes, box: list[float], start_seconds: float, destination: Path) -> int:
    """Render the recording into ``destination`` through a scratch folder beside it, so a
    half-written film is never served, then keep only the newest films."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        source = Path(scratch) / "source.mp4"
        source.write_bytes(recording)
        draft = Path(scratch) / "film.webm"
        frames = render_film(source, box, start_seconds, draft)
        os.replace(draft, destination)
    prune_films(destination.parent)
    return frames


def _film_scratch(destination: Path) -> tempfile.TemporaryDirectory:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=destination.parent)


def _publish_film(draft: Path, destination: Path, fingerprint: str) -> None:
    # Once authorized for a response, this revision's file is immutable.
    try:
        existing = json.loads(destination.with_suffix(".json").read_text())
        if destination.is_file() and isinstance(existing, dict) and existing.get("photo_fingerprint") == fingerprint:
            return
    except (OSError, ValueError):
        pass
    sidecar = draft.with_suffix(".json")
    sidecar.write_text(json.dumps({"photo_fingerprint": fingerprint}))
    # An interrupted publication without its sidecar cannot authorize a response.
    os.replace(draft, destination)
    os.replace(sidecar, destination.with_suffix(".json"))
    prune_films(destination.parent)


class VisitFilmService:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._gate = asyncio.Semaphore(1)
        self._pending: set[str] = set()
        # Retry deadlines, including permanent failures, have bounded memory.
        self._failed: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._tasks: set[asyncio.Task] = set()

    def path_for(self, event_id: str, fingerprint: str | None = None) -> Path:
        if not _EVENT_ID.match(event_id) or event_id.startswith("."):
            raise ValueError("invalid_event_id")
        if fingerprint is not None:
            if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
                raise ValueError("invalid_photo_fingerprint")
            return FILMS_DIR / f"{event_id}__{fingerprint}.webm"
        # Legacy paths remain addressable for cleanup, but cannot authorize a response.
        return FILMS_DIR / f"{event_id}.webm"

    async def _photo_revision_unlocked(self, event_id: str) -> tuple[str | None, dict | None]:
        metadata = await media_cache.get_snapshot_metadata(event_id)
        if not metadata:
            return None, metadata
        path = await media_cache.get_snapshot_path(event_id)
        if path is None:
            return None, metadata
        try:
            image = await asyncio.to_thread(path.read_bytes)
            if not image:
                return None, metadata
            digest = hashlib.sha256(image)
            alignment = validate_film_alignment(metadata.get("film_alignment"), image)
            proof = metadata.get("snapshot_photo_hints") or {}
            hints = proof.get("event_hints") or {}
            moment = (hints.get("snapshot") or {}).get("frame_time")
            if moment is None:
                moment = (hints.get("data") or {}).get("snapshot_frame_time")
            retained_box = (hints.get("data") or {}).get("box")
            if retained_box is None:
                retained_box = (hints.get("snapshot") or {}).get("box")
            original = (
                metadata.get("source") == "frigate_snapshot_cropped"
                and not metadata.get("manual_selection")
                and proof.get("image_sha256") == digest.hexdigest()
                and moment is not None
                and snapshot_matches_photo(metadata, retained_box, moment)
            )
            if alignment is None and not original:
                return None, metadata
            digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
            metadata = dict(metadata)
            metadata["film_alignment"] = alignment
            return digest.hexdigest(), metadata
        except (OSError, AttributeError, TypeError, ValueError, OverflowError):
            return None, metadata

    async def _photo_revision(self, event_id: str) -> tuple[str | None, dict | None]:
        async with media_cache._snapshot_commit_lock(event_id):
            return await self._photo_revision_unlocked(event_id)

    async def ready_path(self, event_id: str) -> Path | None:
        if not media_cache.available:
            return None
        try:
            self.path_for(event_id)
        except ValueError:
            return None
        async with media_cache._snapshot_commit_lock(event_id):
            fingerprint, _ = await self._photo_revision_unlocked(event_id)
            if fingerprint is None:
                return None
            path = self.path_for(event_id, fingerprint)
            if not await asyncio.to_thread(path.is_file):
                return None
            try:
                sidecar = json.loads(await asyncio.to_thread(path.with_suffix(".json").read_text))
            except (OSError, ValueError):
                return None
            if isinstance(sidecar, dict) and sidecar.get("photo_fingerprint") == fingerprint:
                return path
        return None

    async def request(self, event_id: str) -> str:
        """Admit films only with absolute snapshot localization bound to the current photo."""
        if not media_cache.available or not _EVENT_ID.match(event_id) or event_id.startswith("."):
            return "unavailable"
        if await self.ready_path(event_id) is not None:
            return "ready"
        fingerprint, _ = await self._photo_revision(event_id)
        if fingerprint is None:
            return "unavailable"
        if event_id in self._pending:
            return "pending"
        failure = self._failed.get(event_id)
        if failure is not None:
            retry_at, failed_fingerprint = failure
            self._failed.move_to_end(event_id)
            if failed_fingerprint == fingerprint and self._clock() < retry_at:
                return "unavailable"
        if len(self._pending) >= FILMS_PENDING_LIMIT:
            # Deferred requests keep their photograph and can ask again later.
            return "pending"
        self._pending.add(event_id)
        task = asyncio.create_task(self._make(event_id, fingerprint))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return "pending"

    async def _make(self, event_id: str, fingerprint: str) -> None:
        try:
            async with self._gate:
                await self._render(event_id, fingerprint)
                self._failed.pop(event_id, None)
        except _PhotoUnsupported:
            # Photo replacement can make this same visit eligible later.
            self._failed.pop(event_id, None)
        except Exception as exc:  # a film is decoration; its failure must never surface
            reason = str(exc) or type(exc).__name__
            if isinstance(exc, _RecordingNotReady):
                retry_at = self._clock() + SETTLING_RETRY_SECONDS
            else:
                retry_at = math.inf if reason in PERMANENT_FAILURES else self._clock() + FAILED_RETRY_SECONDS
            self._failed[event_id] = (retry_at, fingerprint)
            self._failed.move_to_end(event_id)
            while len(self._failed) > FILM_FAILURES_KEPT:
                self._failed.popitem(last=False)
            log.info("Visit film unavailable", event_id=event_id, reason=reason)
        finally:
            self._pending.discard(event_id)

    async def _render(self, event_id: str, fingerprint: str) -> None:
        current, metadata = await self._photo_revision(event_id)
        if current != fingerprint:
            raise _PhotoUnsupported()
        event, error = await frigate_client.get_event_with_error(event_id)
        if not event:
            raise ValueError(error or "event_unavailable")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        alignment = (metadata or {}).get("film_alignment")
        box = alignment["box"] if alignment else data.get("box")
        moment = alignment["frame_time"] if alignment else data.get("snapshot_frame_time")
        camera = event.get("camera")
        if not (isinstance(box, list) and len(box) == 4 and moment and camera):
            raise _PhotoUnsupported("no_box_or_moment")
        if not alignment and not snapshot_matches_photo(metadata or {}, box, moment):
            raise _PhotoUnsupported("photo_snapshot_mismatch")
        settling = ("end_time" in event and event["end_time"] is None) or (
            float(moment) >= time.time() - RECENT_RECORDING_SECONDS
        )
        after = math.floor(float(moment) - WINDOW_BEFORE)
        before = math.ceil(float(moment) + WINDOW_AFTER)
        clip, error = await frigate_client.get_recording_clip_with_error(str(camera), after, before)
        if not clip:
            if settling and error in {"clip_not_retained", "clip_not_found"}:
                raise _RecordingNotReady(error)
            raise ValueError(error or "recording_unavailable")
        # Start half a second before the snapshot moment, measured from the window's start.
        start = max(0.0, float(moment) - after - 0.5)
        destination = self.path_for(event_id, fingerprint)
        scratch = await media_cache._complete_file_operation(_film_scratch, destination)
        try:
            draft = Path(scratch.name) / "film.webm"
            try:
                # Cancellation waits for this scratch-file writer before removing its folder.
                frames = await media_cache._complete_file_operation(write_film, clip, box, start, draft)
            except ValueError as exc:
                if settling and str(exc) == "recording_too_short":
                    raise _RecordingNotReady("recording_too_short") from exc
                raise
            async with media_cache._snapshot_commit_lock(event_id):
                current, _ = await self._photo_revision_unlocked(event_id)
                if current != fingerprint:
                    raise _PhotoUnsupported()
                await media_cache._complete_file_operation(_publish_film, draft, destination, fingerprint)
        finally:
            await media_cache._complete_file_operation(scratch.cleanup)
        log.info("Visit film made", event_id=event_id, frames=frames)


visit_film_service = VisitFilmService()
