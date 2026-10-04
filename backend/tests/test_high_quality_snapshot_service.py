import asyncio
import hashlib
from contextlib import asynccontextmanager
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
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.utils.api_datetime import utc_naive_now
from app.services import high_quality_snapshot_service as hq_module
from app.services import media_cache as media_cache_module


async def _removed_photo_choices(monkeypatch, event_id, *, changed=False, remaining=True, legacy=False):
    service = hq_module.HighQualitySnapshotService()
    removed_bytes = _jpeg_bytes("red", size=(200, 200))
    choices = [
        {
            "candidate_id": "removed-photo",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": 1,
            "crop_box": [0, 0, 200, 200],
            "detector_box": [40, 40, 120, 120],
            "crop_confidence": 0.9,
            "classifier_label": "House Finch",
            "classifier_score": 0.99,
            "ranking_score": 0.99,
            "frame_width": 640,
            "frame_height": 480,
            "image_width": 200,
            "image_height": 200,
            "image_bytes": removed_bytes,
            "image_ref": event_id + "__removed_choice__image",
        },
        {
            "candidate_id": "chosen-photo",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": 1,
            "crop_box": [300, 0, 500, 200],
            "detector_box": [340, 40, 420, 120],
            "crop_confidence": 0.9,
            "classifier_label": "House Finch",
            "classifier_score": 0.9,
            "ranking_score": 0.9,
            "frame_width": 640,
            "frame_height": 480,
            "image_width": 200,
            "image_height": 200,
            "image_bytes": _jpeg_bytes("green", size=(200, 200)),
            "selected": True,
        },
        {
            "candidate_id": "original-scene",
            "source_mode": "full_frame",
            "clip_variant": "event",
            "frame_index": 1,
            "crop_box": None,
            "classifier_label": "House Finch",
            "classifier_score": 0.8,
            "ranking_score": 0.4,
            "frame_width": 640,
            "frame_height": 480,
            "image_width": 640,
            "image_height": 480,
            "image_bytes": _jpeg_bytes("white", size=(640, 480)),
        },
    ]
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event_id,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(
            event_id,
            [
                {**choice, "content_sha256": None if legacy else hashlib.sha256(choice["image_bytes"]).hexdigest()}
                for choice in choices
            ],
        )
        assert await repo.dismiss_snapshot_candidate(event_id, "removed-photo", True)
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda candidate: dict(candidate)))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"House Finch"}))
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_recheck_weak_count_candidates", AsyncMock(return_value=[]))
    if changed:
        choices[0]["image_bytes"] = _jpeg_bytes("purple", size=(200, 200))
    return service, choices if remaining else choices[:1], removed_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize("changed,restored", [(False, False), (True, False), (False, True)])
async def test_regeneration_respects_removed_photo_content_without_losing_count_evidence(
    monkeypatch, changed, restored
):
    event = "dismissed-rescan-" + str(changed) + str(restored)
    service, choices, _ = await _removed_photo_choices(monkeypatch, event, changed=changed)
    if restored:
        async with get_db() as db:
            assert await DetectionRepository(db).dismiss_snapshot_candidate(event, "removed-photo", False)
    bundle = await service._score_and_select_snapshot_candidates(event, choices)
    assert bundle["selected_candidate"]["candidate_id"] == ("removed-photo" if changed or restored else "chosen-photo")
    assert {row["candidate_id"] for row in bundle["candidates"]} == {
        "removed-photo",
        "chosen-photo",
        "original-scene",
    }
    assert {bird.candidate_id for bird in bundle["bird_selection"].birds} == {"removed-photo", "chosen-photo"}
    assert bundle["bird_selection"].full_frame_candidate_id == "original-scene"


@pytest.mark.asyncio
async def test_only_removed_photo_preserves_the_current_manual_photograph(tmp_path, monkeypatch):
    event = "dismissed-only-rescan"
    cache = _make_cache_service(tmp_path, monkeypatch)
    service, choices, _ = await _removed_photo_choices(monkeypatch, event, remaining=False)
    chosen_bytes = _jpeg_bytes("green", size=(200, 200))
    await cache.cache_snapshot(event, chosen_bytes, source="high_quality_bird_crop")
    assert await cache.replace_snapshot(
        event, chosen_bytes, source="high_quality_bird_crop", manual_selection=True, manual_candidate_id="chosen-photo"
    )
    monkeypatch.setattr(service, "enabled", lambda: True)
    monkeypatch.setattr(service, "_load_event_clip", AsyncMock(return_value=(b"clip", None)))
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_apply_classification_refinement", AsyncMock(return_value=False))

    async def generate(*args, **kwargs):
        return await service._score_and_select_snapshot_candidates(event, choices)

    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_bytes", generate)
    outcome = await service._process_event_once(event, manual_override=True)
    assert outcome == "bird_presence_unconfirmed"
    assert await cache.get_snapshot(event) == chosen_bytes
    assert (await cache.get_snapshot_metadata(event))["manual_selection"] is True
    async with get_db() as db:
        listed = await DetectionRepository(db).list_snapshot_candidates(event)
        assert next(row for row in listed if row["candidate_id"] == "removed-photo")["photo_hidden"]
        birds = await hq_module.BirdObservationRepository(db).list_for_event(event)
        assert len(birds) == 1 and birds[0]["candidate_id"] == "removed-photo"


@pytest.mark.asyncio
async def test_raw_photo_fallback_cannot_reapply_removed_content(monkeypatch):
    event = "dismissed-fallback"
    service, choices, removed_bytes = await _removed_photo_choices(monkeypatch, event)
    monkeypatch.setattr(service, "_automatic_crop_enabled", lambda: False)
    monkeypatch.setattr(service, "_maybe_crop_snapshot_bytes", lambda *args: (removed_bytes, True))
    monkeypatch.setattr(
        service,
        "_score_snapshot_candidate",
        AsyncMock(
            return_value={
                **choices[0],
                "crop_strategy": "detector_supported",
            }
        ),
    )
    image, applied = await service._identity_safe_fallback_crop(event, b"raw-frame", None)
    assert image is None and applied is False


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_legacy_removed_photo_uses_retained_pixels_to_guard_fallback(tmp_path, monkeypatch, changed):
    event = "dismissed-legacy-fallback-" + str(changed)
    cache = _make_cache_service(tmp_path, monkeypatch)
    service, choices, removed_bytes = await _removed_photo_choices(monkeypatch, event, legacy=True)
    await cache.cache_snapshot(choices[0]["image_ref"], removed_bytes, source="snapshot_candidate")
    crop = _jpeg_bytes("purple", size=(200, 200)) if changed else removed_bytes
    monkeypatch.setattr(service, "_automatic_crop_enabled", lambda: False)
    monkeypatch.setattr(service, "_maybe_crop_snapshot_bytes", lambda *args: (crop, True))
    fallback = {**choices[0], "crop_strategy": "detector_supported"}
    fallback.pop("candidate_id")
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(return_value=fallback))
    image, applied = await service._identity_safe_fallback_crop(event, b"raw-frame", None)
    assert applied is changed
    assert image == (crop if changed else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_legacy_photo_removal_survives_identical_persistence_and_next_rescan(tmp_path, monkeypatch, changed):
    event = "dismissed-legacy-persist-" + str(changed)
    cache = _make_cache_service(tmp_path, monkeypatch)
    service, choices, removed_bytes = await _removed_photo_choices(monkeypatch, event, legacy=True, changed=changed)
    await cache.cache_snapshot(choices[0]["image_ref"], removed_bytes, source="snapshot_candidate")
    bundle = await service._score_and_select_snapshot_candidates(event, choices)
    await service._persist_snapshot_candidates(event, bundle["candidates"])
    async with get_db() as db:
        stored = await DetectionRepository(db).list_snapshot_candidates(event)
        removed = next(row for row in stored if row["candidate_id"] == "removed-photo")
        assert removed["photo_hidden"] is not changed
        assert removed["content_sha256"] == hashlib.sha256(choices[0]["image_bytes"]).hexdigest()
    again = await service._score_and_select_snapshot_candidates(event, choices)
    assert again["selected_candidate"]["candidate_id"] == ("removed-photo" if changed else "chosen-photo")


def test_job_snapshot_keeps_timestamp_stable_between_polls():
    service = hq_module.HighQualitySnapshotService()
    service._queued_ids.add("evt-stable")

    first = service.get_jobs_snapshot()[0]
    second = service.get_jobs_snapshot()[0]

    assert first["created_at"] is not None
    assert first["created_at"] == second["created_at"]
    assert first["updated_at"] == second["updated_at"]


def _jpeg_bytes(color: str, size: tuple[int, int] = (32, 32), *, quality: int = 92) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


async def _mock_supported_photo_bundle(monkeypatch, method, event_id):
    """Queue/cache tests isolate the already-checked photo selection boundary."""
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event_id,
                camera_name="test",
            )
        )
    candidate = {
        "candidate_id": "supported-photo",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 2,
        "image_bytes": b"derived-bytes",
        "crop_strategy": "detector_supported",
        "crop_confidence": 0.9,
        "selected": True,
    }
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        method,
        AsyncMock(
            return_value={
                "selected_candidate": candidate,
                "candidates": [candidate],
                "photo_outcome": None,
            }
        ),
    )


