import asyncio
import os
import sys

import pytest

from app.services.classifier_worker_client import ClassifierWorkerClient
from app.services.classifier_worker_protocol import (
    build_classify_request,
    build_heartbeat_event,
    build_progress_event,
    build_ready_event,
    build_runtime_recovery_event,
    encode_protocol_message,
)


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stdin = _FakeStdin()
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self._wait_event = asyncio.Event()

    async def wait(self) -> int:
        await self._wait_event.wait()
        return int(self.returncode or 0)

    def feed(self, message: dict) -> None:
        self.stdout.feed_data(encode_protocol_message(message))

    def feed_stderr(self, data: bytes) -> None:
        self.stderr.feed_data(data)

    def finish(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._wait_event.set()

    def terminate(self) -> None:
        self.terminated = True
        self.finish(-15)

    def kill(self) -> None:
        self.killed = True
        self.finish(-9)


async def _client_for_process(process: _FakeProcess, **kwargs) -> ClassifierWorkerClient:
    async def factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="reaping-test",
        worker_generation=1,
        heartbeat_timeout_seconds=5,
        process_factory=factory,
        **kwargs,
    )
    await client.start()
    return client


@pytest.mark.asyncio
async def test_pipe_eof_does_not_report_process_exit():
    process = _FakeProcess()
    client = await _client_for_process(process)
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    waiter = asyncio.create_task(client.wait_closed())
    try:
        await asyncio.wait_for(client._reader_task, 1)
        await asyncio.wait_for(client._stderr_task, 1)
        await asyncio.sleep(0)
        assert not waiter.done()
        assert client.get_status()["exit_code"] is None
    finally:
        process.finish(7)
        await asyncio.wait_for(waiter, 1)
    assert client.get_status()["exit_code"] == 7


@pytest.mark.asyncio
async def test_stderr_eof_does_not_fail_a_live_worker_handshake():
    process = _FakeProcess()
    client = await _client_for_process(process)
    try:
        process.stderr.feed_eof()
        await asyncio.wait_for(client._stderr_task, 1)
        process.feed(build_ready_event(worker_generation=1))
        await client.wait_until_ready(1)
    finally:
        process.finish()
        await client.wait_closed()


@pytest.mark.asyncio
async def test_cancelled_exit_wait_does_not_cancel_process_reaping():
    process = _FakeProcess()
    client = await _client_for_process(process)
    waiter = asyncio.create_task(client.wait_closed())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    process.finish(12)
    await asyncio.wait_for(client.wait_closed(), 1)
    assert client.get_status()["exit_code"] == 12


@pytest.mark.asyncio
async def test_terminate_escalates_when_the_child_ignores_term():
    process = _FakeProcess()
    process.terminate = lambda: setattr(process, "terminated", True)
    client = await _client_for_process(process, terminate_timeout_seconds=0.01)
    try:
        await asyncio.wait_for(client.terminate(), 1)
        assert process.terminated and process.killed
        assert client.get_status()["exit_code"] == -9
    finally:
        process.finish()
        await client.wait_closed()


@pytest.mark.asyncio
async def test_cancelling_termination_still_reaps_the_child():
    process = _FakeProcess()
    term_sent = asyncio.Event()
    process.terminate = term_sent.set
    client = await _client_for_process(process, terminate_timeout_seconds=0.01)
    stopping = asyncio.create_task(client.terminate())
    try:
        await asyncio.wait_for(term_sent.wait(), 1)
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(stopping, 1)
        assert process.returncode == -9
        assert client.get_status()["exit_code"] == -9
    finally:
        process.finish()
        await client.wait_closed()


@pytest.mark.asyncio
async def test_stop_is_idempotent_after_a_natural_exit():
    process = _FakeProcess()
    client = await _client_for_process(process)
    process.finish(3)
    await client.wait_closed()

    def already_gone():
        raise ProcessLookupError()

    process.terminate = already_gone
    process.kill = already_gone
    await client.terminate()
    await client.kill()
    assert client.get_status()["exit_code"] == 3


