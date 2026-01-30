import asyncio
import os
import tempfile
import structlog
import time
from collections import deque
from datetime import datetime
from typing import Optional, Dict

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.classifier_service import get_classifier
from app.services.broadcaster import broadcaster
from app.services.media_cache import media_cache
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

log = structlog.get_logger()

class AutoVideoClassifierService:
    """
    Service to automatically classify video clips from Frigate events.

    This service polls Frigate for clip availability, downloads it,
    runs the temporal ensemble classifier, and saves results to the DB.
    """

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._classifier = get_classifier()
        self._failure_events: deque[tuple[float, str]] = deque()
        self._failure_event_ids: set[str] = set()
        self._circuit_open_until: float | None = None
        self._pending_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None
        self._stale_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the queue processor."""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue_loop())
        self._stale_task = asyncio.create_task(self._stale_watchdog_loop())
        log.info("AutoVideoClassifierService started")

    async def stop(self):
        """Stop the queue processor."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        if self._stale_task:
            self._stale_task.cancel()
            try:
                await self._stale_task
            except asyncio.CancelledError:
                pass
        # Cancel all active tasks
        for task in self._active_tasks.values():
            task.cancel()
        self._active_tasks.clear()
        log.info("AutoVideoClassifierService stopped")

    async def _process_queue_loop(self):
        """Background loop to process queued classification tasks."""
        while self._running:
            try:
                # Check constraints
                if self._is_circuit_open():
                    await asyncio.sleep(5)
                    continue

                max_concurrent = settings.classification.video_classification_max_concurrent
                if len(self._active_tasks) >= max_concurrent:
                    await asyncio.sleep(1)
                    continue

                # Get next task
                try:
                    # Wait for a task or timeout to recheck constraints
                    frigate_event, camera = await asyncio.wait_for(self._pending_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if frigate_event in self._active_tasks:
                    self._pending_queue.task_done()
                    continue

                # Start task - skip initial delay for queued (historical) tasks
                task = asyncio.create_task(self._process_event(frigate_event, camera, skip_delay=True))
                self._active_tasks[frigate_event] = task
                task.add_done_callback(lambda t: self._cleanup_task(frigate_event, t))
                self._pending_queue.task_done()
                
                log.debug("Started queued video classification", 
                          event_id=frigate_event, 
                          queue_size=self._pending_queue.qsize())

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Error in video classification queue loop", error=str(e))
                await asyncio.sleep(5)

    async def _stale_watchdog_loop(self):
        """Periodically mark stale pending/processing detections as failed."""
        while self._running:
            try:
                max_age = settings.classification.video_classification_stale_minutes
                async with get_db() as db:
                    repo = DetectionRepository(db)
                    count = await repo.reset_stale_video_statuses(max_age)
                if count:
                    log.warning("Reset stale video classifications", count=count, max_age_minutes=max_age)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Error in stale watchdog loop", error=str(e))
            await asyncio.sleep(60)

    def _prune_failures(self):
        window = settings.classification.video_classification_failure_window_minutes * 60
        now = time.time()
        while self._failure_events and now - self._failure_events[0][0] > window:
            _, event_id = self._failure_events.popleft()
            self._failure_event_ids.discard(event_id)

    def _record_failure(self, event_id: str):
        self._prune_failures()
        if event_id in self._failure_event_ids:
            return
        now = time.time()
        self._failure_events.append((now, event_id))
        self._failure_event_ids.add(event_id)

        threshold = settings.classification.video_classification_failure_threshold
        if len(self._failure_events) >= threshold:
            cooldown = settings.classification.video_classification_failure_cooldown_minutes * 60
            self._circuit_open_until = now + cooldown
            log.warning("Video classification circuit opened",
                        failures=len(self._failure_events),
                        cooldown_minutes=settings.classification.video_classification_failure_cooldown_minutes)

    def _record_success(self, event_id: str):
        self._prune_failures()
        if event_id in self._failure_event_ids:
            self._failure_event_ids.discard(event_id)
            self._failure_events = deque([(ts, eid) for ts, eid in self._failure_events if eid != event_id])

    def _is_circuit_open(self) -> bool:
        if not self._circuit_open_until:
            return False
        now = time.time()
        if now >= self._circuit_open_until:
            self._circuit_open_until = None
            self._failure_events.clear()
            self._failure_event_ids.clear()
            return False
        return True

    def get_circuit_status(self) -> dict:
        open_status = self._is_circuit_open()
        until = None
        if open_status and self._circuit_open_until:
            until = datetime.fromtimestamp(self._circuit_open_until).isoformat()
        return {
            "open": open_status,
            "open_until": until,
            "failure_count": len(self._failure_events)
        }

    def get_status(self) -> dict:
        """Get current queue status."""
        return {
            "pending": self._pending_queue.qsize(),
            "active": len(self._active_tasks),
            "circuit_open": self._is_circuit_open()
        }

    async def queue_classification(self, frigate_event: str, camera: str):
        """
        Queue a video classification task.
        Use this for bulk operations or retries.
        """
        await self._pending_queue.put((frigate_event, camera))
        log.debug("Queued video classification", event_id=frigate_event, queue_size=self._pending_queue.qsize())

    def _cleanup_task(self, frigate_event: str, task: asyncio.Task):
        """Safely cleanup a completed task from the active tasks dict."""
        try:
            self._active_tasks.pop(frigate_event, None)
            if task.cancelled():
                log.debug("Video classification task was cancelled", event_id=frigate_event)
            elif task.exception():
                log.error("Video classification task failed with exception",
                         event_id=frigate_event,
                         error=str(task.exception()))
        except Exception as e:
            log.error("Error during task cleanup", event_id=frigate_event, error=str(e))

    async def trigger_classification(self, frigate_event: str, camera: str):
        """
        Trigger automatic video classification for an event.
        Starts a background task if not already processing.
        """
        if not settings.classification.auto_video_classification:
            return

        # Clean up completed tasks before checking limit
        self._cleanup_completed_tasks()

        if self._is_circuit_open():
            log.warning("Circuit breaker open, skipping auto video classification", event_id=frigate_event)
            await self._update_status(frigate_event, 'failed', error="circuit_open", broadcast=True)
            return

        if frigate_event in self._active_tasks:
            log.debug("Video classification already in progress", event_id=frigate_event)
            return

        max_concurrent = settings.classification.video_classification_max_concurrent
        if len(self._active_tasks) >= max_concurrent:
            log.warning("Max concurrent video classifications reached, skipping",
                        event_id=frigate_event,
                        limit=max_concurrent)
            return

        task = asyncio.create_task(self._process_event(frigate_event, camera))
        self._active_tasks[frigate_event] = task
        task.add_done_callback(lambda t: self._cleanup_task(frigate_event, t))

    def _cleanup_completed_tasks(self):
        """Remove all completed/failed tasks from the active tasks dict."""
        completed = [event_id for event_id, task in self._active_tasks.items() if task.done()]
        for event_id in completed:
            self._active_tasks.pop(event_id, None)
        if completed:
            log.debug("Cleaned up completed tasks", count=len(completed))

    async def _process_event(self, frigate_event: str, camera: str, skip_delay: bool = False):
        """Main workflow for processing a video clip."""
        log.info("Starting auto video classification", event_id=frigate_event, camera=camera, skip_delay=skip_delay)
        
        try:
            # 1. Update status in DB to 'pending'
            await self._update_status(frigate_event, 'pending', error=None, broadcast=False)

            # Broadcast start
            await broadcaster.broadcast({
                "type": "reclassification_started",
                "data": {
                    "event_id": frigate_event,
                    "strategy": "auto_video"
                }
            })

            event_data, event_error = await frigate_client.get_event_with_error(frigate_event, timeout=8.0)
            if event_error:
                log.warning("Frigate event precheck failed", event_id=frigate_event, error=event_error)
                await self._update_status(frigate_event, 'failed', error=event_error, broadcast=True)
                self._record_failure(frigate_event)
                await self._auto_delete_if_missing(frigate_event, event_error)
                await broadcaster.broadcast({
                    "type": "reclassification_completed",
                    "data": { "event_id": frigate_event, "results": [] }
                })
                return

            # 2. Wait for clip availability
            clip_bytes, clip_error = await self._wait_for_clip(frigate_event, skip_delay=skip_delay)
            if not clip_bytes:
                log.warning("Clip not available after retries", event_id=frigate_event)
                await self._update_status(frigate_event, 'failed', error=clip_error or "clip_unavailable", broadcast=True)
                self._record_failure(frigate_event)
                await self._auto_delete_if_missing(frigate_event, clip_error or "clip_unavailable")
                await broadcaster.broadcast({
                    "type": "reclassification_completed",
                    "data": { "event_id": frigate_event, "results": [] }
                })
                return

            # 3. Save to temp file for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name

            try:
                # 4. Run classification
                await self._update_status(frigate_event, 'processing', error=None, broadcast=False)
                
                async def progress_callback(current, total, score, label, frame_thumb=None, frame_index=None, clip_total=None, model_name=None):
                    # Broadcast progress via SSE
                    await broadcaster.broadcast({
                        "type": "reclassification_progress",
                        "data": {
                            "event_id": frigate_event,
                            "current_frame": current,
                            "total_frames": total,
                            "frame_score": score,
                            "top_label": label,
                            "frame_thumb": frame_thumb,
                            "frame_index": frame_index,
                            "clip_total": clip_total,
                            "model_name": model_name
                        }
                    })

                timeout = settings.classification.video_classification_timeout_seconds
                try:
                    results = await asyncio.wait_for(
                        self._classifier.classify_video_async(
                            tmp_path,
                            max_frames=15,
                            progress_callback=progress_callback
                        ),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    log.warning("Video classification timed out", event_id=frigate_event, timeout_seconds=timeout)
                    await self._update_status(frigate_event, 'failed', error="video_timeout", broadcast=True)
                    self._record_failure(frigate_event)
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })
                    return

                if results:
                    top = results[0]
                    # 5. Save results to DB
                    await self._save_results(frigate_event, top)
                    self._record_success(frigate_event)
                    
                    # Broadcast completion
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": {
                            "event_id": frigate_event,
                            "results": results
                        }
                    })

                    log.info("Auto video classification completed", 
                             event_id=frigate_event, 
                             label=top['label'], 
                             score=top['score'])
                else:
                    log.warning("Video classification returned no results", event_id=frigate_event)
                    await self._update_status(frigate_event, 'failed', error="video_no_results", broadcast=True)
                    self._record_failure(frigate_event)
                    await broadcaster.broadcast({
                        "type": "reclassification_completed",
                        "data": { "event_id": frigate_event, "results": [] }
                    })

            finally:
                # Always cleanup temp file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        except asyncio.CancelledError:
            log.info("Video classification task cancelled", event_id=frigate_event)
            await self._update_status(frigate_event, 'failed', error="video_cancelled", broadcast=True)
            self._record_failure(frigate_event)
            raise
        except Exception as e:
            log.error("Video classification failed", event_id=frigate_event, error=str(e))
            await self._update_status(frigate_event, 'failed', error="video_exception", broadcast=True)
            self._record_failure(frigate_event)
            await self._auto_delete_if_missing(frigate_event, "video_exception")
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": { "event_id": frigate_event, "results": [] }
            })

    async def _wait_for_clip(self, frigate_event: str, skip_delay: bool = False) -> tuple[Optional[bytes], Optional[str]]:
        """Poll Frigate for clip availability with retries."""
        # Initial delay to allow Frigate to finalize the clip
        if not skip_delay:
            await asyncio.sleep(settings.classification.video_classification_delay)

        max_retries = settings.classification.video_classification_max_retries
        retry_interval = settings.classification.video_classification_retry_interval

        last_error: Optional[str] = None
        for attempt in range(max_retries + 1):
            log.debug("Polling for clip", event_id=frigate_event, attempt=attempt)
            clip_bytes, error = await frigate_client.get_clip_with_error(frigate_event, timeout=10.0)
            
            if clip_bytes and len(clip_bytes) > 0:
                # Basic sanity check: MP4 header
                if clip_bytes.startswith(b'\x00\x00\x00\x18ftyp') or b'ftyp' in clip_bytes[:32]:
                    if await self._clip_decodes(clip_bytes):
                        return clip_bytes, None
                    last_error = "clip_decode_failed"
                else:
                    last_error = "clip_invalid"
            else:
                last_error = error or "clip_unavailable"
            
            if attempt < max_retries:
                # Exponential backoff: 1x, 2x, 4x...
                wait_time = retry_interval * (2 ** attempt)
                log.debug(f"Clip not ready, waiting {wait_time}s", event_id=frigate_event)
                await asyncio.sleep(wait_time)

        return None, last_error

    async def _clip_decodes(self, clip_bytes: bytes) -> bool:
        """Ensure clip bytes decode into at least one frame."""
        import cv2

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
                tmp.write(clip_bytes)
                tmp_path = tmp.name

            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                cap.release()
                return False
            ok, _frame = cap.read()
            cap.release()
            return ok
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def _auto_delete_if_missing(self, frigate_event: str, error: str):
        """Auto-delete detection when clip/event is missing (if enabled)."""
        if not settings.maintenance.auto_delete_missing_clips:
            return

        missing_errors = {
            "event_not_found",
            "clip_unavailable",
            "clip_invalid",
            "clip_decode_failed",
            "video_exception",
        }
        if error not in missing_errors:
            return

        try:
            await media_cache.delete_cached_media(frigate_event)
            async with get_db() as db:
                repo = DetectionRepository(db)
                deleted = await repo.delete_by_frigate_event(frigate_event)
            if deleted:
                await broadcaster.broadcast({
                    "type": "detection_deleted",
                    "data": {
                        "frigate_event": frigate_event,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                })
                log.info("Auto-deleted detection due to missing clip/event",
                         event_id=frigate_event, error=error)
        except Exception as e:
            log.error("Failed to auto-delete missing clip detection",
                      event_id=frigate_event, error=str(e))

    async def _update_status(self, frigate_event: str, status: str, error: Optional[str] = None, broadcast: bool = False):
        """Update video classification status in DB."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.update_video_status(frigate_event, status, error=error)
            if broadcast:
                det = await repo.get_by_frigate_event(frigate_event)
                if det:
                    await broadcaster.broadcast({
                        "type": "detection_updated",
                        "data": {
                            "frigate_event": frigate_event,
                            "display_name": det.display_name,
                            "score": det.score,
                            "timestamp": det.detection_time.isoformat(),
                            "camera": det.camera_name,
                            "is_hidden": det.is_hidden,
                            "frigate_score": det.frigate_score,
                            "sub_label": det.sub_label,
                            "manual_tagged": det.manual_tagged,
                            "audio_confirmed": det.audio_confirmed,
                            "audio_species": det.audio_species,
                            "audio_score": det.audio_score,
                            "temperature": det.temperature,
                            "weather_condition": det.weather_condition,
                            "scientific_name": det.scientific_name,
                            "common_name": det.common_name,
                            "taxa_id": det.taxa_id,
                            "video_classification_score": det.video_classification_score,
                            "video_classification_label": det.video_classification_label,
                            "video_classification_status": det.video_classification_status,
                            "video_classification_error": det.video_classification_error,
                            "video_classification_timestamp": det.video_classification_timestamp.isoformat() if det.video_classification_timestamp else None
                        }
                    })

    async def _save_results(self, frigate_event: str, result: dict):
        """Save final results via DetectionService to handle intelligent overrides."""
        from app.services.detection_service import DetectionService
        svc = DetectionService(self._classifier)
        
        await svc.apply_video_result(
            frigate_event=frigate_event,
            video_label=result['label'],
            video_score=result['score'],
            video_index=result['index']
        )
        # _record_success is already called on completion in _process_event.

# Global singleton
auto_video_classifier = AutoVideoClassifierService()
