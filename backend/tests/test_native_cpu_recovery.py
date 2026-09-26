import asyncio
import signal
import sys

import pytest

from app.services.native_cpu_recovery import NativeCpuRecovery, NativeCpuRecoveryUnavailable
from app.services.native_crash_quarantine import NativeCrashQuarantine


PROFILE = {
    "model_id": "only-installed-model",
    "provider": "intel_gpu",
    "model_sha256": "abc",
    "external_weights_sha256": None,
    "labels_sha256": "def",
}
RUNTIME = {**PROFILE, "active_provider": "cpu", "inference_backend": "onnx"}


class Worker:
    worker_name = "native-cpu"
    worker_generation = 1

    def __init__(self):
        self.runtime = dict(RUNTIME)
        self.result_runtime = None
        self.closed = False
        self.exit_code = None
        self.delay = 0
        self.sent = []

    async def start(self):
        pass

    async def wait_until_ready(self, **kwargs):
        pass

    def get_status(self):
        return {"runtime": self.runtime, "exit_code": self.exit_code, "ready": not self.closed}

    async def send(self, message):
        self.sent.append(message)

    async def next_event(self):
        await asyncio.sleep(self.delay)
        return {
            **self.sent[-1],
            "type": "result",
            "runtime": self.result_runtime or self.runtime,
            "results": [{"label": "bird", "score": 0.9}],
        }

    async def kill(self):
        self.closed = True

    async def wait_closed(self):
        while not self.closed:
            await asyncio.sleep(0.001)


def recovery(tmp_path, worker):
    policy = NativeCrashQuarantine(lambda: PROFILE, root=tmp_path)
    policy.record(PROFILE, -signal.SIGSEGV)
    return NativeCpuRecovery(lambda: dict(PROFILE), policy, worker_factory=lambda: worker)


async def classify(recovery, priority="live", timeout=1):
    return await recovery.run(
        priority=priority,
        timeout_seconds=timeout,
        payload={"image_b64": "unused", "camera_name": None, "model_id": None},
    )


@pytest.mark.asyncio
async def test_same_artifact_cpu_recovery_reuses_isolated_worker_and_keeps_negative_evidence(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    try:
        assert await classify(runner)
        assert await classify(runner, "background")
        assert len(worker.sent) == 2
        assert runner.snapshot()["live"]["status"] == "degraded"
        assert runner.snapshot()["background"]["status"] == "degraded"
        assert len(list(tmp_path.glob("*.json"))) == 1
    finally:
        await runner.shutdown()
    assert worker.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"active_provider": "intel_gpu"},
        {"model_sha256": "other"},
        {"labels_sha256": "other"},
        {"model_id": "other"},
        {"external_weights_sha256": "other"},
    ],
)
async def test_ready_is_not_recovery_and_wrong_artifact_or_provider_is_rejected(tmp_path, change):
    worker = Worker()
    worker.runtime.update(change)
    runner = recovery(tmp_path, worker)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner)
    assert worker.closed and not worker.sent
    assert runner.snapshot()["live"]["status"] == "failed"


@pytest.mark.asyncio
async def test_changed_runtime_after_inference_is_not_reported_as_recovery(tmp_path):
    worker = Worker()
    worker.result_runtime = RUNTIME | {"model_sha256": "another-model"}
    runner = recovery(tmp_path, worker)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner)
    assert worker.closed


@pytest.mark.asyncio
async def test_slow_cpu_is_reaped_and_not_retried_on_every_frame(tmp_path):
    worker = Worker()
    worker.delay = 10
    runner = recovery(tmp_path, worker)
    for _ in range(2):
        with pytest.raises(NativeCpuRecoveryUnavailable):
            await classify(runner, timeout=0.02)
    assert len(worker.sent) == 1
    assert worker.closed
    assert runner.snapshot()["live"]["status"] == "failed"


@pytest.mark.asyncio
async def test_cancellation_reaps_worker_and_never_claims_recovery(tmp_path):
    worker = Worker()
    worker.delay = 10
    runner = recovery(tmp_path, worker)
    task = asyncio.create_task(classify(runner))
    while not worker.sent:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert worker.closed
    assert runner.snapshot()["live"]["status"] == "failed"


@pytest.mark.asyncio
async def test_queue_timeout_does_not_kill_another_pools_active_request(tmp_path):
    worker = Worker()
    worker.delay = 0.05
    runner = recovery(tmp_path, worker)
    task = asyncio.create_task(classify(runner, "background"))
    while not worker.sent:
        await asyncio.sleep(0)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner, timeout=0.01)
    assert await task
    assert not worker.closed
    await runner.shutdown()


@pytest.mark.asyncio
async def test_cpu_ready_without_completed_inference_is_only_recovering(tmp_path):
    worker = Worker()
    worker.delay = 0.05
    runner = recovery(tmp_path, worker)
    task = asyncio.create_task(classify(runner))
    while not worker.sent:
        await asyncio.sleep(0)
    assert runner.snapshot()["live"]["status"] == "recovering"
    assert runner.snapshot()["live"]["recovered"] is False
    await task
    await runner.shutdown()


@pytest.mark.asyncio
async def test_native_cpu_crash_is_persisted_and_no_other_pool_relaunches(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)

    async def crash(_message):
        worker.exit_code = -signal.SIGABRT
        worker.closed = True

    worker.send = crash
    for priority in ("live", "background", "video"):
        with pytest.raises(NativeCpuRecoveryUnavailable):
            await classify(runner, priority)
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert runner._worker is None


