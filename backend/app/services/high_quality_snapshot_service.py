"""Asynchronous replacement of event snapshots using frames extracted from Frigate clips."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections import Counter, deque
from pathlib import Path
from typing import Optional

import cv2
import structlog

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.media_cache import media_cache
from app.utils.tasks import create_background_task

log = structlog.get_logger()


class HighQualitySnapshotService:
    """Best-effort background replacement of cached snapshots from event clips."""

    INITIAL_DELAY_SECONDS = 2
    MAX_CLIP_RETRIES = 4
    CLIP_RETRY_INTERVAL_SECONDS = 2
    CLIP_FETCH_TIMEOUT_SECONDS = 10.0
    MAX_PENDING_QUEUE = 32
    MAX_CONCURRENT_TASKS = 2

    def __init__(self):
        self._active_ids: set[str] = set()
        self._queued_ids: set[str] = set()
        self._deferred_ids: set[str] = set()
        self._deferred_order: deque[str] = deque()
        self._completed_ids: set[str] = set()
        self._pending_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.MAX_PENDING_QUEUE)
        self._worker_tasks: list[asyncio.Task] = []
        self._scheduled_total = 0
        self._duplicate_requests = 0
        self._disabled_requests = 0
        self._queue_full_rejections = 0
        self._queue_full_deferrals = 0
        self._outcomes: Counter[str] = Counter()
        self._last_result: dict[str, str] | None = None

    def enabled(self) -> bool:
        return bool(
            settings.media_cache.enabled
            and settings.media_cache.cache_snapshots
            and settings.media_cache.high_quality_event_snapshots
            and (settings.frigate.clips_enabled or settings.frigate.recording_clip_enabled)
        )

    def schedule_replacement(self, event_id: str) -> bool:
        """Schedule background replacement if enabled and not already active."""
        if not self.enabled():
            self._disabled_requests += 1
            return False

        self._cleanup_completed_workers()
        if event_id in self._active_ids or event_id in self._queued_ids or event_id in self._deferred_ids:
            self._duplicate_requests += 1
            return False

        self._ensure_workers_started()
        if not self._enqueue_pending(event_id):
            self._deferred_ids.add(event_id)
            self._deferred_order.append(event_id)
            self._queue_full_deferrals += 1
        self._scheduled_total += 1
        return True

    async def process_event(self, event_id: str) -> str:
        """Fetch the clip, derive a frame, and atomically replace the cached snapshot."""
        if not self.enabled():
            return self._record_outcome(event_id, "disabled")

        clip_bytes, clip_error = await self._wait_for_clip(event_id)
        if not clip_bytes:
            clip_bytes = await self._load_recording_clip_bytes(event_id)
        if not clip_bytes:
            return self._record_outcome(event_id, clip_error or "clip_unavailable")

        try:
            image_bytes = await asyncio.to_thread(self._extract_snapshot_from_clip, clip_bytes)
        except Exception as e:
            log.warning("High-quality snapshot extraction failed", event_id=event_id, error=str(e))
            return self._record_outcome(event_id, "frame_extract_failed")

        replaced = await media_cache.replace_snapshot(event_id, image_bytes)
        if not replaced:
            return self._record_outcome(event_id, "snapshot_replace_failed")

        log.info("High-quality snapshot replaced", event_id=event_id, size=len(image_bytes))
        return self._record_outcome(event_id, "replaced")

    async def _load_recording_clip_bytes(self, event_id: str) -> Optional[bytes]:
        """Fall back to the full-visit recording clip when the event clip is unavailable."""
        if not settings.frigate.recording_clip_enabled:
            return None

        try:
            from app.routers.proxy import _fetch_recording_clip_ready, _get_valid_cached_recording_clip_path
        except Exception as e:
            log.warning("Failed to import recording clip helpers for HQ snapshot fallback", event_id=event_id, error=str(e))
            return None

        try:
            cached_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(event_id, "en")
            if cached_path and cached_path.exists():
                return await asyncio.to_thread(cached_path.read_bytes)

            ready = await _fetch_recording_clip_ready(event_id, "en")
            if not ready:
                return None

            cached_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(event_id, "en")
            if cached_path and cached_path.exists():
                return await asyncio.to_thread(cached_path.read_bytes)
        except Exception as e:
            log.warning("High-quality snapshot recording fallback failed", event_id=event_id, error=str(e))
            return None

        return None

    async def replace_from_clip_bytes(self, event_id: str, clip_bytes: bytes) -> str:
        """Best-effort replacement using clip bytes already fetched by another workflow."""
        if not self.enabled():
            return self._record_outcome(event_id, "disabled")

        self._cleanup_completed_workers()
        if event_id in self._active_ids:
            self._duplicate_requests += 1
            return self._record_outcome(event_id, "duplicate")

        self._active_ids.add(event_id)
        try:
            try:
                image_bytes = await asyncio.to_thread(self._extract_snapshot_from_clip, clip_bytes)
            except Exception as e:
                log.warning("High-quality snapshot extraction failed", event_id=event_id, error=str(e))
                return self._record_outcome(event_id, "frame_extract_failed")

            replaced = await media_cache.replace_snapshot(event_id, image_bytes)
            if not replaced:
                return self._record_outcome(event_id, "snapshot_replace_failed")

            if event_id in self._queued_ids or event_id in self._deferred_ids:
                self._completed_ids.add(event_id)

            log.info("High-quality snapshot replaced from clip bytes", event_id=event_id, size=len(image_bytes))
            return self._record_outcome(event_id, "replaced")
        finally:
            self._active_ids.discard(event_id)
            self._promote_deferred_events()

    async def wait_for_idle(self) -> None:
        """Wait for all scheduled replacement tasks to complete."""
        while True:
            self._promote_deferred_events()
            await self._pending_queue.join()
            self._promote_deferred_events()
            if not self._active_ids and self._pending_queue.qsize() == 0 and not self._deferred_ids:
                return
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        """Cancel and clear all active tasks for tests or shutdown."""
        current_loop = asyncio.get_running_loop()
        tasks = list(self._worker_tasks)
        for task in tasks:
            task.cancel()
        # Only await tasks that belong to the current event loop; tasks from a
        # previous (now-closed) loop cannot be gathered and are simply discarded.
        same_loop_tasks = [t for t in tasks if not t.done() and t.get_loop() is current_loop]
        if same_loop_tasks:
            await asyncio.gather(*same_loop_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        self._active_ids.clear()
        self._queued_ids.clear()
        self._deferred_ids.clear()
        self._deferred_order.clear()
        self._completed_ids.clear()
        self._pending_queue = asyncio.Queue(maxsize=self.MAX_PENDING_QUEUE)
        self._queue_full_rejections = 0
        self._queue_full_deferrals = 0
        self._scheduled_total = 0
        self._duplicate_requests = 0
        self._disabled_requests = 0
        self._outcomes.clear()
        self._last_result = None

    async def reset_state(self) -> None:
        await self.stop()

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            event_id = await self._pending_queue.get()
            self._queued_ids.discard(event_id)
            if event_id in self._completed_ids:
                self._completed_ids.discard(event_id)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                self._pending_queue.task_done()
                continue
            if event_id in self._active_ids:
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                self._pending_queue.task_done()
                continue
            self._active_ids.add(event_id)
            try:
                await self.process_event(event_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(
                    "High-quality snapshot worker failed",
                    worker=worker_index,
                    event_id=event_id,
                    error=str(e),
                    exc_info=True,
                )
                self._record_outcome(event_id, "worker_exception")
            finally:
                self._active_ids.discard(event_id)
                self._pending_queue.task_done()
                self._promote_deferred_events()

    def _ensure_workers_started(self) -> None:
        self._cleanup_completed_workers()
        while len(self._worker_tasks) < self.MAX_CONCURRENT_TASKS:
            worker_index = len(self._worker_tasks)
            task = create_background_task(
                self._worker_loop(worker_index),
                name=f"high_quality_snapshot_worker:{worker_index}",
            )
            self._worker_tasks.append(task)

    def _cleanup_completed_workers(self) -> None:
        alive_tasks: list[asyncio.Task] = []
        for task in self._worker_tasks:
            if task.done():
                if task.cancelled():
                    log.debug("High-quality snapshot worker cancelled", task=task.get_name())
                elif task.exception():
                    log.error("High-quality snapshot worker crashed", task=task.get_name(), error=str(task.exception()))
            else:
                alive_tasks.append(task)
        self._worker_tasks = alive_tasks

    def get_status(self) -> dict:
        self._cleanup_completed_workers()
        return {
            "enabled": self.enabled(),
            "active": len(self._active_ids),
            "queue_size": self._pending_queue.qsize(),
            "deferred": len(self._deferred_ids),
            "workers": len(self._worker_tasks),
            "scheduled_total": self._scheduled_total,
            "duplicate_requests": self._duplicate_requests,
            "disabled_requests": self._disabled_requests,
            "queue_full_rejections": self._queue_full_rejections,
            "queue_full_deferrals": self._queue_full_deferrals,
            "outcomes": dict(self._outcomes),
            "last_result": self._last_result,
        }

    def _enqueue_pending(self, event_id: str) -> bool:
        try:
            self._pending_queue.put_nowait(event_id)
        except asyncio.QueueFull:
            return False
        self._queued_ids.add(event_id)
        return True

    def _promote_deferred_events(self) -> None:
        while self._deferred_order:
            if self._pending_queue.full():
                return

            event_id = self._deferred_order.popleft()
            if event_id not in self._deferred_ids:
                continue

            self._deferred_ids.discard(event_id)
            if event_id in self._completed_ids:
                self._completed_ids.discard(event_id)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                continue
            if event_id in self._active_ids or event_id in self._queued_ids:
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                continue
            if not self._enqueue_pending(event_id):
                self._deferred_ids.add(event_id)
                self._deferred_order.appendleft(event_id)
                return

    async def _wait_for_clip(self, event_id: str) -> tuple[Optional[bytes], Optional[str]]:
        """Poll Frigate for clip availability with bounded retries."""
        await asyncio.sleep(self.INITIAL_DELAY_SECONDS)

        last_error: Optional[str] = None
        for attempt in range(self.MAX_CLIP_RETRIES + 1):
            clip_bytes, error = await frigate_client.get_clip_with_error(
                event_id,
                timeout=self.CLIP_FETCH_TIMEOUT_SECONDS,
            )
            if clip_bytes:
                return clip_bytes, None
            last_error = error or "clip_unavailable"
            if attempt >= self.MAX_CLIP_RETRIES:
                break
            await asyncio.sleep(self.CLIP_RETRY_INTERVAL_SECONDS * (2**attempt))
        return None, last_error

    def _extract_snapshot_from_clip(self, clip_bytes: bytes) -> bytes:
        """Write clip bytes to a temp file and extract a representative JPEG frame."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(clip_bytes)
            tmp_path = Path(tmp.name)

        try:
            return self._extract_snapshot_from_clip_path(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass

    def _extract_snapshot_from_clip_path(self, clip_path: Path) -> bytes:
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            raise ValueError(f"Unable to open clip for snapshot extraction: {clip_path}")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            candidate_indices = []
            if frame_count > 0:
                mid = frame_count // 2
                candidate_indices.extend([mid, max(0, mid - 1), 0])
            else:
                candidate_indices.append(0)

            seen: set[int] = set()
            for frame_index in candidate_indices:
                if frame_index in seen:
                    continue
                seen.add(frame_index)
                if frame_count > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                if ok and frame is not None:
                    encoded_ok, encoded = cv2.imencode(
                        ".jpg",
                        frame,
                        [
                            int(cv2.IMWRITE_JPEG_QUALITY),
                            int(settings.media_cache.high_quality_event_snapshot_jpeg_quality),
                        ],
                    )
                    if not encoded_ok:
                        raise ValueError("Failed to encode extracted frame as JPEG")
                    return encoded.tobytes()

            raise ValueError("No readable frame found in clip")
        finally:
            cap.release()

    def _record_outcome(self, event_id: str, result: str) -> str:
        self._outcomes[result] += 1
        self._last_result = {"event_id": event_id, "result": result}
        return result


high_quality_snapshot_service = HighQualitySnapshotService()
