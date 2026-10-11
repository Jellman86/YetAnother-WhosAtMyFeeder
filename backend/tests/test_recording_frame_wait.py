"""A live detection waits for its recording frame when the owner chose to identify from it.

Frigate can serve a recording frame only once that stretch of recording is written, 10 to 15
seconds after the moment (measured at 11 to 13 seconds on a live install). A new event is
classified about a second after it starts, so reading at once fell back to the detect snapshot
every time and "Recording frame" never applied to a live detection.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.event_processor as module
from app.config import settings
from app.services.event_processor import EventProcessor

NOW = 1_700_000_001.0


@pytest.fixture(autouse=True)
def _clock_and_mode(monkeypatch):
    monkeypatch.setattr(settings.frigate, "classification_image_source", "recording_snapshot")
    with patch("app.services.event_processor.time.time", return_value=NOW):
        yield


def _payload(event_type: str, frame_time: float | None = NOW - 0.5, *, camera: str = "birdcam", event_id="evt"):
    after = {"id": event_id, "label": "bird", "camera": camera, "start_time": NOW - 1.0}
    if frame_time is not None:
        after["snapshot"] = {"frame_time": frame_time, "box": [320, 144, 448, 252]}
    return json.dumps({"type": event_type, "after": after}).encode()


def _processor():
    processor = EventProcessor(MagicMock())
    processor.detection_service.get_detection_by_frigate_event = AsyncMock(return_value=None)
    processor._classify_snapshot = AsyncMock(return_value=None)
    slept: list[float] = []
    gate = asyncio.Event()

    async def sleep(seconds):
        slept.append(seconds)
        await gate.wait()

    processor._sleep = sleep
    return processor, slept, gate


async def _settle(processor, event_id="evt"):
    wait = processor._recording_waits.get(event_id)
    if wait is not None:
        await wait["task"]


@pytest.mark.asyncio
async def test_a_new_event_is_identified_once_its_recording_frame_can_exist():
    processor, slept, gate = _processor()

    await processor.process_mqtt_message(_payload("new"))

    processor._classify_snapshot.assert_not_awaited()
    await asyncio.sleep(0)  # let the waiting task start
    assert slept == [pytest.approx(module.RECORDING_FRAME_READY_SECONDS - 0.5)]
    gate.set()
    await _settle(processor)

    processor._classify_snapshot.assert_awaited_once()
    deferred = processor._classify_snapshot.await_args.args[0]
    assert deferred.recording_wait_done is True
    assert "evt" not in processor._recording_waits


@pytest.mark.asyncio
async def test_updates_are_held_and_an_early_end_is_replayed_after_the_deferred_identification():
    processor, _slept, gate = _processor()

    await processor.process_mqtt_message(_payload("new"))
    await processor.process_mqtt_message(_payload("update"))
    await processor.process_mqtt_message(_payload("end"))
    processor._classify_snapshot.assert_not_awaited()

    gate.set()
    await _settle(processor)

    types = [call.args[0].type for call in processor._classify_snapshot.await_args_list]
    # The deferred identification, then the end replayed through the normal terminal path.
    assert types == ["new", "end"]
    assert processor._classify_snapshot.await_args_list[1].args[0].recording_wait_done is False


@pytest.mark.asyncio
async def test_the_detection_snapshot_setting_never_waits(monkeypatch):
    monkeypatch.setattr(settings.frigate, "classification_image_source", "frigate_snapshot")
    processor, slept, _gate = _processor()

    await processor.process_mqtt_message(_payload("new"))

    processor._classify_snapshot.assert_awaited_once()
    assert slept == []


@pytest.mark.asyncio
async def test_a_frame_old_enough_to_be_recorded_is_identified_at_once():
    processor, slept, _gate = _processor()

    await processor.process_mqtt_message(_payload("new", frame_time=NOW - module.RECORDING_FRAME_READY_SECONDS - 1))

    processor._classify_snapshot.assert_awaited_once()
    assert slept == []


@pytest.mark.asyncio
async def test_an_event_without_a_snapshot_time_is_identified_at_once():
    processor, slept, _gate = _processor()

    await processor.process_mqtt_message(_payload("new", frame_time=None))

    processor._classify_snapshot.assert_awaited_once()
    assert slept == []


@pytest.mark.asyncio
async def test_a_camera_whose_recordings_never_arrived_stops_waiting_for_a_while():
    processor, slept, _gate = _processor()
    processor._note_recording_frame_outcome("patiocam", "recording_not_ready")

    await processor.process_mqtt_message(_payload("new", camera="patiocam"))

    processor._classify_snapshot.assert_awaited_once()
    assert slept == []

    processor._note_recording_frame_outcome("patiocam", "recording_frame")
    processor._classify_snapshot.reset_mock()
    await processor.process_mqtt_message(_payload("new", camera="patiocam", event_id="evt-2"))
    processor._classify_snapshot.assert_not_awaited()
    processor._recording_waits["evt-2"]["task"].cancel()


@pytest.mark.asyncio
async def test_a_false_positive_during_the_wait_is_not_ingested_afterwards():
    processor, _slept, gate = _processor()
    processor._handle_false_positive = AsyncMock()

    await processor.process_mqtt_message(_payload("new"))
    false_positive = json.loads(_payload("update"))
    false_positive["after"]["false_positive"] = True
    await processor.process_mqtt_message(json.dumps(false_positive).encode())
    gate.set()
    await _settle(processor)

    processor._classify_snapshot.assert_not_awaited()


def test_the_wait_is_reported_in_health():
    processor, _slept, _gate = _processor()
    status = processor.get_status()
    assert status["recording_frame_waits"] == 0


def _image(size):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("arrives", [True, False])
async def test_the_deferred_identification_retries_until_the_recording_frame_arrives(monkeypatch, arrives):
    from app.services.event_processor import EventData
    from app.services.frigate_client import frigate_client

    detection, recording = _image((1280, 720)), _image((3840, 2160))
    not_yet = (None, "recording_snapshot_http_404")
    reads = AsyncMock(side_effect=[not_yet, not_yet, (recording, None)] if arrives else None, return_value=not_yet)
    monkeypatch.setattr(frigate_client, "get_snapshot_with_error", AsyncMock(return_value=(detection, None)))
    monkeypatch.setattr(frigate_client, "get_alignment_snapshot_with_error", AsyncMock(return_value=(detection, None)))
    monkeypatch.setattr(frigate_client, "get_recording_snapshot_with_error", reads)
    clock = {"now": NOW}

    async def sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr("app.services.recording_snapshot_input.time.time", lambda: clock["now"])
    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(return_value=[{"label": "Bird", "score": 0.9, "index": 1}])
    processor = EventProcessor(classifier)
    processor._sleep = sleep
    event = EventData(
        {
            "type": "new",
            "__recording_wait_done": True,
            "after": {
                "id": "evt-wait",
                "camera": "birdcam",
                "start_time": NOW - 13,
                "snapshot": {"frame_time": NOW - 12, "box": [320, 144, 448, 252]},
            },
        }
    )

    result = await processor._classify_snapshot(event)

    if arrives:
        assert result[1:] == (recording, "frigate_recording_snapshot")
        assert reads.await_count == 3
        assert "birdcam" not in processor._recording_unavailable_until
    else:
        # Past the deadline it identifies from the detection snapshot and stops waiting on this camera.
        assert result[1] == detection
        assert clock["now"] <= NOW - 12 + module.RECORDING_FRAME_DEADLINE_SECONDS + 5
        assert "birdcam" in processor._recording_unavailable_until


def test_a_slow_recording_read_does_not_stop_the_camera_waiting():
    # Slow means Frigate was busy, not that the camera keeps no recordings.
    processor, _slept, _gate = _processor()
    processor._note_recording_frame_outcome("birdcam", "recording_slow")
    assert "birdcam" not in processor._recording_unavailable_until
