import asyncio
import inspect
import itertools
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from .classifier_worker_client import ClassifierWorkerClient
from .classifier_worker_protocol import build_classify_request, build_classify_video_request


WorkPriority = Literal["live", "background", "video"]


class ClassifierWorkerHeartbeatTimeoutError(RuntimeError):
    pass


class ClassifierWorkerDeadlineExceededError(RuntimeError):
    pass


class ClassifierWorkerExitedError(RuntimeError):
    pass


class ClassifierWorkerStartupTimeoutError(RuntimeError):
    pass


class ClassifierWorkerCircuitOpenError(RuntimeError):
    pass


@dataclass
class _WorkerSlot:
    priority: WorkPriority
    index: int
    worker_name: str
    worker_generation: int
    worker: Any | None
    consumer_task: asyncio.Task[None] | None


@dataclass
class _Assignment:
    priority: WorkPriority
    worker_name: str
    worker_generation: int
    request_id: str
    work_id: str
    lease_token: int
    started_at: float
    future: asyncio.Future[list[dict[str, Any]]]
    progress_callback: Callable[..., Awaitable[None] | None] | None = None


class ClassifierSupervisor:
    def __init__(
        self,
        *,
        live_worker_count: int,
        background_worker_count: int,
        video_worker_count: int = 1,
        heartbeat_timeout_seconds: float,
        hard_deadline_seconds: float,
        video_hard_deadline_seconds: float | None = None,
        worker_ready_timeout_seconds: float = 20.0,
        video_worker_ready_timeout_seconds: float | None = None,
        worker_factory=None,
        watchdog_interval_seconds: float = 0.05,
        restart_window_seconds: float = 60.0,
        restart_threshold: int = 3,
        breaker_cooldown_seconds: float = 60.0,
    ) -> None:
        self._worker_counts = {
            "live": max(1, int(live_worker_count)),
            "background": max(1, int(background_worker_count)),
            "video": max(1, int(video_worker_count)),
        }
        self._heartbeat_timeout_seconds = max(0.01, float(heartbeat_timeout_seconds))
        base_hard_deadline_seconds = max(0.01, float(hard_deadline_seconds))
        self._hard_deadline_seconds = {
            "live": base_hard_deadline_seconds,
            "background": base_hard_deadline_seconds,
            "video": max(
                0.01,
                float(video_hard_deadline_seconds)
                if video_hard_deadline_seconds is not None
                else base_hard_deadline_seconds,
            ),
        }
        base_ready_timeout_seconds = max(0.01, float(worker_ready_timeout_seconds))
        self._worker_ready_timeout_seconds = {
            "live": base_ready_timeout_seconds,
            "background": base_ready_timeout_seconds,
            "video": max(
                0.01,
                float(video_worker_ready_timeout_seconds)
                if video_worker_ready_timeout_seconds is not None
                else base_ready_timeout_seconds,
            ),
        }
        self._watchdog_interval_seconds = max(0.01, float(watchdog_interval_seconds))
        self._restart_window_seconds = max(0.01, float(restart_window_seconds))
        self._restart_threshold = max(1, int(restart_threshold))
        self._breaker_cooldown_seconds = max(0.01, float(breaker_cooldown_seconds))
        self._worker_factory = worker_factory
        self._slots: dict[WorkPriority, list[_WorkerSlot]] = {"live": [], "background": [], "video": []}
        self._assignments: dict[str, _Assignment] = {}
        self._metrics = {
            "live": {
                "workers": 0,
                "restarts": 0,
                "last_exit_reason": None,
                "last_stderr_excerpt": "",
                "last_stderr_truncated_bytes": 0,
                "last_runtime_recovery": None,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "background": {
                "workers": 0,
                "restarts": 0,
                "last_exit_reason": None,
                "last_stderr_excerpt": "",
                "last_stderr_truncated_bytes": 0,
                "last_runtime_recovery": None,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "video": {
                "workers": 0,
                "restarts": 0,
                "last_exit_reason": None,
                "last_stderr_excerpt": "",
                "last_stderr_truncated_bytes": 0,
                "last_runtime_recovery": None,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "late_results_ignored": 0,
        }
        self._restart_history: dict[WorkPriority, deque[float]] = {
            "live": deque(),
            "background": deque(),
            "video": deque(),
        }
        self._consumer_tasks: set[asyncio.Task[None]] = set()
        self._request_counter = itertools.count(1)
        self._condition = asyncio.Condition()
        self._start_locks: dict[WorkPriority, asyncio.Lock] = {
            "live": asyncio.Lock(),
            "background": asyncio.Lock(),
            "video": asyncio.Lock(),
        }
        self._pool_started: dict[WorkPriority, bool] = {"live": False, "background": False, "video": False}
        self._watchdog_task: asyncio.Task[None] | None = None
        self._started = False

    async def start(self, priority: WorkPriority | None = None) -> None:
        priorities: tuple[WorkPriority, ...]
        if priority is None:
            priorities = ("live", "background", "video")
        else:
            priorities = (priority,)

        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

        previously_started = {current: self._pool_started[current] for current in priorities}
        await asyncio.gather(*(self._ensure_pool_started(current) for current in priorities))
        await asyncio.gather(
            *(
                self._restore_unavailable_slots(current)
                for current in priorities
                if previously_started[current]
            )
        )
        self._started = any(self._pool_started.values())

    async def shutdown(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        for priority in ("live", "background", "video"):
            for slot in self._slots[priority]:
                if slot.worker is not None:
                    await slot.worker.terminate()
                    await slot.worker.wait_closed()
        for task in list(self._consumer_tasks):
            task.cancel()
        for task in list(self._consumer_tasks):
            try:
                await task
            except asyncio.CancelledError:
                pass

    def get_metrics(self) -> dict[str, Any]:
        return {
            "live": dict(self._metrics["live"]),
            "background": dict(self._metrics["background"]),
            "video": dict(self._metrics["video"]),
            "late_results_ignored": self._metrics["late_results_ignored"],
        }

    async def classify(
        self,
        *,
        priority: WorkPriority,
        work_id: str,
        lease_token: int,
        image_b64: str,
        camera_name: str | None,
        model_id: str | None,
    ) -> list[dict[str, Any]]:
        return await self._submit_request(
            priority=priority,
            work_id=str(work_id),
            lease_token=int(lease_token),
            build_message=lambda slot, request_id: build_classify_request(
                worker_generation=slot.worker_generation,
                request_id=request_id,
                work_id=str(work_id),
                lease_token=int(lease_token),
                image_b64=image_b64,
                camera_name=camera_name,
                model_id=model_id,
            ),
        )

    async def classify_video(
        self,
        *,
        work_id: str,
        lease_token: int,
        video_path: str,
        stride: int = 5,
        max_frames: int | None = None,
        progress_callback: Callable[..., Awaitable[None] | None] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._submit_request(
            priority="video",
            work_id=str(work_id),
            lease_token=int(lease_token),
            build_message=lambda slot, request_id: build_classify_video_request(
                worker_generation=slot.worker_generation,
                request_id=request_id,
                work_id=str(work_id),
                lease_token=int(lease_token),
                video_path=video_path,
                stride=int(stride),
                max_frames=max_frames,
            ),
            progress_callback=progress_callback,
        )

    async def _submit_request(
        self,
        *,
        priority: WorkPriority,
        work_id: str,
        lease_token: int,
        build_message: Callable[[_WorkerSlot, str], dict[str, Any]],
        progress_callback: Callable[..., Awaitable[None] | None] | None = None,
    ) -> list[dict[str, Any]]:
        await self.start(priority)
        self._refresh_circuit_state(priority)
        await self._restore_unavailable_slots(priority)
        if self._metrics[priority]["circuit_open"]:
            raise ClassifierWorkerCircuitOpenError(f"{priority} classifier circuit is open")

        loop = asyncio.get_running_loop()
        request_id = f"req-{next(self._request_counter)}"
        future: asyncio.Future[list[dict[str, Any]]] = loop.create_future()
        future.add_done_callback(self._consume_future_exception)

        async with self._condition:
            slot = await self._wait_for_idle_slot(priority)
            assignment = _Assignment(
                priority=priority,
                worker_name=slot.worker_name,
                worker_generation=slot.worker_generation,
                request_id=request_id,
                work_id=work_id,
                lease_token=lease_token,
                started_at=time.monotonic(),
                future=future,
                progress_callback=progress_callback,
            )
            self._assignments[slot.worker_name] = assignment

        try:
            await slot.worker.send(build_message(slot, request_id))
        except Exception as exc:
            assignment_error = ClassifierWorkerExitedError(
                f"worker send failed: {type(exc).__name__}"
            )
            current_slot = self._find_slot(slot.worker_name)
            if current_slot is not None and current_slot.worker_generation == slot.worker_generation:
                await self._replace_worker(
                    priority,
                    current_slot.index,
                    reason="send_failed",
                    assignment_error=assignment_error,
                    kill=False,
                )
            else:
                assignment = self._assignments.pop(slot.worker_name, None)
                if assignment is not None and not assignment.future.done():
                    assignment.future.set_exception(assignment_error)
                async with self._condition:
                    self._condition.notify_all()
            raise assignment_error from exc
        return await future

    async def _ensure_pool_started(self, priority: WorkPriority) -> None:
        if self._pool_started[priority]:
            return

        async with self._start_locks[priority]:
            if self._pool_started[priority]:
                return

            slots: list[_WorkerSlot] = []
            for index in range(self._worker_counts[priority]):
                try:
                    slots.append(await self._spawn_worker(priority, index, generation=1))
                except BaseException as exc:
                    if not slots:
                        self._slots[priority] = []
                        self._metrics[priority]["workers"] = 0
                        raise exc
                    slots.append(
                        _WorkerSlot(
                            priority=priority,
                            index=index,
                            worker_name=f"{priority}-{index}",
                            worker_generation=1,
                            worker=None,
                            consumer_task=None,
                        )
                    )
                    if isinstance(exc, ClassifierWorkerStartupTimeoutError):
                        self._metrics[priority]["last_exit_reason"] = "startup_timeout"
                    else:
                        self._metrics[priority]["last_exit_reason"] = "startup_failed"

            self._slots[priority] = slots
            self._metrics[priority]["workers"] = len(slots)
            self._pool_started[priority] = True
            self._metrics[priority]["workers"] = self._active_worker_count(priority)

    async def _wait_for_idle_slot(self, priority: WorkPriority) -> _WorkerSlot:
        while True:
            for slot in self._slots[priority]:
                if slot.worker is not None and slot.worker_name not in self._assignments:
                    return slot
            await self._condition.wait()

    async def _restore_unavailable_slots(self, priority: WorkPriority) -> None:
        if not self._pool_started[priority]:
            return

        async with self._start_locks[priority]:
            for index, slot in enumerate(list(self._slots[priority])):
                if slot.worker is not None:
                    continue
                try:
                    self._slots[priority][index] = await self._spawn_worker(
                        priority,
                        index,
                        generation=slot.worker_generation,
                    )
                except ClassifierWorkerStartupTimeoutError:
                    self._record_unavailable_slot(priority, index, "startup_timeout")
                    continue
                except Exception:
                    self._record_unavailable_slot(priority, index, "startup_failed")
                    continue
            self._metrics[priority]["workers"] = self._active_worker_count(priority)

    async def _spawn_worker(self, priority: WorkPriority, index: int, generation: int) -> _WorkerSlot:
        worker_name = f"{priority}-{index}"
        worker = None
        try:
            if self._worker_factory is None:
                worker = ClassifierWorkerClient(
                    worker_name=worker_name,
                    worker_generation=generation,
                    heartbeat_timeout_seconds=self._heartbeat_timeout_seconds,
                )
            else:
                worker = await self._worker_factory(
                    worker_name=worker_name,
                    worker_generation=generation,
                    priority=priority,
                    index=index,
                )
            await worker.start()
            await worker.wait_until_ready(timeout_seconds=self._worker_ready_timeout_seconds[priority])
        except TimeoutError as exc:
            await self._close_failed_worker(worker)
            self._record_start_failure(priority, worker, reason="startup_timeout")
            raise ClassifierWorkerStartupTimeoutError(
                f"worker startup timed out worker={worker_name} generation={generation} timeout={self._worker_ready_timeout_seconds[priority]}"
            ) from exc
        except Exception as exc:
            await self._close_failed_worker(worker)
            self._record_start_failure(priority, worker, reason="startup_failed")
            raise ClassifierWorkerExitedError(str(exc) or "worker failed during startup") from exc
        consumer_task = asyncio.create_task(self._consume_worker_events(worker_name, generation, worker))
        self._consumer_tasks.add(consumer_task)
        consumer_task.add_done_callback(self._consumer_tasks.discard)
        return _WorkerSlot(
            priority=priority,
            index=index,
            worker_name=worker_name,
            worker_generation=generation,
            worker=worker,
            consumer_task=consumer_task,
        )

    async def _close_failed_worker(self, worker: Any) -> None:
        if worker is None:
            return
        try:
            await worker.terminate()
        except Exception:
            pass
        try:
            await worker.wait_closed()
        except Exception:
            pass

    def _record_start_failure(self, priority: WorkPriority, worker: Any, *, reason: str) -> None:
        status = worker.get_status() if worker is not None and hasattr(worker, "get_status") else {}
        self._metrics[priority]["last_exit_reason"] = reason
        self._metrics[priority]["last_stderr_excerpt"] = str(status.get("recent_stderr_excerpt") or "")
        self._metrics[priority]["last_stderr_truncated_bytes"] = int(status.get("stderr_truncated_bytes") or 0)

    def _record_unavailable_slot(self, priority: WorkPriority, index: int, reason: str) -> None:
        slot = self._slots[priority][index]
        self._slots[priority][index] = _WorkerSlot(
            priority=priority,
            index=index,
            worker_name=slot.worker_name,
            worker_generation=slot.worker_generation,
            worker=None,
            consumer_task=slot.consumer_task,
        )
        self._metrics[priority]["last_exit_reason"] = reason
        self._metrics[priority]["workers"] = self._active_worker_count(priority)
        self._record_restart(priority)

    def _active_worker_count(self, priority: WorkPriority) -> int:
        return sum(1 for slot in self._slots[priority] if slot.worker is not None)

    async def _consume_worker_events(self, worker_name: str, generation: int, worker: Any) -> None:
        while True:
            try:
                message = await worker.next_event()
            except asyncio.CancelledError:
                raise
            current_slot = self._find_slot(worker_name)
            if current_slot is None or current_slot.worker_generation != generation:
                self._metrics["late_results_ignored"] += 1
                continue

            assignment = self._assignments.get(worker_name)
            if message["type"] == "runtime_recovery":
                self._metrics[current_slot.priority]["last_runtime_recovery"] = dict(message.get("recovery") or {})
                continue
            if message["type"] == "progress":
                if assignment is None:
                    self._metrics["late_results_ignored"] += 1
                    continue
                if (
                    assignment.worker_generation != generation
                    or message.get("request_id") != assignment.request_id
                    or message.get("work_id") != assignment.work_id
                    or int(message.get("lease_token") or -1) != assignment.lease_token
                ):
                    self._metrics["late_results_ignored"] += 1
                    continue
                if assignment.progress_callback is not None:
                    callback_result = assignment.progress_callback(
                        message.get("current_frame"),
                        message.get("total_frames"),
                        message.get("frame_score"),
                        message.get("top_label"),
                        message.get("frame_thumb"),
                        message.get("frame_index"),
                        message.get("clip_total"),
                        message.get("model_name"),
                    )
                    if inspect.isawaitable(callback_result):
                        await callback_result
                continue
            if assignment is None:
                self._metrics["late_results_ignored"] += 1
                continue

            if (
                assignment.worker_generation != generation
                or message.get("request_id") != assignment.request_id
                or message.get("work_id") != assignment.work_id
                or int(message.get("lease_token") or -1) != assignment.lease_token
            ):
                self._metrics["late_results_ignored"] += 1
                continue

            self._assignments.pop(worker_name, None)
            if message["type"] == "result":
                if not assignment.future.done():
                    assignment.future.set_result(list(message["results"]))
            else:
                if not assignment.future.done():
                    assignment.future.set_exception(RuntimeError(str(message.get("error") or "worker_error")))
            async with self._condition:
                self._condition.notify_all()

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(self._watchdog_interval_seconds)
            for priority in ("live", "background", "video"):
                for index, slot in enumerate(list(self._slots[priority])):
                    if slot.worker is None:
                        continue
                    status = slot.worker.get_status()
                    exit_code = status.get("exit_code")
                    if exit_code is not None:
                        await self._replace_worker(
                            priority,
                            index,
                            reason=f"exit_code_{exit_code}",
                            assignment_error=ClassifierWorkerExitedError(f"worker exited with code {exit_code}"),
                            kill=False,
                        )
                        continue

                    assignment = self._assignments.get(slot.worker_name)
                    if assignment is None:
                        continue
                    now = time.monotonic()
                    last_heartbeat = status.get("last_heartbeat_monotonic")
                    if (
                        isinstance(last_heartbeat, (int, float))
                        and now - float(last_heartbeat) > self._heartbeat_timeout_seconds
                    ):
                        await self._replace_worker(
                            priority,
                            index,
                            reason="heartbeat_timeout",
                            assignment_error=ClassifierWorkerHeartbeatTimeoutError("worker heartbeat timed out"),
                            kill=True,
                        )
                        continue
                    if now - assignment.started_at > self._hard_deadline_seconds[priority]:
                        await self._replace_worker(
                            priority,
                            index,
                            reason="hard_deadline",
                            assignment_error=ClassifierWorkerDeadlineExceededError("worker hard deadline exceeded"),
                            kill=True,
                        )

    async def _replace_worker(
        self,
        priority: WorkPriority,
        index: int,
        *,
        reason: str,
        assignment_error: Exception,
        kill: bool,
    ) -> None:
        slot = self._slots[priority][index]
        worker_status = slot.worker.get_status()
        if kill:
            await slot.worker.kill()
        else:
            await self._close_failed_worker(slot.worker)
        assignment = self._assignments.pop(slot.worker_name, None)
        if assignment is not None and not assignment.future.done():
            assignment.future.set_exception(assignment_error)
        self._metrics[priority]["restarts"] += 1
        self._metrics[priority]["last_exit_reason"] = reason
        self._metrics[priority]["last_stderr_excerpt"] = str(worker_status.get("recent_stderr_excerpt") or "")
        self._metrics[priority]["last_stderr_truncated_bytes"] = int(worker_status.get("stderr_truncated_bytes") or 0)
        self._record_restart(priority)
        try:
            new_slot = await self._spawn_worker(priority, index, generation=slot.worker_generation + 1)
        except ClassifierWorkerStartupTimeoutError:
            self._record_unavailable_slot(priority, index, "startup_timeout")
        except Exception:
            self._record_unavailable_slot(priority, index, "startup_failed")
        else:
            self._slots[priority][index] = new_slot
            self._metrics[priority]["workers"] = self._active_worker_count(priority)
        async with self._condition:
            self._condition.notify_all()

    def _find_slot(self, worker_name: str) -> _WorkerSlot | None:
        for priority in ("live", "background", "video"):
            for slot in self._slots[priority]:
                if slot.worker_name == worker_name:
                    return slot
        return None

    def _record_restart(self, priority: WorkPriority) -> None:
        now = time.monotonic()
        history = self._restart_history[priority]
        history.append(now)
        while history and now - history[0] > self._restart_window_seconds:
            history.popleft()
        if len(history) >= self._restart_threshold:
            self._metrics[priority]["circuit_open"] = True
            self._metrics[priority]["circuit_open_until_monotonic"] = now + self._breaker_cooldown_seconds

    def _refresh_circuit_state(self, priority: WorkPriority) -> None:
        if not self._metrics[priority]["circuit_open"]:
            return
        open_until = self._metrics[priority]["circuit_open_until_monotonic"]
        if isinstance(open_until, (int, float)) and time.monotonic() >= float(open_until):
            self._metrics[priority]["circuit_open"] = False
            self._metrics[priority]["circuit_open_until_monotonic"] = None
            history = self._restart_history[priority]
            history.clear()

    @staticmethod
    def _consume_future_exception(future: asyncio.Future[list[dict[str, Any]]]) -> None:
        if future.cancelled():
            return
        try:
            future.exception()
        except Exception:
            pass