def _clip_file(tmp_path):
    """The clip reaches the service as a file the caller owns (#341)."""
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"clip-bytes")
    return path


def test_final_frigate_model_crop_keeps_detector_confidence_and_tight_box():
    service = hq_module.HighQualitySnapshotService()
    payload = service._build_final_snapshot_candidate_payload(
        "evt-final",
        Image.new("RGB", (160, 160), "green"),
        source_mode="model_crop",
        frame_size=(640, 480),
        crop_result={
            "box": (10, 20, 170, 180),
            "detector_box": (50, 60, 120, 130),
            "confidence": 0.12,
            "observation_boxes": [{"box": (50, 60, 120, 130), "confidence": 0.12}],
        },
    )

    assert payload["crop_confidence"] == 0.12
    assert payload["crop_box"] == (10, 20, 170, 180)
    assert payload["detector_box"] == (50, 60, 120, 130)
    assert payload["observation_boxes"] == [{"box": (50, 60, 120, 130), "confidence": 0.12}]


@pytest.mark.asyncio
async def test_whole_frame_count_is_not_limited_by_photo_crop_choices(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    boxes = [{"box": (index * 60, 0, index * 60 + 40, 40), "confidence": 0.9 - index * 0.02} for index in range(10)]
    monkeypatch.setattr(hq_module.bird_crop_service, "detect_observation_boxes", lambda image, **kwargs: boxes)
    scored = [
        {
            "candidate_id": "whole",
            "source_mode": "full_frame",
            "clip_variant": "event",
            "frame_index": 2,
            "image_bytes": _jpeg_bytes("white", size=(640, 64)),
        },
        {
            "candidate_id": "crop-0",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": 2,
            "detector_box": (0, 0, 40, 40),
            "classifier_label": "House Finch",
            "classifier_score": 0.91,
            "crop_confidence": 0.9,
        },
    ]

    observed = await service._detect_count_candidates(scored)
    selection = hq_module.select_bird_observations(scored + observed, selected_candidate=scored[1])

    assert len(selection.birds) == 10
    assert selection.full_frame_candidate_id == "whole"
    assert selection.birds[0].species == "House Finch"
    assert all(bird.species == "Unknown Bird" for bird in selection.birds[1:])


@pytest.mark.asyncio
async def test_count_reuses_photo_crop_detector_boxes_without_a_second_frame_scan(monkeypatch):
    service = hq_module.HighQualitySnapshotService()

    def unexpected_rescan(_image, **kwargs):
        raise AssertionError("the photo crop already supplied every detector box")

    monkeypatch.setattr(hq_module.bird_crop_service, "detect_observation_boxes", unexpected_rescan)
    scored = [
        {
            "candidate_id": "whole",
            "source_mode": "full_frame",
            "clip_variant": "event",
            "frame_index": 2,
            "image_bytes": _jpeg_bytes("white"),
        },
        {
            "candidate_id": "crop-0",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": 2,
            "detector_box": (0, 0, 40, 40),
            "observation_boxes": [
                {"box": (0, 0, 40, 40), "confidence": 0.8},
                {"box": (80, 0, 120, 40), "confidence": 0.7},
            ],
        },
    ]

    observations = await service._detect_count_candidates(scored)

    assert len(observations) == 2
    assert [item["crop_box"] for item in observations] == [(0, 0, 40, 40), (80, 0, 120, 40)]


@pytest.mark.asyncio
async def test_group_sized_detector_box_does_not_inherit_a_small_birds_species():
    service = hq_module.HighQualitySnapshotService()
    scored = [
        {"candidate_id": "whole", "source_mode": "full_frame", "clip_variant": "event", "frame_index": 2},
        {
            "candidate_id": "crop",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": 2,
            "detector_box": (20, 20, 60, 60),
            "classifier_label": "House Finch",
            "classifier_score": 0.9,
            "observation_boxes": [
                {"box": (20, 20, 60, 60), "confidence": 0.8},
                {"box": (0, 0, 200, 200), "confidence": 0.7},
            ],
        },
    ]

    observed = await service._detect_count_candidates(scored)

    assert observed[0]["classifier_label"] == "House Finch"
    assert observed[1]["classifier_label"] is None


@pytest.mark.asyncio
async def test_regeneration_retains_whole_frame_for_manually_reviewed_bird(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    old_full = {
        "candidate_id": "old-full",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 1,
        "image_ref": "old-full-image",
        "thumbnail_ref": "old-full-thumb",
        "ranking_score": 0.4,
    }
    old_crop = {
        "candidate_id": "old-crop",
        "source_mode": "model_crop",
        "clip_variant": "event",
        "frame_index": 1,
        "image_ref": "old-crop-image",
        "thumbnail_ref": "old-crop-thumb",
        "ranking_score": 0.6,
    }
    new_full = {
        "candidate_id": "new-full",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 2,
        "image_ref": "new-full-image",
        "thumbnail_ref": "new-full-thumb",
        "ranking_score": 0.7,
    }
    repo = MagicMock()
    repo.list_snapshot_candidates = AsyncMock(return_value=[old_full, old_crop])
    repo.replace_snapshot_candidates = AsyncMock()
    bird_repo = MagicMock()
    bird_repo.list_for_event = AsyncMock(
        return_value=[{"clip_variant": "event", "frame_index": 1, "manual_species": True, "is_hidden": False}]
    )

    @asynccontextmanager
    async def fake_db():
        yield object()

    monkeypatch.setattr(hq_module, "get_db", fake_db)
    monkeypatch.setattr(hq_module, "DetectionRepository", lambda db: repo)
    monkeypatch.setattr(hq_module, "BirdObservationRepository", lambda db: bird_repo)
    delete_snapshot = AsyncMock()
    delete_thumbnail = AsyncMock()
    monkeypatch.setattr(hq_module.media_cache, "delete_snapshot", delete_snapshot)
    monkeypatch.setattr(hq_module.media_cache, "delete_thumbnail", delete_thumbnail)

    await service._persist_snapshot_candidates("evt", [new_full])

    saved = repo.replace_snapshot_candidates.await_args.args[1]
    assert {item["candidate_id"] for item in saved} == {"new-full", "old-full", "old-crop"}
    delete_snapshot.assert_not_awaited()
    delete_thumbnail.assert_not_awaited()


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
async def test_replace_from_clip_path_persists_and_selects_ranked_snapshot_candidates(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_candidates", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)

    async def fake_generate(event_id, clip_path, event_data=None, clip_variant="event", clip_start_timestamp=None):
        assert event_id == "evt_candidates"
        # The clip reaches candidate generation as a file, never as bytes (#341).
        assert Path(clip_path).read_bytes() == b"clip-bytes"
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
        "generate_snapshot_candidates_from_clip_path",
        fake_generate,
        raising=False,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_persist_snapshot_candidates",
        fake_persist,
        raising=False,
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_path(
        "evt_candidates", _clip_file(tmp_path)
    )

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


def test_extract_crop_event_hints_keeps_frigate_retention_signals():
    service = hq_module.HighQualitySnapshotService()

    hints = service._extract_crop_event_hints(
        {
            "start_time": 100.0,
            "end_time": 101.0,
            "data": {"box": [10, 20, 30, 40]},
            "position_changes": 0,
            "has_snapshot": False,
            "has_clip": False,
        }
    )

    assert hints is not None
    assert hints["position_changes"] == 0
    assert hints["has_snapshot"] is False
    assert hints["has_clip"] is False


def test_extract_crop_event_hints_keeps_retention_signals_without_localization_data():
    service = hq_module.HighQualitySnapshotService()

    hints = service._extract_crop_event_hints(
        {
            "end_time": 101.0,
            "position_changes": 0,
            "has_snapshot": False,
            "has_clip": False,
        }
    )

    assert hints == {
        "end_time": 101.0,
        "position_changes": 0,
        "has_snapshot": False,
        "has_clip": False,
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


def test_candidate_generation_keeps_multiple_model_birds_without_changing_visit_count(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    monkeypatch.setattr(service, "_crop_from_event_hints", lambda image, event_data: None)

    class _CropService:
        def generate_classification_candidate_crops(self, image, *, max_crops, raise_on_error=False):
            assert max_crops == hq_module.HQ_MAX_MODEL_CROPS_PER_FRAME
            return [
                {"crop_image": image.crop((20, 20, 220, 220)), "box": (20, 20, 220, 220), "reason": "selected"},
                {"crop_image": image.crop((320, 20, 520, 220)), "box": (320, 20, 520, 220), "reason": "selected"},
            ]

    monkeypatch.setattr(hq_module, "bird_crop_service", _CropService())
    image = Image.new("RGB", (600, 400))
    candidates = service._candidate_images_for_frame(image, event_data=None, event_id="evt-two-birds")

    assert [source for source, _image, _result in candidates] == ["full_frame", "model_crop", "model_crop"]
    assert service._build_snapshot_candidate_id(
        "evt-two-birds", frame_index=3, source_mode="model_crop", crop_index=0
    ) != service._build_snapshot_candidate_id("evt-two-birds", frame_index=3, source_mode="model_crop", crop_index=1)


def test_pre_cropped_frigate_fallback_requires_matching_species_evidence():
    service = hq_module.HighQualitySnapshotService()
    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "pre-cropped",
                "source_mode": "full_frame",
                "input_is_cropped": True,
                "classifier_label": "Northern Cardinal",
                "ranking_score": 0.9,
            }
        ],
        expected_labels={"Black-capped Chickadee"},
    )
    assert selected is None


def test_pre_cropped_frigate_fallback_without_classifier_evidence_is_not_selected():
    service = hq_module.HighQualitySnapshotService()
    selected = service._select_canonical_snapshot_candidate(
        [{"candidate_id": "pre-cropped", "source_mode": "full_frame", "input_is_cropped": True, "ranking_score": 0.9}],
        expected_labels={"Black-capped Chickadee"},
    )
    assert selected is None


@pytest.mark.parametrize("reuse_scene", [False, True])
def test_clip_candidate_extraction_keeps_separate_birds_from_one_frame(monkeypatch, tmp_path, reuse_scene):
    service = hq_module.HighQualitySnapshotService()
    frame = np.zeros((300, 500, 3), dtype=np.uint8)
    reads = []

    class FakeCapture:
        def isOpened(self):
            return True

        def get(self, prop):
            return 1 if prop == hq_module.cv2.CAP_PROP_FRAME_COUNT else 30

        def set(self, _prop, _value):
            pass

        def read(self):
            reads.append(0)
            return True, frame

        def release(self):
            pass

    monkeypatch.setattr(hq_module.cv2, "VideoCapture", lambda _path: FakeCapture())
    monkeypatch.setattr(service, "_candidate_frame_indices", lambda **_kwargs: [0])
    monkeypatch.setattr(
        service,
        "_candidate_images_for_frame",
        lambda image, **_kwargs: [
            ("full_frame", image, None),
            ("model_crop", image.crop((0, 0, 200, 200)), {"box": (0, 0, 200, 200)}),
            ("model_crop", image.crop((280, 0, 480, 200)), {"box": (280, 0, 480, 200)}),
        ],
    )

    clip = tmp_path / "example.mp4"
    clip.write_bytes(b"test decoder owns pixels")
    cache_kwargs = {}
    if reuse_scene:
        from app.services.video_scene_cache import VideoSceneCache

        evidence = {
            "frame_index": 0,
            "frame_width": 500,
            "frame_height": 300,
            "frame_offset_seconds": 0.0,
            "score": 0.9,
        }
        directory = tmp_path / "scenes"
        directory.mkdir()
        cache = VideoSceneCache()
        cache.retain(evidence, Image.fromarray(frame))
        assert cache.write(directory, clip, "event", evidence)
        loaded = VideoSceneCache()
        assert loaded.load(directory, clip, "event")
        cache_kwargs["scene_cache"] = loaded
    candidates = service._extract_snapshot_candidate_payloads_from_clip_path(
        clip, event_id="evt-two-birds", **cache_kwargs
    )

    assert len(candidates) == 3
    assert len({candidate["candidate_id"] for candidate in candidates}) == 3
    assert [candidate["crop_box"] for candidate in candidates[1:]] == [
        (0, 0, 200, 200),
        (280, 0, 480, 200),
    ]
    assert len(reads) == int(not reuse_scene)


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


def test_restore_frigate_hint_box_preserves_normalized_rest_xywh_contract():
    service = hq_module.HighQualitySnapshotService()

    restored = service._restore_frigate_hint_box(
        [0.30703125, 0.22430555555555556, 0.0484375, 0.06527777777777778],
        (2560, 1440),
    )

    assert restored == (786, 323, 910, 417)


def test_restore_frigate_hint_box_treats_mqtt_pixel_coordinates_as_xyxy():
    service = hq_module.HighQualitySnapshotService()

    restored = service._restore_frigate_hint_box(
        [786, 323, 910, 417],
        (2560, 1440),
    )

    assert restored == (786, 323, 910, 417)


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
        clip_start_timestamp=100.0,
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
        clip_start_timestamp=100.0,
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
        clip_start_timestamp=100.0,
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
        clip_start_timestamp=1784561844.911783,
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

    first = service._event_hints_for_frame(
        event_data, frame_offset_seconds=0.0, clip_variant="event", clip_start_timestamp=100.0
    )
    last = service._event_hints_for_frame(
        event_data, frame_offset_seconds=6.0, clip_variant="event", clip_start_timestamp=100.0
    )
    stale = service._event_hints_for_frame(
        event_data, frame_offset_seconds=3.0, clip_variant="event", clip_start_timestamp=100.0
    )
    recording = service._event_hints_for_frame(event_data, frame_offset_seconds=6.0, clip_variant="recording")

    assert first is not event_data
    # Frigate path_data points are the tracked box's bottom-centre, not its centre.
    assert first["data"]["box"] == pytest.approx([0.10, 0.15, 0.20, 0.10])
    assert last["data"]["box"] == pytest.approx([0.60, 0.65, 0.20, 0.10])
    assert stale is None
    assert recording is None


def test_event_hint_withholds_pixel_tracking_size_when_detect_resolution_is_unknown():
    service = hq_module.HighQualitySnapshotService()
    event_data = {
        "start_time": 100.0,
        "data": {
            "box": [10, 20, 30, 40],
            "path_data": [[[0.5, 0.6], 100.0]],
        },
    }

    tracked = service._event_hints_for_frame(
        event_data,
        frame_offset_seconds=0.0,
        clip_variant="event",
        clip_start_timestamp=100.0,
        image_size=(100, 100),
    )

    assert tracked is None


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
        clip_start_timestamp=100.0,
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
async def test_final_clean_snapshot_keeps_multiple_bird_crops_when_clip_is_unavailable(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    monkeypatch.setattr(
        hq_module.frigate_client,
        "get_clean_snapshot_with_error",
        AsyncMock(return_value=(_jpeg_bytes("blue", size=(600, 400)), None)),
    )

    class _CropService:
        def generate_classification_candidate_crops(self, image, *, max_crops, search_box, raise_on_error=False):
            assert max_crops == hq_module.HQ_MAX_MODEL_CROPS_PER_FRAME
            assert search_box is not None
            return [
                {"crop_image": image.crop((20, 20, 220, 220)), "box": (20, 20, 220, 220)},
                {"crop_image": image.crop((320, 20, 520, 220)), "box": (320, 20, 520, 220)},
            ]

    monkeypatch.setattr(hq_module, "bird_crop_service", _CropService())

    candidates = await service._load_final_frigate_snapshot_candidates(
        "evt-two-birds", {"end_time": 102.0, "snapshot": {"box": [0.1, 0.1, 0.4, 0.5]}}
    )

    assert [candidate["source_mode"] for candidate in candidates] == [
        "full_frame",
        "frigate_hint_crop",
        "model_crop",
        "model_crop",
    ]
    assert len({candidate["candidate_id"] for candidate in candidates}) == 4
    assert [candidate["crop_box"] for candidate in candidates[2:]] == [
        (20, 20, 220, 220),
        (320, 20, 520, 220),
    ]


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


def test_select_canonical_snapshot_candidate_can_use_second_bird_crop():
    service = hq_module.HighQualitySnapshotService()
    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "whole-scene",
                "source_mode": "full_frame",
                "ranking_score": 0.3,
                "classifier_label": "Northern Cardinal",
            },
            {
                "candidate_id": "first-bird",
                "source_mode": "model_crop",
                "ranking_score": 0.9,
                "classifier_label": "Northern Cardinal",
                "image_width": 240,
                "image_height": 220,
            },
            {
                "candidate_id": "tracked-bird",
                "source_mode": "model_crop",
                "ranking_score": 0.7,
                "classifier_label": "Black-capped Chickadee",
                "image_width": 240,
                "image_height": 220,
            },
        ],
        expected_labels={"Black-capped Chickadee"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "tracked-bird"


def test_select_canonical_snapshot_candidate_falls_back_to_full_frame_when_every_label_conflicts():
    service = hq_module.HighQualitySnapshotService()

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "conflicting-full",
                "source_mode": "full_frame",
                "ranking_score": 0.20,
                "image_width": 2560,
                "image_height": 1440,
                "classifier_label": "Cyanistes caeruleus",
            },
            {
                "candidate_id": "conflicting-crop",
                "source_mode": "frigate_hint_crop",
                "ranking_score": 0.95,
                "image_width": 1566,
                "image_height": 717,
                "classifier_label": "Cyanistes caeruleus",
            },
        ],
        expected_labels={"Prunella modularis"},
    )

    assert selected is not None
    assert selected["candidate_id"] == "conflicting-full"


