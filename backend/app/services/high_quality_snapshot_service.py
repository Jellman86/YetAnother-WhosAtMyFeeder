"""Asynchronous replacement of event snapshots using frames extracted from Frigate clips."""

from __future__ import annotations

import asyncio
import math
import os
import sys
import tempfile
from io import BytesIO
from collections import Counter, deque
from pathlib import Path
from typing import Any, Optional

import cv2
import structlog
from PIL import Image

from app.config import settings
from app.services.bird_crop_service import bird_crop_service
from app.services.frigate_client import frigate_client
from app.services.media_cache import media_cache
from app.utils.tasks import create_background_task

log = structlog.get_logger()

HQ_HINT_CROP_EXPAND_RATIO = 0.36
HQ_MODEL_CROP_EXTRA_EXPAND_RATIO = 0.18
HQ_MAX_CROP_SCORING_FRAMES = 3


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
        self._crop_event_hints: dict[str, dict[str, Any]] = {}
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

    def schedule_replacement(self, event_id: str, event_data: Optional[dict[str, Any]] = None) -> bool:
        """Schedule background replacement if enabled and not already active."""
        if not self.enabled():
            self._disabled_requests += 1
            return False

        self._cleanup_completed_workers()
        self._store_crop_event_hints(event_id, event_data)
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
            self._crop_event_hints.pop(event_id, None)
            return self._record_outcome(event_id, "disabled")

        event_data = self._pop_crop_event_hints(event_id)
        clip_bytes, clip_error = await self._wait_for_clip(event_id)
        if not clip_bytes:
            clip_bytes = await self._load_recording_clip_bytes(event_id)
        if not clip_bytes:
            return self._record_outcome(event_id, clip_error or "clip_unavailable")

        if event_data is None:
            event_data = await self._load_event_data_for_crop(event_id)
        try:
            image_bytes = await asyncio.to_thread(self._extract_snapshot_from_clip, clip_bytes, event_data)
        except Exception as e:
            log.warning("High-quality snapshot extraction failed", event_id=event_id, error=str(e))
            return self._record_outcome(event_id, "frame_extract_failed")
        image_bytes, crop_applied = await asyncio.to_thread(
            self._maybe_crop_snapshot_bytes,
            event_id,
            image_bytes,
            event_data,
        )

        replaced = await media_cache.replace_snapshot(
            event_id,
            image_bytes,
            source="high_quality_bird_crop" if crop_applied else "high_quality_snapshot",
        )
        if not replaced:
            return self._record_outcome(event_id, "snapshot_replace_failed")

        log.info("High-quality snapshot replaced", event_id=event_id, size=len(image_bytes))
        return self._record_outcome(event_id, "bird_crop_replaced" if crop_applied else "replaced")

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

    async def replace_from_clip_bytes(
        self,
        event_id: str,
        clip_bytes: bytes,
        event_data: Optional[dict[str, Any]] = None,
    ) -> str:
        """Best-effort replacement using clip bytes already fetched by another workflow."""
        if not self.enabled():
            return self._record_outcome(event_id, "disabled")

        self._cleanup_completed_workers()
        if event_id in self._active_ids:
            self._crop_event_hints.pop(event_id, None)
            self._duplicate_requests += 1
            return self._record_outcome(event_id, "duplicate")

        self._active_ids.add(event_id)
        try:
            try:
                crop_event_data = event_data if isinstance(event_data, dict) else await self._load_event_data_for_crop(event_id)
                image_bytes = await asyncio.to_thread(self._extract_snapshot_from_clip, clip_bytes, crop_event_data)
            except Exception as e:
                log.warning("High-quality snapshot extraction failed", event_id=event_id, error=str(e))
                return self._record_outcome(event_id, "frame_extract_failed")
            image_bytes, crop_applied = await asyncio.to_thread(
                self._maybe_crop_snapshot_bytes,
                event_id,
                image_bytes,
                crop_event_data,
            )

            replaced = await media_cache.replace_snapshot(
                event_id,
                image_bytes,
                source="high_quality_bird_crop" if crop_applied else "high_quality_snapshot",
            )
            if not replaced:
                return self._record_outcome(event_id, "snapshot_replace_failed")

            if event_id in self._queued_ids or event_id in self._deferred_ids:
                self._completed_ids.add(event_id)

            log.info("High-quality snapshot replaced from clip bytes", event_id=event_id, size=len(image_bytes))
            return self._record_outcome(event_id, "bird_crop_replaced" if crop_applied else "replaced")
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
        cancellable_tasks = [t for t in tasks if self._task_belongs_to_current_open_loop(t, current_loop) and not t.done()]
        for task in cancellable_tasks:
            task.cancel()
        # Only await tasks that belong to the current event loop; tasks from a
        # previous (now-closed) loop cannot be cancelled or gathered safely and
        # are simply discarded from service state.
        if cancellable_tasks:
            await asyncio.gather(*cancellable_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        self._active_ids.clear()
        self._queued_ids.clear()
        self._deferred_ids.clear()
        self._deferred_order.clear()
        self._completed_ids.clear()
        self._crop_event_hints.clear()
        self._pending_queue = asyncio.Queue(maxsize=self.MAX_PENDING_QUEUE)
        self._queue_full_rejections = 0
        self._queue_full_deferrals = 0
        self._scheduled_total = 0
        self._duplicate_requests = 0
        self._disabled_requests = 0
        self._outcomes.clear()
        self._last_result = None

    @staticmethod
    def _task_belongs_to_current_open_loop(task: asyncio.Task, current_loop: asyncio.AbstractEventLoop) -> bool:
        try:
            task_loop = task.get_loop()
        except Exception:
            return False
        return task_loop is current_loop and not task_loop.is_closed()

    async def reset_state(self) -> None:
        await self.stop()

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            queue = self._pending_queue
            event_id = await queue.get()
            self._queued_ids.discard(event_id)
            if event_id in self._completed_ids:
                self._completed_ids.discard(event_id)
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                queue.task_done()
                continue
            if event_id in self._active_ids:
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                queue.task_done()
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
                queue.task_done()
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
            "crop_hints": len(self._crop_event_hints),
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
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                continue
            if event_id in self._active_ids or event_id in self._queued_ids:
                self._crop_event_hints.pop(event_id, None)
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

    def _extract_snapshot_from_clip(self, clip_bytes: bytes, event_data: Optional[dict[str, Any]] = None) -> bytes:
        """Write clip bytes to a temp file and extract a representative JPEG frame."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(clip_bytes)
            tmp_path = Path(tmp.name)

        try:
            return self._extract_snapshot_from_clip_path(tmp_path, event_data=event_data)
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass

    def _store_crop_event_hints(self, event_id: str, event_data: Optional[dict[str, Any]]) -> None:
        hints = self._extract_crop_event_hints(event_data)
        if hints:
            self._crop_event_hints[event_id] = hints

    def _pop_crop_event_hints(self, event_id: str) -> Optional[dict[str, Any]]:
        return self._crop_event_hints.pop(event_id, None)

    def _extract_crop_event_hints(self, event_data: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(event_data, dict):
            return None
        raw_payload = event_data.get("data")
        if not isinstance(raw_payload, dict):
            return None
        payload: dict[str, Any] = {}
        for key in ("box", "region"):
            raw_hint = raw_payload.get(key)
            if isinstance(raw_hint, (list, tuple)) and len(raw_hint) == 4:
                payload[key] = list(raw_hint)
        raw_path_data = raw_payload.get("path_data")
        if isinstance(raw_path_data, list):
            path_data = []
            for item in raw_path_data[:50]:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    point, timestamp = item[0], item[1]
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        path_data.append([list(point[:2]), timestamp])
            if path_data:
                payload["path_data"] = path_data

        hints: dict[str, Any] = {"data": payload} if payload else {}
        for key in ("start_time", "end_time"):
            value = event_data.get(key)
            if value is not None:
                hints[key] = value
        return hints or None

    async def _load_event_data_for_crop(self, event_id: str) -> Optional[dict[str, Any]]:
        """Fetch event metadata only when it can improve HQ bird-crop accuracy."""
        if not bool(getattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", False)):
            return None

        try:
            event_data, error = await frigate_client.get_event_with_error(event_id, timeout=8.0)
        except Exception as e:
            log.debug("High-quality bird crop event metadata fetch failed", event_id=event_id, error=str(e))
            return None

        if not isinstance(event_data, dict):
            log.debug(
                "High-quality bird crop event metadata unavailable",
                event_id=event_id,
                reason=error or "event_unavailable",
            )
            return None
        return event_data

    def _maybe_crop_snapshot_bytes(
        self,
        event_id: str,
        image_bytes: bytes,
        event_data: Optional[dict[str, Any]] = None,
    ) -> tuple[bytes, bool]:
        """Optionally run the crop detector against the HQ frame, falling back to the frame."""
        if not bool(getattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", False)):
            return image_bytes, False
        if not self._background_crop_work_allowed():
            log.debug("Skipping high-quality bird crop while classifier or MQTT pressure is active", event_id=event_id)
            return image_bytes, False

        try:
            with Image.open(BytesIO(image_bytes)) as img:
                source_image = img.convert("RGB")
        except Exception as e:
            log.warning("High-quality bird crop source decode failed", event_id=event_id, error=str(e))
            return image_bytes, False

        crop_result = self._crop_from_event_hints(source_image, event_data)
        if not self._has_crop_image(crop_result):
            model_available = self._bird_crop_model_available()
            crop_result = self._crop_from_bird_model(source_image, event_id=event_id) if model_available else None

        crop_image = crop_result.get("crop_image") if isinstance(crop_result, dict) else None
        if not isinstance(crop_image, Image.Image):
            log.debug(
                "High-quality bird crop unavailable; keeping full HQ frame",
                event_id=event_id,
                reason=(crop_result or {}).get("reason") if isinstance(crop_result, dict) else "invalid_crop_result",
            )
            return image_bytes, False

        try:
            output = BytesIO()
            crop_image.convert("RGB").save(
                output,
                format="JPEG",
                quality=int(settings.media_cache.high_quality_event_snapshot_jpeg_quality),
                optimize=True,
            )
            log.debug(
                "High-quality bird crop applied",
                event_id=event_id,
                reason=str(crop_result.get("reason") or "crop"),
                crop_box=crop_result.get("box"),
            )
            return output.getvalue(), True
        except Exception as e:
            log.warning("High-quality bird crop encode failed", event_id=event_id, error=str(e))
            return image_bytes, False

    def _crop_from_bird_model(self, image: Image.Image, *, event_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        try:
            crop_result = bird_crop_service.generate_crop(image)
        except Exception as e:
            log.warning("High-quality bird crop generation failed", event_id=event_id, error=str(e))
            return None
        if not self._has_crop_image(crop_result):
            return crop_result if isinstance(crop_result, dict) else None
        return self._expand_model_crop_context(image, crop_result)

    @staticmethod
    def _has_crop_image(crop_result: Any) -> bool:
        return isinstance(crop_result, dict) and isinstance(crop_result.get("crop_image"), Image.Image)

    def _expand_model_crop_context(self, image: Image.Image, crop_result: dict[str, Any]) -> dict[str, Any]:
        box = self._normalize_crop_box(crop_result.get("box"), image.size)
        if box is None:
            return crop_result
        expanded = self._expand_box_by_ratio(
            box,
            image.size,
            expand_ratio=HQ_MODEL_CROP_EXTRA_EXPAND_RATIO,
            min_crop_size=1,
        )
        if expanded is None or expanded == box:
            return crop_result
        updated = dict(crop_result)
        updated["crop_image"] = image.crop(expanded)
        updated["box"] = expanded
        return updated

    def _normalize_crop_box(
        self,
        raw_box: Any,
        image_size: tuple[int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            return None
        try:
            left = float(raw_box[0])
            top = float(raw_box[1])
            right = float(raw_box[2])
            bottom = float(raw_box[3])
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, right, bottom)):
            return None
        image_width, image_height = image_size
        left_i = max(0, min(image_width, int(math.floor(left))))
        top_i = max(0, min(image_height, int(math.floor(top))))
        right_i = max(0, min(image_width, int(math.ceil(right))))
        bottom_i = max(0, min(image_height, int(math.ceil(bottom))))
        if right_i <= left_i or bottom_i <= top_i:
            return None
        return left_i, top_i, right_i, bottom_i

    def _crop_from_event_hints(
        self,
        image: Image.Image,
        event_data: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        raw_payload = (event_data or {}).get("data") if isinstance(event_data, dict) else None
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        for hint_key, reason in (("box", "frigate_box"), ("region", "frigate_region")):
            box = self._restore_frigate_hint_box(payload.get(hint_key), image.size)
            if box is None:
                continue
            expanded = self._expand_hint_box(box, image.size)
            if expanded is None:
                continue
            return {
                "crop_image": image.crop(expanded),
                "box": expanded,
                "confidence": None,
                "reason": reason,
            }
        return None

    def _restore_frigate_hint_box(
        self,
        raw_hint: Any,
        image_size: tuple[int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        if not isinstance(raw_hint, (list, tuple)) or len(raw_hint) != 4:
            return None
        try:
            left = float(raw_hint[0])
            top = float(raw_hint[1])
            width = float(raw_hint[2])
            height = float(raw_hint[3])
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, width, height)):
            return None

        image_width, image_height = image_size
        normalized = (
            0.0 <= left <= 1.0
            and 0.0 <= top <= 1.0
            and 0.0 <= width <= 1.0
            and 0.0 <= height <= 1.0
        )
        if normalized:
            left *= float(image_width)
            top *= float(image_height)
            width *= float(image_width)
            height *= float(image_height)

        right = left + width
        bottom = top + height
        if right <= left or bottom <= top:
            return None
        left_i = max(0, min(image_width, int(math.floor(left))))
        top_i = max(0, min(image_height, int(math.floor(top))))
        right_i = max(0, min(image_width, int(math.ceil(right))))
        bottom_i = max(0, min(image_height, int(math.ceil(bottom))))
        if right_i <= left_i or bottom_i <= top_i:
            return None
        return left_i, top_i, right_i, bottom_i

    def _expand_hint_box(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        expand_ratio = HQ_HINT_CROP_EXPAND_RATIO
        min_crop_size = 96
        try:
            raw_expand_ratio = getattr(bird_crop_service, "hint_expand_ratio", None)
            if isinstance(raw_expand_ratio, bool):
                raw_expand_ratio = None
            if isinstance(raw_expand_ratio, (int, float, str)):
                expand_ratio = max(0.0, float(raw_expand_ratio))
        except Exception:
            expand_ratio = HQ_HINT_CROP_EXPAND_RATIO
        try:
            min_crop_size = max(1, int(getattr(bird_crop_service, "min_crop_size", min_crop_size)))
        except Exception:
            min_crop_size = 96

        return self._expand_box_by_ratio(
            box,
            image_size,
            expand_ratio=expand_ratio,
            min_crop_size=min_crop_size,
        )

    def _expand_box_by_ratio(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
        *,
        expand_ratio: float,
        min_crop_size: int,
    ) -> Optional[tuple[int, int, int, int]]:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None

        pad_x = int(round(width * max(0.0, expand_ratio)))
        pad_y = int(round(height * max(0.0, expand_ratio)))
        expanded_left = max(0, left - pad_x)
        expanded_top = max(0, top - pad_y)
        expanded_right = min(int(image_size[0]), right + pad_x)
        expanded_bottom = min(int(image_size[1]), bottom + pad_y)
        crop_width = expanded_right - expanded_left
        crop_height = expanded_bottom - expanded_top
        if crop_width < min_crop_size or crop_height < min_crop_size:
            return None
        if expanded_right <= expanded_left or expanded_bottom <= expanded_top:
            return None
        return expanded_left, expanded_top, expanded_right, expanded_bottom

    def _candidate_frame_indices(
        self,
        *,
        frame_count: int,
        fps: float,
        event_data: Optional[dict[str, Any]] = None,
    ) -> list[int]:
        if frame_count <= 0:
            return [0]

        candidates: list[int] = []
        target_indices = self._target_frame_indices_from_event_path(
            frame_count=frame_count,
            fps=fps,
            event_data=event_data,
        )
        for target_index in target_indices:
            candidates.extend([target_index, target_index - 1, target_index + 1])

        mid = frame_count // 2
        candidates.extend([mid, max(0, mid - 1), 0])

        seen: set[int] = set()
        normalized: list[int] = []
        for raw_index in candidates:
            index = max(0, min(frame_count - 1, int(raw_index)))
            if index in seen:
                continue
            seen.add(index)
            normalized.append(index)
        return normalized

    def _target_frame_indices_from_event_path(
        self,
        *,
        frame_count: int,
        fps: float,
        event_data: Optional[dict[str, Any]],
    ) -> list[int]:
        if frame_count <= 0 or fps <= 0.0 or not isinstance(event_data, dict):
            return []
        try:
            start_time = float(event_data.get("start_time"))
        except (TypeError, ValueError):
            return []
        if not math.isfinite(start_time):
            return []

        raw_payload = event_data.get("data")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        path_points: list[tuple[float, float, float]] = []
        for item in payload.get("path_data") or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            point = item[0]
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                x = float(point[0])
                y = float(point[1])
                timestamp = float(item[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(x) and math.isfinite(y) and math.isfinite(timestamp):
                path_points.append((timestamp, x, y))
        if not path_points:
            return []

        ordered_timestamps = self._ordered_path_timestamps_for_crop(payload, path_points)
        clip_duration_seconds = float(frame_count) / float(fps)
        indices: list[int] = []
        for target_time in ordered_timestamps:
            offset_seconds = max(0.0, target_time - start_time)
            offset_seconds = min(offset_seconds, max(0.0, clip_duration_seconds))
            indices.append(int(round(offset_seconds * fps)))
        return indices

    def _ordered_path_timestamps_for_crop(
        self,
        payload: dict[str, Any],
        path_points: list[tuple[float, float, float]],
    ) -> list[float]:
        ordered: list[float] = []
        seen: set[float] = set()

        def add_timestamp(timestamp: float) -> None:
            if timestamp in seen:
                return
            seen.add(timestamp)
            ordered.append(timestamp)

        box_center = self._normalized_box_center(payload)
        if box_center is not None:
            center_x, center_y = box_center
            normalized_points = [
                item for item in path_points
                if 0.0 <= item[1] <= 1.0 and 0.0 <= item[2] <= 1.0
            ]
            for timestamp, _x, _y in sorted(
                normalized_points,
                key=lambda item: ((item[1] - center_x) ** 2 + (item[2] - center_y) ** 2, item[0]),
            ):
                add_timestamp(timestamp)

        by_time = sorted(path_points, key=lambda item: item[0])
        fallback_indices = [len(by_time) // 2, len(by_time) - 1, 0]
        for index in fallback_indices:
            add_timestamp(by_time[index][0])
        return ordered

    def _normalized_box_center(self, payload: dict[str, Any]) -> Optional[tuple[float, float]]:
        raw_box = payload.get("box")
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            return None
        try:
            x, y, width, height = [float(value) for value in raw_box]
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            return None
        return x + width / 2.0, y + height / 2.0

    def _extract_snapshot_from_clip_path(self, clip_path: Path, event_data: Optional[dict[str, Any]] = None) -> bytes:
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            raise ValueError(f"Unable to open clip for snapshot extraction: {clip_path}")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            candidate_indices = self._candidate_frame_indices(
                frame_count=frame_count,
                fps=fps,
                event_data=event_data,
            )
            score_crops = bool(
                getattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", False)
                and self._bird_crop_model_available()
                and self._background_crop_work_allowed()
            )

            seen: set[int] = set()
            first_readable: bytes | None = None
            best_crop_frame: tuple[float, bytes] | None = None
            crop_frames_scored = 0
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
                    encoded_bytes = encoded.tobytes()
                    if first_readable is None:
                        first_readable = encoded_bytes
                    if not score_crops:
                        return encoded_bytes

                    if crop_frames_scored < HQ_MAX_CROP_SCORING_FRAMES:
                        crop_frames_scored += 1
                        crop_score = self._score_frame_for_bird_crop(frame, frame_order=crop_frames_scored)
                        if crop_score is not None and (
                            best_crop_frame is None or crop_score > best_crop_frame[0]
                        ):
                            best_crop_frame = (crop_score, encoded_bytes)
                    if crop_frames_scored >= HQ_MAX_CROP_SCORING_FRAMES and first_readable is not None:
                        break

            if best_crop_frame is not None:
                return best_crop_frame[1]
            if first_readable is not None:
                return first_readable

            raise ValueError("No readable frame found in clip")
        finally:
            cap.release()

    def _score_frame_for_bird_crop(self, frame: Any, *, frame_order: int) -> Optional[float]:
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb_frame).convert("RGB")
        except Exception as e:
            log.debug("High-quality crop frame conversion failed", error=str(e))
            return None

        crop_result = self._crop_from_bird_model(image)
        if not self._has_crop_image(crop_result):
            return None
        return self._score_crop_result(crop_result, image.size, frame_order=frame_order)

    def _bird_crop_model_available(self) -> bool:
        get_status = getattr(bird_crop_service, "get_status", None)
        if not callable(get_status):
            return True
        try:
            status = get_status()
        except Exception:
            return True
        if not isinstance(status, dict):
            return True
        installed = status.get("installed")
        if installed is False:
            return False
        enabled = status.get("enabled_for_runtime")
        if enabled is False:
            return False
        return True

    def _background_crop_work_allowed(self) -> bool:
        """Keep optional HQ crop inference out of issue-33 pressure paths."""
        return self._mqtt_pressure_allows_background_crop() and self._classifier_pressure_allows_background_crop()

    def _mqtt_pressure_allows_background_crop(self) -> bool:
        try:
            from app.services.mqtt_service import mqtt_service

            status = mqtt_service.get_status() or {}
        except Exception:
            return True
        if not isinstance(status, dict):
            return True
        pressure_level = str(status.get("pressure_level") or "normal").lower()
        if pressure_level in {"elevated", "high", "critical"}:
            return False
        if bool(status.get("under_pressure")):
            return False
        if bool(status.get("backlog_wait_active")):
            return False
        if bool(status.get("recent_handler_slot_wait_exhaustion")):
            return False
        return True

    def _classifier_pressure_allows_background_crop(self) -> bool:
        try:
            classifier_module = sys.modules.get("app.services.classifier_service")
            if classifier_module is None:
                return True
            classifier = getattr(classifier_module, "_classifier_instance", None)
            if classifier is None:
                return True
            get_admission_status = getattr(classifier, "get_admission_status", None)
            if not callable(get_admission_status):
                return True
            status = get_admission_status() or {}
        except Exception:
            return True
        if not isinstance(status, dict):
            return True

        live = status.get("live") if isinstance(status.get("live"), dict) else {}
        background = status.get("background") if isinstance(status.get("background"), dict) else {}
        live_busy = self._safe_status_int(live.get("queued")) > 0 or self._safe_status_int(live.get("running")) > 0
        background_busy = (
            self._safe_status_int(background.get("queued")) > 0
            or self._safe_status_int(background.get("running")) > 0
        )
        if live_busy or background_busy:
            return False
        if bool(status.get("background_throttled")):
            return False
        return True

    @staticmethod
    def _safe_status_int(value: Any) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, parsed)

    def _score_crop_result(
        self,
        crop_result: dict[str, Any],
        image_size: tuple[int, int],
        *,
        frame_order: int,
    ) -> Optional[float]:
        crop_image = crop_result.get("crop_image")
        if not isinstance(crop_image, Image.Image):
            return None
        confidence = self._finite_float(crop_result.get("confidence"))
        if confidence is None:
            confidence = 0.5

        box = self._normalize_crop_box(crop_result.get("box"), image_size)
        image_area = max(1, int(image_size[0]) * int(image_size[1]))
        if box is not None:
            crop_area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        else:
            crop_area = max(1, int(crop_image.width) * int(crop_image.height))
        area_bonus = min(0.05, crop_area / image_area * 0.05)
        order_penalty = max(0, frame_order - 1) * 0.001
        return confidence + area_bonus - order_penalty

    @staticmethod
    def _finite_float(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        return parsed

    def _record_outcome(self, event_id: str, result: str) -> str:
        self._outcomes[result] += 1
        self._last_result = {"event_id": event_id, "result": result}
        return result


high_quality_snapshot_service = HighQualitySnapshotService()
