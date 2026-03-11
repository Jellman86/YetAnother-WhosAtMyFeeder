import asyncio

import pytest

from app.services.classifier_worker_process import ClassifierWorkerProcess
from app.services.classifier_worker_protocol import (
    build_classify_request,
    decode_protocol_message,
)


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


async def _feed_lines(reader: asyncio.StreamReader, messages: list[dict]) -> None:
    for message in messages:
        reader.feed_data((await asyncio.to_thread(lambda: message)).__class__ and b"")


@pytest.mark.asyncio
async def test_classifier_worker_process_emits_ready_and_heartbeat():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()
    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=lambda **_: [],
        worker_generation=9,
        heartbeat_interval_seconds=0.01,
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0.03)
    reader.feed_eof()
    await task

    assert writer.messages[0]["type"] == "ready"
    assert writer.messages[0]["worker_generation"] == 9
    assert any(message["type"] == "heartbeat" for message in writer.messages[1:])


@pytest.mark.asyncio
async def test_classifier_worker_process_handles_classify_request():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()
    seen: list[tuple[str | None, str | None]] = []

    def _classify_fn(*, image_b64: str, camera_name: str | None, model_id: str | None):
        seen.append((camera_name, model_id))
        assert image_b64 == "payload"
        return [{"label": "Robin", "score": 0.92}]

    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=_classify_fn,
        worker_generation=10,
        heartbeat_interval_seconds=0.5,
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0)
    reader.feed_data(
        process.encode_message(
            build_classify_request(
                worker_generation=10,
                request_id="req-1",
                work_id="live-1",
                lease_token=4,
                image_b64="payload",
                camera_name="front",
                model_id="default",
            )
        )
    )
    await asyncio.sleep(0.05)
    reader.feed_eof()
    await task

    assert seen == [("front", "default")]
    assert any(
        message["type"] == "result" and message["results"][0]["label"] == "Robin"
        for message in writer.messages
    )


@pytest.mark.asyncio
async def test_classifier_worker_process_emits_structured_error():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()

    def _classify_fn(**_kwargs):
        raise RuntimeError("broken")

    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=_classify_fn,
        worker_generation=11,
        heartbeat_interval_seconds=0.5,
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0)
    reader.feed_data(
        process.encode_message(
            build_classify_request(
                worker_generation=11,
                request_id="req-2",
                work_id="live-2",
                lease_token=5,
                image_b64="payload",
                camera_name=None,
                model_id=None,
            )
        )
    )
    await asyncio.sleep(0.05)
    reader.feed_eof()
    await task

    assert any(
        message["type"] == "error" and message["error"] == "broken"
        for message in writer.messages
    )
