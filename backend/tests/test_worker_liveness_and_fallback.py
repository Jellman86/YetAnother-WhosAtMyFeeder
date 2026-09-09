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


def _service_with_fake_model(supervisor, *, pool_workers: dict[str, int] | None = None):
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()
    loads: list[str] = []

    class _LoadedModel:
        loaded = True

    def _fake_init() -> None:
        loads.append("load")
        service._models["bird"] = _LoadedModel()

    sentinel = [{"display_name": "Robin", "score": 0.9}]
    service._classifier_supervisor = supervisor
    service._init_bird_model = _fake_init
    service.classify = lambda image, camera_name=None, model_id=None, input_context=None: sentinel
    if pool_workers is not None:
        service._get_supervisor_metrics = lambda: {
            pool: {"workers": count, "last_exit_reason": None} for pool, count in pool_workers.items()
        }
    return service, sentinel, loads


@pytest.mark.asyncio
async def test_workers_that_never_become_ready_fall_back_to_in_process_and_say_so():
    """Killed mid-model-load on slow hardware, the pool never starts. That used to
    drop every detection as worker-unavailable; it must classify here instead."""
    from app.services.classifier_supervisor import ClassifierWorkerStartupTimeoutError

    class _NeverReadySupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerStartupTimeoutError("worker startup timed out")

    service, sentinel, loads = _service_with_fake_model(_NeverReadySupervisor())

    results = await service._run_supervised_inference("live", Image.new("RGB", (8, 8)), "front", None)

    assert results == sentinel
    fallback = service.get_worker_fallback_status()
    assert fallback["active"] is True
    assert fallback["reason"] == "worker_startup_timeout"
    assert loads == ["load"]


@pytest.mark.asyncio
async def test_a_pool_with_no_workers_left_falls_back_to_in_process():
    from app.services.classifier_supervisor import ClassifierWorkerExitedError

    class _EmptyPoolSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerExitedError("No active workers available for live")

    service, sentinel, _loads = _service_with_fake_model(_EmptyPoolSupervisor(), pool_workers={"live": 0})

    results = await service._run_supervised_inference("live", Image.new("RGB", (8, 8)), "front", None)

    assert results == sentinel
    assert service.get_worker_fallback_status()["reason"] == "workers_unavailable"


@pytest.mark.asyncio
async def test_a_worker_dying_mid_request_does_not_fall_back_while_others_remain():
    """The supervisor replaces a dead worker; loading a second model copy in the
    parent for one lost request would double memory for nothing."""
    from app.services.classifier_service import LiveImageClassificationOverloadedError
    from app.services.classifier_supervisor import ClassifierWorkerExitedError

    class _OneDiedSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerExitedError("worker live-1 exited")

    service, _sentinel, loads = _service_with_fake_model(_OneDiedSupervisor(), pool_workers={"live": 1})

    with pytest.raises(LiveImageClassificationOverloadedError):
        await service._run_supervised_inference("live", Image.new("RGB", (8, 8)), "front", None)

    assert loads == []
    assert service.get_worker_fallback_status()["active"] is False


@pytest.mark.asyncio
async def test_fallback_that_cannot_load_a_model_keeps_the_original_error_code():
    from app.services.classifier_service import LiveImageClassificationOverloadedError
    from app.services.classifier_supervisor import ClassifierWorkerStartupTimeoutError

    class _NeverReadySupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerStartupTimeoutError("worker startup timed out")

    service, _sentinel, _loads = _service_with_fake_model(_NeverReadySupervisor())

    def _cannot_load() -> None:
        raise RuntimeError("no model files")

    service._init_bird_model = _cannot_load

    with pytest.raises(LiveImageClassificationOverloadedError) as raised:
        await service._run_supervised_inference("live", Image.new("RGB", (8, 8)), "front", None)

    assert "classify_snapshot_worker_unavailable" in str(raised.value)
    assert service.get_worker_fallback_status()["active"] is False


def test_status_reports_the_runtime_the_workers_loaded_not_the_parents_idle_default():
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()
    service._image_execution_mode = "subprocess"
    service._resolve_active_model_id = lambda: "rope_vit_b14_inat21"
    metrics = {
        "live": {
            "workers": 1,
            "runtime": {
                "inference_backend": "openvino",
                "active_provider": "intel_npu",
                "model_id": "rope_vit_b14_inat21",
            },
        },
        "background": {"workers": 0, "runtime": None},
        "video": {"workers": 0, "runtime": None},
    }

    assert (service._inference_backend, service._active_inference_provider) == ("tflite", "tflite")
    backend, provider = service._effective_subprocess_runtime_fields(
        None, service._latest_worker_reported_runtime(metrics)
    )
    assert (backend, provider) == ("openvino", "intel_npu")

    service._get_supervisor_metrics = lambda: metrics
    key = service._active_inference_runtime_key()
    assert (key.backend, key.provider, key.model_id) == ("openvino", "intel_npu", "rope_vit_b14_inat21")


def test_a_worker_report_for_a_different_model_is_ignored_after_a_switch():
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()
    service._image_execution_mode = "subprocess"
    service._resolve_active_model_id = lambda: "rope_vit_b14_inat21"
    metrics = {
        "live": {
            "workers": 0,
            "runtime": {
                "inference_backend": "openvino",
                "active_provider": "intel_npu",
                "model_id": "eva02_large_inat21",
            },
        },
        "background": {"workers": 0, "runtime": None},
        "video": {"workers": 0, "runtime": None},
    }

    assert service._latest_worker_reported_runtime(metrics) is None
    assert service._effective_subprocess_runtime_fields(None, None) == ("tflite", "tflite")


