import asyncio

import pytest

from app.services.classifier_worker_client import ClassifierWorkerClient
from app.services.classifier_worker_protocol import (
    build_classify_request,
    build_heartbeat_event,
    build_ready_event,
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
