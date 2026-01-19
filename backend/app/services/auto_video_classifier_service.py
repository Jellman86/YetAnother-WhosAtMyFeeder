import asyncio
import os
import tempfile
import structlog
from datetime import datetime
from typing import Optional, Dict

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.classifier_service import get_classifier
from app.services.broadcaster import broadcaster
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

    async def _process_event(self, frigate_event: str, camera: str):
        """Main workflow for processing a video clip."""
        log.info("Starting auto video classification", event_id=frigate_event, camera=camera)
        
        try:
            # 1. Update status in DB to 'pending'
            await self._update_status(frigate_event, 'pending')

            # Broadcast start
            await broadcaster.broadcast({
                "type": "reclassification_started",
                "data": {
                    "event_id": frigate_event,
                    "strategy": "auto_video"
                }
            })

            # 2. Wait for clip availability
            clip_bytes = await self._wait_for_clip(frigate_event)
            if not clip_bytes:
                log.warning("Clip not available after retries", event_id=frigate_event)
                await self._update_status(frigate_event, 'failed')
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
                await self._update_status(frigate_event, 'processing')
                
                async def progress_callback(current, total, score, label, frame_thumb=None):
                    # Broadcast progress via SSE
                    await broadcaster.broadcast({
                        "type": "reclassification_progress",
                        "data": {
                            "event_id": frigate_event,
                            "current_frame": current,
                            "total_frames": total,
                            "frame_score": score,
                            "top_label": label,
                            "frame_thumb": frame_thumb
                        }
                    })

                results = await self._classifier.classify_video_async(
                    tmp_path,
                    max_frames=15,
                    progress_callback=progress_callback
                )

                if results:
                    top = results[0]
                    # 5. Save results to DB
                    await self._save_results(frigate_event, top)
                    
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
                    await self._update_status(frigate_event, 'failed')
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
            await self._update_status(frigate_event, 'failed')
            raise
        except Exception as e:
            log.error("Video classification failed", event_id=frigate_event, error=str(e))
            await self._update_status(frigate_event, 'failed')
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": { "event_id": frigate_event, "results": [] }
            })

    async def _wait_for_clip(self, frigate_event: str) -> Optional[bytes]:
        """Poll Frigate for clip availability with retries."""
        # Initial delay to allow Frigate to finalize the clip
        await asyncio.sleep(settings.classification.video_classification_delay)

        max_retries = settings.classification.video_classification_max_retries
        retry_interval = settings.classification.video_classification_retry_interval

        for attempt in range(max_retries + 1):
            log.debug("Polling for clip", event_id=frigate_event, attempt=attempt)
            clip_bytes = await frigate_client.get_clip(frigate_event)
            
            if clip_bytes and len(clip_bytes) > 0:
                # Basic sanity check: MP4 header
                if clip_bytes.startswith(b'\x00\x00\x00\x18ftyp') or b'ftyp' in clip_bytes[:32]:
                    return clip_bytes
            
            if attempt < max_retries:
                # Exponential backoff: 1x, 2x, 4x...
                wait_time = retry_interval * (2 ** attempt)
                log.debug(f"Clip not ready, waiting {wait_time}s", event_id=frigate_event)
                await asyncio.sleep(wait_time)

        return None

    async def _update_status(self, frigate_event: str, status: str):
        """Update video classification status in DB."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.update_video_status(frigate_event, status)

    async def _save_results(self, frigate_event: str, result: dict):
        """Save final results to DB and broadcast detection update."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.update_video_classification(
                frigate_event=frigate_event,
                label=result['label'],
                score=result['score'],
                index=result['index'],
                status='completed'
            )
            
            # Fetch the full updated detection to broadcast
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
                        "video_classification_timestamp": det.video_classification_timestamp.isoformat() if det.video_classification_timestamp else None
                    }
                })

# Global singleton
auto_video_classifier = AutoVideoClassifierService()