def test_select_canonical_snapshot_candidate_rejects_conflicting_crop_without_full_frame():
    service = hq_module.HighQualitySnapshotService()

    selected = service._select_canonical_snapshot_candidate(
        [
            {
                "candidate_id": "conflicting-crop",
                "source_mode": "frigate_hint_crop",
                "ranking_score": 0.95,
                "image_width": 320,
                "image_height": 240,
                "classifier_label": "Cyanistes caeruleus",
            }
        ],
        expected_labels={"Prunella modularis"},
    )

    assert selected is None


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


def test_persisted_candidates_keep_whole_frame_for_selected_crop():
    service = hq_module.HighQualitySnapshotService()
    ranked = [
        {
            "candidate_id": f"crop-{index}",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": index,
            "ranking_score": 1.0 - index * 0.01,
        }
        for index in range(hq_module.HQ_MAX_PERSISTED_CANDIDATES)
    ]
    selected = {
        "candidate_id": "chosen-crop",
        "source_mode": "model_crop",
        "clip_variant": "event",
        "frame_index": 42,
        "ranking_score": 0.2,
    }
    matching_full = {
        "candidate_id": "chosen-whole-frame",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 42,
        "ranking_score": 0.1,
    }
    unrelated_full = {
        "candidate_id": "other-whole-frame",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 1,
        "ranking_score": 0.3,
    }
    ranked.extend([unrelated_full, selected, matching_full])

    persisted = service._select_persisted_candidates(ranked, selected_candidate=selected)

    assert {"chosen-crop", "chosen-whole-frame"} <= {item["candidate_id"] for item in persisted}


