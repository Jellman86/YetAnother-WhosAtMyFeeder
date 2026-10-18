"""Retire a failed Intel GPU worker instead of reloading in its own process (#721).

An isolated OpenVINO GPU worker that hits a device-level OpenCL failure must
report the original error and exit. Compiling a replacement model and cleaning
up the failed one in the same PID can abort natively, and no Python handler
can catch a C++ destructor abort. The supervisor quarantines the launch
profile from the retirement record (not from an exit code), reaps the child,
and the request falls to the validated CPU recovery path.
"""

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.classifier_service import (
    ClassifierService,
    InvalidInferenceOutputError,
    _summarize_runtime_exception,
)
from app.services.classifier_supervisor import ClassifierSupervisor
from app.services.classifier_worker_process import ClassifierWorkerProcess
from app.services.classifier_worker_protocol import build_classify_request, decode_protocol_message
from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError


@pytest.mark.parametrize("code", ["CL_OUT_OF_RESOURCES", "CL_INVALID_EVENT"])
def test_runtime_exception_summary_keeps_opencl_code_from_long_nested_cause(code):
    try:
        try:
            raise RuntimeError("prefix " * 80 + f"clFlush failed: {code}")
        except RuntimeError as inner:
            raise RuntimeError("inference wrapper failed") from inner
    except RuntimeError as exc:
        summary = _summarize_runtime_exception(exc)

    assert code in summary
    assert len(summary) <= 280


def _service(*, worker_process_mode: bool) -> ClassifierService:
    with (
        patch.object(ClassifierService, "_init_bird_model"),
        patch.object(ClassifierService, "_refresh_accel_caps", return_value={}),
    ):
        return ClassifierService(worker_process_mode=worker_process_mode)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["CL_OUT_OF_RESOURCES", "CL_INVALID_EVENT"])
async def test_worker_mode_gpu_runtime_failure_retires_without_cleanup_or_reload(code):
    from app.services.classifier_worker_protocol import ClassifierWorkerRetirementError

    service = _service(worker_process_mode=True)
    model = MagicMock()
    service._models["bird"] = model
    service._attempt_gpu_retry_after_invalid_output = MagicMock(return_value=True)
    service._load_runtime_fallback_bird_model = MagicMock()
    error = InvalidInferenceOutputError(
        backend="openvino",
        provider="GPU",
        detail=f"BirdClassifier runtime exception: RuntimeError: clWaitForEvents failed: {code}",
    )
    try:
        with pytest.raises(ClassifierWorkerRetirementError) as raised:
            service._recover_from_invalid_bird_output(model, error)
        assert raised.value.error_code == code
        assert code in raised.value.detail
        service._attempt_gpu_retry_after_invalid_output.assert_not_called()
        service._load_runtime_fallback_bird_model.assert_not_called()
        model.cleanup.assert_not_called()
        assert service._models["bird"] is model
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_worker_mode_nonfinite_output_still_recovers_in_process():
    service = _service(worker_process_mode=True)
    model = MagicMock()
    service._models["bird"] = model
    service._attempt_gpu_retry_after_invalid_output = MagicMock(return_value=True)
    error = InvalidInferenceOutputError(
        backend="openvino",
        provider="GPU",
        detail="BirdClassifier inference produced no finite probabilities",
    )
    try:
        assert service._recover_from_invalid_bird_output(model, error) is True
        service._attempt_gpu_retry_after_invalid_output.assert_called_once()
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_in_process_gpu_runtime_failure_does_not_retire_the_parent():
    service = _service(worker_process_mode=False)
    model = MagicMock()
    service._models["bird"] = model
    service._attempt_gpu_retry_after_invalid_output = MagicMock(return_value=True)
    error = InvalidInferenceOutputError(
        backend="openvino",
        provider="GPU",
        detail="BirdClassifier runtime exception: RuntimeError: CL_OUT_OF_RESOURCES",
    )
    try:
        assert service._recover_from_invalid_bird_output(model, error) is True
        service._attempt_gpu_retry_after_invalid_output.assert_called_once()
    finally:
        await service.shutdown()


