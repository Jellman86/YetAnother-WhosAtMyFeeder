import io
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.config import settings
from app.services.classification_input_provenance import (
    build_snapshot_classification_input_context,
    cached_snapshot_input_provenance,
    frigate_snapshot_input_provenance,
    ClassificationInputProvenance,
)


def image_bytes(size):
    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, format="JPEG")
    return buffer.getvalue()


def recording_client(**methods):
    return SimpleNamespace(
        **{
            "get_alignment_snapshot_with_error": AsyncMock(return_value=(image_bytes((1280, 720)), None)),
            **methods,
        }
    )


@pytest.fixture
def recording_mode(monkeypatch):
    monkeypatch.setattr(settings.frigate, "classification_image_source", "recording_snapshot")


@pytest.mark.asyncio
@pytest.mark.parametrize("mqtt", [False, True])
async def test_prefers_native_recording_at_snapshot_timestamp_with_scaled_matching_box(recording_mode, mqtt):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    snapshot = image_bytes((1280, 720))
    recording = image_bytes((3840, 2160))
    event = {
        "camera": "birdcam",
        "start_time": 100.0,
        "end_time": 110.0,
        "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]},
    }
    if mqtt:
        event["data"] = {"box": [800, 300, 900, 500]}
        event["snapshot"] = {"frame_time": 105.25, "box": [320, 144, 448, 252]}
    client = recording_client(get_recording_snapshot_with_error=AsyncMock(return_value=(recording, None)))
    data, provenance = await prefer_recording_snapshot(
        "evt",
        event,
        snapshot,
        frigate_snapshot_input_provenance(event),
        client=client,
    )
    assert data == recording
    assert provenance.input_source == "frigate_recording_snapshot"
    context = build_snapshot_classification_input_context(event_id="evt", event_data=event, provenance=provenance)
    assert context["frigate_box"] == pytest.approx([0.25, 0.2, 0.1, 0.15])
    assert context["restore_frigate_snapshot_crop"] is True
    assert context["is_cropped"] is False
    client.get_recording_snapshot_with_error.assert_awaited_once_with("birdcam", 105.25, timeout=5.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["no_timestamp", "invalid_timestamp", "wrong_box", "after_event", "no_camera"])
async def test_does_not_guess_recording_timestamp_or_box(recording_mode, change):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    event = {
        "camera": "birdcam",
        "start_time": 100.0,
        "end_time": 110.0,
        "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]},
    }
    if change == "no_timestamp":
        del event["data"]["snapshot_frame_time"]
    elif change == "invalid_timestamp":
        event["data"]["snapshot_frame_time"] = float("nan")
    elif change == "wrong_box":
        event["data"]["box"] = [0.9, 0.2, 0.2, 0.15]
    elif change == "after_event":
        event["data"]["snapshot_frame_time"] = 120.0
    else:
        event["camera"] = None
    original = image_bytes((1280, 720))
    provenance = frigate_snapshot_input_provenance(event)
    client = recording_client(get_recording_snapshot_with_error=AsyncMock())
    fallback = (
        provenance if change == "no_camera" else ClassificationInputProvenance("frigate_snapshot_unaligned", False)
    )
    assert await prefer_recording_snapshot("evt", event, original, provenance, client=client) == (original, fallback)
    client.get_recording_snapshot_with_error.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recording",
    [None, b"invalid", image_bytes((640, 360)), image_bytes((2000, 2000))],
    ids=["missing", "invalid", "smaller", "different-aspect"],
)
async def test_unavailable_invalid_smaller_or_different_aspect_recording_keeps_snapshot(recording_mode, recording):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    original = image_bytes((1280, 720))
    provenance = frigate_snapshot_input_provenance(event)
    client = recording_client(get_recording_snapshot_with_error=AsyncMock(return_value=(recording, "not_retained")))
    assert await prefer_recording_snapshot("evt", event, original, provenance, client=client) == (
        original,
        ClassificationInputProvenance("frigate_snapshot_unaligned", False),
    )


