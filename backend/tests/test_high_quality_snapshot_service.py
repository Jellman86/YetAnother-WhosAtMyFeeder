import asyncio
import sys
from types import SimpleNamespace
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import pytest_asyncio
from PIL import Image

from app.config import settings
from app.services import high_quality_snapshot_service as hq_module
from app.services import media_cache as media_cache_module


def _jpeg_bytes(color: str, size: tuple[int, int] = (32, 32), *, quality: int = 92) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _make_cache_service(tmp_path, monkeypatch):
    cache_base = tmp_path / "media_cache"
    snapshots = cache_base / "snapshots"
    clips = cache_base / "clips"
    previews = cache_base / "previews"
    snapshots.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(media_cache_module, "CACHE_BASE_DIR", cache_base)
    monkeypatch.setattr(media_cache_module, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(media_cache_module, "CLIPS_DIR", clips)
    monkeypatch.setattr(media_cache_module, "PREVIEWS_DIR", previews)
    service = media_cache_module.MediaCacheService()
    monkeypatch.setattr(hq_module, "media_cache", service)
    return service


def test_extract_crop_event_hints_keeps_only_valid_box_and_region():
    service = hq_module.HighQualitySnapshotService()

    hints = service._extract_crop_event_hints(
        {
            "id": "evt",
            "data": {
                "box": (0.1, 0.2, 0.3, 0.4),
                "region": ["10", "20", "30", "40"],
                "path_data": [[[0.5, 0.6], 100.1]],
                "score": 0.99,
            },
            "start_time": 100.0,
            "end_time": 101.0,
            "large_irrelevant_payload": "ignored",
        }
    )

    assert hints == {
        "start_time": 100.0,
        "end_time": 101.0,
        "data": {
            "box": [0.1, 0.2, 0.3, 0.4],
            "region": ["10", "20", "30", "40"],
            "path_data": [[[0.5, 0.6], 100.1]],
        }
    }
    assert service._extract_crop_event_hints({"data": {"box": [1, 2, 3]}}) is None
    assert service._extract_crop_event_hints({"data": "bad"}) is None
    assert service._extract_crop_event_hints(None) is None


def test_expand_hint_box_keeps_more_context_around_frigate_box():
    service = hq_module.HighQualitySnapshotService()

    expanded = service._expand_hint_box((50, 50, 150, 150), (300, 300))

    assert expanded == (14, 14, 186, 186)


def test_extract_snapshot_from_clip_path_prefers_frame_with_model_confirmed_crop(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: True)
    monkeypatch.setattr(service, "_candidate_frame_indices", lambda **_kwargs: [0, 1])

    red_frame = np.zeros((40, 40, 3), dtype=np.uint8)
    red_frame[:, :] = (0, 0, 255)
    green_frame = np.zeros((40, 40, 3), dtype=np.uint8)
    green_frame[:, :] = (0, 255, 0)

    class FakeCapture:
        def __init__(self):
            self.index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == hq_module.cv2.CAP_PROP_FRAME_COUNT:
                return 2
            if prop == hq_module.cv2.CAP_PROP_FPS:
                return 1
            return 0

        def set(self, _prop, value):
            self.index = int(value)

        def read(self):
            return True, [red_frame, green_frame][self.index]

        def release(self):
            pass

    fake_crop_service = MagicMock()

    def generate_crop(image):
        r, g, _b = image.getpixel((0, 0))
        if g > r:
            return {
                "crop_image": image.crop((4, 4, 28, 28)),
                "box": (4, 4, 28, 28),
                "confidence": 0.91,
                "reason": "selected",
            }
        return {"crop_image": None, "reason": "no_candidate", "confidence": None}

    fake_crop_service.generate_crop.side_effect = generate_crop
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)
    monkeypatch.setattr(hq_module.cv2, "VideoCapture", lambda _path: FakeCapture())

    result = service._extract_snapshot_from_clip_path(Path("/tmp/demo.mp4"))

    with Image.open(BytesIO(result)) as img:
        r, g, _b = img.convert("RGB").getpixel((0, 0))
    assert g > r
    assert fake_crop_service.generate_crop.call_count == 2


