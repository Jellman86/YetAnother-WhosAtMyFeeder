import asyncio
import contextlib
import inspect
import itertools
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal


WorkPriority = Literal["live", "background"]
WorkState = Literal["queued", "running", "completed", "failed", "abandoned", "rejected"]


class ClassificationAdmissionError(RuntimeError):
    """Base class for coordinator submission failures."""


class ClassificationAdmissionTimeoutError(ClassificationAdmissionError):
    """Raised when queued work cannot be admitted in time."""

    def __init__(self, priority: WorkPriority, kind: str, timeout_seconds: float):
        super().__init__(
            f"classification_admission_timeout priority={priority} kind={kind} timeout={timeout_seconds}"
        )
        self.priority = priority
        self.kind = kind
        self.timeout_seconds = timeout_seconds


class ClassificationLeaseExpiredError(ClassificationAdmissionError):
    """Raised when admitted work exceeds its lease deadline."""

    def __init__(self, priority: WorkPriority, kind: str, timeout_seconds: float):
        super().__init__(
            f"classification_lease_expired priority={priority} kind={kind} timeout={timeout_seconds}"
        )
        self.priority = priority
        self.kind = kind
        self.timeout_seconds = timeout_seconds


@dataclass(slots=True)
class _WorkItem:
    work_id: str
    priority: WorkPriority
    kind: str
    runner: Callable[..., Awaitable[Any]]
    queue_timeout_seconds: float
    lease_timeout_seconds: float
    enqueued_at: float
    admitted_future: asyncio.Future[None]
    result_future: asyncio.Future[Any]
    runner_accepts_work_metadata: bool = False
    on_lease_expired: Callable[[str, int], Awaitable[None] | None] | None = None
    state: WorkState = "queued"
    lease_token: int = 0
    admitted_at: float | None = None
    deadline_at: float | None = None
    task: asyncio.Task[Any] | None = None


