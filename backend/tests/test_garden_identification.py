"""Species suggestions remain private, explicit and subordinate to bird work."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.garden_identification import normalize_country, bird_work_pending


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("United Kingdom", "GBR"),
        (" UK ", "GBR"),
        ("gb", "GBR"),
        ("GBR", "GBR"),
        ("United States", "USA"),
        ("Australia", "AUS"),
        ("NZ", "NZL"),
        ("Côte d'Ivoire", "CIV"),
    ],
)
def test_location_country_normalizes_exact_names_and_iso_codes(value, expected):
    assert normalize_country(value) == expected


@pytest.mark.parametrize("value", [None, "", "Congo-ish", "London", "ZZZ", "51.5,-0.1"])
def test_unknown_location_abstains_without_network_or_fuzzy_country_guess(value):
    assert normalize_country(value) is None


@pytest.mark.parametrize("priority", ["live", "background"])
@pytest.mark.parametrize("field", ["queued", "running"])
def test_any_pending_bird_work_prevents_garden_admission(priority, field):
    assert bird_work_pending({priority: {field: 1}})


def test_unknown_or_quarantined_bird_state_fails_closed():
    assert bird_work_pending(None)
    assert bird_work_pending({"live": {}, "background": {}, "worker_pools": {"video": {"busy": 1}}})
    assert not bird_work_pending({"live": {"queued": 0, "running": 0}, "background": {"queued": 0, "running": 0}})


@pytest.fixture
def idle_cpu_recovery():
    runtime = {"model_id": "bird-model", "model_sha256": "a" * 64, "active_provider": "intel_cpu"}
    return {
        "live": {"queued": 0, "running": 0},
        "background": {"queued": 0, "running": 0},
        "native_work_pending": False,
        "worker_pools": {
            "live": {
                "last_exit_reason": "native_runtime_quarantined",
                "last_runtime_recovery": {"status": "recovered"},
                "runtime": runtime,
                "native_cpu_recovery": {
                    "status": "degraded",
                    "reason": "native_crash_same_model_cpu",
                    "recovered": True,
                    "model_id": "bird-model",
                    "runtime": runtime,
                },
            }
        },
    }


@pytest.mark.parametrize("provider", ["cpu", "intel_cpu", "tflite"])
def test_idle_validated_cpu_recovery_allows_garden_without_releasing_accelerator_quarantine(
    idle_cpu_recovery, provider
):
    status = idle_cpu_recovery
    pool = status["worker_pools"]["live"]
    pool["native_cpu_recovery"]["runtime"]["active_provider"] = provider
    assert not bird_work_pending(status)
    assert pool["last_exit_reason"] == "native_runtime_quarantined"
    assert pool["last_runtime_recovery"]["status"] == "recovered"


@pytest.mark.parametrize(
    "reason", ["missing", "failed", "recovering", "unproven", "accelerator", "different_model", "no_digest"]
)
def test_quarantined_bird_pool_still_blocks_garden_without_a_proven_cpu_result(idle_cpu_recovery, reason):
    pool = idle_cpu_recovery["worker_pools"]["live"]
    state = pool["native_cpu_recovery"]
    if reason == "missing":
        del pool["native_cpu_recovery"]
    elif reason in {"failed", "recovering"}:
        state["status"] = reason
    elif reason == "unproven":
        state["recovered"] = False
    elif reason == "accelerator":
        state["runtime"]["active_provider"] = "intel_npu"
    elif reason == "different_model":
        state["model_id"] = "different-bird-model"
    else:
        state["runtime"]["model_sha256"] = None
    assert bird_work_pending(idle_cpu_recovery)


@pytest.mark.parametrize(
    "kind", ["live_queued", "background_running", "native", "pool_busy", "circuit", "failed", "recovering"]
)
def test_recovered_cpu_evidence_never_overrides_bird_work_or_an_unsafe_worker_state(idle_cpu_recovery, kind):
    if kind == "live_queued":
        idle_cpu_recovery["live"]["queued"] = 1
    elif kind == "background_running":
        idle_cpu_recovery["background"]["running"] = 1
    elif kind == "native":
        idle_cpu_recovery["native_work_pending"] = True
    else:
        pool = idle_cpu_recovery["worker_pools"]["live"]
        if kind in {"failed", "recovering"}:
            pool["last_runtime_recovery"]["status"] = kind
        else:
            pool["busy" if kind == "pool_busy" else "circuit_open"] = True
    assert bird_work_pending(idle_cpu_recovery)


@pytest.mark.asyncio
async def test_worker_is_reaped_before_yielding_to_a_bird():
    from app.services.garden_identification import supervise_worker, GardenBusy

    process = AsyncMock()
    process.returncode = None
    process.terminate = lambda: setattr(process, "returncode", -15)
    process.communicate = AsyncMock(side_effect=wait_for_native_call)
    pressures = iter([False, True])
    with pytest.raises(GardenBusy):
        await supervise_worker(process, lambda: next(pressures, True), poll_seconds=0.001)
    process.wait.assert_awaited()


@pytest.mark.asyncio
async def test_timeout_reaps_native_worker_and_ignores_late_results():
    from app.services.garden_identification import supervise_worker

    process = AsyncMock()
    process.returncode = None
    process.terminate = lambda: setattr(process, "returncode", -15)
    process.communicate = AsyncMock(side_effect=wait_for_native_call)
    with pytest.raises(TimeoutError):
        await supervise_worker(process, lambda: False, timeout_seconds=0.01, poll_seconds=0.001)
    process.wait.assert_awaited()


async def wait_for_native_call():
    await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_request_cancellation_reaps_the_native_worker():
    from app.services.garden_identification import supervise_worker

    process = AsyncMock()
    process.returncode = None
    process.terminate = lambda: setattr(process, "returncode", -15)
    process.communicate = AsyncMock(side_effect=wait_for_native_call)
    task = asyncio.create_task(supervise_worker(process, lambda: False, poll_seconds=0.001))
    await asyncio.sleep(0.002)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.wait.assert_awaited()
    assert process.returncode == -15


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returncode", "output", "signal_name", "error_type"),
    [
        (1, b"WORKER_ERROR:ValueError\n", None, "ValueError"),
        (-11, b"", "SIGSEGV", None),
        (1, b"WORKER_ERROR:../x\n", None, None),
    ],
)
async def test_failed_worker_reports_its_exit_code_signal_and_named_error(returncode, output, signal_name, error_type):
    from app.services.garden_identification import (
        GardenNativeWorkerFailed,
        supervise_worker,
        worker_failure_fields,
    )

    process = AsyncMock()
    process.returncode = returncode
    process.communicate = AsyncMock(return_value=(output, b""))
    with pytest.raises(GardenNativeWorkerFailed) as raised:
        await supervise_worker(process, lambda: False, poll_seconds=0.001)
    # A Python exception (exit 1) and a native fault (SIGSEGV) are told apart, never merged.
    assert worker_failure_fields(raised.value) == {
        "exit_code": returncode,
        "signal": signal_name,
        "worker_error": error_type,
    }
    assert worker_failure_fields(ValueError("other")) == {}


def test_provider_contract_matches_the_strict_native_runtime():
    from app.models.garden import GardenIdentifyRequest

    for provider in ("cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"):
        assert GardenIdentifyRequest(provider=provider).provider == provider


def test_garden_reads_both_bird_supervisors_without_constructing_classifier(monkeypatch):
    from types import SimpleNamespace
    from app.services import classifier_service

    # Real supervisors are ordinary identity-hashable instances.
    class Supervisor:
        def __init__(self, busy):
            self.busy = busy

        def has_native_work(self):
            return self.busy

    service = SimpleNamespace(
        _image_execution_mode="subprocess",
        _classifier_supervisor=Supervisor(False),
        _video_supervisor=Supervisor(True),
        get_admission_status=lambda: {"live": {}, "background": {}},
    )
    monkeypatch.setattr(classifier_service, "_classifier_instance", service)
    assert classifier_service.garden_inference_pressure()["native_work_pending"]
    monkeypatch.setattr(classifier_service, "_classifier_instance", None)
    assert classifier_service.garden_inference_pressure() is None


@pytest.mark.parametrize("pending", [False, True])
def test_garden_pressure_also_observes_cpu_recovery_work_and_cleanup(monkeypatch, pending):
    from types import SimpleNamespace
    from app.services import classifier_service

    # Supervisors are stored in a set, so use an ordinary hashable object.
    class Supervisor:
        def has_native_work(self):
            return False

    idle_supervisor = Supervisor()
    service = SimpleNamespace(
        _image_execution_mode="subprocess",
        _classifier_supervisor=idle_supervisor,
        _video_supervisor=idle_supervisor,
        _native_cpu_recovery=SimpleNamespace(has_native_work=lambda: pending),
        get_admission_status=lambda: {"live": {}, "background": {}},
    )
    monkeypatch.setattr(classifier_service, "_classifier_instance", service)
    assert classifier_service.garden_inference_pressure()["native_work_pending"] is pending


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"new", b"bad"])
async def test_installer_verifies_before_atomic_replacement_and_clears_busy(tmp_path, monkeypatch, content):
    import hashlib
    import httpx
    from fastapi import HTTPException
    from app.services import garden_identification as module

    service = module.GardenIdentificationService()
    service.models = tmp_path
    path = service.model_path("4.0.3b")
    path.write_bytes(b"old")
    monkeypatch.setattr(module, "MODEL_SIZES", {"4.0.3b": 3})
    monkeypatch.setattr(
        service.catalog, "load", lambda: {"model_sha256": {"4.0.3b": hashlib.sha256(b"new").hexdigest()}}
    )
    client_class = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=content))
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kwargs: client_class(transport=transport, **kwargs))
    if content == b"bad":
        with pytest.raises(HTTPException) as failure:
            await service.install("4.0.3b")
        assert failure.value.status_code == 503
        assert path.read_bytes() == b"old"
    else:
        assert not (await service.install("4.0.3b")).busy
        assert path.read_bytes() == b"new"
        assert not (await service.install("4.0.3b")).busy
    assert not service.busy
    assert list(tmp_path.glob(".garden-*")) == []


@pytest.mark.asyncio
async def test_native_cleanup_escalates_to_kill_then_quarantines_if_still_unreaped():
    from app.services.garden_identification import _stop_worker, GardenCleanupFailed

    process = AsyncMock()
    process.returncode = None
    process.wait.side_effect = TimeoutError
    process.terminate = lambda: None
    killed = []
    process.kill = lambda: killed.append(True)
    with pytest.raises(GardenCleanupFailed):
        await _stop_worker(process)
    assert killed == [True]
    assert process.wait.await_count == 2


@pytest.mark.asyncio
async def test_unreaped_worker_prevents_all_later_garden_native_requests(monkeypatch):
    from fastapi import HTTPException
    from app.models.garden import GardenIdentifyRequest
    from app.services.garden_identification import GardenIdentificationService, GardenCleanupFailed

    service = GardenIdentificationService()
    identify = AsyncMock(side_effect=GardenCleanupFailed())
    monkeypatch.setattr(service, "_identify", identify)
    for _ in range(2):
        with pytest.raises(HTTPException) as failure:
            await service.identify("capture", GardenIdentifyRequest())
        assert failure.value.status_code == 503
    assert service.error and not service.busy
    identify.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_model_status_does_not_clear_a_new_operation_busy_flag(tmp_path, monkeypatch):
    import hashlib
    from app.models.garden import GardenIdentificationStatus
    from app.services.garden_identification import GardenIdentificationService

    service = GardenIdentificationService()
    service.models = tmp_path
    service.model_path("4.0.3b").write_bytes(b"installed")
    monkeypatch.setattr(
        service.catalog, "load", lambda: {"model_sha256": {"4.0.3b": hashlib.sha256(b"installed").hexdigest()}}
    )

    async def status_after_operation():
        assert not service.busy
        # Another owner request begins while the completed install reads status.
        service.busy = True
        return GardenIdentificationStatus(country="GBR", catalogue_ready=True, busy=True, models=[])

    monkeypatch.setattr(service, "status", status_after_operation)
    await service.install("4.0.3b")
    assert service.busy


@pytest.mark.asyncio
async def test_reader_error_cannot_hide_an_unreaped_native_worker():
    from app.services.garden_identification import supervise_worker, GardenCleanupFailed

    process = AsyncMock()
    process.returncode = None
    process.communicate.side_effect = OSError("reader failed")
    process.wait.side_effect = TimeoutError
    process.terminate = lambda: None
    process.kill = lambda: None
    with pytest.raises(GardenCleanupFailed):
        await supervise_worker(process, lambda: False)


@pytest.mark.asyncio
async def test_failed_native_cleanup_still_cancels_the_pipe_reader():
    from app.services.garden_identification import supervise_worker, GardenCleanupFailed

    closed = []

    async def reader():
        try:
            await asyncio.sleep(60)
        finally:
            closed.append(True)

    process = AsyncMock()
    process.returncode = None
    process.communicate = reader
    process.wait.side_effect = TimeoutError
    process.terminate = lambda: None
    process.kill = lambda: None
    with pytest.raises(GardenCleanupFailed):
        await supervise_worker(process, lambda: True)
    assert closed == [True]


@pytest.mark.asyncio
async def test_unavailable_optional_garden_catalogue_does_not_fail_bird_startup(monkeypatch):
    import sqlite3
    from app.services.garden_identification import GardenIdentificationService

    service = GardenIdentificationService()

    def unavailable():
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(service.catalog, "initialize", unavailable)
    monkeypatch.setattr(service.catalog, "load", unavailable)
    await service.initialize()
    status = await service.status()
    assert not status.catalogue_ready
    assert not status.busy
    assert service.error is None
