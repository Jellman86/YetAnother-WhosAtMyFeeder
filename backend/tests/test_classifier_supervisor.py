import asyncio
import time

import pytest

from app.services.classifier_supervisor import (
    ClassifierSupervisor,
    ClassifierWorkerCircuitOpenError,
    ClassifierWorkerDeadlineExceededError,
    ClassifierWorkerExitedError,
    ClassifierWorkerHeartbeatTimeoutError,
    ClassifierWorkerStartupTimeoutError,
)


class _FakeWorker:
    def __init__(self, worker_name: str, worker_generation: int) -> None:
        self.worker_name = worker_name
        self.worker_generation = worker_generation
        self.sent_messages: list[dict] = []
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self.last_heartbeat_monotonic = time.monotonic()
        self.current_request_id: str | None = None
        self.busy = False
        self.ready = True
        self.exit_code: int | None = None
        self.recent_stderr_excerpt = ""
        self.stderr_truncated_bytes = 0
        self.terminated = False
        self.killed = False
        self.closed = False

    async def start(self) -> None:
        return None

    async def wait_until_ready(self, timeout_seconds: float = 1.0) -> None:
        return None

    async def send(self, message: dict) -> None:
        self.sent_messages.append(message)
        self.current_request_id = message.get("request_id")
        self.busy = True

    async def next_event(self) -> dict:
        return await self.events.get()

    async def terminate(self) -> None:
        self.terminated = True
        self.closed = True

    async def kill(self) -> None:
        self.killed = True
        self.closed = True

    async def wait_closed(self) -> None:
        return None

    def get_status(self) -> dict:
        return {
            "worker_name": self.worker_name,
            "worker_generation": self.worker_generation,
            "ready": self.ready,
            "busy": self.busy,
            "current_request_id": self.current_request_id,
            "last_heartbeat_monotonic": self.last_heartbeat_monotonic,
            "heartbeat_timeout_seconds": 0.05,
            "exit_code": self.exit_code,
            "recent_stderr_excerpt": self.recent_stderr_excerpt,
            "stderr_truncated_bytes": self.stderr_truncated_bytes,
        }


class _SlowReadyWorker(_FakeWorker):
    def __init__(self, worker_name: str, worker_generation: int, *, ready_delay_seconds: float) -> None:
        super().__init__(worker_name, worker_generation)
        self.ready_delay_seconds = float(ready_delay_seconds)
        self.ready_timeout_seen: float | None = None

    async def wait_until_ready(self, timeout_seconds: float = 1.0) -> None:
        self.ready_timeout_seen = float(timeout_seconds)
        await asyncio.sleep(min(self.ready_delay_seconds, timeout_seconds))
        if self.ready_delay_seconds > timeout_seconds:
            raise TimeoutError()


class _SendFailWorker(_FakeWorker):
    async def send(self, message: dict) -> None:
        self.sent_messages.append(message)
        self.current_request_id = message.get("request_id")
        self.busy = True
        raise ConnectionResetError("Connection lost")


class _GateReadyWorker(_FakeWorker):
    def __init__(self, worker_name: str, worker_generation: int, *, gate: asyncio.Event) -> None:
        super().__init__(worker_name, worker_generation)
        self._gate = gate
        self.ready_timeout_seen: float | None = None

    async def wait_until_ready(self, timeout_seconds: float = 1.0) -> None:
        self.ready_timeout_seen = float(timeout_seconds)
        await self._gate.wait()


def _find_worker(created: list[_FakeWorker], worker_name: str, generation: int) -> _FakeWorker:
    for worker in created:
        if worker.worker_name == worker_name and worker.worker_generation == generation:
            return worker
    raise AssertionError(f"worker not found: {worker_name} gen={generation}")


