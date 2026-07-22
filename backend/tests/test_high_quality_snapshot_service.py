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


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_persists_and_selects_ranked_snapshot_candidates(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_candidates", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)

    async def fake_generate(event_id, clip_bytes, event_data=None, clip_variant="event"):
        assert event_id == "evt_candidates"
        assert clip_bytes == b"clip-bytes"
        assert clip_variant == "event"
        return {
            "selected_candidate": {
                "candidate_id": "cand-best",
                "image_bytes": _jpeg_bytes("green", size=(40, 40)),
                "source_mode": "model_crop",
                "snapshot_source": "hq_candidate_model_crop",
            },
            "candidates": [
                {
                    "candidate_id": "cand-best",
                    "frame_index": 8,
                    "frame_offset_seconds": 0.32,
                    "source_mode": "model_crop",
                    "clip_variant": "recording",
                    "crop_box": [4, 4, 32, 32],
                    "crop_confidence": 0.93,
                    "classifier_label": "Robin",
                    "classifier_score": 0.91,
                    "ranking_score": 0.97,
                    "selected": True,
                    "thumbnail_ref": "evt_candidates__cand-best__thumb",
                    "image_ref": "evt_candidates__cand-best__image",
                    "snapshot_source": "hq_candidate_model_crop",
                },
                {
                    "candidate_id": "cand-fallback",
                    "frame_index": 2,
                    "frame_offset_seconds": 0.08,
                    "source_mode": "full_frame",
                    "clip_variant": "event",
                    "crop_box": None,
                    "crop_confidence": None,
                    "classifier_label": "Robin",
                    "classifier_score": 0.44,
                    "ranking_score": 0.44,
                    "selected": False,
                    "thumbnail_ref": "evt_candidates__cand-fallback__thumb",
                    "image_ref": "evt_candidates__cand-fallback__image",
                    "snapshot_source": "hq_candidate_full_frame",
                },
            ],
        }

    persisted = {}

    async def fake_persist(event_id, candidates):
        persisted["event_id"] = event_id
        persisted["candidates"] = candidates

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "generate_snapshot_candidates_from_clip_bytes",
        fake_generate,
        raising=False,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_persist_snapshot_candidates",
        fake_persist,
        raising=False,
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_candidates", b"clip-bytes")

    assert result == "bird_crop_replaced"
    assert persisted["event_id"] == "evt_candidates"
    assert persisted["candidates"][0]["candidate_id"] == "cand-best"
    cached = await cache_service.get_snapshot("evt_candidates")
    assert cached is not None


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
            "snapshot": {"box": [0.11, 0.21, 0.31, 0.41], "frame_time": 100.8},
            "large_irrelevant_payload": "ignored",
        }
    )

    assert hints == {
        "start_time": 100.0,
        "end_time": 101.0,
        "snapshot": {"box": [0.11, 0.21, 0.31, 0.41], "frame_time": 100.8},
        "data": {
            "box": [0.1, 0.2, 0.3, 0.4],
            "region": ["10", "20", "30", "40"],
            "path_data": [[[0.5, 0.6], 100.1]],
        },
    }