@pytest.mark.asyncio
async def test_snapshot_default_adds_no_recording_requests(monkeypatch):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    monkeypatch.setattr(settings.frigate, "classification_image_source", "frigate_snapshot")
    client = recording_client(get_recording_snapshot_with_error=AsyncMock())
    provenance = frigate_snapshot_input_provenance(None)
    assert await prefer_recording_snapshot("evt", {}, b"original", provenance, client=client) == (
        b"original",
        provenance,
    )
    client.get_recording_snapshot_with_error.assert_not_awaited()


def test_cached_recording_context_uses_its_own_alignment_not_latest_event_box():
    metadata = {
        "source": "frigate_recording_snapshot",
        "recording_alignment": {
            "frame_time": 105.25,
            "box": [0.25, 0.2, 0.1, 0.15],
            "image_sha256": hashlib.sha256(b"frame").hexdigest(),
        },
    }
    provenance = cached_snapshot_input_provenance(metadata, snapshot_data=b"frame")
    context = build_snapshot_classification_input_context(
        event_id="evt",
        event_data={"data": {"box": [0.8, 0.1, 0.1, 0.1]}},
        provenance=provenance,
    )
    assert context["frigate_box"] == [0.25, 0.2, 0.1, 0.15]
    assert context["restore_frigate_snapshot_crop"] is True


@pytest.mark.asyncio
async def test_recording_deadline_and_cancellation_do_not_wait_for_retention(recording_mode, monkeypatch):
    import asyncio
    import app.services.recording_snapshot_input as module

    monkeypatch.setattr(module, "RECORDING_SNAPSHOT_TIMEOUT_SECONDS", 0.01)

    async def slow(*args, **kwargs):
        await asyncio.sleep(1)

    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    original = image_bytes((1280, 720))
    provenance = frigate_snapshot_input_provenance(event)
    client = recording_client(get_recording_snapshot_with_error=slow)
    assert await module.prefer_recording_snapshot("evt", event, original, provenance, client=client) == (
        original,
        ClassificationInputProvenance("frigate_snapshot_unaligned", False),
    )
    task = asyncio.create_task(module.prefer_recording_snapshot("evt", event, original, provenance, client=client))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_live_ingest_classifies_recording_full_frame_with_matching_box(recording_mode, monkeypatch):
    from unittest.mock import MagicMock
    from app.services.event_processor import EventData, EventProcessor
    from app.services.frigate_client import frigate_client

    detection = image_bytes((1280, 720))
    recording = image_bytes((3840, 2160))
    event = EventData(
        {
            "type": "new",
            "after": {
                "id": "evt-record",
                "camera": "birdcam",
                "start_time": 100.0,
                "end_time": None,
                "snapshot": {"frame_time": 105.25, "box": [320, 144, 448, 252]},
                "box": [800, 300, 900, 500],
            },
        }
    )
    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(return_value=[{"label": "Bird", "score": 0.9, "index": 1}])
    monkeypatch.setattr(frigate_client, "get_snapshot_with_error", AsyncMock(return_value=(detection, None)))
    monkeypatch.setattr(frigate_client, "get_recording_snapshot_with_error", AsyncMock(return_value=(recording, None)))
    monkeypatch.setattr(frigate_client, "get_alignment_snapshot_with_error", AsyncMock(return_value=(detection, None)))
    result = await EventProcessor(classifier)._classify_snapshot(event)
    assert result[1:] == (recording, "frigate_recording_snapshot")
    assert classifier.classify_async_live.call_args.args[0].size == (3840, 2160)
    assert classifier.classify_async_live.call_args.kwargs["input_context"]["frigate_box"] == pytest.approx(
        [0.25, 0.2, 0.1, 0.15]
    )
    assert event.recording_alignment["frame_time"] == 105.25
    frigate_client.get_snapshot_with_error.assert_awaited_once_with("evt-record", crop=False, quality=95)


