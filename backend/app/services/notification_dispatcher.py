import asyncio
import os
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from app.services.error_diagnostics import error_diagnostics_history
from app.utils.tasks import create_background_task

log = structlog.get_logger()

NOTIFICATION_DISPATCH_WORKERS = max(1, int(os.getenv("NOTIFICATION_DISPATCH_WORKERS", "2")))
NOTIFICATION_DISPATCH_QUEUE_MAX = max(10, int(os.getenv("NOTIFICATION_DISPATCH_QUEUE_MAX", "500")))
NOTIFICATION_DISPATCH_TIMEOUT_SECONDS = max(5.0, float(os.getenv("NOTIFICATION_DISPATCH_TIMEOUT_SECONDS", "30.0")))


class NotificationDispatcher:
    """Bounded async queue for notification jobs.

    This keeps remote notification I/O off latency-sensitive ingest paths and
    prevents unbounded task fan-out under burst traffic.
    """

    def __init__(self):
        self._queue: asyncio.Queue[tuple[str, Callable[[], Coroutine[Any, Any, None]]]] | None = None
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._dropped_jobs = 0
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_loop_state(self) -> int:
        loop = asyncio.get_running_loop()
        if self._loop is loop and self._queue is not None and self._lock is not None:
            return 0

        for worker in self._workers:
            worker.cancel()
        dropped = self._queue.qsize() if self._queue is not None else 0
        self._queue = asyncio.Queue(maxsize=NOTIFICATION_DISPATCH_QUEUE_MAX)
        self._workers = []
        self._running = False
        self._lock = asyncio.Lock()
        self._loop = loop
        return dropped

    def _queue_size(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    def _record_loop_reset_drop(self, dropped: int) -> None:
        if dropped <= 0:
            return
        self._dropped_jobs += dropped
        log.warning(
            "Notification dispatcher dropped queued jobs after event-loop reset",
            dropped_queued=dropped,
            dropped_jobs=self._dropped_jobs,
        )
        error_diagnostics_history.record(
            source="notification_dispatcher",
            component="notification_dispatcher",
            stage="loop_reset",
            reason_code="loop_reset_drop",
            message="Notification dispatcher dropped queued jobs after event-loop reset",
            severity="error",
            event_id="event_loop_reset",
            context={
                "dropped_queued": dropped,
                "dropped_jobs": self._dropped_jobs,
                "queue_max": NOTIFICATION_DISPATCH_QUEUE_MAX,
            },
        )

    async def start(self) -> None:
        dropped = self._ensure_loop_state()
        self._record_loop_reset_drop(dropped)
        async with self._lock:
            if self._running:
                return
            self._running = True
            self._workers = [
                create_background_task(self._worker_loop(i), name=f"notification_dispatcher:{i}")
                for i in range(NOTIFICATION_DISPATCH_WORKERS)
            ]
            log.info(
                "Notification dispatcher started",
                workers=NOTIFICATION_DISPATCH_WORKERS,
                queue_max=NOTIFICATION_DISPATCH_QUEUE_MAX,
                timeout_seconds=NOTIFICATION_DISPATCH_TIMEOUT_SECONDS,
            )

    async def stop(self) -> None:
        self._ensure_loop_state()
        async with self._lock:
            if not self._running:
                return
            self._running = False
            for worker in self._workers:
                worker.cancel()
            for worker in self._workers:
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
            self._workers.clear()
            queued = 0
            while self._queue is not None and not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                    queued += 1
                except asyncio.QueueEmpty:
                    break
            log.info(
                "Notification dispatcher stopped",
                queued=queued,
                dropped_jobs=self._dropped_jobs,
            )

    async def enqueue(
        self,
        job_name: str,
        job_factory: Callable[[], Coroutine[Any, Any, None]],
    ) -> bool:
        dropped = self._ensure_loop_state()
        self._record_loop_reset_drop(dropped)
        if not self._running:
            await self.start()

        if self._queue is not None and self._queue.full():
            self._dropped_jobs += 1
            log.warning(
                "Notification job dropped: dispatcher queue is full",
                job=job_name,
                queue_size=self._queue_size(),
                queue_max=NOTIFICATION_DISPATCH_QUEUE_MAX,
                dropped_jobs=self._dropped_jobs,
            )
            error_diagnostics_history.record(
                source="notification_dispatcher",
                component="notification_dispatcher",
                stage="enqueue",
                reason_code="queue_full",
                message="Notification job dropped because dispatcher queue is full",
                severity="error",
                event_id=job_name,
                context={
                    "queue_size": self._queue_size(),
                    "queue_max": NOTIFICATION_DISPATCH_QUEUE_MAX,
                    "dropped_jobs": self._dropped_jobs,
                },
            )
            return False

        try:
            self._queue.put_nowait((job_name, job_factory))
            return True
        except asyncio.QueueFull:
            self._dropped_jobs += 1
            log.warning(
                "Notification job dropped: dispatcher queue became full before enqueue",
                job=job_name,
                queue_size=self._queue_size(),
                queue_max=NOTIFICATION_DISPATCH_QUEUE_MAX,
                dropped_jobs=self._dropped_jobs,
            )
            error_diagnostics_history.record(
                source="notification_dispatcher",
                component="notification_dispatcher",
                stage="enqueue",
                reason_code="queue_full_race",
                message="Notification job dropped because dispatcher queue became full",
                severity="error",
                event_id=job_name,
                context={
                    "queue_size": self._queue_size(),
                    "queue_max": NOTIFICATION_DISPATCH_QUEUE_MAX,
                    "dropped_jobs": self._dropped_jobs,
                },
            )
            return False

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "workers": len(self._workers),
            "queue_size": self._queue_size(),
            "queue_max": NOTIFICATION_DISPATCH_QUEUE_MAX,
            "dropped_jobs": self._dropped_jobs,
            "timeout_seconds": NOTIFICATION_DISPATCH_TIMEOUT_SECONDS,
        }

    async def _worker_loop(self, worker_idx: int) -> None:
        while self._running:
            try:
                job_name, job_factory = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await asyncio.wait_for(job_factory(), timeout=NOTIFICATION_DISPATCH_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                log.warning(
                    "Notification job timed out",
                    job=job_name,
                    worker=worker_idx,
                    timeout_seconds=NOTIFICATION_DISPATCH_TIMEOUT_SECONDS,
                )
                error_diagnostics_history.record(
                    source="notification_dispatcher",
                    component="notification_dispatcher",
                    stage="worker",
                    reason_code="job_timeout",
                    message=f"Notification job timed out after {NOTIFICATION_DISPATCH_TIMEOUT_SECONDS}s",
                    severity="error",
                    event_id=job_name,
                    context={"worker": worker_idx, "timeout_seconds": NOTIFICATION_DISPATCH_TIMEOUT_SECONDS},
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(
                    "Notification job failed",
                    job=job_name,
                    worker=worker_idx,
                    error=str(e),
                    exc_info=True,
                )
                error_diagnostics_history.record(
                    source="notification_dispatcher",
                    component="notification_dispatcher",
                    stage="worker",
                    reason_code="job_failed",
                    message=f"Notification job failed: {e}",
                    severity="critical",
                    event_id=job_name,
                    context={"worker": worker_idx, "error": str(e)},
                )
            finally:
                self._queue.task_done()


notification_dispatcher = NotificationDispatcher()