def test_candidate_generation_attempts_model_crop_when_legacy_crop_flag_is_off(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", False, raising=False)
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    monkeypatch.setattr(service, "_crop_from_event_hints", lambda image, event_data: None)
    monkeypatch.setattr(
        service,
        "_crop_candidate_from_bird_model",
        lambda image, event_id=None: {
            "crop_image": image.crop((8, 8, 96, 96)),
            "box": (8, 8, 96, 96),
            "confidence": 0.8,
        },
    )

    candidates = service._candidate_images_for_frame(
        Image.new("RGB", (128, 128)),
        event_data=None,
        event_id="evt",
    )

    assert [source for source, _image, _result in candidates] == ["full_frame", "model_crop"]


def test_candidate_generation_uses_distance_tolerant_evidence_crop_without_replacing_frame(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    monkeypatch.setattr(service, "_crop_from_event_hints", lambda image, event_data: None)

    class _CropService:
        def generate_crop(self, _image, *, detector_tier=None):
            raise AssertionError(f"normal replacement policy should not run: {detector_tier}")

        def generate_classification_candidate_crop(self, image):
            return {
                "crop_image": image.crop((16, 16, 96, 112)),
                "box": (16, 16, 96, 112),
                "confidence": 0.03,
                "reason": "selected",
            }

    monkeypatch.setattr(hq_module, "bird_crop_service", _CropService())

    candidates = service._candidate_images_for_frame(
        Image.new("RGB", (128, 128)),
        event_data=None,
        event_id="evt-distant",
    )

    assert [source for source, _image, _result in candidates] == ["full_frame", "model_crop"]
    assert candidates[1][2]["confidence"] == 0.03


def test_candidate_generation_guides_model_with_same_frame_frigate_crop(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    image = Image.new("RGB", (1000, 800))
    hint_result = {
        "crop_image": image.crop((300, 200, 700, 600)),
        "box": (300, 200, 700, 600),
        "reason": "frigate_box",
    }
    monkeypatch.setattr(service, "_crop_from_event_hints", lambda _image, _event_data: hint_result)
    seen = []

    class _CropService:
        def generate_guided_classification_candidate_crop(self, candidate_image, *, search_box):
            seen.append((candidate_image.size, search_box))
            return {
                "crop_image": candidate_image.crop((400, 300, 560, 460)),
                "box": (400, 300, 560, 460),
                "confidence": 0.72,
                "reason": "selected",
                "strategy": "frigate_guided",
            }

    monkeypatch.setattr(hq_module, "bird_crop_service", _CropService())

    candidates = service._candidate_images_for_frame(
        image,
        event_data={"data": {"box": [0.3, 0.25, 0.4, 0.5]}},
        event_id="evt-guided",
    )

    assert seen == [((1000, 800), (300, 200, 700, 600))]
    assert [source for source, _image, _result in candidates] == [
        "full_frame",
        "frigate_hint_crop",
        "model_crop",
    ]
    assert candidates[2][2]["strategy"] == "frigate_guided"


@pytest.mark.asyncio
async def test_reconcile_recent_detections_only_reschedules_unfinished_snapshot_jobs(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "enabled", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True, raising=False)

    detections = [
        SimpleNamespace(frigate_event="evt_unfinished"),
        SimpleNamespace(frigate_event="evt_complete"),
        SimpleNamespace(frigate_event="evt_reverted"),
    ]

    class FakeDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    class FakeRepo:
        def __init__(self, _db):
            pass

        async def get_recent_full_visit_candidates(self, **_kwargs):
            return detections

        async def list_snapshot_candidates(self, event_id):
            return [{"candidate_id": "manual"}] if event_id == "evt_reverted" else []

    monkeypatch.setattr(hq_module, "get_db", lambda: FakeDbContext())
    monkeypatch.setattr(hq_module, "DetectionRepository", FakeRepo)
    monkeypatch.setattr(
        hq_module.media_cache,
        "get_snapshot_metadata",
        AsyncMock(
            side_effect=lambda event_id: (
                {"source": "hq_candidate_model_crop"} if event_id == "evt_complete" else {"source": "frigate_snapshot"}
            )
        ),
    )
    scheduled: list[str] = []
    monkeypatch.setattr(service, "schedule_replacement", lambda event_id: scheduled.append(event_id) or True)

    recovered = await service.reconcile_recent_detections()

    assert recovered == 1
    assert scheduled == ["evt_unfinished"]
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

    def generate_crop(image, *, detector_tier=None):
        assert detector_tier == "accurate"
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

    assert indices[0] == 12
    assert len(indices) == 3
    assert all(abs(left - right) >= 8 for left in indices for right in indices if left != right)


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

    assert indices[0] == 24
    assert len(indices) == 3
    assert all(abs(left - right) >= 8 for left in indices for right in indices if left != right)


def test_candidate_frame_indices_never_count_adjacent_frames_as_independent_samples():
    service = hq_module.HighQualitySnapshotService()

    indices = service._candidate_frame_indices(
        frame_count=300,
        fps=30.0,
        event_data={
            "start_time": 100.0,
            "data": {
                "path_data": [
                    [[0.5, 0.8], 100.0],
                    [[0.5, 0.8], 100.033],
                    [[0.5, 0.8], 100.067],
                ]
            },
        },
    )

    assert len(indices) == 3
    assert indices != [0, 1, 2]
    assert all(abs(left - right) >= 8 for left in indices for right in indices if left != right)


def test_candidate_frame_indices_distribute_real_quark_path_around_visible_interval():
    service = hq_module.HighQualitySnapshotService()

    indices = service._candidate_frame_indices(
        frame_count=300,
        fps=30.0,
        event_data={
            "start_time": 1784561844.911783,
            "data": {
                "box": [0.149609375, 0.16666666666666666, 0.0484375, 0.06510416666666667],
                "path_data": [
                    [[0.1754, 0.2109], 1784561844.961835],
                    [[0.1754, 0.2109], 1784561844.961835],
                    [[0.2121, 0.3109], 1784561851.878304],
                ],
            },
        },
    )

    assert indices[0] == 2
    assert any(index >= 200 for index in indices)
    assert any(90 <= index <= 120 for index in indices)
    assert all(abs(left - right) >= 8 for left in indices for right in indices if left != right)


def test_recording_candidate_frames_ignore_event_clip_timestamps():
    service = hq_module.HighQualitySnapshotService()

    indices = service._candidate_frame_indices(
        frame_count=300,
        fps=30.0,
        clip_variant="recording",
        event_data={
            "start_time": 1784561844.911783,
            "data": {
                "path_data": [
                    [[0.1754, 0.2109], 1784561844.961835],
                    [[0.2121, 0.3109], 1784561851.878304],
                ],
            },
        },
    )

    assert indices == [150, 75, 225]


def test_event_hint_box_tracks_the_nearest_path_point_and_rejects_stale_hints():
    service = hq_module.HighQualitySnapshotService()
    event_data = {
        "start_time": 100.0,
        "data": {
            "box": [0.10, 0.20, 0.20, 0.10],
            "path_data": [
                [[0.20, 0.25], 100.0],
                [[0.70, 0.75], 106.0],
            ],
        },
    }

    first = service._event_hints_for_frame(event_data, frame_offset_seconds=0.0, clip_variant="event")
    last = service._event_hints_for_frame(event_data, frame_offset_seconds=6.0, clip_variant="event")
    stale = service._event_hints_for_frame(event_data, frame_offset_seconds=3.0, clip_variant="event")
    recording = service._event_hints_for_frame(event_data, frame_offset_seconds=6.0, clip_variant="recording")

    assert first is not event_data
    # Frigate path_data points are the tracked box's bottom-centre, not its centre.
    assert first["data"]["box"] == pytest.approx([0.10, 0.15, 0.20, 0.10])
    assert last["data"]["box"] == pytest.approx([0.60, 0.65, 0.20, 0.10])
    assert stale is None
    assert recording is None


def test_path_sampling_compares_bottom_centre_points_with_the_final_box():
    service = hq_module.HighQualitySnapshotService()

    ordered = service._ordered_path_timestamps_for_crop(
        {"box": [0.40, 0.40, 0.20, 0.20]},
        [
            (101.0, 0.50, 0.50),  # Final box centre, but not Frigate's path anchor.
            (102.0, 0.50, 0.60),  # Final box bottom-centre.
        ],
    )

    assert ordered[0] == 102.0


def test_event_hint_path_without_a_valid_box_fails_closed():
    service = hq_module.HighQualitySnapshotService()

    result = service._event_hints_for_frame(
        {
            "start_time": 100.0,
            "data": {
                "path_data": [[[0.20, 0.25], 100.0]],
            },
        },
        frame_offset_seconds=0.0,
        clip_variant="event",
    )

    assert result is None


def test_candidate_frame_indices_return_one_slot_when_fps_is_unknown():
    service = hq_module.HighQualitySnapshotService()

    indices = service._candidate_frame_indices(frame_count=300, fps=0.0)

    assert indices == [150]


def test_decode_neighbours_are_fallbacks_within_one_temporal_slot():
    service = hq_module.HighQualitySnapshotService()

    class FakeCapture:
        def __init__(self):
            self.index = 0

        def set(self, _prop, value):
            self.index = int(value)

        def get(self, _prop):
            return float(self.index + 1)

        def read(self):
            if self.index == 30:
                return False, None
            return True, f"frame-{self.index}"

    decoded = service._read_temporally_independent_frame(
        FakeCapture(),
        target_frame_index=30,
        frame_count=300,
        fps=30.0,
        used_frame_indices=[0],
    )

    assert decoded == (29, "frame-29")

    correlated = service._read_temporally_independent_frame(
        FakeCapture(),
        target_frame_index=5,
        frame_count=300,
        fps=30.0,
        used_frame_indices=[0],
    )

    assert correlated is None


def test_crop_source_order_defines_a_fallback_chain_per_priority():
    assert hq_module.crop_source_order("frigate_hints_first") == ("frigate_hint_crop", "model_crop", "full_frame")
    assert hq_module.crop_source_order("crop_model_first") == ("model_crop", "frigate_hint_crop", "full_frame")
    assert hq_module.crop_source_order("crop_model_only") == ("model_crop", "full_frame")
    assert hq_module.crop_source_order("frigate_hints_only") == ("frigate_hint_crop", "full_frame")
    # Unknown values fall back to the default order.
    assert hq_module.crop_source_order("nonsense") == hq_module.crop_source_order("frigate_hints_first")


def test_rank_snapshot_candidates_sorts_by_score_highest_first():
    service = hq_module.HighQualitySnapshotService()

    ranked = service._rank_snapshot_candidates(
        [
            {"candidate_id": "low", "source_mode": "full_frame", "ranking_score": 0.2},
            {"candidate_id": "high", "source_mode": "model_crop", "ranking_score": 0.9},
        ]
    )

    assert [item["candidate_id"] for item in ranked] == ["high", "low"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_mode", "expected_is_cropped"),
    [("full_frame", False), ("frigate_hint_crop", True), ("model_crop", True)],
)
async def test_candidate_scoring_preserves_model_input_contract(monkeypatch, source_mode, expected_is_cropped):
    from app.services import classifier_service as classifier_module

    service = hq_module.HighQualitySnapshotService()
    classifier = SimpleNamespace()
    seen_contexts: list[dict] = []

    async def classify_async_background(_image, *, input_context, queue_timeout_seconds):
        seen_contexts.append(input_context)
        assert queue_timeout_seconds > 0
        return [{"label": "Columba palumbus", "score": 0.84, "index": 123}]

    classifier.classify_async_background = classify_async_background
    monkeypatch.setattr(classifier_module, "_classifier_instance", classifier)

    result = await service._score_snapshot_candidate(
        {
            "candidate_id": f"candidate-{source_mode}",
            "frame_index": 4,
            "source_mode": source_mode,
            "image_bytes": _jpeg_bytes("green"),
        }
    )

    assert seen_contexts == [{"is_cropped": expected_is_cropped}]
    assert result["classifier_label"] == "Columba palumbus"
    assert result["classifier_score"] == 0.84
    assert result["classifier_index"] == 123


@pytest.mark.asyncio
async def test_candidate_scoring_honours_conservative_crop_override(monkeypatch):
    from app.services import classifier_service as classifier_module

    service = hq_module.HighQualitySnapshotService()
    classifier = SimpleNamespace()
    seen_contexts: list[dict] = []

    async def classify_async_background(_image, *, input_context, queue_timeout_seconds):
        seen_contexts.append(input_context)
        return [{"label": "Columba palumbus", "score": 0.84, "index": 123}]

    classifier.classify_async_background = classify_async_background
    monkeypatch.setattr(classifier_module, "_classifier_instance", classifier)

    await service._score_snapshot_candidate(
        {
            "candidate_id": "regular-snapshot-fallback",
            "frame_index": 0,
            "source_mode": "full_frame",
            "input_is_cropped": True,
            "image_bytes": _jpeg_bytes("green"),
        }
    )

    assert seen_contexts == [{"is_cropped": True}]


@pytest.mark.asyncio
async def test_candidate_scoring_does_not_reward_detector_confidence_or_crop_source(monkeypatch):
    from app.services import classifier_service as classifier_module

    service = hq_module.HighQualitySnapshotService()
    classifier = SimpleNamespace()

    async def classify_async_background(_image, *, input_context, queue_timeout_seconds):
        return [{"label": "Columba palumbus", "score": 0.84, "index": 123}]

    classifier.classify_async_background = classify_async_background
    monkeypatch.setattr(classifier_module, "_classifier_instance", classifier)
    common = {
        "frame_index": 4,
        "image_bytes": _jpeg_bytes("green"),
    }

    hint = await service._score_snapshot_candidate(
        {
            **common,
            "candidate_id": "hint",
            "source_mode": "frigate_hint_crop",
            "crop_confidence": None,
        }
    )
    model = await service._score_snapshot_candidate(
        {
            **common,
            "candidate_id": "model",
            "source_mode": "model_crop",
            "crop_confidence": 0.99,
        }
    )

    assert hint is not None
    assert model is not None
    assert model["ranking_score"] == pytest.approx(hint["ranking_score"])


@pytest.mark.asyncio
async def test_hq_consensus_uses_canonical_detection_update_path(monkeypatch):
    from app.services import detection_service as detection_module
    from app.services import model_manager as model_manager_module

    service = hq_module.HighQualitySnapshotService()
    detection = SimpleNamespace(
        display_name="Unknown Bird",
        category_name="Unknown Bird",
        scientific_name=None,
        common_name=None,
        score=0.51,
        manual_tagged=False,
    )

    class FakeDbContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    class FakeRepo:
        def __init__(self, _db):
            pass

        async def get_by_frigate_event(self, event_id):
            assert event_id == "evt-refine"
            return detection

    applied_calls: list[dict] = []

    class FakeDetectionService:
        def __init__(self, classifier):
            assert classifier is fake_classifier

        async def apply_video_result(self, **kwargs):
            applied_calls.append(kwargs)
            return True

    fake_classifier = SimpleNamespace(_active_inference_provider="intel_gpu", _inference_backend="openvino")
    classifier_module = sys.modules["app.services.classifier_service"]
    monkeypatch.setattr(classifier_module, "_classifier_instance", fake_classifier)
    monkeypatch.setattr(hq_module, "get_db", lambda: FakeDbContext())
    monkeypatch.setattr(hq_module, "DetectionRepository", FakeRepo)
    monkeypatch.setattr(detection_module, "DetectionService", FakeDetectionService)
    monkeypatch.setattr(
        model_manager_module.model_manager,
        "get_active_model_spec",
        lambda: {
            "model_id": "eva02_large_inat21",
            "recommended_threshold": 0.45,
            "preprocessing": {"resize_mode": "center_crop"},
        },
    )

    applied = await service._apply_classification_refinement(
        "evt-refine",
        [
            {
                "candidate_id": "crop-1",
                "frame_index": 10,
                "frame_offset_seconds": 0.5,
                "source_mode": "frigate_hint_crop",
                "classifier_label": "Columba palumbus",
                "classifier_score": 0.82,
                "classifier_index": 123,
            },
            {
                "candidate_id": "crop-2",
                "frame_index": 20,
                "frame_offset_seconds": 1.0,
                "source_mode": "model_crop",
                "classifier_label": "Columba palumbus",
                "classifier_score": 0.79,
                "classifier_index": 123,
            },
        ],
    )

    assert applied is True
    assert applied_calls == [
        {
            "frigate_event": "evt-refine",
            "video_label": "Columba palumbus",
            "video_score": 0.82,
            "video_index": 123,
            "video_provider": "intel_gpu",
            "video_backend": "openvino",
            "video_model_id": "eva02_large_inat21",
            "persist_video_result": False,
        }
    ]
    assert service.get_status()["classification_refinements"] == {"promoted": 1}


def test_select_canonical_snapshot_candidate_falls_back_to_crop_by_default():
    service = hq_module.HighQualitySnapshotService()

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "model-crop",
                "source_mode": "model_crop",
                "ranking_score": 1.0,
                "image_width": 198,
                "image_height": 182,
                "classifier_label": "Columba palumbus",
            },
            {
                "candidate_id": "full-frame",
                "source_mode": "full_frame",
                "ranking_score": 0.97,
                "image_width": 2560,
                "image_height": 1920,
            },
        ],
        expected_labels={"Columba palumbus"},
    )

    assert selected is not None
    # Default priority (frigate_hints_first) has no hint crop here, so it falls back to the model
    # crop instead of dropping to the full frame.
    assert selected["candidate_id"] == "model-crop"