@pytest.mark.asyncio
async def test_backfill_classifies_and_retains_recording_alignment(recording_mode, monkeypatch):
    from unittest.mock import MagicMock
    from app.services import backfill_service as module

    detection = image_bytes((1280, 720))
    recording = image_bytes((3840, 2160))
    classifier = MagicMock()
    classifier.classify_async_background = AsyncMock(return_value=[{"label": "Bird", "score": 0.9, "index": 1}])
    service = module.BackfillService(classifier)
    service.detection_service.select_usable_classification = MagicMock(
        return_value=({"label": "Bird", "score": 0.9, "index": 1}, None)
    )
    service.detection_service.save_detection = AsyncMock(return_value=(True, True))
    monkeypatch.setattr(module.frigate_client, "get_snapshot", AsyncMock(return_value=detection))
    monkeypatch.setattr(
        module.frigate_client, "get_alignment_snapshot_with_error", AsyncMock(return_value=(detection, None))
    )
    monkeypatch.setattr(
        module.frigate_client, "get_recording_snapshot_with_error", AsyncMock(return_value=(recording, None))
    )
    monkeypatch.setattr(module.media_cache, "has_snapshot", lambda event_id: False)
    monkeypatch.setattr(module.media_cache, "cache_snapshot", AsyncMock(return_value=True))
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", False)
    event = {
        "id": "evt-record",
        "camera": "birdcam",
        "start_time": 100.0,
        "end_time": 110.0,
        "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]},
    }
    assert await service.process_historical_event(event) == ("new", None)
    assert classifier.classify_async_background.call_args.args[0].size == (3840, 2160)
    assert module.media_cache.cache_snapshot.call_args.kwargs["recording_alignment"]["frame_time"] == 105.25
    assert module.media_cache.cache_snapshot.call_args.kwargs["source"] == "frigate_recording_snapshot"


@pytest.mark.asyncio
async def test_oversized_recording_is_rejected_before_pixel_decode(recording_mode, monkeypatch):
    import app.services.recording_snapshot_input as module

    monkeypatch.setattr(module, "MAX_RECORDING_SNAPSHOT_PIXELS", 1280 * 720)
    original = image_bytes((1280, 720))
    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    client = recording_client(
        get_recording_snapshot_with_error=AsyncMock(return_value=(image_bytes((3840, 2160)), None))
    )
    provenance = frigate_snapshot_input_provenance(event)
    assert await module.prefer_recording_snapshot("evt", event, original, provenance, client=client) == (
        original,
        ClassificationInputProvenance("frigate_snapshot_unaligned", False),
    )


@pytest.mark.asyncio
async def test_reclassification_keeps_retained_owner_photo_without_recording_fetch(recording_mode):
    from app.services.classification_input_provenance import load_snapshot_classification_input

    cache = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=b"owner-photo"),
        get_snapshot_metadata=AsyncMock(return_value={"source": "hq_candidate_full_frame", "manual_selection": True}),
    )
    client = recording_client(get_snapshot=AsyncMock(), get_recording_snapshot_with_error=AsyncMock())
    image, provenance = await load_snapshot_classification_input(
        "evt", media_cache_service=cache, frigate_client_service=client
    )
    assert image == b"owner-photo"
    assert provenance.input_source == "hq_candidate_full_frame"
    client.get_snapshot.assert_not_awaited()
    client.get_recording_snapshot_with_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_recording_crop_scales_the_entire_snapshot_region_including_minimum_context(recording_mode):
    from app.services.recording_snapshot_input import prefer_recording_snapshot
    from app.services.classifier_service import ClassifierService
    from app.utils.frigate_coordinates import restore_frigate_hint_box

    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    detection = image_bytes((1280, 720))
    recording = image_bytes((3840, 2160))
    client = recording_client(get_recording_snapshot_with_error=AsyncMock(return_value=(recording, None)))
    _, provenance = await prefer_recording_snapshot(
        "evt", event, detection, frigate_snapshot_input_provenance(event), client=client
    )
    region = provenance.recording_crop_region
    original_box = ClassifierService._frigate_snapshot_crop_box((320, 144, 448, 252), (1280, 720))
    scaled = restore_frigate_hint_box(region, (3840, 2160))
    assert scaled == tuple(value * 3 for value in original_box)
    assert scaled[2] - scaled[0] == 900
    context = build_snapshot_classification_input_context(event_id="evt", event_data=event, provenance=provenance)
    assert context["frigate_snapshot_crop_region"] == list(region)
    restored = cached_snapshot_input_provenance(
        {"source": provenance.input_source, "recording_alignment": provenance.recording_alignment()},
        snapshot_data=recording,
    )
    assert restored == provenance


