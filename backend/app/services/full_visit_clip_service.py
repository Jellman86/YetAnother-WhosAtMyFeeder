import asyncio
import time
import weakref
from datetime import datetime, timedelta, timezone

import httpx
import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.routers.proxy import _get_recording_clip_context, _is_no_recordings_response
from app.services.frigate_client import frigate_client
from app.services.media_cache import media_cache
from app.utils.tasks import create_background_task

log = structlog.get_logger()

FULL_VISIT_FETCH_RETRY_ATTEMPTS = 2
FULL_VISIT_FETCH_RETRY_DELAY_SECONDS = 2.0
FULL_VISIT_RECONCILE_INTERVAL_SECONDS = 300.0
FULL_VISIT_RECONCILE_LOOKBACK_HOURS = 24
FULL_VISIT_RECONCILE_LIMIT = 100
FULL_VISIT_FAILURE_COOLDOWN_SECONDS = 1800.0


class FullVisitClipService:
    def __init__(self) -> None:
        self._event_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
        self._failure_retry_after: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def _auto_generation_enabled(self) -> bool:
        return bool(
            settings.frigate.clips_enabled
            and settings.frigate.recording_clip_enabled
            and settings.media_cache.enabled
        )

    def _lock_for_event(self, event_id: str) -> asyncio.Lock:
        lock = self._event_locks.get(event_id)
        if lock is None:
            lock = asyncio.Lock()
            self._event_locks[event_id] = lock
        return lock

    def _in_failure_cooldown(self, event_id: str) -> bool:
        next_retry_at = self._failure_retry_after.get(event_id)
        if next_retry_at is None:
            return False

        if time.time() >= next_retry_at:
            self._failure_retry_after.pop(event_id, None)
            return False

        return True

    def _mark_fetch_failure(self, event_id: str) -> None:
        self._failure_retry_after[event_id] = time.time() + FULL_VISIT_FAILURE_COOLDOWN_SECONDS

    def _mark_fetch_success(self, event_id: str) -> None:
        self._failure_retry_after.pop(event_id, None)

    def trigger_background(
        self,
        event_id: str,
        camera: str | None = None,
        *,
        source: str = "mqtt_end",
        lang: str = "en",
    ) -> asyncio.Task | None:
        if not self._auto_generation_enabled():
            return None
        return create_background_task(
            self.trigger_for_event(event_id, camera, source=source, lang=lang),
            name=f"full_visit_clip:{event_id}:{source}",
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = create_background_task(
            self._reconcile_loop(),
            name="full_visit_clip_reconcile",
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def trigger_for_event(
        self,
        event_id: str,
        camera: str | None = None,
        *,
        source: str = "mqtt_end",
        lang: str = "en",
    ) -> bool:
        if not self._auto_generation_enabled():
            return False

        if media_cache.get_recording_clip_path(event_id):
            self._mark_fetch_success(event_id)
            return True

        if self._in_failure_cooldown(event_id):
            log.debug(
                "Automatic full-visit fetch suppressed by cooldown",
                event_id=event_id,
                camera=camera,
                source=source,
            )
            return False

        lock = self._lock_for_event(event_id)
        async with lock:
            if media_cache.get_recording_clip_path(event_id):
                self._mark_fetch_success(event_id)
                return True

            if self._in_failure_cooldown(event_id):
                log.debug(
                    "Automatic full-visit fetch suppressed by cooldown after wait",
                    event_id=event_id,
                    camera=camera,
                    source=source,
                )
                return False

            for attempt in range(FULL_VISIT_FETCH_RETRY_ATTEMPTS):
                ready = await self._fetch_once(event_id, lang)
                if ready:
                    self._mark_fetch_success(event_id)
                    log.info(
                        "Automatic full-visit clip ready",
                        event_id=event_id,
                        camera=camera,
                        source=source,
                        attempt=attempt + 1,
                    )
                    return True
                if attempt < FULL_VISIT_FETCH_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(FULL_VISIT_FETCH_RETRY_DELAY_SECONDS)

        self._mark_fetch_failure(event_id)
        log.info(
            "Automatic full-visit clip unavailable",
            event_id=event_id,
            camera=camera,
            source=source,
        )
        return False

    async def reconcile_recent_detections(self) -> int:
        if not self._auto_generation_enabled():
            return 0

        now = datetime.now(timezone.utc)
        detected_before = now - timedelta(seconds=max(1, int(settings.frigate.recording_clip_after_seconds)))
        detected_after = now - timedelta(hours=FULL_VISIT_RECONCILE_LOOKBACK_HOURS)

        async with get_db() as db:
            repo = DetectionRepository(db)
            candidates = await repo.get_recent_full_visit_candidates(
                detected_before=detected_before,
                detected_after=detected_after,
                limit=FULL_VISIT_RECONCILE_LIMIT,
            )

        generated = 0
        for detection in candidates:
            if media_cache.get_recording_clip_path(detection.frigate_event):
                continue
            ready = await self.trigger_for_event(
                detection.frigate_event,
                detection.camera_name,
                source="reconcile",
                lang="en",
            )
            if ready:
                generated += 1
        return generated

    async def _reconcile_loop(self) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return

        while self._running:
            try:
                await self.reconcile_recent_detections()
                await asyncio.sleep(FULL_VISIT_RECONCILE_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 - keep recovery loop alive
                log.error("Automatic full-visit reconcile loop failed", error=str(exc))
                await asyncio.sleep(60)

    async def _fetch_once(self, event_id: str, lang: str) -> bool:
        camera_name, start_ts, end_ts = await _get_recording_clip_context(event_id, lang)
        clip_url = frigate_client.get_camera_recording_clip_url(camera_name, start_ts, end_ts)
        headers = frigate_client._get_headers()

        client = httpx.AsyncClient(timeout=120.0)
        req = client.build_request("GET", clip_url, headers=headers)
        response = await client.send(req, stream=True)
        try:
            if await _is_no_recordings_response(response) or response.status_code == 404:
                return False
            response.raise_for_status()
            cached = await media_cache.cache_recording_clip_streaming(event_id, response.aiter_bytes())
            return bool(cached)
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
            log.warning("Automatic full-visit fetch failed", event_id=event_id, error=str(exc))
            return False
        finally:
            await response.aclose()
            await client.aclose()


full_visit_clip_service = FullVisitClipService()