def test_select_canonical_snapshot_candidate_rejects_tiny_crop_in_favour_of_full_frame():
    service = hq_module.HighQualitySnapshotService()

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "small-crop",
                "source_mode": "frigate_hint_crop",
                "ranking_score": 0.30,
                "image_width": 96,
                "image_height": 120,
                "frame_width": 2560,
                "frame_height": 1920,
            },
            {
                "candidate_id": "full-frame",
                "source_mode": "full_frame",
                "ranking_score": 0.90,
                "image_width": 2560,
                "image_height": 1920,
            },
        ]
    )

    assert selected is not None
    assert selected["candidate_id"] == "full-frame"


def test_select_canonical_snapshot_candidate_chooses_best_crop_regardless_of_legacy_priority(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.classification, "bird_crop_source_priority", "crop_model_first", raising=False)

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "hint-crop",
                "source_mode": "frigate_hint_crop",
                "ranking_score": 1.1,
                "image_width": 240,
                "image_height": 220,
                "classifier_label": "Columba palumbus",
            },
            {
                "candidate_id": "full-frame",
                "source_mode": "full_frame",
                "ranking_score": 0.97,
                "image_width": 2560,
                "image_height": 1920,
            },
            {
                "candidate_id": "model-crop",
                "source_mode": "model_crop",
                "ranking_score": 1.0,
                "image_width": 198,
                "image_height": 182,
                "classifier_label": "Columba palumbus",
            },
        ],
        expected_labels={"Columba palumbus"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "hint-crop"


def test_model_crop_must_materially_outscore_available_frigate_crop():
    service = hq_module.HighQualitySnapshotService()
    common = {
        "image_width": 320,
        "image_height": 280,
        "classifier_label": "Columba palumbus",
    }

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                **common,
                "candidate_id": "hint",
                "source_mode": "frigate_hint_crop",
                "classifier_score": 0.89,
                "ranking_score": 0.90,
            },
            {
                **common,
                "candidate_id": "model",
                "source_mode": "model_crop",
                "classifier_score": 0.90,
                "ranking_score": 0.94,
            },
        ],
        expected_labels={"Columba palumbus"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "hint"


def test_model_crop_can_win_after_material_classifier_improvement():
    service = hq_module.HighQualitySnapshotService()
    common = {
        "image_width": 320,
        "image_height": 280,
        "classifier_label": "Columba palumbus",
    }

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                **common,
                "candidate_id": "hint",
                "source_mode": "frigate_hint_crop",
                "classifier_score": 0.86,
                "ranking_score": 0.87,
            },
            {
                **common,
                "candidate_id": "model",
                "source_mode": "model_crop",
                "classifier_score": 0.90,
                "ranking_score": 0.91,
            },
        ],
        expected_labels={"Columba palumbus"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "model"


def test_final_frigate_snapshot_is_protected_from_marginal_clip_candidate():
    service = hq_module.HighQualitySnapshotService()
    common = {
        "image_width": 420,
        "image_height": 360,
        "classifier_label": "Columba palumbus",
        "source_mode": "frigate_hint_crop",
    }

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                **common,
                "candidate_id": "frigate-final",
                "clip_variant": "frigate_snapshot",
                "classifier_score": 0.88,
                "ranking_score": 0.89,
            },
            {
                **common,
                "candidate_id": "clip-frame",
                "clip_variant": "event",
                "classifier_score": 0.89,
                "ranking_score": 0.97,
            },
        ],
        expected_labels={"Columba palumbus"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "frigate-final"


def test_clip_candidate_can_replace_final_frigate_snapshot_after_material_improvement():
    service = hq_module.HighQualitySnapshotService()
    common = {
        "image_width": 420,
        "image_height": 360,
        "classifier_label": "Columba palumbus",
        "source_mode": "frigate_hint_crop",
    }

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                **common,
                "candidate_id": "frigate-final",
                "clip_variant": "frigate_snapshot",
                "classifier_score": 0.86,
                "ranking_score": 0.87,
            },
            {
                **common,
                "candidate_id": "clip-frame",
                "clip_variant": "event",
                "classifier_score": 0.90,
                "ranking_score": 0.91,
            },
        ],
        expected_labels={"Columba palumbus"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "clip-frame"


@pytest.mark.asyncio
async def test_final_snapshot_candidates_use_uncropped_frigate_image_and_final_box(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    snapshot_bytes = _jpeg_bytes("blue", size=(400, 300))
    clean_snapshot_fetch = AsyncMock(return_value=(snapshot_bytes, None))
    regular_snapshot_fetch = AsyncMock()
    monkeypatch.setattr(hq_module.frigate_client, "get_clean_snapshot_with_error", clean_snapshot_fetch)
    monkeypatch.setattr(hq_module.frigate_client, "get_snapshot_with_error", regular_snapshot_fetch)
    monkeypatch.setattr(service, "_expand_hint_box", lambda box, _image_size: box)

    candidates = await service._load_final_frigate_snapshot_candidates(
        "evt-final",
        {
            "end_time": 102.0,
            "data": {"box": [0.25, 0.20, 0.30, 0.40]},
            "snapshot": {"box": [0.10, 0.10, 0.20, 0.20]},
        },
    )

    assert [candidate["source_mode"] for candidate in candidates] == ["full_frame", "frigate_hint_crop"]
    assert all(candidate["clip_variant"] == "frigate_snapshot" for candidate in candidates)
    assert candidates[0]["image_width"] == 400
    assert candidates[0]["image_height"] == 300
    assert candidates[0]["image_bytes"].startswith(b"\xff\xd8")
    assert candidates[1]["crop_box"] == (40, 30, 120, 90)
    assert candidates[1]["image_width"] == 80
    assert candidates[1]["image_height"] == 60
    clean_snapshot_fetch.assert_awaited_once_with("evt-final", timeout=8.0)
    regular_snapshot_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_snapshot_fallback_does_not_apply_box_to_possibly_precropped_regular_image(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    snapshot_bytes = _jpeg_bytes("blue", size=(180, 180))
    monkeypatch.setattr(
        hq_module.frigate_client,
        "get_clean_snapshot_with_error",
        AsyncMock(return_value=(None, "clean_snapshot_not_found")),
    )
    regular_snapshot_fetch = AsyncMock(return_value=(snapshot_bytes, None))
    monkeypatch.setattr(hq_module.frigate_client, "get_snapshot_with_error", regular_snapshot_fetch)

    candidates = await service._load_final_frigate_snapshot_candidates(
        "evt-legacy-snapshot",
        {
            "end_time": 102.0,
            "data": {"box": [0.25, 0.20, 0.30, 0.40]},
        },
    )

    assert [candidate["source_mode"] for candidate in candidates] == ["full_frame"]
    assert candidates[0]["snapshot_source"] == "hq_candidate_frigate_snapshot_fallback"
    assert candidates[0]["input_is_cropped"] is True
    regular_snapshot_fetch.assert_awaited_once_with(
        "evt-legacy-snapshot",
        crop=False,
        quality=95,
        timeout=8.0,
    )


def test_select_canonical_snapshot_candidate_keeps_better_ranked_full_frame(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.classification, "bird_crop_source_priority", "crop_model_only", raising=False)

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "full",
                "source_mode": "full_frame",
                "ranking_score": 0.99,
                "image_width": 2560,
                "image_height": 1920,
            },
            {
                "candidate_id": "hint",
                "source_mode": "frigate_hint_crop",
                "ranking_score": 0.81,
                "image_width": 320,
                "image_height": 280,
                "classifier_label": "Columba palumbus",
            },
        ]
    )

    assert selected is not None
    assert selected["candidate_id"] == "full"


