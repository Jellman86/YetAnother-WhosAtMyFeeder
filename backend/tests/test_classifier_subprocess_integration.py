"""Real pipes, processes and supervisor recovery; inference alone is synthetic."""

import asyncio
import sys

import pytest

from app.services.classifier_supervisor import (
    ClassifierSupervisor,
    ClassifierWorkerDeadlineExceededError,
    ClassifierWorkerExitedError,
)
from app.services.classifier_worker_client import ClassifierWorkerClient


async def classify(supervisor, priority, token):
    return await supervisor.classify(
        priority=priority,
        work_id=f"integration-{token}",
        lease_token=token,
        image_b64="test-mode-image",
        camera_name=None,
        model_id=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_lane", ["live", "background"])
async def test_real_worker_exit_recovers_without_restarting_other_lane(monkeypatch, failed_lane):
    monkeypatch.setenv("YA_WAMF_CLASSIFIER_WORKER_TEST_MODE", "1")
    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=10,
        hard_deadline_seconds=15,
        worker_ready_timeout_seconds=10,
    )
    other_lane = "background" if failed_lane == "live" else "live"
    processes = []
    try:
        await asyncio.wait_for(
            asyncio.gather(classify(supervisor, "live", 1), classify(supervisor, "background", 2)), 30
        )
        slot = supervisor._slots[failed_lane][0]
        other = supervisor._slots[other_lane][0].worker._process
        old = slot.worker._process
        processes.extend([old, other])
        generation = slot.worker_generation
        old.kill()
        await asyncio.wait_for(old.wait(), 5)

        async def replaced():
            while True:
                current = supervisor._slots[failed_lane][0]
                if current.worker_generation > generation and current.worker.get_status()["ready"]:
                    return current.worker._process
                await asyncio.sleep(0.01)

        processes.append(await asyncio.wait_for(replaced(), 20))
        results = await asyncio.wait_for(
            asyncio.gather(*(classify(supervisor, lane, i + 10) for i, lane in enumerate(["live", "background"] * 8))),
            20,
        )
        assert all(rows == [{"label": "WorkerTest", "score": 0.99}] for rows in results)
        assert supervisor._slots[other_lane][0].worker._process is other
        assert not supervisor._assignments
        assert not supervisor._pending_requests
    finally:
        await supervisor.shutdown()
    assert all(process.returncode is not None for process in processes)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exit", "deadline"])
async def test_real_inflight_failure_is_bounded_and_next_request_recovers(failure):
    processes = []

    async def spawn(**kwargs):
        # Only the inference function is replaced; framing, pipes, heartbeat,
        # task ownership, process termination and replacement are production code.
        program = """
import asyncio, sys
from app.services.classifier_worker_process import run_worker_main
async def inference(**kwargs):
    if kwargs['image_b64'] == 'stall':
        await asyncio.Event().wait()
    return [{'label': 'Recovered', 'score': 0.9}]
asyncio.run(run_worker_main(classify_fn=inference, worker_generation=int(sys.argv[1]), heartbeat_interval_seconds=0.02))
"""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            program,
            str(kwargs["worker_generation"]),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        processes.append(process)
        return process

    async def factory(**kwargs):
        return ClassifierWorkerClient(
            worker_name=kwargs["worker_name"],
            worker_generation=kwargs["worker_generation"],
            heartbeat_timeout_seconds=5,
            process_factory=spawn,
        )

    supervisor = ClassifierSupervisor(
        live_worker_count=1,
        background_worker_count=1,
        heartbeat_timeout_seconds=5,
        hard_deadline_seconds=1,
        worker_ready_timeout_seconds=10,
        worker_factory=factory,
    )
    request = None
    try:
        await supervisor.start("background")
        request = asyncio.create_task(
            supervisor.classify(
                priority="background",
                work_id="blocked",
                lease_token=1,
                image_b64="stall",
                camera_name=None,
                model_id=None,
            )
        )

        async def busy():
            while not supervisor._slots["background"][0].worker.get_status()["busy"]:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(busy(), 5)
        if failure == "exit":
            processes[0].kill()
        expected = ClassifierWorkerExitedError if failure == "exit" else ClassifierWorkerDeadlineExceededError
        with pytest.raises(expected):
            await asyncio.wait_for(request, 10)
        assert await asyncio.wait_for(classify(supervisor, "background", 2), 15) == [
            {"label": "Recovered", "score": 0.9}
        ]
        assert len(processes) == 2
        assert not supervisor._assignments
    finally:
        if request is not None:
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        await supervisor.shutdown()
    assert all(process.returncode is not None for process in processes)