def test_persisted_candidates_keep_distinct_bird_when_first_slots_repeat_one_species():
    service = hq_module.HighQualitySnapshotService()
    ranked = [
        {
            "candidate_id": f"cardinal-{index}",
            "source_mode": "model_crop",
            "classifier_label": "Northern Cardinal",
            "ranking_score": 1.0 - index * 0.01,
        }
        for index in range(hq_module.HQ_MAX_PERSISTED_CANDIDATES)
    ]
    ranked.append(
        {
            "candidate_id": "chickadee",
            "source_mode": "model_crop",
            "classifier_label": "Black-capped Chickadee",
            "ranking_score": 0.7,
        }
    )

    persisted = service._select_persisted_candidates(ranked, selected_candidate=ranked[0])

    assert len(persisted) == hq_module.HQ_MAX_PERSISTED_CANDIDATES
    assert "chickadee" in {candidate["candidate_id"] for candidate in persisted}


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


def test_persisted_candidates_keep_every_bird_crop_from_final_still():
    service = hq_module.HighQualitySnapshotService()
    ranked = [
        {
            "candidate_id": f"clip-{index}",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "classifier_label": "Northern Cardinal",
            "ranking_score": 1.0 - index * 0.01,
        }
        for index in range(hq_module.HQ_MAX_PERSISTED_CANDIDATES)
    ]
    ranked.extend(
        {
            "candidate_id": f"final-bird-{index}",
            "source_mode": "model_crop",
            "clip_variant": "frigate_snapshot",
            "classifier_label": "Northern Cardinal",
            "ranking_score": 0.4 - index * 0.01,
        }
        for index in range(hq_module.HQ_MAX_MODEL_CROPS_PER_FRAME)
    )
    ranked.append(
        {
            "candidate_id": "final-whole",
            "source_mode": "full_frame",
            "clip_variant": "frigate_snapshot",
            "ranking_score": 0.1,
        }
    )

    persisted = service._select_persisted_candidates(ranked, selected_candidate=ranked[0])

    persisted_ids = {candidate["candidate_id"] for candidate in persisted}
    assert len(persisted) == hq_module.HQ_MAX_PERSISTED_CANDIDATES
    assert {f"final-bird-{index}" for index in range(hq_module.HQ_MAX_MODEL_CROPS_PER_FRAME)} <= persisted_ids
    assert "final-whole" in persisted_ids


def test_raw_photo_crop_does_not_treat_event_hint_as_bird_presence(monkeypatch):
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
        {"data": {"box": [5, 5, 25, 25]}},
    )

    assert crop_applied is False
    fake_crop_service.generate_crop.assert_not_called()
    with Image.open(BytesIO(cropped_bytes)) as img:
        assert img.size == (100, 80)


def test_raw_photo_crop_keeps_original_when_only_an_unverified_hint_exists(monkeypatch):
    """A hint alone cannot certify that a bird is still inside its crop."""
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
        {"data": {"box": [5, 5, 25, 25]}},
    )

    assert crop_applied is False
    fake_crop_service.generate_crop.assert_not_called()
    with Image.open(BytesIO(cropped_bytes)) as img:
        assert img.size == (100, 80)


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
        {"data": {"box": [5, 5, 25, 25]}},
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
    await _mock_supported_photo_bundle(monkeypatch, "generate_snapshot_candidates_from_clip_bytes", "evt_replace")
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
async def test_process_event_preserves_existing_crop_when_only_full_frame_is_available(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    original = _jpeg_bytes("red", size=(32, 32))
    await cache_service.cache_snapshot(
        "evt_preserve_crop",
        original,
        source="frigate_snapshot_cropped",
    )
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)

    async def fake_wait_for_clip(_event_id: str):
        return b"clip-bytes", None

    async def fake_generate(*_args, **_kwargs):
        return {
            "selected_candidate": {
                "candidate_id": "full-frame",
                "image_bytes": _jpeg_bytes("blue", size=(64, 64)),
                "source_mode": "full_frame",
                "snapshot_source": "hq_candidate_full_frame",
            },
            "candidates": [],
        }

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "generate_snapshot_candidates_from_clip_bytes",
        fake_generate,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_persist_snapshot_candidates",
        AsyncMock(),
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_apply_classification_refinement",
        AsyncMock(return_value=False),
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_preserve_crop")

    assert result == "existing_crop_preserved"
    assert await cache_service.get_snapshot("evt_preserve_crop") == original


