"""The favourite archive (#178): a favourite's photograph and clip, kept where no cache
operation reaches.

Favouriting a visit enqueues it. The worker copies the stored photograph (the crop, when there
is one) and the event clip out of the media cache, or fetches them from Frigate when the cache
has nothing, into ``ARCHIVE_DIR/<event>/``. Every file is written to a temporary name and
renamed into place; ``manifest.json`` is written last, so a directory without a manifest is an
unfinished archive and is never served. The favourite row records a state per asset: pending,
durable, unavailable (Frigate honestly had nothing) or failed (something that should have worked
did not, and will be retried with backoff).

A reconcile pass at startup and every half hour queues every favourite that is not at an end
state, which is what makes the promise survive a restart, a crash mid-download, an install
whose favourites predate the archive, and a visit favourited before Frigate has written its clip.

Only three everyday actions remove an archive: unfavouriting, deleting the visit, and a database
reset (with Remove all favourites). Age cleanup, orphan cleanup and a cache clear never touch
this directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os
import structlog

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, derive_archive_state
from app.services.broadcaster import broadcaster
from app.services.frigate_client import frigate_client
from app.services.media_cache import media_cache, sanitize_event_id
from app.utils.tasks import create_background_task

log = structlog.get_logger()

ARCHIVE_DIR = Path(os.getenv("ARCHIVE_DIR", "/config/archive"))
MANIFEST_NAME = "manifest.json"
SNAPSHOT_NAME = "snapshot.jpg"
SNAPSHOT_META_NAME = "snapshot.meta.json"
CLIP_NAME = "clip.mp4"
RECORDING_NAME = "recording.mp4"

# Below this much free space nothing is written; a half-written archive on a full disk helps no one.
DISK_FLOOR_BYTES = 256 * 1024 * 1024
# A clip smaller than this is a truncated download, not a clip.
MIN_VALID_CLIP_BYTES = 512
RETRY_DELAYS_SECONDS: tuple[int, ...] = (60, 300, 900, 3600)
MAX_ATTEMPTS = 8
ARCHIVE_WORKERS = 2
QUEUE_MAX = 256
RECONCILE_INTERVAL_SECONDS = 30 * 60
CLIP_DOWNLOAD_TIMEOUT_SECONDS = 120.0
# Frigate answers 404 for a clip until the event has ended and been written; a visit this young
# with no clip yet is still pending, not clipless.
CLIP_SETTLE_HOURS = 24

END_STATES = {"durable", "unavailable"}


def retry_due_at(attempts: int, updated_at: datetime | None) -> datetime | None:
    """When a failed archive may be tried again; None once the attempts are spent."""
    if attempts >= MAX_ATTEMPTS:
        return None
    if updated_at is None:
        return datetime.now(timezone.utc)
    delay = RETRY_DELAYS_SECONDS[min(max(attempts, 1) - 1, len(RETRY_DELAYS_SECONDS) - 1)]
    base = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    return base + timedelta(seconds=delay)


class ArchiveService:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_override = base_dir
        self._event_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._running = False
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._queued_ids: set[str] = set()
        self._active_ids: set[str] = set()
        self._job_timestamps: dict[str, tuple[float, float]] = {}
        self._workers: list[asyncio.Task] = []
        self._reconcile_task: asyncio.Task | None = None
        self._queue_full_rejections = 0

    # ---- layout -------------------------------------------------------------------------

    @property
    def base_dir(self) -> Path:
        return self._base_override or ARCHIVE_DIR

    def event_dir(self, event_id: str) -> Path:
        safe = sanitize_event_id(event_id)
        base = str(self.base_dir)
        candidate = os.path.normpath(os.path.join(base, safe))
        if not candidate.startswith(base + os.sep):
            raise ValueError(f"Path traversal detected: {event_id}")
        return Path(candidate)

    def _lock_for_event(self, event_id: str) -> asyncio.Lock:
        lock = self._event_locks.get(event_id)
        if lock is None:
            lock = asyncio.Lock()
            self._event_locks[event_id] = lock
        return lock

    async def _finished(self, event_dir: Path) -> bool:
        return await aiofiles.os.path.exists(event_dir / MANIFEST_NAME)

    async def _file_if_archived(self, event_id: str, name: str) -> Optional[Path]:
        try:
            event_dir = self.event_dir(event_id)
        except ValueError:
            return None
        if not await self._finished(event_dir):
            return None
        path = event_dir / name
        return path if await aiofiles.os.path.exists(path) else None

    async def snapshot_path(self, event_id: str) -> Optional[Path]:
        return await self._file_if_archived(event_id, SNAPSHOT_NAME)

    async def clip_path(self, event_id: str) -> Optional[Path]:
        return await self._file_if_archived(event_id, CLIP_NAME)

    async def recording_path(self, event_id: str) -> Optional[Path]:
        return await self._file_if_archived(event_id, RECORDING_NAME)

    async def snapshot_metadata(self, event_id: str) -> Optional[dict]:
        return await self._read_json(event_id, SNAPSHOT_META_NAME)

    async def manifest(self, event_id: str) -> Optional[dict]:
        return await self._read_json(event_id, MANIFEST_NAME)

    async def _read_json(self, event_id: str, name: str) -> Optional[dict]:
        path = await self._file_if_archived(event_id, name)
        if path is None:
            return None
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as handle:
                parsed = json.loads(await handle.read())
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    # ---- writes ---------------------------------------------------------------------------

    async def _write_bytes(self, path: Path, data: bytes) -> int:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            async with aiofiles.open(tmp, "wb") as handle:
                await handle.write(data)
                await handle.flush()
                await asyncio.to_thread(os.fsync, handle.fileno())
            await asyncio.to_thread(tmp.replace, path)
            return len(data)
        except BaseException:  # cancellation at shutdown must not leave a temporary file either
            await asyncio.to_thread(_unlink_quiet, tmp)
            raise

    async def _copy_file(self, source: Path, path: Path) -> int:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            await asyncio.to_thread(_copy_and_sync, source, tmp)
            await asyncio.to_thread(tmp.replace, path)
            return int((await aiofiles.os.stat(path)).st_size)
        except BaseException:
            await asyncio.to_thread(_unlink_quiet, tmp)
            raise

    async def _sweep_temporary_files(self, event_dir: Path) -> None:
        """A worker cancelled mid-download leaves a temporary file; the next attempt clears it."""
        stale = await asyncio.to_thread(lambda: [p for p in event_dir.glob(".*.tmp") if p.is_file()])
        for path in stale:
            await asyncio.to_thread(_unlink_quiet, path)

    async def _free_bytes(self) -> int:
        await asyncio.to_thread(self.base_dir.mkdir, parents=True, exist_ok=True)
        usage = await asyncio.to_thread(shutil.disk_usage, self.base_dir)
        return int(usage.free)

    # ---- acquisition ----------------------------------------------------------------------

    async def _acquire_snapshot(self, event_id: str, event_dir: Path) -> tuple[str, Optional[str], int]:
        """(state, error, bytes) for the photograph.

        The cache holds the photograph as currently chosen, so it wins over a copy already in
        the archive: that is how a re-chosen frame reaches the archive.
        """
        target = event_dir / SNAPSHOT_NAME
        cached = await media_cache.get_snapshot_path(event_id)
        if cached is None and await aiofiles.os.path.exists(target):
            return "durable", None, int((await aiofiles.os.stat(target)).st_size)
        if cached is not None:
            size = await self._copy_file(cached, target)
            metadata = await media_cache.get_snapshot_metadata(event_id) or {}
            await self._write_bytes(
                event_dir / SNAPSHOT_META_NAME,
                json.dumps({"source": metadata.get("source") or "media_cache"}).encode("utf-8"),
            )
            return "durable", None, size
        data, error = await frigate_client.get_snapshot_with_error(event_id, crop=True, timeout=30.0)
        if data:
            size = await self._write_bytes(target, data)
            await self._write_bytes(
                event_dir / SNAPSHOT_META_NAME, json.dumps({"source": "frigate_snapshot_cropped"}).encode("utf-8")
            )
            return "durable", None, size
        if error == "snapshot_not_found":
            return "unavailable", None, 0
        return "failed", error or "snapshot_unknown_error", 0

    async def _acquire_clip(
        self, event_id: str, event_dir: Path, *, visit_settled: bool
    ) -> tuple[str, Optional[str], int]:
        """(state, error, bytes) for the event clip.

        A 404 from Frigate on a visit that only just happened is not "no clip": Frigate writes
        the clip after the event ends. Such a visit stays pending and reconcile tries again.
        """
        target = event_dir / CLIP_NAME
        if await aiofiles.os.path.exists(target):
            return "durable", None, int((await aiofiles.os.stat(target)).st_size)
        cached = media_cache.get_clip_path(event_id)
        if cached is not None:
            return "durable", None, await self._copy_file(cached, target)
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            ok, error = await frigate_client.download_clip_to_file(
                event_id, str(tmp), timeout=CLIP_DOWNLOAD_TIMEOUT_SECONDS
            )
            if ok:
                size = int((await aiofiles.os.stat(tmp)).st_size) if await aiofiles.os.path.exists(tmp) else 0
                if size < MIN_VALID_CLIP_BYTES:
                    await asyncio.to_thread(_unlink_quiet, tmp)
                    return "failed", "clip_partial", 0
                await asyncio.to_thread(_fsync_file, tmp)
                await asyncio.to_thread(tmp.replace, target)
                return "durable", None, size
        except BaseException:
            await asyncio.to_thread(_unlink_quiet, tmp)
            raise
        await asyncio.to_thread(_unlink_quiet, tmp)
        if error == "clip_not_found" and not visit_settled:
            return "pending", None, 0
        if error in {"clip_not_found", "clip_not_retained"}:
            return "unavailable", None, 0
        return "failed", error or "clip_unknown_error", 0

    async def _copy_recording_if_cached(self, event_id: str, event_dir: Path) -> int:
        target = event_dir / RECORDING_NAME
        if await aiofiles.os.path.exists(target):
            return int((await aiofiles.os.stat(target)).st_size)
        cached = media_cache.get_recording_clip_path(event_id)
        if cached is None:
            return 0
        try:
            return await self._copy_file(cached, target)
        except Exception as exc:  # the recording is a bonus, never a failure
            log.debug("Recording not copied into archive", event_id=event_id, error=str(exc))
            return 0

    async def archive_event(self, event_id: str) -> dict:
        """Bring one favourite's archive to an end state, or record why it could not."""
        async with self._lock_for_event(event_id):
            async with get_db() as db:
                favorite = await DetectionRepository(db).get_favorite_archive(event_id)
            if favorite is None:
                await self._remove_dir(event_id)
                return {"event_id": event_id, "state": "not_favorite"}
            if favorite["snapshot_state"] in END_STATES and favorite["clip_state"] in END_STATES:
                return {"event_id": event_id, "state": favorite["state"]}

            now = datetime.now(timezone.utc)
            attempts = int(favorite["attempts"])
            snapshot_state, clip_state = favorite["snapshot_state"], favorite["clip_state"]
            error: Optional[str] = None
            total_bytes = 0
            visit_settled = _visit_settled(favorite.get("detection_time"), now)

            try:
                if await self._free_bytes() < DISK_FLOOR_BYTES:
                    raise OSError(28, "archive volume below the free-space floor")
                event_dir = self.event_dir(event_id)
                await asyncio.to_thread(event_dir.mkdir, parents=True, exist_ok=True)
                await self._sweep_temporary_files(event_dir)
                if snapshot_state not in END_STATES:
                    snapshot_state, snapshot_error, snapshot_bytes = await self._acquire_snapshot(event_id, event_dir)
                    error = error or snapshot_error
                else:
                    snapshot_bytes = await _size_or_zero(event_dir / SNAPSHOT_NAME)
                if clip_state not in END_STATES:
                    clip_state, clip_error, clip_bytes = await self._acquire_clip(
                        event_id, event_dir, visit_settled=visit_settled
                    )
                    error = error or clip_error
                else:
                    clip_bytes = await _size_or_zero(event_dir / CLIP_NAME)
                recording_bytes = await self._copy_recording_if_cached(event_id, event_dir)
                total_bytes = snapshot_bytes + clip_bytes + recording_bytes
                if snapshot_bytes or clip_bytes or recording_bytes:
                    await self._write_manifest(event_id, event_dir, now)
            except OSError as exc:
                # A full or unwritable volume is a failed archive the owner can see, not a
                # favourite that spins forever.
                error = "disk_full" if exc.errno == 28 else "disk_error"
                snapshot_state = "failed" if snapshot_state not in END_STATES else snapshot_state
                clip_state = "failed" if clip_state not in END_STATES else clip_state
                log.warning("Archive write failed", event_id=event_id, error=str(exc))

            failed = snapshot_state == "failed" or clip_state == "failed"
            state = derive_archive_state(snapshot_state, clip_state)
            async with get_db() as db:
                repo = DetectionRepository(db)
                still_favorite = await repo.update_favorite_archive(
                    event_id,
                    snapshot_state=snapshot_state,
                    clip_state=clip_state,
                    bytes_on_disk=total_bytes,
                    attempts=attempts + 1 if failed else attempts,
                    error=error if failed else None,
                    archived_at=now if state == "durable" else favorite["archived_at"],
                    updated_at=now,
                )
            if not still_favorite:
                # Unfavourited while the files were being written: nothing may be left behind.
                await self._remove_dir(event_id)
                return {"event_id": event_id, "state": "not_favorite"}
            log.info("Favourite archive updated", event_id=event_id, state=state, bytes=total_bytes, error=error)
            await self._broadcast_state(event_id)
            return {"event_id": event_id, "state": state, "error": error, "bytes": total_bytes}

    async def _broadcast_state(self, event_id: str) -> None:
        """Open records and lists learn the archive's state the way they learn everything else."""
        try:
            from app.routers.events import _detection_updated_payload

            async with get_db() as db:
                detection = await DetectionRepository(db).get_by_frigate_event(event_id)
            if detection is not None:
                await broadcaster.broadcast(
                    {"type": "detection_updated", "data": _detection_updated_payload(detection)}
                )
        except Exception as exc:  # a missed broadcast costs a poll, never the archive
            log.debug("Archive state broadcast skipped", event_id=event_id, error=str(exc))

    async def _write_manifest(self, event_id: str, event_dir: Path, now: datetime) -> None:
        files: dict[str, int] = {}
        for name in (SNAPSHOT_NAME, SNAPSHOT_META_NAME, CLIP_NAME, RECORDING_NAME):
            if await aiofiles.os.path.exists(event_dir / name):
                files[name] = await _size_or_zero(event_dir / name)
        payload = {"event_id": event_id, "files": files, "archived_at": now.isoformat(), "format": 1}
        await self._write_bytes(event_dir / MANIFEST_NAME, json.dumps(payload, indent=2).encode("utf-8"))

    # ---- removal --------------------------------------------------------------------------

    async def _remove_dir(self, event_id: str) -> int:
        try:
            event_dir = self.event_dir(event_id)
        except ValueError:
            return 0
        if not await aiofiles.os.path.exists(event_dir):
            return 0
        freed = await asyncio.to_thread(_dir_size, event_dir)
        await asyncio.to_thread(shutil.rmtree, event_dir, True)
        return freed

    async def remove(self, event_id: str) -> int:
        """Remove a visit's archive; bytes freed.

        If an acquisition holds the event's lock, this returns at once: that acquisition reads
        the favourite row again before it finishes and removes the directory itself, and a
        clip download can take two minutes that no HTTP request should wait for.
        """
        lock = self._lock_for_event(event_id)
        if lock.locked():
            log.debug("Archive removal left to the acquisition in flight", event_id=event_id)
            return 0
        async with lock:
            freed = await self._remove_dir(event_id)
        if freed:
            log.info("Favourite archive removed", event_id=event_id, bytes=freed)
        return freed

    async def refresh_photograph(self, event_id: str) -> bool:
        """The photograph changed: archive it again if the visit is a favourite."""
        async with get_db() as db:
            changed = await DetectionRepository(db).mark_favorite_snapshot_pending(event_id)
        if changed:
            self.enqueue(event_id)
        return changed

    async def _archive_dir_names(self) -> list[str]:
        if not await aiofiles.os.path.exists(self.base_dir):
            return []
        return await asyncio.to_thread(
            lambda: sorted(
                entry.name for entry in self.base_dir.iterdir() if entry.is_dir() and not entry.name.startswith(".")
            )
        )

    async def remove_all(self) -> dict:
        """Every archive, for Remove all favourites and for a database reset."""
        removed, freed = 0, 0
        for name in await self._archive_dir_names():
            freed += await self.remove(name)
            removed += 1
        return {"removed": removed, "bytes_freed": freed}

    async def orphan_sweep(self) -> dict:
        """Remove archives whose visit is no longer a favourite (after a reset or a hand-edited
        database). Each directory is checked against the database under its own lock, so a visit
        favourited while the sweep runs is never mistaken for an orphan."""
        removed, freed = 0, 0
        for name in await self._archive_dir_names():
            lock = self._lock_for_event(name)
            if lock.locked():
                continue
            async with lock:
                async with get_db() as db:
                    if await DetectionRepository(db).get_favorite_archive(name) is not None:
                        continue
                bytes_freed = await self._remove_dir(name)
            removed += 1
            freed += bytes_freed
            log.info("Removed archive with no favourite behind it", event_id=name, bytes=bytes_freed)
        return {"removed": removed, "bytes_freed": freed}

    # ---- worker ---------------------------------------------------------------------------

    def enqueue(self, event_id: str) -> bool:
        """Queue one favourite. Before the worker runs, the startup reconcile pass finds it instead."""
        if not self._running:
            return False
        if event_id in self._queued_ids or event_id in self._active_ids:
            return False
        try:
            self._queue.put_nowait(event_id)
        except asyncio.QueueFull:
            self._queue_full_rejections += 1
            return False
        self._queued_ids.add(event_id)
        self._job_timestamps[event_id] = (time.time(), time.time())
        return True

    async def reconcile(self) -> int:
        """Queue every favourite not at an end state whose retry is due."""
        async with get_db() as db:
            unfinished = await DetectionRepository(db).list_unfinished_favorite_archives()
        now = datetime.now(timezone.utc)
        queued = 0
        for item in unfinished:
            if item["state"] == "failed":
                due = retry_due_at(item["attempts"], item["updated_at"])
                if due is None or due > now:
                    continue
            if self.enqueue(item["frigate_event"]):
                queued += 1
        return queued

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._workers = [
            create_background_task(self._worker_loop(index), name=f"favorite_archive_worker:{index}")
            for index in range(ARCHIVE_WORKERS)
        ]
        self._reconcile_task = create_background_task(self._reconcile_loop(), name="favorite_archive_reconcile")

    async def stop(self) -> None:
        self._running = False
        if self._reconcile_task:
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
            self._reconcile_task = None
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._queued_ids.clear()
        self._active_ids.clear()
        self._job_timestamps.clear()

    async def _reconcile_loop(self) -> None:
        while self._running:
            try:
                queued = await self.reconcile()
                if queued:
                    log.info("Favourite archive reconcile queued work", queued=queued)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Favourite archive reconcile failed", error=str(exc))
            await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)

    async def _worker_loop(self, worker_index: int) -> None:
        while self._running:
            try:
                event_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            self._queued_ids.discard(event_id)
            self._active_ids.add(event_id)
            created_at, _updated = self._job_timestamps.get(event_id, (time.time(), time.time()))
            self._job_timestamps[event_id] = (created_at, time.time())
            try:
                await self.archive_event(event_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Favourite archive worker failed", worker=worker_index, event_id=event_id, error=str(exc))
            finally:
                self._active_ids.discard(event_id)
                self._job_timestamps.pop(event_id, None)
                self._queue.task_done()

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "queued": self._queue.qsize(),
            "active": len(self._active_ids),
            "workers": len(self._workers),
            "queue_capacity": QUEUE_MAX,
            "queue_full_rejections": self._queue_full_rejections,
            "archive_dir": str(self.base_dir),
        }

    def get_jobs_snapshot(self) -> list[dict]:
        jobs: list[dict] = []
        for event_id in sorted(self._active_ids):
            jobs.append(self._job_snapshot(event_id, "running", "archiving"))
        for event_id in sorted(self._queued_ids):
            jobs.append(self._job_snapshot(event_id, "queued", "waiting"))
        return jobs

    def _job_snapshot(self, event_id: str, status: str, phase: str) -> dict:
        now = time.time()
        created_at, updated_at = self._job_timestamps.setdefault(event_id, (now, now))
        return {
            "id": f"favorite_archive:{event_id}",
            "event_id": event_id,
            "kind": "favorite_archive",
            "source": "automatic",
            "status": status,
            "phase": phase,
            "current": 0,
            "total": 0,
            "unit": "items",
            "route": f"/events?detection={event_id}",
            "created_at": datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat(),
            "updated_at": datetime.fromtimestamp(updated_at, tz=timezone.utc).isoformat(),
            "error": None,
        }


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.debug("Could not remove temporary archive file", path=str(path), error=str(exc))


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _visit_settled(detection_time: datetime | None, now: datetime) -> bool:
    """Old enough that Frigate has written whatever clip it will ever write."""
    if detection_time is None:
        return True
    when = detection_time if detection_time.tzinfo else detection_time.replace(tzinfo=timezone.utc)
    return (now - when) >= timedelta(hours=CLIP_SETTLE_HOURS)


def _copy_and_sync(source: Path, dest: Path) -> None:
    with open(source, "rb") as src, open(dest, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())


def _dir_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


async def _size_or_zero(path: Path) -> int:
    if not await aiofiles.os.path.exists(path):
        return 0
    return int((await aiofiles.os.stat(path)).st_size)


archive_service = ArchiveService()