def test_extract_snapshot_from_clip_path_skips_crop_scoring_when_model_missing(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: True)
    monkeypatch.setattr(service, "_candidate_frame_indices", lambda **_kwargs: [0, 1])

    red_frame = np.zeros((40, 40, 3), dtype=np.uint8)
    red_frame[:, :] = (0, 0, 255)
    green_frame = np.zeros((40, 40, 3), dtype=np.uint8)
    green_frame[:, :] = (0, 255, 0)

    class FakeCapture:
        def __init__(self):
            self.index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == hq_module.cv2.CAP_PROP_FRAME_COUNT:
                return 2
            if prop == hq_module.cv2.CAP_PROP_FPS:
                return 1
            return 0

        def set(self, _prop, value):
            self.index = int(value)

        def read(self):
            return True, [red_frame, green_frame][self.index]

        def release(self):
            pass

    fake_crop_service = MagicMock()
    fake_crop_service.get_status.return_value = {"installed": False}
    fake_crop_service.generate_crop.side_effect = AssertionError("crop model should not be called")
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)
    monkeypatch.setattr(hq_module.cv2, "VideoCapture", lambda _path: FakeCapture())

    result = service._extract_snapshot_from_clip_path(Path("/tmp/demo.mp4"))

    with Image.open(BytesIO(result)) as img:
        r, g, _b = img.convert("RGB").getpixel((0, 0))
    assert r > g
    fake_crop_service.generate_crop.assert_not_called()


def test_extract_snapshot_from_clip_path_skips_crop_scoring_under_pressure(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: False)
    monkeypatch.setattr(service, "_candidate_frame_indices", lambda **_kwargs: [0, 1])

    red_frame = np.zeros((40, 40, 3), dtype=np.uint8)
    red_frame[:, :] = (0, 0, 255)
    green_frame = np.zeros((40, 40, 3), dtype=np.uint8)
    green_frame[:, :] = (0, 255, 0)

    class FakeCapture:
        def __init__(self):
            self.index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == hq_module.cv2.CAP_PROP_FRAME_COUNT:
                return 2
            if prop == hq_module.cv2.CAP_PROP_FPS:
                return 1
            return 0

        def set(self, _prop, value):
            self.index = int(value)

        def read(self):
            return True, [red_frame, green_frame][self.index]

        def release(self):
            pass

    fake_crop_service = MagicMock()
    fake_crop_service.get_status.return_value = {"installed": True, "enabled_for_runtime": True}
    fake_crop_service.generate_crop.side_effect = AssertionError("crop model should not run under pressure")
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)
    monkeypatch.setattr(hq_module.cv2, "VideoCapture", lambda _path: FakeCapture())

    result = service._extract_snapshot_from_clip_path(Path("/tmp/demo.mp4"))

    with Image.open(BytesIO(result)) as img:
        r, g, _b = img.convert("RGB").getpixel((0, 0))
    assert r > g
    fake_crop_service.generate_crop.assert_not_called()


def test_candidate_frame_indices_prefers_event_path_timing():
    service = hq_module.HighQualitySnapshotService()

    indices = service._candidate_frame_indices(
        frame_count=90,
        fps=30.0,
        event_data={
            "start_time": 100.0,
            "end_time": 103.0,
            "data": {
                "path_data": [
                    [[0.5, 0.8], 100.1],
                    [[0.6, 0.8], 100.4],
                    [[0.7, 0.8], 100.8],
                ]
            },
        },
    )

    assert indices[:3] == [12, 11, 13]
    assert 45 in indices
    assert 0 in indices


def test_candidate_frame_indices_prefers_path_point_nearest_box_center():
    service = hq_module.HighQualitySnapshotService()

    indices = service._candidate_frame_indices(
        frame_count=90,
        fps=30.0,
        event_data={
            "start_time": 100.0,
            "data": {
                "box": [0.75, 0.70, 0.10, 0.10],
                "path_data": [
                    [[0.2, 0.2], 100.1],
                    [[0.4, 0.4], 100.4],
                    [[0.8, 0.75], 100.8],
                ],
            },
        },
    )

    assert indices[:3] == [24, 23, 25]