@pytest.mark.asyncio
async def test_process_event_uses_persisted_hints_when_frigate_event_is_gone(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    persisted_hints = {
        "start_time": 100.0,
        "end_time": 105.0,
        "data": {"box": [20, 10, 50, 30]},
    }
    await cache_service.cache_snapshot(
        "evt_persisted_hint",
        _jpeg_bytes("red"),
        source="frigate_snapshot_cropped",
        event_hints=persisted_hints,
    )
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True, raising=False)

    async def fake_wait_for_clip(_event_id: str):
        return b"clip-bytes", None

    captured: dict[str, object] = {}

    async def fake_generate(_event_id, _clip_bytes, *, event_data=None, clip_variant="event"):
        captured["event_data"] = event_data
        captured["clip_variant"] = clip_variant
        return None

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", fake_wait_for_clip)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service, "_load_event_data_for_crop", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "generate_snapshot_candidates_from_clip_bytes",
        fake_generate,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda *_args: _jpeg_bytes("blue"),
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_maybe_crop_snapshot_bytes",
        lambda _event_id, image_bytes, _event_data: (image_bytes, False),
    )

    await hq_module.high_quality_snapshot_service.process_event("evt_persisted_hint")

    assert captured["event_data"] == persisted_hints


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
        event_data={"data": {"box": [20, 10, 50, 30]}},
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
    assert cached == b"frigate-bytes"


@pytest.mark.asyncio
async def test_process_event_keeps_existing_photo_when_hint_crop_identity_is_unverified(tmp_path, monkeypatch):
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
        AsyncMock(return_value=({"data": {"box": [20, 10, 50, 30]}}, None)),
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

    assert result == "bird_presence_unconfirmed"
    fake_crop_service.generate_crop.assert_not_called()
    cached = await cache_service.get_snapshot("evt_hint_crop")
    assert cached is not None
    assert cached == b"frigate-bytes"
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["outcomes"]["bird_presence_unconfirmed"] == 1
    assert status["last_result"] == {"event_id": "evt_hint_crop", "result": "bird_presence_unconfirmed"}


@pytest.mark.asyncio
async def test_unknown_clip_origin_uses_detector_without_reusing_static_frigate_box(tmp_path, monkeypatch):
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
        AsyncMock(return_value=({"data": {"box": [20, 10, 50, 30]}}, None)),
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

    assert result == "bird_presence_unconfirmed"
    fake_crop_service.generate_crop.assert_called_once()
    cached = await cache_service.get_snapshot("evt_hint_first")
    assert cached is not None
    assert cached == b"frigate-bytes"


@pytest.mark.asyncio
async def test_unknown_clip_origin_never_trusts_static_box_under_legacy_priority(tmp_path, monkeypatch):
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
        AsyncMock(return_value=({"data": {"box": [20, 10, 50, 30]}}, None)),
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

    assert result == "bird_presence_unconfirmed"
    fake_crop_service.generate_crop.assert_called_once()
    cached = await cache_service.get_snapshot("evt_model_first")
    assert cached is not None
    assert cached == b"frigate-bytes"


@pytest.mark.asyncio
async def test_process_event_keeps_existing_photo_when_detector_crop_identity_is_unverified(tmp_path, monkeypatch):
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

    assert result == "bird_presence_unconfirmed"
    fake_crop_service.generate_crop.assert_called_once()
    cached = await cache_service.get_snapshot("evt_crop")
    assert cached is not None
    assert cached == b"frigate-bytes"


@pytest.mark.asyncio
async def test_process_event_keeps_existing_photo_when_bird_crop_unavailable(tmp_path, monkeypatch):
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

    assert result == "bird_presence_unconfirmed"
    assert await cache_service.get_snapshot("evt_crop_fallback") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_process_event_falls_back_to_cached_recording_clip_when_event_clip_missing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_recording_fallback", b"frigate-bytes")
    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", lambda _path: 30.0)
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
        "generate_snapshot_candidates_from_clip_path",
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

    assert result == "bird_presence_unconfirmed"
    assert await cache_service.get_snapshot("evt_recording_fallback") == b"frigate-bytes"
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
    await _mock_supported_photo_bundle(monkeypatch, "generate_snapshot_candidates_from_clip_bytes", "evt_status")
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
async def test_replace_from_clip_path_replaces_cached_snapshot_when_enabled(tmp_path, monkeypatch):
    await _mock_supported_photo_bundle(monkeypatch, "generate_snapshot_candidates_from_clip_path", "evt_clip_bytes")
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_bytes", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip_path",
        lambda clip_path, *_args: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_path(
        "evt_clip_bytes", _clip_file(tmp_path)
    )

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_clip_bytes") == b"derived-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_path_is_disabled_when_feature_flag_off(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_disabled", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = False

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip_path",
        lambda clip_path, *_args: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_path(
        "evt_clip_disabled", _clip_file(tmp_path)
    )

    assert result == "disabled"
    assert await cache_service.get_snapshot("evt_clip_disabled") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_path_preserves_original_on_extraction_failure(tmp_path, monkeypatch):
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

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_path(
        "evt_clip_failure", _clip_file(tmp_path)
    )

    assert result == "frame_extract_failed"
    assert await cache_service.get_snapshot("evt_clip_failure") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_path_satisfies_queued_event_without_duplicate_worker_processing(tmp_path, monkeypatch):
    await _mock_supported_photo_bundle(monkeypatch, "generate_snapshot_candidates_from_clip_path", "evt_clip_queued")
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_queued", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip_path",
        lambda clip_path, *_args: b"derived-bytes",
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

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_path(
        "evt_clip_queued", _clip_file(tmp_path)
    )
    assert result == "replaced"

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.sleep(0.05)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert worker_processed.is_set() is False
    assert await cache_service.get_snapshot("evt_clip_queued") == b"derived-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_path_satisfies_deferred_event_without_later_worker_processing(tmp_path, monkeypatch):
    await _mock_supported_photo_bundle(
        monkeypatch, "generate_snapshot_candidates_from_clip_path", "evt_clip_deferred_2"
    )
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_deferred_1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt_clip_deferred_2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip_path",
        lambda clip_path, *_args: b"derived-bytes",
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

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_path(
        "evt_clip_deferred_2", _clip_file(tmp_path)
    )
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

    def fake_extract(
        clip_path,
        *,
        event_id,
        event_data=None,
        clip_variant="event",
        override_frame_indices=None,
        clip_start_timestamp=None,
    ):
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

    def fake_extract(
        clip_path,
        *,
        event_id,
        event_data=None,
        clip_variant="event",
        override_frame_indices=None,
        clip_start_timestamp=None,
    ):
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


@pytest.mark.asyncio
@pytest.mark.parametrize("label,expected_crop", [("Northern Cardinal", False), ("House Finch", True), (None, False)])
async def test_fallback_crop_requires_the_recorded_species(monkeypatch, label, expected_crop):
    service = hq_module.HighQualitySnapshotService()
    whole, crop = _jpeg_bytes("blue", (640, 480)), _jpeg_bytes("red", (240, 240))
    monkeypatch.setattr(service, "_maybe_crop_snapshot_bytes", lambda *_: (crop, True))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"house finch"}))
    monkeypatch.setattr(
        service,
        "_score_snapshot_candidate",
        AsyncMock(
            return_value={
                "image_bytes": crop,
                "source_mode": "model_crop",
                "image_width": 240,
                "image_height": 240,
                "classifier_label": label,
                "classifier_score": 0.95,
                "ranking_score": 0.99,
            }
        ),
    )
    result, cropped = await service._identity_safe_fallback_crop("evt", whole, None)
    assert cropped is expected_crop
    assert result == (crop if expected_crop else None)