@pytest.mark.asyncio
async def test_a_failed_kill_is_bounded_and_never_claims_exit():
    process = _FakeProcess()
    process.kill = lambda: None
    client = await _client_for_process(process, kill_timeout_seconds=0.01)
    try:
        with pytest.raises(TimeoutError):
            await client.kill()
        assert client.get_status()["exit_code"] is None
        assert not client._wait_task.done()
    finally:
        process.finish()
        await client.wait_closed()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="SIGTERM handler requires POSIX")
async def test_real_child_with_closed_pipes_and_ignored_term_is_reaped():
    children = []

    async def factory(**_kwargs):
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);os.close(1);os.close(2);time.sleep(30)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        children.append(child)
        return child

    client = ClassifierWorkerClient(
        worker_name="real-reaping",
        worker_generation=1,
        heartbeat_timeout_seconds=5,
        process_factory=factory,
        terminate_timeout_seconds=0.02,
    )
    try:
        await client.start()
        await asyncio.wait_for(client._reader_task, 5)
        assert children[0].returncode is None
        await asyncio.wait_for(client.terminate(), 5)
        assert children[0].returncode == -9
        assert client.get_status()["exit_code"] == -9
        assert all(task.done() for task in (client._reader_task, client._stderr_task, client._wait_task))
        await client.terminate()
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
            await child.wait()


@pytest.mark.asyncio
async def test_classifier_worker_client_waits_for_ready_handshake():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-1",
        worker_generation=1,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=1))

    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    assert client.get_status()["ready"] is True
    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_ignores_non_protocol_stdout_before_ready():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-noise",
        worker_generation=9,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.stdout.feed_data(b"2026-03-12 08:25:46 [info] worker bootstrap log line\n")
    process.feed(build_ready_event(worker_generation=9))

    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    status = client.get_status()
    assert status["ready"] is True
    assert "bootstrap log line" in status["recent_stderr_excerpt"]

    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_tracks_heartbeat_state():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-2",
        worker_generation=2,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=2))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)
    process.feed(build_heartbeat_event(worker_generation=2, request_id="req-1", busy=True))
    await asyncio.sleep(0.01)

    status = client.get_status()
    assert status["current_request_id"] == "req-1"
    assert status["busy"] is True
    assert status["last_heartbeat_monotonic"] is not None

    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_treats_progress_as_worker_liveness():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="video-progress",
        worker_generation=12,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=12))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)
    ready_activity = client.get_status()["last_activity_monotonic"]

    await asyncio.sleep(0.01)
    process.feed(
        build_progress_event(
            worker_generation=12,
            request_id="req-progress",
            work_id="video-progress-1",
            lease_token=3,
            current_frame=19,
            total_frames=20,
            frame_score=0.91,
            top_label="Blue Tit",
        )
    )
    await asyncio.wait_for(client.next_event(), timeout=0.2)

    assert client.get_status()["last_activity_monotonic"] > ready_activity
    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_records_non_zero_exit():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-3",
        worker_generation=3,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=3))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)
    process.finish(returncode=9)
    await client.wait_closed()

    assert client.get_status()["exit_code"] == 9


