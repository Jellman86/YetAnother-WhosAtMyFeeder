import asyncio
import signal
import sys

import pytest

from app.services.native_cpu_recovery import NativeCpuRecovery, NativeCpuRecoveryUnavailable
from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError


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
async def test_idle_cpu_recovery_is_distinct_from_inference_and_unconfirmed_cleanup(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    try:
        assert await classify(runner)
        assert runner.snapshot()["live"]["recovered"]
        assert runner._worker is worker
        assert not runner.has_native_work()
        await runner._lock.acquire("live")
        try:
            assert runner.has_native_work()
        finally:
            runner._lock.release()
        runner._cleanup_pending = True
        assert runner.has_native_work()
        runner._cleanup_pending = False
        assert not runner.has_native_work()
    finally:
        await runner.shutdown()
    assert runner.has_native_work()  # Closed recovery cannot authorize new Garden admission.


@pytest.mark.asyncio
@pytest.mark.parametrize("validated,expected", [(["intel_cpu", "cpu"], "intel_cpu"), (["cpu"], "cpu"), ([], "cpu")])
async def test_recovery_prefers_current_artifact_validated_intel_cpu(tmp_path, monkeypatch, validated, expected):
    from app.services import model_validation

    seen = []

    def eligible(model_id, *, artifact_sha256):
        seen.append((model_id, artifact_sha256))
        return validated

    monkeypatch.setattr(model_validation, "host_eligible_providers", eligible)
    profile = PROFILE | {"model_runtime": "onnx"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile, -signal.SIGSEGV)
    worker = Worker()
    worker.runtime.update(
        active_provider=expected, inference_backend="openvino" if expected == "intel_cpu" else "onnxruntime"
    )
    runner = NativeCpuRecovery(lambda: dict(profile), policy, worker_factory=lambda: worker)
    try:
        assert await classify(runner)
        assert runner._profile["provider"] == expected
        assert runner.snapshot()["live"]["runtime"]["active_provider"] == expected
        assert seen == [(PROFILE["model_id"], PROFILE["model_sha256"])]
        with pytest.raises(NativeCrashQuarantinedError):
            policy.guard(profile)
    finally:
        await runner.shutdown()


@pytest.mark.asyncio
async def test_recovery_skips_quarantined_intel_cpu_without_clearing_its_evidence(tmp_path, monkeypatch):
    from app.services import model_validation
    from app.services.native_crash_quarantine import NativeCrashQuarantinedError

    monkeypatch.setattr(model_validation, "host_eligible_providers", lambda *_args, **_kwargs: ["intel_cpu", "cpu"])
    profile = PROFILE | {"model_runtime": "onnx"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    policy.record(profile | {"provider": "intel_cpu"}, -signal.SIGABRT)
    worker = Worker()
    runner = NativeCpuRecovery(lambda: dict(profile), policy, worker_factory=lambda: worker)
    try:
        assert await classify(runner)
        assert runner._profile["provider"] == "cpu"
        with pytest.raises(NativeCrashQuarantinedError):
            policy.guard(profile | {"provider": "intel_cpu"})
    finally:
        await runner.shutdown()


@pytest.mark.parametrize("change", [{"model_runtime": "tflite"}, {"model_id": None}, {"model_sha256": None}])
def test_recovery_does_not_apply_intel_validation_to_unidentified_or_non_onnx_artifact(tmp_path, monkeypatch, change):
    from app.services import model_validation

    def unexpected_validation(*_args, **_kwargs):
        pytest.fail("No artifact-specific Intel CPU lookup should be made")

    monkeypatch.setattr(model_validation, "host_eligible_providers", unexpected_validation)
    profile = PROFILE | {"model_runtime": "onnx"} | change
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    runner = NativeCpuRecovery(lambda: profile, policy)
    assert runner._cpu_profile(profile) == profile | {"provider": "cpu"}


@pytest.mark.asyncio
async def test_all_cpu_profiles_quarantined_never_starts_another_worker(tmp_path, monkeypatch):
    from app.services import model_validation

    monkeypatch.setattr(model_validation, "host_eligible_providers", lambda *_args, **_kwargs: ["intel_cpu", "cpu"])
    profile = PROFILE | {"model_runtime": "onnx"}
    policy = NativeCrashQuarantine(lambda: profile, root=tmp_path)
    for provider in ["intel_cpu", "cpu"]:
        policy.record(profile | {"provider": provider}, -signal.SIGABRT)
    worker = Worker()
    runner = NativeCpuRecovery(lambda: dict(profile), policy, worker_factory=lambda: worker)
    with pytest.raises(NativeCpuRecoveryUnavailable):
        await classify(runner)
    assert runner._worker is None
    assert not worker.sent
    assert len(list(tmp_path.glob("*.json"))) == 2


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
    assert "live" not in runner.snapshot()


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
    assert "live" not in runner.snapshot()
    assert await classify(runner, "live")
    assert len(worker.sent) == 2
    assert not runner._lock.locked()
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
    assert runner._warm_seconds == {}


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
@pytest.mark.parametrize("fail_progress", [False, True])
async def test_video_progress_cannot_block_cpu_result_or_the_next_live_request(tmp_path, fail_progress):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    original = worker.next_event
    progress_started = asyncio.Event()
    progress_cancelled = asyncio.Event()
    calls = 0

    async def events():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {**worker.sent[-1], "type": "progress", "current_frame": 1}
        await progress_started.wait()
        return await original()

    async def slow_progress(*_args):
        progress_started.set()
        if fail_progress:
            raise RuntimeError("Progress storage failed")
        try:
            await asyncio.Event().wait()
        finally:
            progress_cancelled.set()

    worker.next_event = events
    try:
        result = await runner.run(
            priority="video",
            timeout_seconds=0.1,
            payload={"video_path": "unused"},
            progress_callback=slow_progress,
        )
        assert result and runner.snapshot()["video"]["recovered"]
        assert not worker.closed
        if not fail_progress:
            assert progress_cancelled.is_set()
        assert await classify(runner, "live", timeout=0.1)
        assert len(worker.sent) == 2
    finally:
        await runner.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["result", "cancel", "timeout"])
async def test_cpu_progress_retention_is_bounded_and_cleaned_on_every_request_exit(tmp_path, finish):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    original = worker.next_event
    progress_started = asyncio.Event()
    progress_cancelled = asyncio.Event()
    burst_drained = asyncio.Event()
    progress_calls = 0
    event_calls = 0

    async def events():
        nonlocal event_calls
        event_calls += 1
        if event_calls <= 100:
            return {**worker.sent[-1], "type": "progress", "current_frame": event_calls}
        burst_drained.set()
        if finish != "result":
            await asyncio.Event().wait()
        return await original()

    async def slow_progress(*_args):
        nonlocal progress_calls
        progress_calls += 1
        progress_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            progress_cancelled.set()

    worker.next_event = events
    task = asyncio.create_task(
        runner.run(
            priority="video",
            timeout_seconds=2,
            payload={"video_path": "unused"},
            progress_callback=slow_progress,
        )
    )
    try:
        await asyncio.wait_for(progress_started.wait(), 5)
        await asyncio.wait_for(burst_drained.wait(), 5)
        assert progress_calls == 1
        if finish == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif finish == "timeout":
            with pytest.raises(NativeCpuRecoveryUnavailable):
                await task
        else:
            assert await task
        assert progress_cancelled.is_set()
        assert worker.closed == (finish != "result")
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runner.shutdown()


@pytest.mark.asyncio
async def test_progress_cancellation_cleanup_cannot_hold_the_cpu_worker_or_accumulate_tasks(tmp_path):
    worker = Worker()
    runner = recovery(tmp_path, worker)
    original = worker.next_event
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    progress_calls = 0
    event_calls = 0

    async def events():
        nonlocal event_calls
        event_calls += 1
        if event_calls % 2:
            return {**worker.sent[-1], "type": "progress", "current_frame": 1}
        return await original()

    async def slow_cleanup(*_args):
        nonlocal progress_calls
        progress_calls += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleanup_started.set()
            await release_cleanup.wait()

    worker.next_event = events
    try:
        for _ in range(2):
            assert await asyncio.wait_for(
                runner.run(
                    priority="video",
                    timeout_seconds=1,
                    payload={"video_path": "unused"},
                    progress_callback=slow_cleanup,
                ),
                0.5,
            )
        assert cleanup_started.is_set()
        assert progress_calls == 1
        assert runner._progress_task is not None and not runner._progress_task.done()
        assert await classify(runner, "live", timeout=1)
        assert not runner._lock.locked()
        assert not worker.closed
    finally:
        release_cleanup.set()
        await runner.shutdown()
    assert runner._progress_task is None


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
    from unittest.mock import AsyncMock

    worker = Worker()
    worker.next_event = AsyncMock(side_effect=TimeoutError("classification timed out"))
    runner = recovery(tmp_path, worker)
    original_kill = worker.kill

    async def unreaped():
        raise TimeoutError("not reaped")

    worker.kill = unreaped
    with pytest.raises(NativeCpuRecoveryUnavailable, match="cleanup"):
        await classify(runner)
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
@pytest.mark.parametrize("priority", ["live", "background", "video"])
@pytest.mark.parametrize("previous_success", [False, True])
async def test_caller_cancellation_allows_later_same_workload_to_recover(tmp_path, priority, previous_success):
    delays = {"now": 0}
    runner, workers = recovery_with_fresh_workers(tmp_path, delays)

    async def request():
        payload = (
            {"video_path": "/tmp/unused.mp4", "stride": 5, "max_frames": 3}
            if priority == "video"
            else {"image_b64": "unused", "camera_name": None, "model_id": None}
        )
        return await runner.run(priority=priority, timeout_seconds=5, payload=payload)

    try:
        if previous_success:
            assert await request()
        before = runner.snapshot().get(priority)
        delays["now"] = 10
        for worker in workers:
            worker.delay = 10
        task = asyncio.create_task(request())
        while not workers or len(workers[-1].sent) < 1 + int(previous_success):
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert workers[-1].closed
        assert runner.snapshot().get(priority) == before
        delays["now"] = 0
        assert await request()
        assert len(workers) == 2
        assert runner.snapshot()[priority]["status"] == "degraded"
    finally:
        await runner.shutdown()


@pytest.mark.asyncio
async def test_queued_retry_waits_for_cancelled_worker_cleanup(tmp_path):
    delays = {"now": 10}
    runner, workers = recovery_with_fresh_workers(tmp_path, delays)
    cleanup_started, release_cleanup = asyncio.Event(), asyncio.Event()
    active = asyncio.create_task(classify(runner, timeout=5))
    while not workers or not workers[0].sent:
        await asyncio.sleep(0)
    original_kill = workers[0].kill

    async def delayed_kill():
        cleanup_started.set()
        await release_cleanup.wait()
        await original_kill()

    workers[0].kill = delayed_kill
    delays["now"] = 0
    queued = asyncio.create_task(classify(runner, timeout=5))
    active.cancel()
    await cleanup_started.wait()
    assert len(workers) == 1
    assert not queued.done()
    release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await active
    try:
        assert await queued
        assert len(workers) == 2 and workers[0].closed
    finally:
        await runner.shutdown()


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


@pytest.mark.asyncio
async def test_queued_live_recovery_runs_before_earlier_background_work(tmp_path):
    active = asyncio.Event()
    release = asyncio.Event()

    class GatedWorker(Worker):
        async def send(self, message):
            await super().send(message)
            active.set()

        async def next_event(self):
            if len(self.sent) == 1:
                await release.wait()
            return await super().next_event()

    worker = GatedWorker()
    runner = recovery(tmp_path, worker)

    async def submit(priority, camera):
        return await runner.run(
            priority=priority,
            timeout_seconds=5,
            payload={"image_b64": "unused", "camera_name": camera, "model_id": None},
        )

    tasks = [asyncio.create_task(submit("background", "active"))]
    try:
        await asyncio.wait_for(active.wait(), timeout=1)
        tasks.append(asyncio.create_task(submit("background", "queued-background")))
        await asyncio.sleep(0)
        tasks.append(asyncio.create_task(submit("live", "queued-live")))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(*tasks)
        assert [message["camera_name"] for message in worker.sent] == ["active", "queued-live", "queued-background"]
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.shutdown()


@pytest.mark.asyncio
async def test_cancelling_live_lock_handoff_releases_the_next_background_waiter():
    from app.services.native_cpu_recovery import _CpuRecoveryLock

    lock = _CpuRecoveryLock()
    await lock.acquire("background")
    background = asyncio.create_task(lock.acquire("background"))
    await asyncio.sleep(0)
    live = asyncio.create_task(lock.acquire("live"))
    await asyncio.sleep(0)
    lock.release()
    live.cancel()
    with pytest.raises(asyncio.CancelledError):
        await live
    assert await asyncio.wait_for(background, timeout=1)
    lock.release()
    assert not lock.locked()


@pytest.mark.asyncio
async def test_cancelled_queued_live_work_does_not_block_background_or_steal_ownership():
    from app.services.native_cpu_recovery import _CpuRecoveryLock

    lock = _CpuRecoveryLock()
    await lock.acquire("background")
    live = asyncio.create_task(lock.acquire("live"))
    await asyncio.sleep(0)
    live.cancel()
    with pytest.raises(asyncio.CancelledError):
        await live
    assert lock.locked()
    background = asyncio.create_task(lock.acquire("background"))
    await asyncio.sleep(0)
    lock.release()
    assert await asyncio.wait_for(background, timeout=1)
    lock.release()
    assert not lock.locked()


@pytest.mark.asyncio
async def test_cpu_recovery_shutdown_gets_the_next_turn_ahead_of_queued_inference():
    from app.services.native_cpu_recovery import _CpuRecoveryLock

    lock = _CpuRecoveryLock()
    await lock.acquire("background")
    live = asyncio.create_task(lock.acquire("live"))
    await asyncio.sleep(0)
    control = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    lock.release()
    assert await asyncio.wait_for(control, timeout=1)
    assert not live.done()
    lock.release()
    assert await asyncio.wait_for(live, timeout=1)
    lock.release()


@pytest.mark.asyncio
async def test_video_and_background_recovery_keep_arrival_order_after_live_work():
    from app.services.native_cpu_recovery import _CpuRecoveryLock

    lock = _CpuRecoveryLock()
    await lock.acquire()
    video = asyncio.create_task(lock.acquire("video"))
    await asyncio.sleep(0)
    background = asyncio.create_task(lock.acquire("background"))
    await asyncio.sleep(0)
    live = asyncio.create_task(lock.acquire("live"))
    await asyncio.sleep(0)
    lock.release()
    assert await asyncio.wait_for(live, timeout=1)
    assert not video.done() and not background.done()
    lock.release()
    assert await asyncio.wait_for(video, timeout=1)
    assert not background.done()
    lock.release()
    assert await asyncio.wait_for(background, timeout=1)
    lock.release()
    assert not lock.locked()


class _ControlledRecoveryWorker(Worker):
    def __init__(self, name, events, release=None):
        super().__init__()
        self.name, self.events, self.release = name, events, release
        self.started = asyncio.Event()

    async def send(self, message):
        await super().send(message)
        self.events.append(f"{self.name}:send")
        self.started.set()

    async def next_event(self):
        if self.release is not None:
            await self.release.wait()
        return await super().next_event()

    async def kill(self):
        self.events.append(f"{self.name}:kill")
        await super().kill()


@pytest.mark.asyncio
async def test_real_shutdown_reaps_before_rejecting_queued_recovery_requests(tmp_path):
    events = []
    release = asyncio.Event()
    worker = _ControlledRecoveryWorker("active", events, release)
    runner = recovery(tmp_path, worker)
    tasks = [asyncio.create_task(classify(runner, "background", timeout=5))]

    async def queued():
        try:
            return await classify(runner, "live", timeout=5)
        except NativeCpuRecoveryUnavailable:
            events.append("queued:rejected")
            raise

    try:
        await asyncio.wait_for(worker.started.wait(), timeout=1)
        tasks.append(asyncio.create_task(queued()))
        await asyncio.sleep(0)
        tasks.append(asyncio.create_task(runner.shutdown()))
        await asyncio.sleep(0)
        assert runner._closed
        release.set()
        assert await tasks[0]
        await tasks[2]
        with pytest.raises(NativeCpuRecoveryUnavailable):
            await tasks[1]
        assert events.index("active:kill") < events.index("queued:rejected")
        assert len(worker.sent) == 1
        assert not runner._lock.locked()
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.shutdown()


@pytest.mark.asyncio
async def test_real_profile_refresh_finishes_before_queued_live_inference(tmp_path):
    events = []
    release = asyncio.Event()
    first = _ControlledRecoveryWorker("old", events, release)
    second = _ControlledRecoveryWorker("new", events)
    workers = iter([first, second])
    source = dict(PROFILE)
    policy = NativeCrashQuarantine(lambda: dict(source), root=tmp_path)
    runner = NativeCpuRecovery(lambda: dict(source), policy, worker_factory=lambda: next(workers))
    tasks = [asyncio.create_task(classify(runner, "background", timeout=5))]

    async def refresh():
        await runner.refresh_profile()
        events.append("refresh:finished")

    try:
        await asyncio.wait_for(first.started.wait(), timeout=1)
        tasks.append(asyncio.create_task(classify(runner, "live", timeout=5)))
        await asyncio.sleep(0)
        source["input_size"] = 512
        tasks.append(asyncio.create_task(refresh()))
        await asyncio.sleep(0)
        release.set()
        assert await tasks[0]
        await tasks[2]
        assert await tasks[1]
        assert events.index("old:kill") < events.index("refresh:finished") < events.index("new:send")
        assert runner._source_profile["input_size"] == 512
        assert len(first.sent) == len(second.sent) == 1
    finally:
        release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await runner.shutdown()


@pytest.mark.asyncio
async def test_expanded_gpu_incident_preserves_cpu_recovery_but_not_a_failed_cpu_profile(tmp_path):
    source = PROFILE | {
        "auxiliary_artifacts": {"crop": {"fast": {"weights": "fixture"}}},
        "video_frames": 15,
        "legacy_profile_keys": [NativeCrashQuarantine._key(PROFILE)],
    }
    policy = NativeCrashQuarantine(lambda: source, root=tmp_path)
    policy.record(source, -signal.SIGSEGV)
    worker = Worker()
    instance = NativeCpuRecovery(lambda: source, policy, worker_factory=lambda: worker)
    try:
        result = await classify(instance)
        assert result[0]["label"] == "bird"
        assert instance._profile["provider"] == "cpu"
    finally:
        await instance.shutdown()
    policy.remember_retirement(source | {"provider": "cpu"})
    with pytest.raises(NativeCpuRecoveryUnavailable):
        instance._cpu_profile(source)