@pytest.mark.asyncio
async def test_empty_candidate_regeneration_preserves_existing_frame_choices(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    repository = MagicMock()
    monkeypatch.setattr(hq_module, "DetectionRepository", repository)
    await service._persist_snapshot_candidates("evt", [])
    repository.assert_not_called()


def test_unknown_event_clip_origin_never_uses_path_timing_or_a_static_crop_hint():
    service = hq_module.HighQualitySnapshotService()
    event = {"start_time": 100, "data": {"box": [0.2, 0.3, 0.1, 0.1], "path_data": [[[0.25, 0.4], 100]]}}
    assert service._event_hints_for_frame(event, frame_offset_seconds=0, clip_variant="event") is None
    assert service._candidate_frame_indices(frame_count=300, fps=15, event_data=event) == [150, 75, 225]


def test_hq_hint_and_frame_sampling_use_the_clip_origin_instead_of_the_event_origin():
    service = hq_module.HighQualitySnapshotService()
    event = {"start_time": 100, "data": {"box": [0.2, 0.3, 0.1, 0.1], "path_data": [[[0.25, 0.4], 100]]}}
    assert (
        service._event_hints_for_frame(event, frame_offset_seconds=0, clip_variant="event", clip_start_timestamp=90)
        is None
    )
    hint = service._event_hints_for_frame(event, frame_offset_seconds=10, clip_variant="event", clip_start_timestamp=90)
    assert hint["data"]["box"] == pytest.approx([0.2, 0.3, 0.1, 0.1])
    assert service._target_frame_indices_from_event_path(
        frame_count=300, fps=15, event_data=event, clip_start_timestamp=90
    ) == [150]


@pytest.mark.asyncio
async def test_hq_regeneration_keeps_prior_retained_photograph_candidate(monkeypatch):
    old = {
        "candidate_id": "retained",
        "source_mode": "retained_photo",
        "clip_variant": "retained_snapshot",
        "frame_index": 0,
        "image_ref": "retained-image",
        "ranking_score": 0,
        "selected": False,
    }
    repo = MagicMock()
    repo.list_snapshot_candidates = AsyncMock(return_value=[old])
    repo.replace_snapshot_candidates = AsyncMock()
    birds = MagicMock()
    birds.list_for_event = AsyncMock(return_value=[])

    @asynccontextmanager
    async def database():
        yield object()

    monkeypatch.setattr(hq_module, "get_db", database)
    monkeypatch.setattr(hq_module, "DetectionRepository", lambda db: repo)
    monkeypatch.setattr(hq_module, "BirdObservationRepository", lambda db: birds)
    monkeypatch.setattr(hq_module.media_cache, "get_snapshot", AsyncMock(return_value=None))
    remove = AsyncMock()
    monkeypatch.setattr(hq_module.media_cache, "delete_snapshot", remove)
    new = {
        "candidate_id": "new",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 2,
        "ranking_score": 0.9,
    }
    await hq_module.HighQualitySnapshotService()._persist_snapshot_candidates("evt", [new])
    assert {row["candidate_id"] for row in repo.replace_snapshot_candidates.await_args.args[1]} == {"retained", "new"}
    remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_hq_keeps_current_photo_even_when_its_old_crop_row_is_replaced(tmp_path, monkeypatch):
    from app.services import video_snapshot_service as video_module

    cache = _make_cache_service(tmp_path, monkeypatch)
    monkeypatch.setattr(video_module, "media_cache", cache)
    photo = _jpeg_bytes("red", size=(640, 480))
    await cache.cache_snapshot("evt-prior", photo, source="video_evidence_crop")
    await cache.cache_snapshot("old-image", photo, source="snapshot_candidate")
    old = {
        "candidate_id": "old",
        "frame_index": 4,
        "clip_variant": "event",
        "source_mode": "model_crop",
        "image_ref": "old-image",
        "ranking_score": 0.8,
        "selected": True,
    }
    new = {
        "candidate_id": "new",
        "frame_index": 5,
        "clip_variant": "event",
        "source_mode": "full_frame",
        "ranking_score": 0.9,
        "selected": True,
    }
    repo = MagicMock()
    repo.list_snapshot_candidates = AsyncMock(return_value=[old])
    repo.replace_snapshot_candidates = AsyncMock()
    birds = MagicMock()
    birds.list_for_event = AsyncMock(return_value=[])

    @asynccontextmanager
    async def database():
        yield object()

    monkeypatch.setattr(hq_module, "get_db", database)
    monkeypatch.setattr(hq_module, "DetectionRepository", lambda db: repo)
    monkeypatch.setattr(hq_module, "BirdObservationRepository", lambda db: birds)
    await hq_module.HighQualitySnapshotService()._persist_snapshot_candidates("evt-prior", [new])
    rows = repo.replace_snapshot_candidates.await_args.args[1]
    prior = next(row for row in rows if row["candidate_id"] == "old")
    assert prior["selected"] is False
    assert await cache.get_snapshot(prior["image_ref"]) == photo
    assert prior["frame_index"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [True, False])
async def test_hq_photo_selection_requires_a_bird_localized_in_the_chosen_moment(monkeypatch, visible):
    service = hq_module.HighQualitySnapshotService()
    candidates = [
        {
            "candidate_id": "empty-hint",
            "source_mode": "frigate_hint_crop",
            "clip_variant": "event",
            "frame_index": 1,
            "crop_box": [0, 0, 160, 160],
            "image_width": 160,
            "image_height": 160,
            "frame_width": 640,
            "frame_height": 480,
            "classifier_label": "House Finch",
            "classifier_score": 0.99,
            "ranking_score": 0.99,
        }
    ]
    if visible:
        candidates.append(
            {
                "candidate_id": "visible-bird",
                "source_mode": "model_crop",
                "clip_variant": "event",
                "frame_index": 2,
                "crop_box": [200, 100, 360, 260],
                "detector_box": [240, 140, 280, 180],
                "crop_confidence": 0.9,
                "image_width": 160,
                "image_height": 160,
                "frame_width": 640,
                "frame_height": 480,
                "classifier_label": "House Finch",
                "classifier_score": 0.82,
                "ranking_score": 0.8,
            }
        )
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda candidate: candidate))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"House Finch"}))
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))
    bundle = await service._score_and_select_snapshot_candidates("photo-presence", candidates)
    if visible:
        assert bundle["selected_candidate"]["candidate_id"] == "visible-bird"
    else:
        assert bundle["selected_candidate"] is None
        assert bundle["photo_outcome"] == "bird_presence_unconfirmed"
    assert {candidate["candidate_id"] for candidate in bundle["candidates"]} == {
        candidate["candidate_id"] for candidate in candidates
    }


@pytest.mark.asyncio
async def test_hq_presence_rejection_cannot_bypass_selection_through_raw_frame_fallback(tmp_path, monkeypatch):
    cache = _make_cache_service(tmp_path, monkeypatch)
    await cache.cache_snapshot("hq-unconfirmed", b"original-photo")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    service = hq_module.high_quality_snapshot_service
    monkeypatch.setattr(
        service,
        "generate_snapshot_candidates_from_clip_path",
        AsyncMock(
            return_value={
                "selected_candidate": None,
                "candidates": [],
                "photo_outcome": "bird_presence_unconfirmed",
            }
        ),
    )
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))

    def unsafe_fallback(*args, **kwargs):
        raise AssertionError("unconfirmed photo must not bypass presence selection")

    monkeypatch.setattr(service, "_extract_snapshot_from_clip_path", unsafe_fallback)
    outcome = await service.replace_from_clip_path("hq-unconfirmed", _clip_file(tmp_path))
    assert outcome == "bird_presence_unconfirmed"
    assert await cache.get_snapshot("hq-unconfirmed") == b"original-photo"


@pytest.mark.asyncio
@pytest.mark.parametrize("confidence", [None, 0.03, 0.9])
async def test_raw_hq_fallback_does_not_replace_from_unlocalized_high_species_score(monkeypatch, confidence):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: True)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True)
    image = Image.new("RGB", (640, 480), "blue")
    crop = image.crop((200, 100, 360, 260))
    monkeypatch.setattr(
        service,
        "_crop_snapshot_best_available",
        lambda *args, **kwargs: {
            "crop_image": crop,
            "box": (200, 100, 360, 260),
            "detector_box": (240, 140, 280, 180) if confidence is not None else None,
            "confidence": confidence,
        },
    )
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"House Finch"}))
    monkeypatch.setattr(
        service,
        "_score_snapshot_candidate",
        AsyncMock(
            side_effect=lambda candidate: {
                **candidate,
                "image_width": 160,
                "image_height": 160,
                "classifier_label": "House Finch",
                "classifier_score": 0.99,
                "ranking_score": 0.99,
            }
        ),
    )
    replacement, applied = await service._identity_safe_fallback_crop("photo", _jpeg_bytes("blue", (640, 480)), None)
    if confidence is None or confidence < 0.08:
        assert replacement is None
        assert applied is False
    else:
        assert replacement is not None
        assert applied is True


