"""A worker loading a large model must not be mistaken for a dead one.

Observed in the field (#300 follow-up): the video worker was killed with
heartbeat_timeout while its stderr was mid-way through TensorFlow's import
chatter. Heavy runtime imports and cold model compiles hold the GIL in long
native stretches, starving the heartbeat task even though the worker is
making progress — and the kill/reload loop means subprocess mode never
classifies anything on slow hardware. These tests pin the three defences:
stderr output counts as life, the first load gets a warm-up deadline, and a
tripped circuit falls back to in-process classification instead of silently
dropping every detection.
"""

import asyncio
import time

import pytest
from PIL import Image

from app.services.classifier_supervisor import (
    ClassifierSupervisor,
    ClassifierWorkerCircuitOpenError,
    ClassifierWorkerHeartbeatTimeoutError,
)


class _FakeWorker:
    def __init__(self, worker_name: str, worker_generation: int) -> None:
        self.worker_name = worker_name
        self.worker_generation = worker_generation
        self.sent_messages: list[dict] = []
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self.last_heartbeat_monotonic = time.monotonic()
        self.last_activity_monotonic: float | None = None
        self.last_stderr_monotonic: float | None = None
        self.current_request_id: str | None = None
        self.busy = False
        self.exit_code: int | None = None
        self.killed = False

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
        return None

    async def kill(self) -> None:
        self.killed = True

    async def wait_closed(self) -> None:
        return None

    def get_status(self) -> dict:
        status = {
            "worker_name": self.worker_name,
            "worker_generation": self.worker_generation,
            "ready": True,
            "busy": self.busy,
            "current_request_id": self.current_request_id,
            "last_heartbeat_monotonic": self.last_heartbeat_monotonic,
            "heartbeat_timeout_seconds": 0.05,
            "exit_code": self.exit_code,
            "recent_stderr_excerpt": "",
            "stderr_truncated_bytes": 0,
        }
        if self.last_activity_monotonic is not None:
            status["last_activity_monotonic"] = self.last_activity_monotonic
        if self.last_stderr_monotonic is not None:
            status["last_stderr_monotonic"] = self.last_stderr_monotonic
        return status


def _make_supervisor(_factory, **overrides):
    kwargs = dict(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=0.05,
        hard_deadline_seconds=1.0,
        worker_factory=_factory,
        watchdog_interval_seconds=0.01,
    )
    kwargs.update(overrides)
    return ClassifierSupervisor(**kwargs)


def _classify_task(supervisor, work_id):
    return asyncio.create_task(
        supervisor.classify(
            priority="live",
            work_id=work_id,
            lease_token=2,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )


async def _resolve(worker, work_id):
    await worker.events.put(
        {
            "type": "result",
            "worker_generation": worker.worker_generation,
            "request_id": worker.current_request_id,
            "work_id": work_id,
            "lease_token": 2,
            "results": [],
        }
    )


@pytest.mark.asyncio
async def test_worker_writing_stderr_is_alive_even_when_heartbeats_starve():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = _make_supervisor(_factory)
    await supervisor.start()

    task = _classify_task(supervisor, "live-loading")
    await asyncio.sleep(0.01)
    # Heartbeats starved for a full second, but stderr keeps chattering the
    # way a TensorFlow import does — long past the assignment's own age.
    for _ in range(4):
        created[0].last_heartbeat_monotonic = time.monotonic() - 1.0
        created[0].last_stderr_monotonic = time.monotonic()
        await asyncio.sleep(0.03)

    assert task.done() is False
    assert created[0].killed is False

    await _resolve(created[0], "live-loading")
    assert await task == []
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_first_load_gets_a_warmup_deadline_then_normal_liveness_applies():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = _make_supervisor(_factory, warmup_liveness_timeout_seconds=10.0)
    await supervisor.start()

    # First request: everything silent well past the heartbeat timeout, but
    # the worker has never completed a request — this is a cold model load.
    task = _classify_task(supervisor, "live-first")
    await asyncio.sleep(0.01)
    created[0].last_heartbeat_monotonic = time.monotonic() - 1.0
    await asyncio.sleep(0.05)

    assert task.done() is False
    assert created[0].killed is False

    await _resolve(created[0], "live-first")
    assert await task == []

    # Second request: warmed up now, so the steady-state timeout applies.
    task = _classify_task(supervisor, "live-second")
    await asyncio.sleep(0.01)
    created[0].last_heartbeat_monotonic = time.monotonic() - 1.0
    with pytest.raises(ClassifierWorkerHeartbeatTimeoutError):
        await task
    assert created[0].killed is True

    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_warmup_extends_the_hard_deadline_until_the_first_result():
    created: list[_FakeWorker] = []

    async def _factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = _make_supervisor(
        _factory,
        hard_deadline_seconds=0.05,
        warmup_liveness_timeout_seconds=10.0,
    )
    await supervisor.start()

    task = _classify_task(supervisor, "live-slow-load")
    await asyncio.sleep(0.01)
    # Keep heartbeats fresh; only the assignment age crosses the hard deadline.
    created[0].last_heartbeat_monotonic = time.monotonic()
    await asyncio.sleep(0.08)
    created[0].last_heartbeat_monotonic = time.monotonic()

    assert task.done() is False
    assert created[0].killed is False

    await _resolve(created[0], "live-slow-load")
    assert await task == []
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_circuit_open_falls_back_to_in_process_and_says_so():
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()

    class _TrippedSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerCircuitOpenError("live classifier circuit is open")

    loads: list[str] = []

    class _LoadedModel:
        loaded = True

    def _fake_init() -> None:
        loads.append("load")
        service._models["bird"] = _LoadedModel()

    sentinel = [{"display_name": "Robin", "score": 0.9}]
    service._classifier_supervisor = _TrippedSupervisor()
    service._init_bird_model = _fake_init
    service.classify = lambda image, camera_name=None, model_id=None, input_context=None: sentinel

    image = Image.new("RGB", (8, 8))
    results = await service._run_supervised_inference("live", image, "front", None)
    assert results == sentinel

    fallback = service.get_worker_fallback_status()
    assert fallback["active"] is True
    assert fallback["reason"] == "circuit_open"

    # A second call reuses the loaded model instead of loading again.
    await service._run_supervised_inference("live", image, "front", None)
    assert loads == ["load"]


def test_openvino_cache_prefers_the_persistent_models_volume(monkeypatch):
    from app.services import openvino_cache

    monkeypatch.delenv("OPENVINO_CACHE_DIR", raising=False)
    monkeypatch.setattr(openvino_cache.os.path, "isdir", lambda p: p == "/data/models")
    assert openvino_cache.resolve_openvino_cache_dir() == "/data/models/.openvino_cache"

    monkeypatch.setattr(openvino_cache.os.path, "isdir", lambda p: False)
    assert openvino_cache.resolve_openvino_cache_dir() == "/tmp/openvino_cache"

    monkeypatch.setenv("OPENVINO_CACHE_DIR", "/custom/cache")
    assert openvino_cache.resolve_openvino_cache_dir() == "/custom/cache"