def test_maybe_crop_snapshot_bytes_prefers_model_crop_over_event_hint(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: True)

    source = Image.new("RGB", (100, 80), color="blue")
    source.paste(Image.new("RGB", (20, 20), color="green"), (65, 30))
    buffer = BytesIO()
    source.save(buffer, format="JPEG", quality=95)

    fake_crop_service = MagicMock()
    fake_crop_service.min_crop_size = 1
    fake_crop_service.get_status.return_value = {"installed": True, "enabled_for_runtime": True}
    fake_crop_service.generate_crop.return_value = {
        "crop_image": source.crop((65, 30, 85, 50)),
        "box": (65, 30, 85, 50),
        "confidence": 0.88,
        "reason": "selected",
    }
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    cropped_bytes, crop_applied = service._maybe_crop_snapshot_bytes(
        "evt_model_crop",
        buffer.getvalue(),
        {"data": {"box": [5, 5, 20, 20]}},
    )

    assert crop_applied is True
    fake_crop_service.generate_crop.assert_called_once()
    with Image.open(BytesIO(cropped_bytes)) as img:
        assert img.size[0] > 20
        r, g, _b = img.convert("RGB").getpixel((img.size[0] // 2, img.size[1] // 2))
    assert g > r


def test_maybe_crop_snapshot_bytes_falls_back_to_hint_when_model_finds_no_crop(monkeypatch):
    """When the model is installed but returns no_candidate, hints should be used as fallback."""
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: True)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.get_status.return_value = {"installed": True, "enabled_for_runtime": True}
    fake_crop_service.generate_crop.return_value = {"crop_image": None, "reason": "no_candidate"}
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    cropped_bytes, crop_applied = service._maybe_crop_snapshot_bytes(
        "evt_no_model_crop",
        frame_bytes,
        {"data": {"box": [5, 5, 20, 20]}},
    )

    assert crop_applied is True
    fake_crop_service.generate_crop.assert_called_once()


def test_maybe_crop_snapshot_bytes_keeps_full_frame_when_model_and_hints_both_fail(monkeypatch):
    """When the model finds no crop AND no hint box is available, the full frame is kept."""
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: True)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.get_status.return_value = {"installed": True, "enabled_for_runtime": True}
    fake_crop_service.generate_crop.return_value = {"crop_image": None, "reason": "no_candidate"}
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    cropped_bytes, crop_applied = service._maybe_crop_snapshot_bytes(
        "evt_no_model_no_hints",
        frame_bytes,
        None,
    )

    assert crop_applied is False
    assert cropped_bytes == frame_bytes
    fake_crop_service.generate_crop.assert_called_once()


def test_maybe_crop_snapshot_bytes_keeps_full_frame_under_pressure(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: False)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.get_status.return_value = {"installed": True, "enabled_for_runtime": True}
    fake_crop_service.generate_crop.side_effect = AssertionError("crop model should not run under pressure")
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    cropped_bytes, crop_applied = service._maybe_crop_snapshot_bytes(
        "evt_pressure",
        frame_bytes,
        {"data": {"box": [5, 5, 20, 20]}},
    )

    assert crop_applied is False
    assert cropped_bytes == frame_bytes
    fake_crop_service.generate_crop.assert_not_called()


def test_background_crop_work_is_blocked_by_mqtt_pressure(monkeypatch):
    service = hq_module.HighQualitySnapshotService()

    from app.services.mqtt_service import mqtt_service

    monkeypatch.setattr(
        mqtt_service,
        "get_status",
        lambda: {
            "pressure_level": "elevated",
            "under_pressure": False,
            "backlog_wait_active": False,
            "recent_handler_slot_wait_exhaustion": False,
        },
    )
    monkeypatch.setattr(service, "_classifier_pressure_allows_background_crop", lambda: True)

    assert service._background_crop_work_allowed() is False


def test_background_crop_work_is_blocked_by_classifier_pressure(monkeypatch):
    service = hq_module.HighQualitySnapshotService()

    from app.services.mqtt_service import mqtt_service

    fake_classifier = MagicMock()
    fake_classifier.get_admission_status.return_value = {
        "live": {"queued": 0, "running": 1},
        "background": {"queued": 0, "running": 0},
        "background_throttled": False,
    }
    monkeypatch.setitem(
        sys.modules,
        "app.services.classifier_service",
        SimpleNamespace(_classifier_instance=fake_classifier),
    )
    monkeypatch.setattr(
        mqtt_service,
        "get_status",
        lambda: {
            "pressure_level": "normal",
            "under_pressure": False,
            "backlog_wait_active": False,
            "recent_handler_slot_wait_exhaustion": False,
        },
    )

    assert service._background_crop_work_allowed() is False