@pytest.mark.asyncio
@pytest.mark.parametrize("from_clip_path", [True, False])
async def test_hq_photo_abstention_keeps_selection_refines_species_and_records_durable_outcome(
    tmp_path,
    monkeypatch,
    from_clip_path,
):
    from app.repositories.processing_job_repository import ProcessingJobRepository

    event_id = "hq-photo-abstention-" + str(from_clip_path)
    cache = _make_cache_service(tmp_path, monkeypatch)
    original = _jpeg_bytes("blue", (160, 160))
    await cache.cache_snapshot(event_id, original, source="video_evidence_crop")
    image_ref = event_id + "__model_crop__f1__aaaaaaaaaa__image"
    await cache.cache_snapshot(image_ref, original, source="snapshot_candidate")
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event_id,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(
            event_id,
            [
                {
                    "candidate_id": "original-selected",
                    "selected": True,
                    "image_ref": image_ref,
                    "source_mode": "model_crop",
                    "clip_variant": "event",
                    "frame_index": 1,
                    "crop_box": [0, 0, 160, 160],
                    "crop_confidence": 0.9,
                    "classifier_label": "House Finch",
                    "classifier_score": 0.9,
                }
            ],
        )
        await ProcessingJobRepository(db).enqueue(hq_module.HQ_PROCESSING_PIPELINE, event_id)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    service = hq_module.high_quality_snapshot_service
    candidates = [
        {
            "candidate_id": "new-exploratory",
            "source_mode": "model_crop",
            "clip_variant": "event",
            "frame_index": 2,
            "crop_box": [0, 0, 160, 160],
            "crop_confidence": 0.03,
            "classifier_label": "House Finch",
            "classifier_score": 0.99,
            "image_bytes": _jpeg_bytes("gray", (160, 160)),
            "selected": False,
        }
    ]
    bundle = {"selected_candidate": None, "candidates": candidates, "photo_outcome": "bird_presence_unconfirmed"}
    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_path", AsyncMock(return_value=bundle))
    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_bytes", AsyncMock(return_value=bundle))
    monkeypatch.setattr(service, "_wait_for_clip", AsyncMock(return_value=(b"clip", None)))
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    refinement = AsyncMock(return_value=False)
    monkeypatch.setattr(service, "_apply_classification_refinement", refinement)
    outcome = (
        (await service.replace_from_clip_path(event_id, _clip_file(tmp_path)))
        if from_clip_path
        else (await service.process_event(event_id))
    )
    assert outcome == "bird_presence_unconfirmed"
    assert await cache.get_snapshot(event_id) == original
    async with get_db() as db:
        rows = await DetectionRepository(db).list_snapshot_candidates(event_id)
        state = await ProcessingJobRepository(db).get(hq_module.HQ_PROCESSING_PIPELINE, event_id)
    assert [row["candidate_id"] for row in rows if row["selected"]] == ["original-selected"]
    assert state.status == "terminal"
    assert state.last_error == "bird_presence_unconfirmed"
    assert state.attempt_count == 1
    assert not state.can_attempt(utc_naive_now())
    refinement.assert_awaited_once()
    assert refinement.await_args.args[0] == event_id
    assert refinement.await_args.args[1][0]["crop_confidence"] == 0.03


@pytest.mark.asyncio
async def test_missing_hq_media_keeps_clip_not_ready_retry_instead_of_reporting_no_bird(tmp_path, monkeypatch):
    from app.repositories.processing_job_repository import ProcessingJobRepository

    event_id = "hq-media-not-ready"
    cache = _make_cache_service(tmp_path, monkeypatch)
    await cache.cache_snapshot(event_id, b"original-photo")
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event_id,
                camera_name="test",
            )
        )
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    service = hq_module.high_quality_snapshot_service
    monkeypatch.setattr(service, "_wait_for_clip", AsyncMock(return_value=(None, "clip_not_ready")))
    monkeypatch.setattr(service, "_load_recording_clip_bytes", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_load_final_frigate_snapshot_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    assert await service.process_event(event_id) == "clip_not_ready"
    async with get_db() as db:
        state = await ProcessingJobRepository(db).get(hq_module.HQ_PROCESSING_PIPELINE, event_id)
    assert state.status == "retryable"
    assert state.last_error == "clip_not_ready"
    assert await cache.get_snapshot(event_id) == b"original-photo"


@pytest.mark.asyncio
@pytest.mark.parametrize("from_clip_path", [True, False])
async def test_temporary_detector_failure_preserves_photo_and_retries_after_recovery(
    tmp_path, monkeypatch, from_clip_path
):
    from app.services.bird_crop_service import BirdCropService
    from app.repositories.processing_job_repository import ProcessingJobRepository

    event_id = "detector-recovery-" + str(from_clip_path)
    cache = _make_cache_service(tmp_path, monkeypatch)
    old_photo = _jpeg_bytes("blue", (160, 160))
    await cache.cache_snapshot(event_id, old_photo)
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event_id,
                camera_name="test",
            )
        )
        await ProcessingJobRepository(db).enqueue(hq_module.HQ_PROCESSING_PIPELINE, event_id)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    detector = BirdCropService()
    monkeypatch.setattr(hq_module, "bird_crop_service", detector)
    monkeypatch.setattr(detector, "_ensure_model_for_tier", lambda tier: object())
    failed = True

    def infer(model, image):
        if failed:
            raise RuntimeError("temporary runtime failure")
        return [{"box": (100, 100, 250, 250), "confidence": 0.9}]

    monkeypatch.setattr(detector, "_infer_candidates", infer)
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_load_preferred_frame_indices", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_final_frigate_snapshot_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value=["House Finch"]))

    async def score(candidate):
        return {
            **candidate,
            "classifier_label": "House Finch",
            "classifier_score": 0.95,
            "classifier_index": 1,
            "ranking_score": 0.95,
        }

    monkeypatch.setattr(service, "_score_snapshot_candidate", score)
    monkeypatch.setattr(service, "_apply_classification_refinement", AsyncMock(return_value=False))
    clip = _clip_file(tmp_path)

    def extract(path, **kwargs):
        rows = []
        for mode, image, details in service._candidate_images_for_frame(
            Image.new("RGB", (640, 480), "gray"), event_data=None, event_id=event_id
        ):
            detail = details or {}
            rows.append(
                {
                    "candidate_id": event_id + "-" + mode,
                    "source_mode": mode,
                    "clip_variant": "event",
                    "frame_index": 30,
                    "image_bytes": service._encode_pil_to_jpeg_bytes(image),
                    "frame_width": 640,
                    "frame_height": 480,
                    "image_width": image.width,
                    "image_height": image.height,
                    "crop_box": detail.get("box"),
                    "detector_box": detail.get("detector_box"),
                    "crop_confidence": detail.get("confidence"),
                    "observation_boxes": detail.get("observation_boxes"),
                }
            )
        return rows

    monkeypatch.setattr(service, "_extract_snapshot_candidate_payloads_from_clip_path", extract)
    monkeypatch.setattr(service, "_wait_for_clip", AsyncMock(return_value=(b"clip", None)))

    async def generate_bytes(event, contents, **kwargs):
        return await service.generate_snapshot_candidates_from_clip_path(event, clip, **kwargs)

    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_bytes", generate_bytes)
    outcome = (
        await service.replace_from_clip_path(event_id, clip)
        if from_clip_path
        else await service.process_event(event_id)
    )
    assert outcome == "detector_error"
    assert await cache.get_snapshot(event_id) == old_photo
    async with get_db() as db:
        state = await ProcessingJobRepository(db).get(hq_module.HQ_PROCESSING_PIPELINE, event_id)
    assert state.status == "retryable"
    assert state.last_error == "detector_error"
    assert state.retry_after is not None
    failed = False
    bundle = await service.generate_snapshot_candidates_from_clip_path(event_id, clip)
    assert bundle["selected_candidate"]["source_mode"] == "model_crop"
    assert bundle["selected_candidate"]["crop_confidence"] == 0.9


