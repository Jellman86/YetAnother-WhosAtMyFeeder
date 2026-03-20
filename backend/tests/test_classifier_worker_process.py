import asyncio

import pytest

from app.services.classifier_worker_process import ClassifierWorkerProcess
from app.services.classifier_worker_protocol import (
    build_classify_request,
    build_classify_video_request,
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


class _SlowProgressWriter(_MemoryWriter):
    def __init__(self) -> None:
        super().__init__()
        self._slow_next_progress = True

    async def drain(self) -> None:
        if self._slow_next_progress and self.messages and self.messages[-1].get("type") == "progress":
            self._slow_next_progress = False
            await asyncio.sleep(1.2)
            return None
        return None


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
async def test_classifier_worker_process_handles_classify_request_with_input_context_and_legacy_callback():
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
                input_context={"is_cropped": True},
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
async def test_classifier_worker_process_forwards_input_context_to_new_callback_signature():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()
    seen: list[dict | None] = []

    def _classify_fn(*, image_b64: str, camera_name: str | None, model_id: str | None, input_context=None):
        seen.append(input_context)
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
                input_context={"is_cropped": True},
            )
        )
    )
    await asyncio.sleep(0.05)
    reader.feed_eof()
    await task

    assert seen[0]["is_cropped"] is True
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


@pytest.mark.asyncio
async def test_classifier_worker_process_emits_runtime_recovery_event():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()
    runtime_recovery = {"value": None}

    def _classify_fn(**_kwargs):
        runtime_recovery["value"] = {
            "status": "recovered",
            "failed_backend": "openvino",
            "failed_provider": "GPU",
            "recovered_backend": "openvino",
            "recovered_provider": "intel_cpu",
            "detail": "invalid probabilities",
            "at": 123.0,
            "diagnostics": {
                "output_summary": {
                    "nan_count": 10000,
                    "finite_count": 0,
                },
                "compile_properties": {
                    "INFERENCE_PRECISION_HINT": "f32",
                },
            },
        }
        return [{"label": "Robin", "score": 0.9}]

    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=_classify_fn,
        worker_generation=12,
        heartbeat_interval_seconds=0.5,
        runtime_recovery_getter=lambda: runtime_recovery["value"],
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0)
    reader.feed_data(
        process.encode_message(
            build_classify_request(
                worker_generation=12,
                request_id="req-3",
                work_id="live-3",
                lease_token=6,
                image_b64="payload",
                camera_name="front",
                model_id="default",
            )
        )
    )
    await asyncio.sleep(0.05)
    reader.feed_eof()
    await task

    assert any(
        message["type"] == "runtime_recovery"
        and message["recovery"]["failed_provider"] == "GPU"
        and message["recovery"]["diagnostics"]["output_summary"]["nan_count"] == 10000
        for message in writer.messages
    )


@pytest.mark.asyncio
async def test_classifier_worker_process_handles_video_request_and_progress():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()
    seen_contexts = []

    def _classify_video_fn(
        *,
        video_path: str,
        stride: int,
        max_frames: int | None,
        progress_callback,
        input_context=None,
    ):
        assert video_path == "/tmp/demo.mp4"
        seen_contexts.append(input_context)
        progress_callback(1, 3, 0.7, "Robin", None, 0, 3, "bird")
        return [{"label": "Robin", "score": 0.91, "index": 0}]

    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=lambda **_: [],
        classify_video_fn=_classify_video_fn,
        worker_generation=13,
        heartbeat_interval_seconds=0.5,
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0)
    reader.feed_data(
        process.encode_message(
            build_classify_video_request(
                worker_generation=13,
                request_id="req-video",
                work_id="video-1",
                lease_token=7,
                video_path="/tmp/demo.mp4",
                stride=5,
                max_frames=3,
                input_context={"is_cropped": False, "event_id": "evt-video"},
            )
        )
    )
    await asyncio.sleep(0.05)
    reader.feed_eof()
    await task

    assert any(message["type"] == "progress" and message["top_label"] == "Robin" for message in writer.messages)
    assert any(message["type"] == "result" and message["results"][0]["label"] == "Robin" for message in writer.messages)
    assert seen_contexts[0]["event_id"] == "evt-video"


@pytest.mark.asyncio
async def test_classifier_worker_process_accepts_keyword_progress_callback_arguments():
    reader = asyncio.StreamReader()
    writer = _MemoryWriter()

    def _classify_video_fn(*, video_path: str, stride: int, max_frames: int | None, progress_callback):
        assert video_path == "/tmp/demo.mp4"
        progress_callback(
            current_frame=1,
            total_frames=3,
            frame_score=0.7,
            top_label="Robin",
            frame_thumb=None,
            frame_index=0,
            clip_total=3,
            model_name="bird",
        )
        return [{"label": "Robin", "score": 0.91, "index": 0}]

    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=lambda **_: [],
        classify_video_fn=_classify_video_fn,
        worker_generation=15,
        heartbeat_interval_seconds=0.5,
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0)
    reader.feed_data(
        process.encode_message(
            build_classify_video_request(
                worker_generation=15,
                request_id="req-video-keyword-progress",
                work_id="video-3",
                lease_token=9,
                video_path="/tmp/demo.mp4",
                stride=5,
                max_frames=3,
            )
        )
    )
    await asyncio.sleep(0.05)
    reader.feed_eof()
    await task

    assert any(message["type"] == "progress" and message["top_label"] == "Robin" for message in writer.messages)
    assert any(message["type"] == "result" and message["results"][0]["label"] == "Robin" for message in writer.messages)
    assert not any(message["type"] == "error" for message in writer.messages)


@pytest.mark.asyncio
async def test_classifier_worker_process_does_not_fail_video_classification_when_progress_emit_is_slow():
    reader = asyncio.StreamReader()
    writer = _SlowProgressWriter()

    def _classify_video_fn(*, video_path: str, stride: int, max_frames: int | None, progress_callback):
        assert video_path == "/tmp/demo.mp4"
        progress_callback(1, 3, 0.7, "Robin", None, 0, 3, "bird")
        return [{"label": "Robin", "score": 0.91, "index": 0}]

    process = ClassifierWorkerProcess(
        reader=reader,
        writer=writer,
        classify_fn=lambda **_: [],
        classify_video_fn=_classify_video_fn,
        worker_generation=14,
        heartbeat_interval_seconds=0.5,
    )

    task = asyncio.create_task(process.run())
    await asyncio.sleep(0)
    reader.feed_data(
        process.encode_message(
            build_classify_video_request(
                worker_generation=14,
                request_id="req-video-slow-progress",
                work_id="video-2",
                lease_token=8,
                video_path="/tmp/demo.mp4",
                stride=5,
                max_frames=3,
            )
        )
    )
    await asyncio.sleep(1.4)
    reader.feed_eof()
    await task

    assert any(message["type"] == "progress" for message in writer.messages)
    assert any(message["type"] == "result" and message["results"][0]["label"] == "Robin" for message in writer.messages)
    assert not any(message["type"] == "error" for message in writer.messages)
