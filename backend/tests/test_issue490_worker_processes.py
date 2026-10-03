"""Exercise #490 worker isolation with real, model-free child processes."""

import asyncio
import sys

import pytest

from app.services.classifier_supervisor import (
    ClassifierSupervisor,
    ClassifierWorkerDeadlineExceededError,
    ClassifierWorkerExitedError,
)
from app.services.classifier_worker_client import ClassifierWorkerClient
from app.services.native_cpu_recovery import NativeCpuRecovery, NativeCpuRecoveryUnavailable
from app.services.native_crash_quarantine import NativeCrashQuarantine


CHILD = """
import json, os, sys, time
generation = int(sys.argv[1])
behavior = sys.argv[2]
runtime = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
print(json.dumps({'type': 'ready', 'worker_generation': generation, 'runtime': runtime}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps({'type': 'heartbeat', 'worker_generation': generation,
                     'request_id': request['request_id'], 'busy': True}), flush=True)
    if behavior == 'hang':
        time.sleep(30)
    if behavior == 'crash':
        os._exit(23)
    print(json.dumps(request | {'type': 'result', 'runtime': runtime,
                              'results': [{'label': 'bird', 'score': 0.9}]}), flush=True)
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["hang", "crash"])
async def test_failed_background_child_is_reaped_while_live_work_keeps_completing(behavior):
    processes = []
    clients = []

    async def worker_factory(*, worker_name, worker_generation, **_kwargs):
        # Only the first background child fails; its replacement is healthy.
        child_behavior = behavior if worker_name.startswith("background") and worker_generation == 1 else "healthy"

        async def process_factory(**_process_kwargs):
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                CHILD,
                str(worker_generation),
                child_behavior,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            processes.append(process)
            return process

        client = ClassifierWorkerClient(
            worker_name=worker_name,
            worker_generation=worker_generation,
            heartbeat_timeout_seconds=5,
            process_factory=process_factory,
            terminate_timeout_seconds=0.1,
            kill_timeout_seconds=1,
        )
        clients.append(client)
        return client

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5,
        hard_deadline_seconds=0.5,
        worker_factory=worker_factory,
        watchdog_interval_seconds=0.01,
    )

    async def classify(priority, work_id):
        return await supervisor.classify(
            priority=priority,
            work_id=work_id,
            lease_token=1,
            image_b64="unused",
            camera_name=None,
            model_id=None,
        )

    background = None
    try:
        await supervisor.start("background")
        await supervisor.start("live")
        background = asyncio.create_task(classify("background", "failing-background"))

        async def wait_for_assignment():
            while "background-0" not in supervisor._assignments:
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_assignment(), 2)
        for index in range(3):
            assert await asyncio.wait_for(classify("live", f"live-{index}"), 0.4)
        error = ClassifierWorkerDeadlineExceededError if behavior == "hang" else ClassifierWorkerExitedError
        with pytest.raises(error):
            await asyncio.wait_for(background, 3)
        assert processes[0].returncode is not None
        assert clients[0].get_status()["exit_code"] == processes[0].returncode
        assert all(task.done() for task in (clients[0]._reader_task, clients[0]._stderr_task, clients[0]._wait_task))
        assert await asyncio.wait_for(classify("background", "replacement-background"), 3)
        assert supervisor.get_metrics()["live"]["restarts"] == 0
        assert supervisor.get_metrics()["background"]["restarts"] == 1
        assert not supervisor._cleanup_pending
    finally:
        if background is not None and not background.done():
            background.cancel()
            await asyncio.gather(background, return_exceptions=True)
        await supervisor.shutdown()
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.wait()
    assert all(process.returncode is not None for process in processes)


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["hang", "crash"])
async def test_failed_real_cpu_recovery_child_is_reaped_without_repeating_the_live_attempt(tmp_path, behavior):
    import json

    profile = {"model_id": "synthetic", "model_sha256": "abc", "labels_sha256": "def", "provider": "intel_gpu"}
    runtime = profile | {"active_provider": "cpu"}
    processes = []

    async def process_factory(**_kwargs):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            CHILD,
            "1",
            behavior,
            json.dumps(runtime),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        processes.append(process)
        return process

    client = ClassifierWorkerClient(
        worker_name="native-cpu",
        worker_generation=1,
        heartbeat_timeout_seconds=5,
        process_factory=process_factory,
        kill_timeout_seconds=1,
    )
    runner = NativeCpuRecovery(
        lambda: profile,
        NativeCrashQuarantine(lambda: profile, root=tmp_path),
        worker_factory=lambda: client,
    )
    try:
        for _ in range(2):
            with pytest.raises(NativeCpuRecoveryUnavailable):
                await runner.run(
                    priority="live",
                    timeout_seconds=0.2,
                    payload={"image_b64": "unused", "camera_name": None, "model_id": None},
                )
        assert len(processes) == 1
        assert processes[0].returncode is not None
        assert runner.snapshot()["live"]["status"] == "failed"
        assert runner._worker is None
        assert all(task.done() for task in (client._reader_task, client._stderr_task, client._wait_task))
    finally:
        await runner.shutdown()
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.wait()