def test_retirement_protocol_message_round_trip_and_field_validation():
    from app.services.classifier_worker_protocol import build_retirement_event, encode_protocol_message

    message = build_retirement_event(
        worker_generation=2,
        request_id="req-1",
        work_id="work-1",
        lease_token=7,
        error_code="CL_OUT_OF_RESOURCES",
        error="openvino GPU runtime failure: CL_OUT_OF_RESOURCES",
    )
    decoded = decode_protocol_message(encode_protocol_message(message))
    assert decoded["type"] == "retirement"
    assert decoded["error_code"] == "CL_OUT_OF_RESOURCES"

    incomplete = dict(message)
    del incomplete["error_code"]
    with pytest.raises(ValueError):
        decode_protocol_message(json.dumps(incomplete))


class _MemoryWriter:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.messages.append(decode_protocol_message(data))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_worker_emits_retirement_before_exiting_without_error_event():
    from app.services.classifier_worker_protocol import ClassifierWorkerRetirementError

    reader = asyncio.StreamReader()
    writer = _MemoryWriter()

    def classify(**_kwargs):
        raise ClassifierWorkerRetirementError(
            error_code="CL_INVALID_EVENT",
            detail="openvino GPU runtime failure: CL_INVALID_EVENT",
        )

    process = ClassifierWorkerProcess(reader=reader, writer=writer, classify_fn=classify, worker_generation=1)
    message = build_classify_request(
        worker_generation=1,
        request_id="req",
        work_id="work",
        lease_token=1,
        image_b64="payload",
        camera_name=None,
        model_id=None,
    )
    reader.feed_data(process.encode_message(message))
    await asyncio.wait_for(process.run(), timeout=5)

    assert [m["type"] for m in writer.messages] == ["ready", "retirement"]
    assert writer.messages[-1]["error_code"] == "CL_INVALID_EVENT"
    assert process.retirement_requested is True


def test_quarantine_records_retirement_evidence_without_a_native_exit_code(tmp_path):
    profile = {"provider": "intel_gpu", "model_id": "eva02_large"}
    quarantine = NativeCrashQuarantine(lambda: dict(profile), root=tmp_path)

    assert quarantine.guard() == profile
    assert quarantine.record_retirement(profile, "CL_OUT_OF_RESOURCES", "clFlush failed") is True
    with pytest.raises(NativeCrashQuarantinedError):
        quarantine.guard()

    evidence_files = list(tmp_path.glob("*.json"))
    assert len(evidence_files) == 1
    evidence = json.loads(evidence_files[0].read_text())
    assert evidence["retirement"]["error_code"] == "CL_OUT_OF_RESOURCES"
    assert evidence["exit_code"] is None


class _FakeWorker:
    def __init__(self, worker_name: str, worker_generation: int) -> None:
        self.worker_name = worker_name
        self.worker_generation = worker_generation
        self.events: asyncio.Queue[dict] = asyncio.Queue()
        self.current_request_id: str | None = None
        self.busy = False
        self.exit_code: int | None = None

    async def start(self) -> None:
        return None

    async def wait_until_ready(self, timeout_seconds: float = 1.0) -> None:
        return None

    async def send(self, message: dict) -> None:
        self.current_request_id = message.get("request_id")
        self.busy = True

    async def next_event(self) -> dict:
        return await self.events.get()

    async def terminate(self) -> None:
        return None

    async def kill(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None

    def get_status(self) -> dict:
        return {
            "worker_name": self.worker_name,
            "worker_generation": self.worker_generation,
            "ready": True,
            "busy": self.busy,
            "current_request_id": self.current_request_id,
            "last_heartbeat_monotonic": time.monotonic(),
            "heartbeat_timeout_seconds": 5.0,
            "exit_code": self.exit_code,
            "recent_stderr_excerpt": "",
            "stderr_truncated_bytes": 0,
        }


def _supervisor(factory, quarantine) -> ClassifierSupervisor:
    return ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5.0,
        hard_deadline_seconds=30.0,
        worker_factory=factory,
        watchdog_interval_seconds=0.01,
        crash_quarantine=quarantine,
    )


