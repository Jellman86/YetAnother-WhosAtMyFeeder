import asyncio
import itertools
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal

from .classifier_worker_client import ClassifierWorkerClient
from .classifier_worker_protocol import build_classify_request


WorkPriority = Literal["live", "background"]


class ClassifierWorkerHeartbeatTimeoutError(RuntimeError):
    pass


class ClassifierWorkerDeadlineExceededError(RuntimeError):
    pass


class ClassifierWorkerExitedError(RuntimeError):
    pass


class ClassifierWorkerCircuitOpenError(RuntimeError):
    pass


@dataclass
class _WorkerSlot:
    priority: WorkPriority
    index: int
    worker_name: str
    worker_generation: int
    worker: Any
    consumer_task: asyncio.Task[None]


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


class ClassifierSupervisor:
    def __init__(
        self,
        *,
        live_worker_count: int,
        background_worker_count: int,
        heartbeat_timeout_seconds: float,
        hard_deadline_seconds: float,
        worker_factory=None,
        watchdog_interval_seconds: float = 0.05,
        restart_window_seconds: float = 60.0,
        restart_threshold: int = 3,
        breaker_cooldown_seconds: float = 60.0,
    ) -> None:
        self._worker_counts = {
            "live": max(1, int(live_worker_count)),
            "background": max(1, int(background_worker_count)),
        }
        self._heartbeat_timeout_seconds = max(0.01, float(heartbeat_timeout_seconds))
        self._hard_deadline_seconds = max(0.01, float(hard_deadline_seconds))
        self._watchdog_interval_seconds = max(0.01, float(watchdog_interval_seconds))
        self._restart_window_seconds = max(0.01, float(restart_window_seconds))
        self._restart_threshold = max(1, int(restart_threshold))
        self._breaker_cooldown_seconds = max(0.01, float(breaker_cooldown_seconds))
        self._worker_factory = worker_factory
        self._slots: dict[WorkPriority, list[_WorkerSlot]] = {"live": [], "background": []}
        self._assignments: dict[str, _Assignment] = {}
        self._metrics = {
            "live": {
                "workers": 0,
                "restarts": 0,
                "last_exit_reason": None,
                "last_stderr_excerpt": "",
                "last_stderr_truncated_bytes": 0,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "background": {
                "workers": 0,
                "restarts": 0,
                "last_exit_reason": None,
                "last_stderr_excerpt": "",
                "last_stderr_truncated_bytes": 0,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "late_results_ignored": 0,
        }
        self._restart_history: dict[WorkPriority, deque[float]] = {
            "live": deque(),
            "background": deque(),
        }
        self._consumer_tasks: set[asyncio.Task[None]] = set()
        self._request_counter = itertools.count(1)
        self._condition = asyncio.Condition()
        self._watchdog_task: asyncio.Task[None] | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        for priority in ("live", "background"):
            for index in range(self._worker_counts[priority]):
                slot = await self._spawn_worker(priority, index, generation=1)
                self._slots[priority].append(slot)
            self._metrics[priority]["workers"] = len(self._slots[priority])
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        self._started = True

    async def shutdown(self) -> None:
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        for priority in ("live", "background"):
            for slot in self._slots[priority]:
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
        if not self._started:
            await self.start()
        self._refresh_circuit_state(priority)
        if self._metrics[priority]["circuit_open"]:
            raise ClassifierWorkerCircuitOpenError(f"{priority} classifier circuit is open")

        loop = asyncio.get_running_loop()
        request_id = f"req-{next(self._request_counter)}"
        future: asyncio.Future[list[dict[str, Any]]] = loop.create_future()

        async with self._condition:
            slot = await self._wait_for_idle_slot(priority)
            assignment = _Assignment(
                priority=priority,
                worker_name=slot.worker_name,
                worker_generation=slot.worker_generation,
                request_id=request_id,
                work_id=str(work_id),
                lease_token=int(lease_token),
                started_at=time.monotonic(),
                future=future,
            )
            self._assignments[slot.worker_name] = assignment

        await slot.worker.send(
            build_classify_request(
                worker_generation=slot.worker_generation,
                request_id=request_id,
                work_id=str(work_id),
                lease_token=int(lease_token),
                image_b64=image_b64,
                camera_name=camera_name,
                model_id=model_id,
            )
        )
        return await future

    async def _wait_for_idle_slot(self, priority: WorkPriority) -> _WorkerSlot:
        while True:
            for slot in self._slots[priority]:
                if slot.worker_name not in self._assignments:
                    return slot
            await self._condition.wait()

    async def _spawn_worker(self, priority: WorkPriority, index: int, generation: int) -> _WorkerSlot:
        worker_name = f"{priority}-{index}"
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
        await worker.wait_until_ready()
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
            for priority in ("live", "background"):
                for index, slot in enumerate(list(self._slots[priority])):
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
                    if now - assignment.started_at > self._hard_deadline_seconds:
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
        assignment = self._assignments.pop(slot.worker_name, None)
        if assignment is not None and not assignment.future.done():
            assignment.future.set_exception(assignment_error)
        self._metrics[priority]["restarts"] += 1
        self._metrics[priority]["last_exit_reason"] = reason
        self._metrics[priority]["last_stderr_excerpt"] = str(worker_status.get("recent_stderr_excerpt") or "")
        self._metrics[priority]["last_stderr_truncated_bytes"] = int(worker_status.get("stderr_truncated_bytes") or 0)
        self._record_restart(priority)
        new_slot = await self._spawn_worker(priority, index, generation=slot.worker_generation + 1)
        self._slots[priority][index] = new_slot
        async with self._condition:
            self._condition.notify_all()

    def _find_slot(self, worker_name: str) -> _WorkerSlot | None:
        for priority in ("live", "background"):
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