def test_a_recovery_after_load_still_overrides_the_ready_report():
    """A worker that fell back from NPU to CPU after loading reports a recovery;
    that is newer than its ready message and must win."""
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()
    service._image_execution_mode = "subprocess"
    worker_runtime = {"inference_backend": "openvino", "active_provider": "intel_npu", "model_id": "m"}
    recovery = {"recovered_backend": "openvino", "recovered_provider": "intel_cpu"}

    assert service._effective_subprocess_runtime_fields(recovery, worker_runtime) == ("openvino", "intel_cpu")


def _subprocess_service(monkeypatch, *, planned_backend="openvino", planned_provider="intel_npu"):
    from app.services import classifier_service as module
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()
    service._image_execution_mode = "subprocess"
    service._resolve_active_model_id = lambda: "rope_vit_b14_inat21"
    service._resolve_active_bird_model_spec = lambda: {
        "model_id": "rope_vit_b14_inat21",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "intel_cpu", "intel_npu"],
        "host_provider_preference_order": ["intel_npu", "cpu"],
    }
    monkeypatch.setattr(
        module,
        "_resolve_inference_selection",
        lambda *_a, **_k: {"backend": planned_backend, "active_provider": planned_provider, "fallback_reason": None},
    )
    return service


def test_before_any_worker_has_loaded_status_names_the_planned_runtime(monkeypatch):
    """Pools start on the first visit. Until then the parent must say what a
    worker will load, resolved the way the worker resolves it, not "tflite"."""
    service = _subprocess_service(monkeypatch)
    empty_pools = {"live": {"workers": 0, "runtime": None}, "background": {"workers": 0, "runtime": None}}

    assert service._subprocess_runtime_identity(empty_pools) == ("openvino", "intel_npu", "planned")


def test_a_workers_report_outranks_the_plan(monkeypatch):
    service = _subprocess_service(monkeypatch, planned_provider="intel_npu")
    pools = {
        "live": {
            "workers": 1,
            "runtime": {
                "inference_backend": "openvino",
                "active_provider": "intel_cpu",
                "model_id": "rope_vit_b14_inat21",
            },
        }
    }

    assert service._subprocess_runtime_identity(pools) == ("openvino", "intel_cpu", "worker")


def test_the_parents_own_fallback_model_outranks_everything(monkeypatch):
    """When this process has loaded a model to cover for the workers, it is the
    one classifying, so status and health must name what it loaded."""
    service = _subprocess_service(monkeypatch)

    class _LoadedModel:
        loaded = True

    service._models["bird"] = _LoadedModel()
    service._inference_backend = "onnxruntime"
    service._active_inference_provider = "cpu"
    pools = {
        "live": {
            "workers": 1,
            "runtime": {
                "inference_backend": "openvino",
                "active_provider": "intel_npu",
                "model_id": "rope_vit_b14_inat21",
            },
        }
    }

    assert service._subprocess_runtime_identity(pools) == ("onnxruntime", "cpu", "in_process_fallback")


def test_a_tflite_model_is_planned_as_tflite(monkeypatch):
    service = _subprocess_service(monkeypatch)
    service._resolve_active_bird_model_spec = lambda: {"model_id": "legacy", "runtime": "tflite"}

    assert service._subprocess_runtime_identity({}) == ("tflite", "tflite", "planned")


def test_an_unresolvable_plan_falls_back_to_the_bare_default(monkeypatch):
    service = _subprocess_service(monkeypatch)

    def _no_spec():
        raise RuntimeError("model manager not ready")

    service._resolve_active_bird_model_spec = _no_spec

    assert service._subprocess_runtime_identity({}) == ("tflite", "tflite", "default")


def test_health_keys_use_the_planned_runtime_before_first_load(monkeypatch):
    service = _subprocess_service(monkeypatch)
    service._get_supervisor_metrics = lambda: {"live": {"workers": 0, "runtime": None}}

    key = service._active_inference_runtime_key()

    assert (key.backend, key.provider) == ("openvino", "intel_npu")


def test_admission_samples_are_keyed_on_the_runtime_that_classified(monkeypatch):
    """The dashboard's health entry was "tflite/tflite/<model>" on an NPU install
    because the admission context copied the parent's idle defaults."""
    service = _subprocess_service(monkeypatch)
    service._get_supervisor_metrics = lambda: {
        "live": {
            "workers": 1,
            "runtime": {
                "inference_backend": "openvino",
                "active_provider": "intel_npu",
                "model_id": "rope_vit_b14_inat21",
            },
        }
    }

    context = service._classification_admission_context()
    key = service._inference_runtime_key_from_context(context)

    assert (context["backend"], context["provider"]) == ("openvino", "intel_npu")
    assert (key.backend, key.provider, key.model_id) == ("openvino", "intel_npu", "rope_vit_b14_inat21")


def test_admission_context_in_process_mode_still_names_the_parents_own_runtime(monkeypatch):
    from app.services.classifier_service import ClassifierService

    service = ClassifierService()
    service._image_execution_mode = "in_process"
    service._inference_backend = "onnxruntime"
    service._active_inference_provider = "cpu"
    service._resolve_active_model_id = lambda: "m"

    context = service._classification_admission_context()

    assert (context["backend"], context["provider"]) == ("onnxruntime", "cpu")
