"""Encoding an image for a classifier worker must not hold the event loop.

In subprocess mode every image goes to the worker as a lossless PNG. Recording-frame
identification and backfill send the whole native frame; on the test install a
2560x1440 frame took about 0.6 s to encode and a 4K frame about 1.4 s, all of it on
the event loop, so SSE, MQTT and the API stalled once per bird event and once per
backfilled event.
"""

from __future__ import annotations

import base64
import io
import threading

import pytest
from PIL import Image

from app.services.classifier_service import ClassifierService


class _RecordingSupervisor:
    def __init__(self) -> None:
        self.image_b64: str | None = None

    async def classify(self, **kwargs):
        self.image_b64 = kwargs["image_b64"]
        return [{"label": "Dunnock", "score": 0.9, "index": 0}]


@pytest.mark.asyncio
async def test_the_worker_image_is_encoded_off_the_event_loop():
    service = ClassifierService()
    supervisor = _RecordingSupervisor()
    service._classifier_supervisor = supervisor
    loop_thread = threading.current_thread()
    encoding_threads: list[threading.Thread] = []
    encode = service._encode_image_for_worker

    def recording_encode(image: Image.Image) -> str:
        encoding_threads.append(threading.current_thread())
        return encode(image)

    service._encode_image_for_worker = recording_encode
    frame = Image.new("RGB", (64, 36), (40, 120, 200))

    results = await service._run_supervised_inference("live", frame, "birdcam", None)

    assert results == [{"label": "Dunnock", "score": 0.9, "index": 0}]
    assert encoding_threads and all(thread is not loop_thread for thread in encoding_threads)
    with Image.open(io.BytesIO(base64.b64decode(supervisor.image_b64 or ""))) as sent:
        assert sent.size == frame.size
        assert sent.convert("RGB").tobytes() == frame.tobytes(), "the worker must get the frame losslessly"