@pytest.mark.asyncio
async def test_supervisor_quarantines_retired_worker_and_fails_request_with_original_code(tmp_path):
    from app.services.classifier_worker_protocol import build_retirement_event

    profile = {"provider": "intel_gpu", "model_id": "eva02_large"}
    quarantine = NativeCrashQuarantine(lambda: dict(profile), root=tmp_path / "crashes")
    created: list[_FakeWorker] = []

    async def factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = _supervisor(factory, quarantine)
    await supervisor.start("live")
    try:
        task = asyncio.create_task(
            supervisor.classify(
                priority="live", work_id="w1", lease_token=2, image_b64="payload", camera_name=None, model_id=None
            )
        )
        await asyncio.sleep(0.05)
        worker = next(w for w in created if w.worker_name == "live-0")
        await worker.events.put(
            build_retirement_event(
                worker_generation=worker.worker_generation,
                request_id=worker.current_request_id,
                work_id="w1",
                lease_token=2,
                error_code="CL_OUT_OF_RESOURCES",
                error="openvino GPU runtime failure: CL_OUT_OF_RESOURCES",
            )
        )
        with pytest.raises(NativeCrashQuarantinedError) as raised:
            await asyncio.wait_for(task, timeout=5)
        assert "CL_OUT_OF_RESOURCES" in str(raised.value)

        deadline = time.monotonic() + 5
        while supervisor.get_metrics()["live"].get("last_retirement") is None and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        metrics = supervisor.get_metrics()["live"]
        assert metrics["last_retirement"]["error_code"] == "CL_OUT_OF_RESOURCES"
        # The retired profile is quarantined: no replacement GPU worker spawns.
        assert len([w for w in created if w.worker_name == "live-0"]) == 1
        with pytest.raises(NativeCrashQuarantinedError):
            quarantine.guard()
    finally:
        await supervisor.shutdown()


@pytest.mark.asyncio
async def test_supervisor_ignores_stale_retirement_with_wrong_lease(tmp_path):
    from app.services.classifier_worker_protocol import build_retirement_event

    profile = {"provider": "intel_gpu", "model_id": "eva02_large"}
    quarantine = NativeCrashQuarantine(lambda: dict(profile), root=tmp_path / "crashes")
    created: list[_FakeWorker] = []

    async def factory(*, worker_name: str, worker_generation: int, **_kwargs):
        worker = _FakeWorker(worker_name, worker_generation)
        created.append(worker)
        return worker

    supervisor = _supervisor(factory, quarantine)
    await supervisor.start("live")
    try:
        task = asyncio.create_task(
            supervisor.classify(
                priority="live", work_id="w1", lease_token=2, image_b64="payload", camera_name=None, model_id=None
            )
        )
        await asyncio.sleep(0.05)
        worker = next(w for w in created if w.worker_name == "live-0")
        await worker.events.put(
            build_retirement_event(
                worker_generation=worker.worker_generation,
                request_id=worker.current_request_id,
                work_id="w1",
                lease_token=999,
                error_code="CL_OUT_OF_RESOURCES",
                error="stale retirement",
            )
        )
        await asyncio.sleep(0.1)
        assert not task.done()
        assert supervisor.get_metrics()["late_results_ignored"] >= 1
        assert quarantine.guard() == profile

        await worker.events.put(
            {
                "type": "result",
                "worker_generation": worker.worker_generation,
                "request_id": worker.current_request_id,
                "work_id": "w1",
                "lease_token": 2,
                "results": [{"label": "Parus major", "score": 0.9}],
            }
        )
        assert (await asyncio.wait_for(task, timeout=5))[0]["label"] == "Parus major"
    finally:
        await supervisor.shutdown()