def test_recording_crop_provenance_does_not_claim_a_crop_model_generated_it():
    from app.services.classifier_service import ClassifierService, _normalize_classification_input_context

    service = object.__new__(ClassifierService)
    context = _normalize_classification_input_context(
        {"input_source": "frigate_recording_snapshot", "is_cropped": False}
    )
    assert service._resolved_classification_input_provenance(
        input_context=context, crop_diagnostics={"crop_applied": True, "crop_reason": "frigate_snapshot_scaled_crop"}
    ) == ("recording_snapshot_frigate_hint_crop", True)


@pytest.mark.asyncio
async def test_cached_recording_hint_is_withheld_when_image_and_metadata_do_not_match(recording_mode):
    from app.services.recording_snapshot_input import prefer_recording_snapshot
    from app.services.classification_input_provenance import load_snapshot_classification_input

    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    original = image_bytes((1280, 720))
    recording = image_bytes((3840, 2160))
    client = recording_client(
        get_recording_snapshot_with_error=AsyncMock(return_value=(recording, None)), get_snapshot=AsyncMock()
    )
    _, provenance = await prefer_recording_snapshot(
        "evt", event, original, frigate_snapshot_input_provenance(event), client=client
    )
    cache = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=image_bytes((3840, 2160)) + b"different"),
        get_snapshot_metadata=AsyncMock(
            return_value={"source": provenance.input_source, "recording_alignment": provenance.recording_alignment()}
        ),
    )
    _, cached_provenance = await load_snapshot_classification_input(
        "evt", event_data=event, media_cache_service=cache, frigate_client_service=client
    )
    context = build_snapshot_classification_input_context(
        event_id="evt", event_data=event, provenance=cached_provenance
    )
    assert "frigate_box" not in context
    assert "restore_frigate_snapshot_crop" not in context


@pytest.mark.asyncio
async def test_lossless_recording_input_is_retained_as_high_quality_jpeg(recording_mode):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    buffer = io.BytesIO()
    Image.new("RGB", (3840, 2160), (200, 40, 80)).save(buffer, format="PNG")
    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    original = image_bytes((1280, 720))
    client = recording_client(get_recording_snapshot_with_error=AsyncMock(return_value=(buffer.getvalue(), None)))
    retained, provenance = await prefer_recording_snapshot(
        "evt", event, original, frigate_snapshot_input_provenance(event), client=client
    )
    assert provenance.input_source == "frigate_recording_snapshot"
    with Image.open(io.BytesIO(retained)) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.size == (3840, 2160)
        assert max(abs(a - b) for a, b in zip(decoded.getpixel((200, 200)), (200, 40, 80))) < 3
        assert max(decoded.quantization[0]) < 20


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata_replaced", [False, True])
async def test_live_snapshot_fallback_preserves_cached_recording_alignment(
    recording_mode, monkeypatch, metadata_replaced
):
    from unittest.mock import MagicMock
    from app.services.event_processor import EventData, EventProcessor
    from app.services.frigate_client import frigate_client
    from app.services.media_cache import media_cache

    recording = image_bytes((3840, 2160))
    alignment = {
        "frame_time": 105.25,
        "box": [0.25, 0.2, 0.1, 0.15],
        "image_sha256": hashlib.sha256(recording).hexdigest(),
    }
    event = EventData(
        {
            "type": "end",
            "after": {
                "id": "evt-cached-record",
                "camera": "birdcam",
                "start_time": 100.0,
                "end_time": 110.0,
                "box": [900, 300, 1000, 500],
            },
        }
    )
    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(return_value=[{"label": "Bird", "score": 0.9, "index": 1}])
    monkeypatch.setattr(frigate_client, "get_snapshot_with_error", AsyncMock(return_value=(None, "missing")))
    monkeypatch.setattr(frigate_client, "get_thumbnail", AsyncMock(return_value=None))
    monkeypatch.setattr(media_cache, "get_snapshot", AsyncMock(return_value=recording))
    retained_metadata = {"source": "frigate_recording_snapshot", "recording_alignment": alignment}
    monkeypatch.setattr(
        media_cache,
        "get_snapshot_metadata",
        AsyncMock(
            side_effect=[retained_metadata, {"source": "frigate_snapshot"} if metadata_replaced else retained_metadata]
        ),
    )
    processor = EventProcessor(classifier)
    monkeypatch.setattr(processor, "_snapshot_unavailable_retry_budget", lambda event: 0)
    result = await processor._classify_snapshot(event)
    assert result[1:] == (recording, "frigate_recording_snapshot")
    context = classifier.classify_async_live.call_args.kwargs["input_context"]
    if metadata_replaced:
        assert "frigate_box" not in context
        assert event.recording_alignment is None
    else:
        assert context["frigate_box"] == alignment["box"]
        assert event.recording_alignment == alignment


