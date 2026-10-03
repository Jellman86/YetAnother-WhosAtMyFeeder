"""Short films of a visit, framed on the bird, for the leaderboard's reel.

A stored crop is a few hundred pixels across; the camera's recording is full resolution. So a
film is cut from Frigate's continuous recording around the moment the visit's best snapshot was
taken (when the bird is known to be where Frigate's box says), cropped to a 16:9 window around
that box, scaled to card size and written as a silent VP8 WebM loop. Browsers play WebM (Chrome,
Firefox, Edge, Safari 15+); the camera's HEVC they mostly do not. OpenCV writes it, so the image
needs no ffmpeg binary.

Films are made once, one at a time, in the background, and kept beside the media cache. A visit
with no recording for that moment gets no film, and is not retried for a while; the reel shows
its photograph instead.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Callable

import structlog

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.media_cache import CACHE_BASE_DIR

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


class VisitFilmService:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._gate = asyncio.Semaphore(1)
        self._pending: set[str] = set()
        self._failed: dict[str, float] = {}
        self._tasks: set[asyncio.Task] = set()

    def path_for(self, event_id: str) -> Path:
        if not _EVENT_ID.match(event_id) or event_id.startswith("."):
            raise ValueError("invalid_event_id")
        return FILMS_DIR / f"{event_id}.webm"

    def ready_path(self, event_id: str) -> Path | None:
        try:
            path = self.path_for(event_id)
        except ValueError:
            return None
        return path if path.is_file() else None

    def request(self, event_id: str) -> str:
        """Make the film if it is not made, being made, or recently found impossible."""
        if not settings.media_cache.enabled or not _EVENT_ID.match(event_id) or event_id.startswith("."):
            return "unavailable"
        if self.ready_path(event_id) is not None:
            return "ready"
        if event_id in self._pending:
            return "pending"
        failed_at = self._failed.get(event_id)
        if failed_at is not None and (failed_at == math.inf or self._clock() - failed_at < FAILED_RETRY_SECONDS):
            return "unavailable"
        self._pending.add(event_id)
        task = asyncio.create_task(self._make(event_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return "pending"

    async def _make(self, event_id: str) -> None:
        try:
            async with self._gate:
                await self._render(event_id)
        except Exception as exc:  # a film is decoration; its failure must never surface
            reason = str(exc) or type(exc).__name__
            self._failed[event_id] = math.inf if reason in PERMANENT_FAILURES else self._clock()
            log.info("Visit film unavailable", event_id=event_id, reason=reason)
        finally:
            self._pending.discard(event_id)

    async def _render(self, event_id: str) -> None:
        event, error = await frigate_client.get_event_with_error(event_id)
        if not event:
            raise ValueError(error or "event_unavailable")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        box = data.get("box")
        moment = data.get("snapshot_frame_time") or event.get("start_time")
        camera = event.get("camera")
        if not (isinstance(box, list) and len(box) == 4 and moment and camera):
            raise ValueError("no_box_or_moment")
        after = math.floor(float(moment) - WINDOW_BEFORE)
        before = math.ceil(float(moment) + WINDOW_AFTER)
        clip, error = await frigate_client.get_recording_clip_with_error(str(camera), after, before)
        if not clip:
            raise ValueError(error or "recording_unavailable")
        # Start half a second before the snapshot moment, measured from the window's start.
        start = max(0.0, float(moment) - after - 0.5)
        frames = await asyncio.to_thread(write_film, clip, box, start, self.path_for(event_id))
        log.info("Visit film made", event_id=event_id, frames=frames)


visit_film_service = VisitFilmService()