def test_select_canonical_snapshot_candidate_requires_crop_identity_consistency():
    service = hq_module.HighQualitySnapshotService()

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "full",
                "source_mode": "full_frame",
                "ranking_score": 0.84,
                "image_width": 2560,
                "image_height": 1920,
            },
            {
                "candidate_id": "wrong-crop",
                "source_mode": "model_crop",
                "ranking_score": 0.98,
                "image_width": 360,
                "image_height": 300,
                "classifier_label": "Streptopelia decaocto",
            },
            {
                "candidate_id": "matching-crop",
                "source_mode": "frigate_hint_crop",
                "ranking_score": 0.91,
                "image_width": 340,
                "image_height": 290,
                "classifier_label": "Columba palumbus",
            },
        ],
        expected_labels={"Columba palumbus", "Wood Pigeon"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "matching-crop"


def test_persisted_candidates_reserve_selected_and_full_frame_fallback():
    service = hq_module.HighQualitySnapshotService()
    ranked = [
        {
            "candidate_id": f"crop-{index}",
            "source_mode": "model_crop",
            "ranking_score": 1.0 - (index * 0.01),
        }
        for index in range(hq_module.HQ_MAX_PERSISTED_CANDIDATES + 2)
    ]
    full_frame = {
        "candidate_id": "full-frame",
        "source_mode": "full_frame",
        "ranking_score": 0.1,
    }
    ranked.append(full_frame)

    persisted = service._select_persisted_candidates(
        ranked,
        selected_candidate=full_frame,
    )

    assert len(persisted) == hq_module.HQ_MAX_PERSISTED_CANDIDATES
    assert "full-frame" in {candidate["candidate_id"] for candidate in persisted}


def test_persisted_candidates_keep_final_frigate_baseline_when_clip_wins():
    service = hq_module.HighQualitySnapshotService()
    ranked = [
        {
            "candidate_id": f"clip-{index}",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "ranking_score": 1.0 - (index * 0.01),
        }
        for index in range(hq_module.HQ_MAX_PERSISTED_CANDIDATES + 2)
    ]
    final_full = {
        "candidate_id": "frigate-final-full",
        "source_mode": "full_frame",
        "clip_variant": "frigate_snapshot",
        "ranking_score": 0.12,
    }
    final_crop = {
        "candidate_id": "frigate-final-crop",
        "source_mode": "frigate_hint_crop",
        "clip_variant": "frigate_snapshot",
        "ranking_score": 0.15,
    }
    ranked.extend([final_crop, final_full])

    persisted = service._select_persisted_candidates(ranked, selected_candidate=ranked[0])
    persisted_ids = {candidate["candidate_id"] for candidate in persisted}

    assert len(persisted) == hq_module.HQ_MAX_PERSISTED_CANDIDATES
    assert "frigate-final-full" in persisted_ids
    assert "frigate-final-crop" in persisted_ids


def test_maybe_crop_snapshot_bytes_prefers_event_hint_over_model_crop(monkeypatch):
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
    fake_crop_service.generate_crop.assert_not_called()
    with Image.open(BytesIO(cropped_bytes)) as img:
        assert img.size == (32, 32)


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
    fake_crop_service.generate_crop.assert_not_called()
    with Image.open(BytesIO(cropped_bytes)) as img:
        assert img.size == (32, 32)


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
async def test_final_replacement_is_deferred_instead_of_dropped_while_live_pass_is_active(monkeypatch):
    service = hq_module.high_quality_snapshot_service
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(service, "_ensure_workers_started", lambda: None)
    service._active_ids.add("evt-final-refresh")

    queued = service.schedule_final_replacement(
        "evt-final-refresh",
        {
            "start_time": 100.0,
            "end_time": 105.0,
            "data": {"box": [0.1, 0.2, 0.3, 0.4]},
        },
    )

    assert queued is True
    assert "evt-final-refresh" in service._deferred_ids
    assert "evt-final-refresh" in service._final_refresh_ids
    service._active_ids.discard("evt-final-refresh")
    service._promote_deferred_events()
    assert "evt-final-refresh" in service._queued_ids
    assert service._crop_event_hints["evt-final-refresh"]["end_time"] == 105.0


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
async def test_process_event_prefers_frigate_hint_before_crop_model(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_hint_first", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.expand_ratio = 0.0
    fake_crop_service.min_crop_size = 1
    fake_crop_service.get_status.return_value = {"installed": True}
    fake_crop_service.generate_crop.return_value = {
        "crop_image": Image.new("RGB", (18, 20), color="green"),
        "box": (2, 3, 20, 23),
        "reason": "model_selected",
    }
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    monkeypatch.setattr(
        hq_module.frigate_client,
        "get_event_with_error",
        AsyncMock(return_value=({"data": {"box": [20, 10, 30, 20]}}, None)),
    )

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_hint_first"
        return b"clip-bytes", None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: frame_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_hint_first")

    assert result == "bird_crop_replaced"
    fake_crop_service.generate_crop.assert_not_called()
    cached = await cache_service.get_snapshot("evt_hint_first")
    assert cached is not None
    with Image.open(BytesIO(cached)) as img:
        assert img.size == (52, 34)


@pytest.mark.asyncio
async def test_process_event_ignores_legacy_model_priority_when_frigate_hint_is_available(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_model_first", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(settings.classification, "bird_crop_source_priority", "crop_model_first", raising=False)

    frame_bytes = _jpeg_bytes("blue", size=(100, 80))
    fake_crop_service = MagicMock()
    fake_crop_service.expand_ratio = 0.0
    fake_crop_service.min_crop_size = 1
    fake_crop_service.get_status.return_value = {"installed": True}
    fake_crop_service.generate_crop.return_value = {
        "crop_image": Image.new("RGB", (18, 20), color="green"),
        "box": (2, 3, 20, 23),
        "reason": "model_selected",
    }
    monkeypatch.setattr(hq_module, "bird_crop_service", fake_crop_service)

    monkeypatch.setattr(
        hq_module.frigate_client,
        "get_event_with_error",
        AsyncMock(return_value=({"data": {"box": [20, 10, 30, 20]}}, None)),
    )

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_model_first"
        return b"clip-bytes", None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes, *_args: frame_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_model_first")

    assert result == "bird_crop_replaced"
    fake_crop_service.generate_crop.assert_not_called()
    cached = await cache_service.get_snapshot("evt_model_first")
    assert cached is not None
    with Image.open(BytesIO(cached)) as img:
        assert img.size == (52, 34)


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
    event_data = {
        "start_time": 100.0,
        "data": {
            "box": [0.1, 0.2, 0.3, 0.4],
            "path_data": [[[0.2, 0.4], 100.0]],
        },
    }
    hq_module.high_quality_snapshot_service._crop_event_hints["evt_recording_fallback"] = event_data

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
        "generate_snapshot_candidates_from_clip_bytes",
        AsyncMock(return_value={}),
    )
    extraction_call = {}

    def fake_extract(clip_bytes, received_event_data=None, clip_variant="event"):
        extraction_call.update(
            clip_bytes=clip_bytes,
            event_data=received_event_data,
            clip_variant=clip_variant,
        )
        return b"derived-from-recording:" + clip_bytes

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        fake_extract,
    )
    crop_call = {}

    def fake_crop(event_id, image_bytes, received_event_data=None):
        crop_call.update(event_id=event_id, event_data=received_event_data)
        return image_bytes, False

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_maybe_crop_snapshot_bytes", fake_crop)

    result = await hq_module.high_quality_snapshot_service.process_event("evt_recording_fallback")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_recording_fallback") == b"derived-from-recording:" + (b"r" * 1024)
    assert extraction_call == {
        "clip_bytes": b"r" * 1024,
        "event_data": None,
        "clip_variant": "recording",
    }
    assert crop_call == {"event_id": "evt_recording_fallback", "event_data": None}


@pytest.mark.asyncio
async def test_process_event_uses_final_frigate_snapshot_when_all_clip_sources_are_missing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_final_only", b"initial-frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)

    final_bytes = _jpeg_bytes("green", size=(96, 64))
    final_candidate = {
        "candidate_id": "evt_final_only__full_frame__final",
        "image_bytes": final_bytes,
        "source_mode": "full_frame",
        "clip_variant": "frigate_snapshot",
        "snapshot_source": "hq_candidate_full_frame",
        "selected": True,
    }
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        AsyncMock(return_value=(None, "clip_not_found")),
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_load_recording_clip_bytes",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_load_event_data_for_crop",
        AsyncMock(return_value={"end_time": 105.0, "data": {"box": [0.1, 0.2, 0.3, 0.4]}}),
    )
    load_final = AsyncMock(return_value=[final_candidate])
    score_and_select = AsyncMock(
        return_value={
            "selected_candidate": final_candidate,
            "candidates": [final_candidate],
        }
    )
    persist = AsyncMock()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_load_final_frigate_snapshot_candidates", load_final)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service, "_score_and_select_snapshot_candidates", score_and_select
    )
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_persist_snapshot_candidates", persist)

    result = await hq_module.high_quality_snapshot_service.process_event("evt_final_only")

    assert result == "replaced"
    load_final.assert_awaited_once()
    score_and_select.assert_awaited_once_with("evt_final_only", [final_candidate])
    persist.assert_awaited_once_with("evt_final_only", [final_candidate])
    assert await cache_service.get_snapshot("evt_final_only") == final_bytes


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
async def test_schedule_snapshot_replacement_rejects_when_bounded_overflow_is_full(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    for event_id in ("evt-bound-1", "evt-bound-2", "evt-bound-3"):
        await cache_service.cache_snapshot(event_id, b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    service = hq_module.high_quality_snapshot_service
    monkeypatch.setattr(service, "MAX_PENDING_QUEUE", 1, raising=False)
    monkeypatch.setattr(service, "MAX_DEFERRED_EVENTS", 1, raising=False)
    await service.reset_state()
    monkeypatch.setattr(service, "_ensure_workers_started", lambda: None)

    assert service.schedule_replacement("evt-bound-1") is True
    assert service.schedule_replacement("evt-bound-2") is True
    assert service.schedule_replacement("evt-bound-3") is False

    status = service.get_status()
    assert status["queue_size"] == 1
    assert status["deferred"] == 1
    assert status["queue_full_rejections"] == 1
    assert "evt-bound-3" not in service._crop_event_hints


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
async def test_replace_from_clip_bytes_satisfies_queued_event_without_duplicate_worker_processing(
    tmp_path, monkeypatch
):
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


# ---------------------------------------------------------------------------
# Top-frame preference tests (Task 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_candidates_uses_stored_top_frames_when_present(tmp_path, monkeypatch):
    """When persisted top frames exist for an event, those frame indices must be used."""
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)

    stored_frames = [
        {
            "frame_index": 42,
            "frame_offset_seconds": 1.68,
            "frame_score": 0.91,
            "top_label": "Robin",
            "top_score": 0.91,
            "rank": 1,
            "clip_variant": "event",
        },
        {
            "frame_index": 38,
            "frame_offset_seconds": 1.52,
            "frame_score": 0.83,
            "top_label": "Robin",
            "top_score": 0.83,
            "rank": 2,
            "clip_variant": "event",
        },
    ]

    async def fake_load_preferred(event_id, *, clip_variant):
        return [f["frame_index"] for f in stored_frames]

    monkeypatch.setattr(service, "_load_preferred_frame_indices", fake_load_preferred)

    used_indices: list[int] = []

    def fake_extract(clip_path, *, event_id, event_data=None, clip_variant="event", override_frame_indices=None):
        if override_frame_indices is not None:
            used_indices.extend(override_frame_indices)
        return []

    monkeypatch.setattr(service, "_extract_snapshot_candidate_payloads_from_clip_path", fake_extract)

    clip_bytes = _jpeg_bytes("blue")  # not a real clip but enough for the temp file write
    await service.generate_snapshot_candidates_from_clip_bytes(
        "evt-top-frame-use",
        clip_bytes,
        clip_variant="event",
    )

    assert 42 in used_indices
    assert 38 in used_indices


@pytest.mark.asyncio
async def test_generate_candidates_falls_back_when_no_stored_top_frames(tmp_path, monkeypatch):
    """When no stored top frames exist, _candidate_frame_indices fallback is used."""
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)

    async def fake_load_preferred(event_id, *, clip_variant):
        return None  # no stored frames

    monkeypatch.setattr(service, "_load_preferred_frame_indices", fake_load_preferred)

    used_override: list = []

    def fake_extract(clip_path, *, event_id, event_data=None, clip_variant="event", override_frame_indices=None):
        used_override.append(override_frame_indices)
        return []

    monkeypatch.setattr(service, "_extract_snapshot_candidate_payloads_from_clip_path", fake_extract)

    clip_bytes = _jpeg_bytes("red")
    await service.generate_snapshot_candidates_from_clip_bytes(
        "evt-no-top-frames",
        clip_bytes,
        clip_variant="event",
    )

    assert len(used_override) == 1
    assert used_override[0] is None  # fallback: no override, use default logic