@pytest.mark.asyncio
async def test_recording_uses_clean_detection_dimensions_not_saved_cropped_or_resized_jpeg(recording_mode):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    original = image_bytes((300, 300))
    clean = image_bytes((1280, 720))
    recording = image_bytes((3840, 2160))
    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    client = recording_client(
        get_alignment_snapshot_with_error=AsyncMock(return_value=(clean, None)),
        get_recording_snapshot_with_error=AsyncMock(return_value=(recording, None)),
    )
    data, provenance = await prefer_recording_snapshot(
        "evt", event, original, frigate_snapshot_input_provenance(event), client=client
    )
    assert data == recording
    assert provenance.input_source == "frigate_recording_snapshot"
    assert provenance.recording_crop_region == pytest.approx([234 / 1280, 48 / 720, 300 / 1280, 300 / 720])
    client.get_alignment_snapshot_with_error.assert_awaited_once_with("evt", timeout=5.0)


@pytest.mark.asyncio
async def test_recording_without_clean_detection_frame_keeps_original_without_guessing_dimensions(recording_mode):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    original = image_bytes((640, 360))
    event = {"camera": "birdcam", "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}}
    provenance = frigate_snapshot_input_provenance(event)
    client = recording_client(
        get_alignment_snapshot_with_error=AsyncMock(return_value=(None, "clean_copy_missing")),
        get_recording_snapshot_with_error=AsyncMock(return_value=(image_bytes((3840, 2160)), None)),
    )
    assert await prefer_recording_snapshot("evt", event, original, provenance, client=client) == (
        original,
        ClassificationInputProvenance("frigate_snapshot_unaligned", False),
    )
    client.get_recording_snapshot_with_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_clean_frame_never_applies_native_hints_to_an_unverified_saved_snapshot(recording_mode):
    from app.services.recording_snapshot_input import prefer_recording_snapshot

    original = image_bytes((300, 300))
    event = {
        "camera": "birdcam",
        "end_time": 110.0,
        "data": {"snapshot_frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]},
    }
    client = recording_client(
        get_alignment_snapshot_with_error=AsyncMock(return_value=(None, "missing")),
        get_recording_snapshot_with_error=AsyncMock(),
    )
    data, provenance = await prefer_recording_snapshot(
        "evt", event, original, frigate_snapshot_input_provenance(event), client=client
    )
    assert data == original
    context = build_snapshot_classification_input_context(event_id="evt", event_data=event, provenance=provenance)
    assert "frigate_box" not in context
    assert "restore_frigate_snapshot_crop" not in context