@pytest.mark.asyncio
async def test_recovery_diagnostics_are_bounded_not_written_per_frame(tmp_path, monkeypatch):
    from app.services import error_diagnostics

    history = error_diagnostics.ErrorDiagnosticsHistory()
    monkeypatch.setattr(error_diagnostics, "error_diagnostics_history", history)
    runner = recovery(tmp_path, Worker())
    for _ in range(10):
        await classify(runner)
    reasons = [event["reason_code"] for event in history.snapshot()["events"]]
    assert reasons.count("native_cpu_recovery_degraded") == 1
    assert reasons.count("native_classifier_crash") == 1
    await runner.shutdown()


@pytest.mark.asyncio
async def test_profile_change_reaps_old_cpu_and_clears_stale_health(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    await classify(runner)
    runner._profile_getter = lambda: PROFILE | {"provider": "cpu"}
    await runner.refresh_profile()
    assert worker.closed
    assert runner.snapshot() == {}


@pytest.mark.asyncio
async def test_already_crashing_cpu_does_not_fall_back_to_itself(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    runner._profile_getter = lambda: PROFILE | {"provider": "cpu"}
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner)
    assert not worker.sent


@pytest.mark.asyncio
async def test_video_progress_is_forwarded_without_losing_result(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    original = worker.next_event
    progress = []
    calls = 0

    async def events():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {**worker.sent[-1], "type": "progress", "current_frame": 1}
        return await original()

    worker.next_event = events
    result = await runner.run(
        priority="video",
        timeout_seconds=1,
        payload={"video_path": "unused"},
        progress_callback=lambda *args: progress.append(args),
    )
    assert result and progress[0][0] == 1
    await runner.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "linux", reason="Native signal contract without macOS crash reporter")
async def test_real_cpu_child_fault_is_reaped_and_blocks_all_workload_retries(tmp_path):
    from app.services.classifier_worker_client import ClassifierWorkerClient

    processes = []

    async def process_factory(**kwargs):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import os,resource,signal; resource.setrlimit(resource.RLIMIT_CORE,(0,0)); os.kill(os.getpid(),signal.SIGABRT)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={},
        )
        processes.append(process)
        return process

    worker = ClassifierWorkerClient(
        worker_name="native-cpu", worker_generation=1, heartbeat_timeout_seconds=5, process_factory=process_factory
    )
    runner = recovery(tmp_path, worker)
    for priority in ("live", "background", "video"):
        with pytest.raises(NativeCpuRecoveryUnavailable):
            await classify(runner, priority, timeout=5)
    assert len(processes) == 1
    assert processes[0].returncode == -signal.SIGABRT
    assert runner._worker is None
    assert len(list(tmp_path.glob("*.json"))) == 2


@pytest.mark.asyncio
async def test_failed_cleanup_never_reuses_worker_in_another_pool(tmp_path):
    worker = Worker()
    worker.delay = 10
    runner = recovery(tmp_path, worker)
    original_kill = worker.kill

    async def unreaped():
        raise TimeoutError("not reaped")

    worker.kill = unreaped
    with pytest.raises(NativeCpuRecoveryUnavailable, match="cleanup"):
        await classify(runner, timeout=0.01)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner, "background")
    assert len(worker.sent) == 1
    assert runner._worker is worker
    worker.kill = original_kill
    await runner.shutdown()


def recovery_with_fresh_workers(tmp_path, delays):
    """Each started worker is a new process, as after a kill in production."""
    workers = []

    def factory():
        worker = Worker()
        worker.delay = delays["now"]
        workers.append(worker)
        return worker

    policy = NativeCrashQuarantine(lambda: PROFILE, root=tmp_path)
    policy.record(PROFILE, -signal.SIGSEGV)
    return NativeCpuRecovery(lambda: dict(PROFILE), policy, worker_factory=factory), workers


@pytest.mark.asyncio
async def test_request_that_spent_its_budget_queueing_does_not_disable_its_workload(tmp_path):
    """A live snapshot queued behind backfill must not end live CPU recovery (#490 review).

    The request reached the shared worker with little budget left and timed out.
    That is queueing, not evidence that CPU cannot serve live work, so the next
    live request with its own budget still runs.
    """
    delays = {"now": 0}
    runner, workers = recovery_with_fresh_workers(tmp_path, delays)
    # A fast earlier result makes the queued request look as if it can still fit.
    assert await classify(runner, "live", timeout=5)
    workers[0].delay = 0.3
    background = asyncio.create_task(classify(runner, "background", timeout=5))
    while len(workers[0].sent) < 2:
        await asyncio.sleep(0)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner, "live", timeout=0.45)
    assert await background
    assert runner.snapshot()["live"]["status"] != "failed"

    delays["now"] = 0
    for worker in workers:
        worker.delay = 0
    assert await classify(runner, "live", timeout=5)
    assert runner.snapshot()["live"]["status"] == "degraded"
    await runner.shutdown()


@pytest.mark.asyncio
async def test_warm_worker_is_kept_when_a_queued_request_cannot_fit(tmp_path):
    """Starting work that cannot finish would kill the worker other pools rely on."""
    worker = Worker()
    worker.delay = 0.2
    runner = recovery(tmp_path, worker)
    assert await classify(runner, "live", timeout=5)
    background = asyncio.create_task(classify(runner, "background", timeout=5))
    while len(worker.sent) < 2:
        await asyncio.sleep(0)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner, "live", timeout=0.3)
    assert await background
    assert not worker.closed
    assert len(worker.sent) == 2
    assert runner.snapshot()["live"]["status"] == "degraded"
    await runner.shutdown()