@pytest_asyncio.fixture(autouse=True)
async def reset_high_quality_snapshot_service_state():
    original_media_enabled = settings.media_cache.enabled
    original_cache_snapshots = settings.media_cache.cache_snapshots
    original_high_quality_snapshots = settings.media_cache.high_quality_event_snapshots
    original_high_quality_bird_crop = settings.media_cache.high_quality_event_snapshot_bird_crop
    original_clips_enabled = settings.frigate.clips_enabled
    original_recording_clip_enabled = settings.frigate.recording_clip_enabled
    await hq_module.high_quality_snapshot_service.reset_state()
    settings.media_cache.enabled = True
    settings.media_cache.cache_snapshots = True
    settings.media_cache.high_quality_event_snapshots = False
    settings.media_cache.high_quality_event_snapshot_bird_crop = False
    settings.frigate.clips_enabled = True
    yield
    await hq_module.high_quality_snapshot_service.reset_state()
    settings.media_cache.enabled = original_media_enabled
    settings.media_cache.cache_snapshots = original_cache_snapshots
    settings.media_cache.high_quality_event_snapshots = original_high_quality_snapshots
    settings.media_cache.high_quality_event_snapshot_bird_crop = original_high_quality_bird_crop
    settings.frigate.clips_enabled = original_clips_enabled
    settings.frigate.recording_clip_enabled = original_recording_clip_enabled


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_skips_when_feature_disabled(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_disabled", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = False

    queued = hq_module.high_quality_snapshot_service.schedule_replacement("evt_disabled")

    assert queued is False
    assert await cache_service.get_snapshot("evt_disabled") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_accepts_recording_clip_only_mode(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_recording_only", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", False, raising=False)
    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", True, raising=False)

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)

    queued = hq_module.high_quality_snapshot_service.schedule_replacement("evt_recording_only")

    assert queued is True
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["enabled"] is True
    assert status["queue_size"] == 1


@pytest.mark.asyncio
async def test_process_event_replaces_cached_snapshot_with_clip_frame(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_replace", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_replace"
        return b"clip-bytes", None

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        fake_wait_for_clip,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_replace")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_replace") == b"derived-bytes"


@pytest.mark.asyncio
async def test_scheduled_replacement_uses_stored_event_hints_without_refetch(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_scheduled_hint", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.expand_ratio = 0.0
    fake_crop_service.min_crop_size = 1
    fake_crop_service.get_status.return_value = {"installed": False}
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)
    monkeypatch.setattr(
        hq_module.frigate_client,
        "get_event_with_error",
        AsyncMock(return_value=({"data": {"box": [0, 0, 100, 80]}}, None)),
    )

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_scheduled_hint"
        return b"clip-bytes", None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: frame_bytes,
    )

    queued = hq_module.high_quality_snapshot_service.schedule_replacement(
        "evt_scheduled_hint",
        event_data={"data": {"box": [20, 10, 30, 20]}},
    )
    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(hq_module.high_quality_snapshot_service.wait_for_idle(), timeout=1.0)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert queued is True
    hq_module.frigate_client.get_event_with_error.assert_not_awaited()
    fake_crop_service.generate_crop.assert_not_called()
    cached = await cache_service.get_snapshot("evt_scheduled_hint")
    assert cached is not None
    with Image.open(BytesIO(cached)) as img:
        assert img.size == (52, 34)


@pytest.mark.asyncio
async def test_process_event_uses_frigate_box_hint_for_hq_bird_crop(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_hint_crop", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.expand_ratio = 0.0
    fake_crop_service.min_crop_size = 1
    fake_crop_service.get_status.return_value = {"installed": False}
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)
    monkeypatch.setattr(
        hq_module.frigate_client,
        "get_event_with_error",
        AsyncMock(return_value=({"data": {"box": [20, 10, 30, 20]}}, None)),
    )

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_hint_crop"
        return b"clip-bytes", None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: frame_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_hint_crop")

    assert result == "bird_crop_replaced"
    fake_crop_service.generate_crop.assert_not_called()
    cached = await cache_service.get_snapshot("evt_hint_crop")
    assert cached is not None
    with Image.open(BytesIO(cached)) as img:
        assert img.size == (52, 34)
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["outcomes"]["bird_crop_replaced"] == 1
    assert status["last_result"] == {"event_id": "evt_hint_crop", "result": "bird_crop_replaced"}