class ClassificationAdmissionCoordinator:
    """Coordinate live/background admission with lease reclaim and stale-completion rejection."""

    REAPER_INTERVAL_SECONDS = 0.01
    RECENT_OUTCOME_LIMIT = 100

    def __init__(
        self,
        *,
        live_capacity: int,
        background_capacity: int,
        live_lease_timeout_seconds: float,
        background_lease_timeout_seconds: float,
        default_queue_timeout_seconds: float = 0.25,
        background_starvation_threshold_seconds: float = 2.0,
    ) -> None:
        self._live_capacity = max(1, int(live_capacity))
        self._background_capacity = max(1, int(background_capacity))
        self._default_lease_timeout_seconds = {
            "live": max(0.01, float(live_lease_timeout_seconds)),
            "background": max(0.01, float(background_lease_timeout_seconds)),
        }
        self._default_queue_timeout_seconds = max(0.01, float(default_queue_timeout_seconds))
        self._background_starvation_threshold_seconds = max(0.01, float(background_starvation_threshold_seconds))

        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._work_id_counter = itertools.count(1)
        self._pending: dict[WorkPriority, deque[_WorkItem]] = {
            "live": deque(),
            "background": deque(),
        }
        self._active: dict[str, _WorkItem] = {}
        self._running: Counter[str] = Counter()
        self._completed: Counter[str] = Counter()
        self._failed: Counter[str] = Counter()
        self._abandoned: Counter[str] = Counter()
        self._rejected: Counter[str] = Counter()
        self._late_completions_ignored = 0
        self._recent_outcomes: deque[dict[str, Any]] = deque(maxlen=self.RECENT_OUTCOME_LIMIT)
        self._closed = False
        self._reaper_task: asyncio.Task[None] | None = None

    async def submit(
        self,
        *,
        priority: WorkPriority,
        kind: str,
        runner: Callable[..., Awaitable[Any]],
        queue_timeout_seconds: float | None = None,
        lease_timeout_seconds: float | None = None,
        runner_accepts_work_metadata: bool = False,
        on_lease_expired: Callable[[str, int], Awaitable[None] | None] | None = None,
    ) -> Any:
        if priority not in {"live", "background"}:
            raise ValueError(f"unsupported priority: {priority}")

        self._ensure_reaper_started()
        loop = asyncio.get_running_loop()
        queue_timeout = max(
            0.01,
            float(
                queue_timeout_seconds
                if queue_timeout_seconds is not None
                else self._default_queue_timeout_seconds
            ),
        )
        lease_timeout = max(
            0.01,
            float(
                lease_timeout_seconds
                if lease_timeout_seconds is not None
                else self._default_lease_timeout_seconds[priority]
            ),
        )
        work_id = f"{priority}-{next(self._work_id_counter)}"
        item = _WorkItem(
            work_id=work_id,
            priority=priority,
            kind=str(kind or "unknown"),
            runner=runner,
            queue_timeout_seconds=queue_timeout,
            lease_timeout_seconds=lease_timeout,
            enqueued_at=time.monotonic(),
            admitted_future=loop.create_future(),
            result_future=loop.create_future(),
            runner_accepts_work_metadata=bool(runner_accepts_work_metadata),
            on_lease_expired=on_lease_expired,
        )

        async with self._condition:
            self._assert_open_locked()
            self._pending[priority].append(item)
            self._schedule_locked()
            self._condition.notify_all()

        try:
            await asyncio.wait_for(asyncio.shield(item.admitted_future), timeout=queue_timeout)
        except asyncio.TimeoutError as exc:
            async with self._condition:
                if item.state == "queued":
                    self._remove_pending_locked(item)
                    item.state = "rejected"
                    self._rejected[priority] += 1
                    self._record_recent_outcome_locked(item, "rejected", reason="queue_timeout")
                    if not item.result_future.done():
                        item.result_future.cancel()
                    self._condition.notify_all()
                    raise ClassificationAdmissionTimeoutError(priority, item.kind, queue_timeout) from exc
            # The item may have been admitted just as the queue timeout fired.
            # In that race, preserve the admitted work and await its real result.

        try:
            return await asyncio.shield(item.result_future)
        finally:
            # If the caller is cancelled after admission, keep the coordinator state authoritative.
            # Reaper or runner completion will settle the work item.
            pass

    async def shutdown(self) -> None:
        self._closed = True
        async with self._condition:
            for priority in ("live", "background"):
                while self._pending[priority]:
                    item = self._pending[priority].popleft()
                    item.state = "rejected"
                    self._rejected[priority] += 1
                    self._record_recent_outcome_locked(item, "rejected", reason="shutdown")
                    if not item.admitted_future.done():
                        item.admitted_future.set_exception(RuntimeError("classification coordinator shutdown"))
                    if not item.result_future.done():
                        item.result_future.cancel()
            self._condition.notify_all()

        if self._reaper_task is not None:
            self._reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper_task

    def close_sync(self) -> None:
        self._closed = True
        if self._reaper_task is not None and not self._reaper_task.done():
            self._reaper_task.cancel()

    def get_metrics(self) -> dict[str, Any]:
        return {
            "live": {
                "capacity": self._live_capacity,
                "queued": len(self._pending["live"]),
                "running": self._running["live"],
                "completed": self._completed["live"],
                "failed": self._failed["live"],
                "abandoned": self._abandoned["live"],
                "rejected": self._rejected["live"],
                "oldest_running_age_seconds": self._oldest_active_age_seconds("live"),
            },
            "background": {
                "capacity": self._background_capacity,
                "queued": len(self._pending["background"]),
                "running": self._running["background"],
                "completed": self._completed["background"],
                "failed": self._failed["background"],
                "abandoned": self._abandoned["background"],
                "rejected": self._rejected["background"],
                "oldest_queued_age_seconds": self._oldest_pending_age_seconds("background"),
                "oldest_running_age_seconds": self._oldest_active_age_seconds("background"),
            },
            "late_completions_ignored": self._late_completions_ignored,
            "recent_outcomes": list(self._recent_outcomes),
            "background_throttled": self._is_live_pressure_active(),
            "background_starvation_relief_active": self._is_background_starvation_relief_active(),
            "closed": self._closed,
        }

    def _ensure_reaper_started(self) -> None:
        if self._reaper_task is not None:
            return
        loop = asyncio.get_running_loop()
        self._reaper_task = loop.create_task(self._reaper_loop())

    async def _reaper_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self.REAPER_INTERVAL_SECONDS)
                async with self._condition:
                    expired_callbacks = self._reclaim_expired_locked()
                    self._schedule_locked()
                    self._condition.notify_all()
                await self._dispatch_lease_expired_callbacks(expired_callbacks)
        except asyncio.CancelledError:
            raise

    def _schedule_locked(self) -> None:
        if self._closed:
            return

        while self._pending["live"] and self._running["live"] < self._live_capacity:
            item = self._pending["live"].popleft()
            self._admit_locked(item)

        while (
            self._pending["background"]
            and self._running["background"] < self._background_capacity
            and (
                not self._is_live_pressure_active()
                or self._is_background_starvation_relief_active()
            )
        ):
            item = self._pending["background"].popleft()
            self._admit_locked(item)

    def _admit_locked(self, item: _WorkItem) -> None:
        item.state = "running"
        item.admitted_at = time.monotonic()
        item.deadline_at = item.admitted_at + item.lease_timeout_seconds
        item.lease_token += 1
        token = item.lease_token
        self._active[item.work_id] = item
        self._running[item.priority] += 1
        self._record_recent_outcome_locked(item, "running")

        if not item.admitted_future.done():
            item.admitted_future.set_result(None)

        loop = asyncio.get_running_loop()
        item.task = loop.create_task(self._run_item(item, token))

    async def _run_item(self, item: _WorkItem, token: int) -> None:
        try:
            if item.runner_accepts_work_metadata:
                result = await item.runner(item.work_id, token)
            else:
                result = await item.runner()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self._condition:
                active = self._active.get(item.work_id)
                if (
                    active is not item
                    or item.state != "running"
                    or item.lease_token != token
                ):
                    self._late_completions_ignored += 1
                    self._record_recent_outcome_locked(item, "late_failure_ignored", error=str(exc))
                    return

                self._active.pop(item.work_id, None)
                self._running[item.priority] -= 1
                item.state = "failed"
                item.deadline_at = None
                self._failed[item.priority] += 1
                self._record_recent_outcome_locked(item, "failed", error=str(exc))
                if not item.result_future.done():
                    item.result_future.set_exception(exc)
                self._schedule_locked()
                self._condition.notify_all()
            return

        async with self._condition:
            active = self._active.get(item.work_id)
            if (
                active is not item
                or item.state != "running"
                or item.lease_token != token
            ):
                self._late_completions_ignored += 1
                self._record_recent_outcome_locked(item, "late_completion_ignored")
                return

            self._active.pop(item.work_id, None)
            self._running[item.priority] -= 1
            item.state = "completed"
            item.deadline_at = None
            self._completed[item.priority] += 1
            self._record_recent_outcome_locked(item, "completed")
            if not item.result_future.done():
                item.result_future.set_result(result)
            self._schedule_locked()
            self._condition.notify_all()

    def _reclaim_expired_locked(self) -> list[tuple[Callable[[str, int], Awaitable[None] | None], str, int]]:
        now = time.monotonic()
        callbacks: list[tuple[Callable[[str, int], Awaitable[None] | None], str, int]] = []
        expired = [
            item
            for item in self._active.values()
            if item.state == "running" and item.deadline_at is not None and item.deadline_at <= now
        ]
        for item in expired:
            if self._active.get(item.work_id) is not item:
                continue
            self._active.pop(item.work_id, None)
            self._running[item.priority] -= 1
            item.state = "abandoned"
            item.deadline_at = None
            self._abandoned[item.priority] += 1
            self._record_recent_outcome_locked(item, "abandoned")
            if not item.result_future.done():
                item.result_future.set_exception(
                    ClassificationLeaseExpiredError(
                        item.priority,
                        item.kind,
                        item.lease_timeout_seconds,
                    )
                )
            if item.on_lease_expired is not None:
                callbacks.append((item.on_lease_expired, item.work_id, item.lease_token))
        return callbacks

    def _is_live_pressure_active(self) -> bool:
        return bool(self._pending["live"]) or self._running["live"] >= self._live_capacity

    def _is_background_starvation_relief_active(self) -> bool:
        if not self._is_live_pressure_active():
            return False
        oldest_pending_age = self._oldest_pending_age_seconds("background")
        if oldest_pending_age is None:
            return False
        return oldest_pending_age >= self._background_starvation_threshold_seconds

    def _remove_pending_locked(self, item: _WorkItem) -> None:
        queue = self._pending[item.priority]
        try:
            queue.remove(item)
        except ValueError:
            return

    def _assert_open_locked(self) -> None:
        if self._closed:
            raise RuntimeError("classification coordinator is closed")

    def _record_recent_outcome_locked(self, item: _WorkItem, outcome: str, **extra: Any) -> None:
        payload = {
            "work_id": item.work_id,
            "priority": item.priority,
            "kind": item.kind,
            "outcome": outcome,
            "timestamp": time.time(),
        }
        payload.update(extra)
        self._recent_outcomes.append(payload)

    def _oldest_active_age_seconds(self, priority: WorkPriority) -> float | None:
        now = time.monotonic()
        ages = [
            max(0.0, now - item.admitted_at)
            for item in self._active.values()
            if item.priority == priority and item.admitted_at is not None
        ]
        if not ages:
            return None
        return round(max(ages), 3)

    def _oldest_pending_age_seconds(self, priority: WorkPriority) -> float | None:
        pending = self._pending[priority]
        if not pending:
            return None
        now = time.monotonic()
        ages = [max(0.0, now - item.enqueued_at) for item in pending]
        if not ages:
            return None
        return round(max(ages), 3)

    async def _dispatch_lease_expired_callbacks(
        self,
        callbacks: list[tuple[Callable[[str, int], Awaitable[None] | None], str, int]],
    ) -> None:
        for callback, work_id, lease_token in callbacks:
            try:
                callback_result = callback(work_id, lease_token)
            except Exception:
                continue
            if inspect.isawaitable(callback_result):
                with contextlib.suppress(Exception):
                    await callback_result