@pytest.mark.asyncio
async def test_candidate_species_inference_failure_does_not_claim_completed_no_bird_scan(monkeypatch):
    import app.services.classifier_service as classifier_module

    service = hq_module.HighQualitySnapshotService()
    classifier = SimpleNamespace(
        classify_async_background=AsyncMock(side_effect=RuntimeError("temporary inference failure"))
    )
    monkeypatch.setattr(classifier_module, "_classifier_instance", classifier)
    with pytest.raises(RuntimeError, match="classifier_error"):
        await service._score_snapshot_candidate({"candidate_id": "transient", "image_bytes": _jpeg_bytes("white")})


@pytest.mark.asyncio
async def test_pressure_deferred_fallback_does_not_claim_completed_no_bird_scan(monkeypatch):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_automatic_crop_enabled", lambda: True)
    monkeypatch.setattr(service, "_background_crop_work_allowed", lambda: False)
    with pytest.raises(RuntimeError, match="inference_deferred"):
        await service._identity_safe_fallback_crop("busy", _jpeg_bytes("white"), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("from_clip_path", [True, False])
@pytest.mark.parametrize(
    "outcome", ["classifier_error", "inference_deferred", "detector_error", "frame_extract_failed"]
)
async def test_incomplete_photo_work_preserves_photo_and_durable_retry(tmp_path, monkeypatch, from_clip_path, outcome):
    from app.repositories.processing_job_repository import ProcessingJobRepository

    event_id = "incomplete-photo-" + outcome + str(from_clip_path)
    cache = _make_cache_service(tmp_path, monkeypatch)
    await cache.cache_snapshot(event_id, b"old-photo")
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event_id,
                camera_name="test",
            )
        )
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_wait_for_clip", AsyncMock(return_value=(b"clip", None)))
    if outcome in {"detector_error", "frame_extract_failed"}:
        generation = AsyncMock(return_value={"selected_candidate": None, "candidates": []})
        error = (
            hq_module.BirdDetectionError("temporary detector failure")
            if outcome == "detector_error"
            else RuntimeError("bad frame")
        )

        def extraction_failure(*args, **kwargs):
            raise error

        monkeypatch.setattr(service, "_extract_snapshot_from_clip", extraction_failure)
        monkeypatch.setattr(service, "_extract_snapshot_from_clip_path", extraction_failure)
    else:
        generation = AsyncMock(side_effect=hq_module.PhotoScanRetry(outcome))
    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_path", generation)
    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_bytes", generation)
    result = (
        await service.replace_from_clip_path(event_id, _clip_file(tmp_path))
        if from_clip_path
        else await service.process_event(event_id)
    )
    assert result == outcome
    async with get_db() as db:
        state = await ProcessingJobRepository(db).get(hq_module.HQ_PROCESSING_PIPELINE, event_id)
    assert state.status == "retryable"
    assert state.last_error == outcome
    assert state.retry_after is not None
    assert await cache.get_snapshot(event_id) == b"old-photo"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,score,eligible", [("House Finch", 0.55, False), ("Goldcrest", 0.95, False), ("House Finch", 0.9, True)]
)
async def test_hq_photo_requires_current_species_and_the_baseline_confidence_gate(monkeypatch, label, score, eligible):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"House Finch"}))
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))

    async def scored(candidate):
        return {
            **candidate,
            "classifier_label": label,
            "classifier_score": score,
            "classifier_index": 1,
            "ranking_score": score,
        }

    monkeypatch.setattr(service, "_score_snapshot_candidate", scored)
    shared = {
        "frame_index": 20,
        "clip_variant": "event",
        "frame_width": 640,
        "frame_height": 480,
        "image_width": 200,
        "image_height": 200,
    }
    raw = [
        {
            **shared,
            "candidate_id": "localized",
            "source_mode": "model_crop",
            "crop_box": [100, 100, 300, 300],
            "detector_box": [130, 130, 250, 250],
            "crop_confidence": 0.9,
        },
        {
            **shared,
            "candidate_id": "whole",
            "source_mode": "full_frame",
            "crop_box": None,
            "image_width": 640,
            "image_height": 480,
        },
    ]
    bundle = await service._score_and_select_snapshot_candidates("species-photo-gate", raw)
    assert (bundle["selected_candidate"] is not None) is eligible
    assert len(bundle["candidates"]) == 2
    if not eligible:
        assert bundle["photo_outcome"] == "bird_presence_unconfirmed"


_CACHED_CLIP = b"\x00\x00\x00\x18ftypmp42" + b"\x01" * 1024


@pytest.mark.asyncio
async def test_a_requested_photo_uses_the_cached_clip_without_asking_frigate(tmp_path, monkeypatch):
    """A visit Frigate has expired still plays from YA-WAMF's cached clip, so Generate must use that clip
    rather than poll Frigate for half a minute and report it missing."""
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_clip("evt_expired_upstream", _CACHED_CLIP)
    frigate = AsyncMock(return_value=(None, "clip_not_found"))
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_wait_for_clip", frigate)

    service = hq_module.high_quality_snapshot_service
    assert await service._load_event_clip("evt_expired_upstream", prefer_cached=True) == (_CACHED_CLIP, None)
    frigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_automatic_photo_asks_frigate_first_and_falls_back_to_the_cached_clip(tmp_path, monkeypatch):
    """A clip played mid-visit can be cached cut short, so the automatic pass prefers Frigate's full clip."""
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_clip("evt_cached", _CACHED_CLIP)
    service = hq_module.high_quality_snapshot_service

    frigate = AsyncMock(return_value=(b"full-clip", None))
    monkeypatch.setattr(service, "_wait_for_clip", frigate)
    assert await service._load_event_clip("evt_cached", prefer_cached=False) == (b"full-clip", None)

    frigate.return_value = (None, "clip_not_found")
    assert await service._load_event_clip("evt_cached", prefer_cached=False) == (_CACHED_CLIP, None)
    assert await service._load_event_clip("evt_uncached", prefer_cached=False) == (None, "clip_not_found")


def _incumbent_photo_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (320, 240), (90, 120, 80)).save(output, format="JPEG")
    return output.getvalue()


def _incumbent_row(**changes):
    return {
        "candidate_id": "shown",
        "selected": True,
        "source_mode": "model_crop",
        "crop_box": [10, 10, 200, 200],
        "crop_confidence": 0.6,
        "classifier_label": "Dunnock",
        "classifier_score": 0.95,
        "image_ref": "shown-image",
        **changes,
    }


async def _load_incumbent(monkeypatch, row, *, metadata=None, shown=None, stored=None):
    service = hq_module.HighQualitySnapshotService()
    repo = MagicMock()
    repo.list_snapshot_candidates = AsyncMock(return_value=[row])

    @asynccontextmanager
    async def fake_db():
        yield object()

    photo = _incumbent_photo_bytes()
    snapshots = {"evt": photo if shown is None else shown, "shown-image": photo if stored is None else stored}
    monkeypatch.setattr(hq_module, "get_db", fake_db)
    monkeypatch.setattr(hq_module, "DetectionRepository", lambda db: repo)
    monkeypatch.setattr(hq_module.media_cache, "get_snapshot_metadata", AsyncMock(return_value=metadata or {}))
    monkeypatch.setattr(hq_module.media_cache, "get_snapshot", AsyncMock(side_effect=lambda key: snapshots.get(key)))
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    return await service._load_verified_incumbent_photo("evt", {"dunnock"})


@pytest.mark.asyncio
async def test_the_shown_photo_is_defended_when_it_is_verified(monkeypatch):
    incumbent = await _load_incumbent(monkeypatch, _incumbent_row())
    assert incumbent is not None
    assert incumbent["candidate_id"] == "shown"
    assert 0 <= incumbent["image_quality_score"] <= 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("row", "options"),
    [
        (_incumbent_row(photo_hidden=True), {}),
        (_incumbent_row(classifier_label="European Robin"), {}),
        (_incumbent_row(crop_confidence=0.12), {}),
        (_incumbent_row(classifier_score=0.5), {}),
        (_incumbent_row(), {"metadata": {"manual_selection": True}}),
        (_incumbent_row(), {"metadata": {"storage_evicted": True}}),
        (_incumbent_row(), {"stored": b"another photograph"}),
    ],
    ids=["removed", "other-species", "weak-box", "weak-species", "owner-choice", "evicted", "not-displayed"],
)
async def test_only_a_verified_shown_photo_is_defended(monkeypatch, row, options):
    assert await _load_incumbent(monkeypatch, row, **options) is None