@pytest.mark.asyncio
async def test_process_event_replaces_cached_snapshot_with_hq_bird_crop_when_enabled(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_crop", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)

    frame_bytes = _jpeg_bytes("blue", size=(64, 64))
    crop_image = Image.new("RGB", (18, 20), color="green")
    fake_crop_service = MagicMock()
    fake_crop_service.generate_crop.return_value = {
        "crop_image": crop_image,
        "box": (2, 3, 20, 23),
        "reason": "selected",
    }
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    async def no_event_data(event_id: str):
        assert event_id == "evt_crop"
        return None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_load_event_data_for_crop", no_event_data)

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_crop"
        return b"clip-bytes", None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: frame_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_crop")

    assert result == "bird_crop_replaced"
    fake_crop_service.generate_crop.assert_called_once()
    cached = await cache_service.get_snapshot("evt_crop")
    assert cached is not None
    with Image.open(BytesIO(cached)) as img:
        assert img.size == (23, 27)


@pytest.mark.asyncio
async def test_process_event_falls_back_to_hq_frame_when_bird_crop_unavailable(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_crop_fallback", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)

    frame_bytes = _jpeg_bytes("blue", size=(64, 64))
    fake_crop_service = MagicMock()
    fake_crop_service.generate_crop.return_value = {"crop_image": None, "reason": "no_crop"}
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    async def no_event_data(event_id: str):
        assert event_id == "evt_crop_fallback"
        return None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_load_event_data_for_crop", no_event_data)

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_crop_fallback"
        return b"clip-bytes", None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: frame_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_crop_fallback")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_crop_fallback") == frame_bytes


@pytest.mark.asyncio
async def test_process_event_falls_back_to_cached_recording_clip_when_event_clip_missing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_recording_fallback", b"frigate-bytes")
    await cache_service.cache_recording_clip("evt_recording_fallback", b"r" * 1024)
    settings.media_cache.high_quality_event_snapshots = True
    settings.frigate.recording_clip_enabled = True

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_recording_fallback"
        return None, "clip_not_found"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        fake_wait_for_clip,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-from-recording:" + clip_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_recording_fallback")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_recording_fallback") == b"derived-from-recording:" + (b"r" * 1024)


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_ignores_duplicates(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_duplicate", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process_event(event_id: str):
        assert event_id == "evt_duplicate"
        started.set()
        await release.wait()
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    first = hq_module.high_quality_snapshot_service.schedule_replacement("evt_duplicate")
    await asyncio.wait_for(started.wait(), timeout=1.0)
    second = hq_module.high_quality_snapshot_service.schedule_replacement("evt_duplicate")
    release.set()
    await hq_module.high_quality_snapshot_service.wait_for_idle()

    assert first is True
    assert second is False
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["scheduled_total"] == 1
    assert status["duplicate_requests"] == 1


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_defers_when_queue_full(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt-queue-1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt-queue-2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)

    first = hq_module.high_quality_snapshot_service.schedule_replacement("evt-queue-1")
    second = hq_module.high_quality_snapshot_service.schedule_replacement("evt-queue-2")

    assert first is True
    assert second is True
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["queue_size"] == 1
    assert status["deferred"] == 1
    assert status["queue_full_rejections"] == 0
    assert status["queue_full_deferrals"] == 1


@pytest.mark.asyncio
async def test_deferred_snapshot_replacements_drain_after_capacity_frees(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt-drain-1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt-drain-2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)

    processed: list[str] = []

    async def fake_process_event(event_id: str):
        processed.append(event_id)
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt-drain-1") is True
    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt-drain-2") is True

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(hq_module.high_quality_snapshot_service.wait_for_idle(), timeout=1.0)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert processed == ["evt-drain-1", "evt-drain-2"]
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["queue_size"] == 0
    assert status["deferred"] == 0
    assert status["queue_full_deferrals"] == 1


@pytest.mark.asyncio
async def test_high_quality_snapshot_service_status_tracks_outcomes(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_status", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_status"
        return b"clip-bytes", None

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        fake_wait_for_clip,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_status")

    assert result == "replaced"
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["enabled"] is True
    assert status["active"] == 0
    assert status["outcomes"]["replaced"] == 1
    assert status["last_result"] == {"event_id": "evt_status", "result": "replaced"}


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_replaces_cached_snapshot_when_enabled(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_bytes", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_bytes", b"clip-bytes")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_clip_bytes") == b"derived-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_is_disabled_when_feature_flag_off(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_disabled", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = False

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_disabled", b"clip-bytes")

    assert result == "disabled"
    assert await cache_service.get_snapshot("evt_clip_disabled") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_preserves_original_on_extraction_failure(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_failure", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    def _boom(_clip_bytes):
        raise ValueError("bad clip")

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        _boom,
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_failure", b"clip-bytes")

    assert result == "frame_extract_failed"
    assert await cache_service.get_snapshot("evt_clip_failure") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_satisfies_queued_event_without_duplicate_worker_processing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_queued", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-bytes",
    )

    worker_processed = asyncio.Event()

    async def fake_process_event(event_id: str):
        worker_processed.set()
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    queued = hq_module.high_quality_snapshot_service.schedule_replacement("evt_clip_queued")
    assert queued is True

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_queued", b"clip-bytes")
    assert result == "replaced"

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.sleep(0.05)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert worker_processed.is_set() is False
    assert await cache_service.get_snapshot("evt_clip_queued") == b"derived-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_satisfies_deferred_event_without_later_worker_processing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_deferred_1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt_clip_deferred_2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: b"derived-bytes",
    )

    worker_processed: list[str] = []

    async def fake_process_event(event_id: str):
        worker_processed.append(event_id)
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt_clip_deferred_1") is True
    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt_clip_deferred_2") is True

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_deferred_2", b"clip-bytes")
    assert result == "replaced"

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(hq_module.high_quality_snapshot_service.wait_for_idle(), timeout=1.0)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert worker_processed == ["evt_clip_deferred_1"]
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["duplicate_requests"] >= 1
    assert status["deferred"] == 0


def test_extract_snapshot_from_clip_uses_configured_jpeg_quality(monkeypatch):
    original_quality = settings.media_cache.high_quality_event_snapshot_jpeg_quality
    settings.media_cache.high_quality_event_snapshot_jpeg_quality = 82

    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.return_value = 1
    cap.read.return_value = (True, object())
    encoded = MagicMock()
    encoded.tobytes.return_value = b"jpeg-bytes"
    imencode = MagicMock(return_value=(True, encoded))

    try:
        monkeypatch.setattr(hq_module.cv2, "VideoCapture", lambda _path: cap)
        monkeypatch.setattr(hq_module.cv2, "imencode", imencode)

        result = hq_module.high_quality_snapshot_service._extract_snapshot_from_clip_path(Path("/tmp/demo.mp4"))

        assert result == b"jpeg-bytes"
        imencode.assert_called_once_with(
            ".jpg",
            cap.read.return_value[1],
            [int(hq_module.cv2.IMWRITE_JPEG_QUALITY), 82],
        )
    finally:
        settings.media_cache.high_quality_event_snapshot_jpeg_quality = original_quality


@pytest.mark.asyncio
async def test_stop_ignores_worker_tasks_from_closed_event_loop(tmp_path, monkeypatch):
    _make_cache_service(tmp_path, monkeypatch)

    class _ClosedLoopTask:
        def __init__(self):
            self._loop = asyncio.new_event_loop()
            self._loop.close()

        def done(self):
            return False

        def get_loop(self):
            return self._loop

        def cancel(self):
            raise RuntimeError("cancel should not be called for closed-loop task")

    hq_module.high_quality_snapshot_service._worker_tasks = [_ClosedLoopTask()]  # type: ignore[list-item]

    await hq_module.high_quality_snapshot_service.stop()

    assert hq_module.high_quality_snapshot_service.get_status()["workers"] == 0


@pytest.mark.asyncio
async def test_worker_loop_tracks_task_done_against_original_queue_when_service_queue_replaced(tmp_path, monkeypatch):
    _make_cache_service(tmp_path, monkeypatch)
    settings.media_cache.high_quality_event_snapshots = True

    original_queue = asyncio.Queue()
    await original_queue.put("evt_queue_swap")
    hq_module.high_quality_snapshot_service._pending_queue = original_queue

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process_event(event_id: str):
        assert event_id == "evt_queue_swap"
        started.set()
        await release.wait()
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(started.wait(), timeout=1.0)

    replacement_queue = asyncio.Queue()
    hq_module.high_quality_snapshot_service._pending_queue = replacement_queue

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert original_queue.qsize() == 0
    assert original_queue._unfinished_tasks == 0
    assert replacement_queue.qsize() == 0
    assert replacement_queue._unfinished_tasks == 0