@pytest.mark.asyncio
async def test_classifier_supervisor_starts_live_and_background_pools():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=2,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.05,
        hard_deadline_seconds=0.1,
        worker_factory=_factory,
    )
    await supervisor.start()

    metrics = supervisor.get_metrics()
    assert metrics["live"]["workers"] == 2
    assert metrics["background"]["workers"] == 1

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_classify_starts_requested_pool_only():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=2,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.5,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
    )

    task = asyncio.create_task(
        supervisor.classify(
            priority="background",
            work_id="background-1",
            lease_token=1,
            image_b64="payload",
            camera_name="garden",
            model_id="default",
        )
    )
    await asyncio.sleep(0.01)

    assert [worker.worker_name for worker in created] == ["background-0"]
    await created[0].events.put(
        {
            "type": "result",
            "worker_generation": 1,
            "request_id": created[0].sent_messages[0]["request_id"],
            "work_id": "background-1",
            "lease_token": 1,
            "results": [{"label": "Robin", "score": 0.8}],
        }
    )

    results = await task
    assert results[0]["label"] == "Robin"
    metrics = supervisor.get_metrics()
    assert metrics["live"]["workers"] == 0
    assert metrics["background"]["workers"] == 1

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_raises_startup_timeout_with_metrics():
    created: list[_SlowReadyWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _SlowReadyWorker(
            worker_name,
            worker_generation,
            ready_delay_seconds=0.1,
        )
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.5,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        worker_ready_timeout_seconds=0.02,
    )

    with pytest.raises(ClassifierWorkerStartupTimeoutError):
        await supervisor.classify(
            priority="background",
            work_id="background-timeout",
            lease_token=1,
            image_b64="payload",
            camera_name="garden",
            model_id="default",
        )

    assert created[0].ready_timeout_seen == pytest.approx(0.02)
    metrics = supervisor.get_metrics()
    assert metrics["background"]["workers"] == 0
    assert metrics["background"]["last_exit_reason"] == "startup_timeout"

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_assigns_work_to_idle_worker():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.5,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
    )
    await supervisor.start()

    task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-1",
            lease_token=1,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    await asyncio.sleep(0.01)
    assert created[0].sent_messages[0]["type"] == "classify"
    await created[0].events.put(
        {
            "type": "result",
            "worker_generation": 1,
            "request_id": created[0].sent_messages[0]["request_id"],
            "work_id": "live-1",
            "lease_token": 1,
            "results": [{"label": "Robin", "score": 0.91}],
        }
    )

    results = await task
    assert results[0]["label"] == "Robin"

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_replaces_worker_after_heartbeat_timeout():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.05,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    await supervisor.start()

    task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-2",
            lease_token=2,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    await asyncio.sleep(0.01)
    created[0].last_heartbeat_monotonic = time.monotonic() - 1.0

    with pytest.raises(ClassifierWorkerHeartbeatTimeoutError):
        await task

    assert created[0].killed is True
    assert supervisor.get_metrics()["live"]["restarts"] == 1

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_replaces_worker_after_hard_deadline():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=0.05,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    await supervisor.start()

    task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-3",
            lease_token=3,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )

    with pytest.raises(ClassifierWorkerDeadlineExceededError):
        await task

    assert created[0].killed is True
    assert supervisor.get_metrics()["live"]["restarts"] == 1

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_replaces_worker_after_send_transport_failure():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        if worker_generation == 1:
            worker = _SendFailWorker(worker_name, worker_generation)
        else:
            worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )

    with pytest.raises(ClassifierWorkerExitedError, match="worker send failed"):
        await supervisor.classify(
            priority="background",
            work_id="background-send-failure",
            lease_token=1,
            image_b64="payload",
            camera_name="garden",
            model_id="default",
        )

    metrics = supervisor.get_metrics()
    assert metrics["background"]["restarts"] == 1
    assert metrics["background"]["last_exit_reason"] == "send_failed"
    assert metrics["background"]["workers"] == 1
    assert len(created) == 2

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_starts_pool_workers_sequentially():
    created: list[_GateReadyWorker] = []
    gate = asyncio.Event()

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _GateReadyWorker(worker_name, worker_generation, gate=gate)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        video_worker_count=2,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
    )

    start_task = asyncio.create_task(supervisor.start("video"))
    await asyncio.sleep(0.01)
    assert [worker.worker_name for worker in created] == ["video-0"]

    gate.set()
    await start_task

    assert [worker.worker_name for worker in created] == ["video-0", "video-1"]
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_uses_video_specific_ready_timeout():
    created: list[_SlowReadyWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _SlowReadyWorker(worker_name, worker_generation, ready_delay_seconds=0.03)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        video_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=1.0,
        worker_ready_timeout_seconds=0.02,
        video_worker_ready_timeout_seconds=0.05,
        worker_factory=_factory,
    )

    task = asyncio.create_task(
        supervisor.classify_video(
            work_id="video-ready-timeout",
            lease_token=1,
            video_path="/tmp/test.mp4",
        )
    )
    await asyncio.sleep(0.05)

    assert created[0].ready_timeout_seen == pytest.approx(0.05)
    await created[0].events.put(
        {
            "type": "result",
            "worker_generation": 1,
            "request_id": created[0].sent_messages[0]["request_id"],
            "work_id": "video-ready-timeout",
            "lease_token": 1,
            "results": [{"label": "Robin", "score": 0.8}],
        }
    )
    results = await task
    assert results[0]["label"] == "Robin"

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_replaces_crashed_worker():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    await supervisor.start()

    created[0].exit_code = 9
    await asyncio.sleep(0.05)

    assert supervisor.get_metrics()["live"]["restarts"] == 1
    assert supervisor.get_metrics()["live"]["last_exit_reason"] == "exit_code_9"

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_ignores_stale_results_from_replaced_worker():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.05,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    await supervisor.start()

    first_task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-4",
            lease_token=4,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    await asyncio.sleep(0.01)
    first_request_id = created[0].sent_messages[0]["request_id"]
    created[0].last_heartbeat_monotonic = time.monotonic() - 1.0

    with pytest.raises(ClassifierWorkerHeartbeatTimeoutError):
        await first_task

    await created[0].events.put(
        {
            "type": "result",
            "worker_generation": 1,
            "request_id": first_request_id,
            "work_id": "live-4",
            "lease_token": 4,
            "results": [{"label": "Old", "score": 0.1}],
        }
    )

    second_task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-5",
            lease_token=5,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    replacement_live_worker = _find_worker(created, "live-0", 2)
    for _ in range(20):
        if replacement_live_worker.sent_messages:
            break
        await asyncio.sleep(0.01)
    assert replacement_live_worker.sent_messages
    await replacement_live_worker.events.put(
        {
            "type": "result",
            "worker_generation": 2,
            "request_id": replacement_live_worker.sent_messages[0]["request_id"],
            "work_id": "live-5",
            "lease_token": 5,
            "results": [{"label": "New", "score": 0.95}],
        }
    )

    results = await second_task
    assert results[0]["label"] == "New"
    assert supervisor.get_metrics()["late_results_ignored"] == 1

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_opens_circuit_after_restart_budget_exhausted():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
        restart_window_seconds=60.0,
        restart_threshold=2,
        breaker_cooldown_seconds=0.5,
    )
    await supervisor.start()

    created[0].exit_code = 7
    await asyncio.sleep(0.05)
    _find_worker(created, "live-0", 2).exit_code = 8
    await asyncio.sleep(0.05)

    metrics = supervisor.get_metrics()
    assert metrics["live"]["circuit_open"] is True

    with pytest.raises(ClassifierWorkerCircuitOpenError):
        await supervisor.classify(
            priority="live",
            work_id="live-circuit",
            lease_token=9,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_allows_recovery_after_cooldown_expires():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
        restart_window_seconds=60.0,
        restart_threshold=1,
        breaker_cooldown_seconds=0.05,
    )
    await supervisor.start()

    created[0].exit_code = 7
    await asyncio.sleep(0.05)

    with pytest.raises(ClassifierWorkerCircuitOpenError):
        await supervisor.classify(
            priority="live",
            work_id="live-open",
            lease_token=10,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )

    await asyncio.sleep(0.06)

    task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-recovered",
            lease_token=11,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    replacement_live_worker = _find_worker(created, "live-0", 2)
    for _ in range(20):
        if replacement_live_worker.sent_messages:
            break
        await asyncio.sleep(0.01)
    assert replacement_live_worker.sent_messages
    await replacement_live_worker.events.put(
        {
            "type": "result",
            "worker_generation": 2,
            "request_id": replacement_live_worker.sent_messages[0]["request_id"],
            "work_id": "live-recovered",
            "lease_token": 11,
            "results": [{"label": "Recovered", "score": 0.99}],
        }
    )

    results = await task
    assert results[0]["label"] == "Recovered"
    assert supervisor.get_metrics()["live"]["circuit_open"] is False

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_records_worker_stderr_on_exit():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.5,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    await supervisor.start()

    created[0].recent_stderr_excerpt = "import failed"
    created[0].stderr_truncated_bytes = 12
    created[0].exit_code = 17

    await asyncio.sleep(0.05)

    metrics = supervisor.get_metrics()
    assert metrics["live"]["last_exit_reason"] == "exit_code_17"
    assert metrics["live"]["last_stderr_excerpt"] == "import failed"
    assert metrics["live"]["last_stderr_truncated_bytes"] == 12

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_records_worker_runtime_recovery():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.5,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    await supervisor.start()

    task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-recovery-1",
            lease_token=14,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    await asyncio.sleep(0.01)
    request_id = created[0].sent_messages[0]["request_id"]
    await created[0].events.put(
        {
            "type": "runtime_recovery",
            "worker_generation": 1,
            "request_id": request_id,
            "work_id": "live-recovery-1",
            "lease_token": 14,
            "recovery": {
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "GPU",
                "recovered_backend": "openvino",
                "recovered_provider": "intel_cpu",
                "detail": "invalid probabilities",
                "at": 123.0,
            },
        }
    )
    await created[0].events.put(
        {
            "type": "result",
            "worker_generation": 1,
            "request_id": request_id,
            "work_id": "live-recovery-1",
            "lease_token": 14,
            "results": [{"label": "Robin", "score": 0.91}],
        }
    )

    await task

    metrics = supervisor.get_metrics()
    assert metrics["live"]["last_runtime_recovery"]["failed_provider"] == "GPU"
    assert metrics["live"]["last_runtime_recovery"]["recovered_provider"] == "intel_cpu"

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_classifier_supervisor_survives_replacement_start_failure():
    created: list[_FakeWorker] = []
    factory_calls = 0

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 2:
            raise RuntimeError("replacement failed to start")
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.05,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
        restart_window_seconds=60.0,
        restart_threshold=1,
        breaker_cooldown_seconds=0.5,
    )
    await supervisor.start("live")

    task = asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id="live-replacement-failure",
            lease_token=12,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )
    await asyncio.sleep(0.01)
    created[0].last_heartbeat_monotonic = time.monotonic() - 1.0

    with pytest.raises(ClassifierWorkerHeartbeatTimeoutError):
        await task

    await asyncio.sleep(0.05)

    assert supervisor._watchdog_task is not None
    assert supervisor._watchdog_task.done() is False
    metrics = supervisor.get_metrics()
    assert metrics["live"]["restarts"] == 1
    assert metrics["live"]["last_exit_reason"] == "startup_failed"
    assert metrics["live"]["circuit_open"] is True

    with pytest.raises(ClassifierWorkerCircuitOpenError):
        await supervisor.classify(
            priority="live",
            work_id="live-replacement-failure-open",
            lease_token=13,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )

    await supervisor.shutdown()
