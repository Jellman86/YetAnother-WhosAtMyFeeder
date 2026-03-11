import asyncio

import pytest

from app.services.classifier_worker_client import ClassifierWorkerClient
from app.services.classifier_worker_protocol import (
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

    def finish(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout.feed_eof()
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