@pytest.mark.asyncio
async def test_classifier_worker_client_queues_runtime_recovery_events():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-recovery",
        worker_generation=11,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=11))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)
    process.feed(
        build_runtime_recovery_event(
            worker_generation=11,
            request_id="req-recovery",
            work_id="live-recovery-1",
            lease_token=4,
            recovery={
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "GPU",
                "recovered_backend": "openvino",
                "recovered_provider": "intel_cpu",
                "detail": "invalid probabilities",
                "at": 123.0,
            },
        )
    )

    event = await asyncio.wait_for(client.next_event(), timeout=0.2)
    assert event["type"] == "runtime_recovery"
    assert event["recovery"]["failed_provider"] == "GPU"

    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_drains_stderr_and_keeps_bounded_excerpt():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-err",
        worker_generation=6,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
        stderr_tail_max_bytes=16,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=6))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    process.feed_stderr(b"0123456789abcdefMORE\n")
    await asyncio.sleep(0.01)

    status = client.get_status()
    assert status["recent_stderr_excerpt"].endswith("abcdefMORE\n")
    assert status["stderr_truncated_bytes"] > 0

    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_ready_failure_includes_stderr_context():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-fail",
        worker_generation=8,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed_stderr(b"startup exploded\n")
    process.finish(returncode=17)

    with pytest.raises(RuntimeError, match="startup exploded"):
        await client.wait_until_ready(timeout_seconds=0.2)


@pytest.mark.asyncio
async def test_classifier_worker_client_terminate_and_kill_delegate_to_process():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-4",
        worker_generation=4,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=4))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    await client.terminate()
    assert process.terminated is True

    process = _FakeProcess()

    async def _factory2(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-5",
        worker_generation=5,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory2,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=5))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    await client.kill()
    assert process.killed is True


@pytest.mark.asyncio
async def test_classifier_worker_client_spawns_real_worker_process(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("YA_WAMF_CLASSIFIER_WORKER_TEST_MODE", "1")

    client = ClassifierWorkerClient(
        worker_name="live-real",
        worker_generation=7,
        heartbeat_timeout_seconds=5.0,
    )
    await client.start()
    await asyncio.wait_for(client.wait_until_ready(), timeout=5.0)
    await client.send(
        build_classify_request(
            worker_generation=7,
            request_id="req-real",
            work_id="live-real-1",
            lease_token=1,
            image_b64="payload",
            camera_name="front",
            model_id="default",
        )
    )

    event = await asyncio.wait_for(client.next_event(), timeout=5.0)

    assert event["type"] == "result"
    assert event["results"][0]["label"] == "WorkerTest"

    await client.terminate()


@pytest.mark.asyncio
async def test_classifier_worker_client_real_worker_accepts_large_classify_request(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("YA_WAMF_CLASSIFIER_WORKER_TEST_MODE", "1")

    client = ClassifierWorkerClient(
        worker_name="background-real",
        worker_generation=10,
        heartbeat_timeout_seconds=5.0,
    )
    await client.start()
    await asyncio.wait_for(client.wait_until_ready(), timeout=5.0)
    await client.send(
        build_classify_request(
            worker_generation=10,
            request_id="req-large",
            work_id="background-real-1",
            lease_token=2,
            image_b64="x" * 200_000,
            camera_name="feeder",
            model_id="default",
        )
    )

    event = await asyncio.wait_for(client.next_event(), timeout=5.0)

    assert event["type"] == "result"
    assert event["results"][0]["label"] == "WorkerTest"

    await client.terminate()


@pytest.mark.asyncio
async def test_classifier_worker_client_records_the_runtime_from_the_ready_message():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-0",
        worker_generation=1,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    runtime = {"inference_backend": "openvino", "active_provider": "intel_npu", "model_id": "rope_vit_b14_inat21"}
    process.feed(build_ready_event(worker_generation=1, runtime=runtime))

    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    assert client.get_status()["runtime"] == runtime
    process.finish()
    await client.wait_closed()


@pytest.mark.asyncio
async def test_classifier_worker_client_reports_no_runtime_for_a_bare_ready_message():
    process = _FakeProcess()

    async def _factory(**_kwargs):
        return process

    client = ClassifierWorkerClient(
        worker_name="live-0",
        worker_generation=1,
        heartbeat_timeout_seconds=5.0,
        process_factory=_factory,
    )
    await client.start()
    process.feed(build_ready_event(worker_generation=1))
    await asyncio.wait_for(client.wait_until_ready(), timeout=0.2)

    assert client.get_status()["runtime"] is None
    process.finish()
    await client.wait_closed()
