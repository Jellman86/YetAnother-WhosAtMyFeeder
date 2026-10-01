from unittest.mock import AsyncMock
import asyncio

import cv2
import numpy as np
import pytest

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services import video_snapshot_service as module
from app.services.high_quality_snapshot_service import HQ_PROCESSING_PIPELINE
from app.utils.api_datetime import utc_naive_now


def _result():
    return {
        "label": "Baeolophus bicolor",
        "index": 1,
        "score": 0.9,
        "_video_snapshot_evidence": {
            "frame_index": 2,
            "frame_offset_seconds": 1.0,
            "frame_width": 80,
            "frame_height": 60,
            "crop_box": [10, 20, 50, 50],
            "input_source": "model_crop",
            "input_is_cropped": True,
            "score": 0.94,
        },
    }


@pytest.fixture(autouse=True)
def photo_settings(monkeypatch):
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "moments.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 2, (80, 60))
    assert writer.isOpened()
    for bgr in [(0, 0, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255)]:
        writer.write(np.full((60, 80, 3), bgr, dtype=np.uint8))
    writer.release()
    return path


def test_extraction_uses_exact_classified_moment_and_crop(clip):
    portrait, scene = module.extract_video_snapshot(clip, _result()["_video_snapshot_evidence"])
    assert portrait.size == (40, 30)
    assert scene.size == (80, 60)
    assert portrait.getpixel((20, 15))[1] > 240
    assert portrait.getpixel((20, 15))[0] < 10


@pytest.mark.parametrize(
    "key,value",
    [
        ("frame_index", True),
        ("frame_index", -1),
        ("frame_index", 100000),
        ("crop_box", [10, 20, 90, 50]),
        ("crop_box", [True, 20, 50, 50]),
        ("crop_box", [10, 20, 10, 50]),
        ("frame_width", 81),
        ("score", float("nan")),
    ],
)
def test_extraction_rejects_invalid_or_different_frame_geometry(clip, key, value):
    evidence = {**_result()["_video_snapshot_evidence"], key: value}
    assert module.extract_video_snapshot(clip, evidence) is None


async def _seed(event_id, **extra):
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.95,
                display_name="Tufted Titmouse",
                category_name="Baeolophus bicolor",
                frigate_event=event_id,
                camera_name="test",
                **extra,
            )
        )


@pytest.mark.asyncio
async def test_video_updates_matching_photo_with_hq_disabled_and_preserves_old_moments(clip, monkeypatch):
    event_id = "video-photo-hq-off"
    await _seed(event_id)
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(
            event_id, [{"candidate_id": "old", "frame_index": 0, "selected": True}]
        )
    cache = module.media_cache
    await cache.cache_snapshot(event_id, b"empty-branch")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", False)
    monkeypatch.setattr(module.archive_service, "refresh_photograph", AsyncMock())
    assert await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event") == "replaced"
    metadata = await cache.get_snapshot_metadata(event_id)
    assert metadata["source"] == "video_evidence_crop"
    async with get_db() as db:
        rows = await DetectionRepository(db).list_snapshot_candidates(event_id)
    assert any(row["candidate_id"] == "old" for row in rows)
    selected = next(row for row in rows if row["selected"])
    assert selected["classifier_label"] == "Baeolophus bicolor"
    assert selected["frame_index"] == 2
    assert selected["crop_box"] == [10, 20, 50, 50]
    assert len([row for row in rows if row["selected"]]) == 1
    module.archive_service.refresh_photograph.assert_awaited_once_with(event_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition", ["manual_photo", "manual_species", "different_species", "hidden", "storage_evicted", "blocked"]
)
async def test_video_photo_respects_owner_choices_current_identity_and_eviction(clip, monkeypatch, condition):
    event_id = f"video-photo-guard-{condition}"
    await _seed(event_id, manual_tagged=condition == "manual_species", is_hidden=condition == "hidden")
    if condition == "blocked":
        monkeypatch.setattr(settings.classification, "blocked_labels", ["Baeolophus bicolor"])
    if condition == "different_species":
        async with get_db() as db:
            await db.execute(
                "UPDATE detections SET category_name = ?, display_name = ? WHERE frigate_event = ?",
                ("Cardinalis cardinalis", "Northern Cardinal", event_id),
            )
            await db.commit()
    if condition == "storage_evicted":
        async with get_db() as db:
            await ProcessingJobRepository(db).mark_storage_evicted(HQ_PROCESSING_PIPELINE, event_id)
            await db.commit()
    await module.media_cache.cache_snapshot(event_id, b"owner-photo")
    if condition == "manual_photo":
        await module.media_cache.set_manual_snapshot_selection(event_id, True)
    monkeypatch.setattr(module.archive_service, "refresh_photograph", AsyncMock())
    await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
    assert await module.media_cache.get_snapshot(event_id) == b"owner-photo"
    module.archive_service.refresh_photograph.assert_not_awaited()


@pytest.mark.asyncio
async def test_video_photo_rechecks_identity_after_decode(clip, monkeypatch):
    event_id = "video-photo-correction-during-decode"
    await _seed(event_id)
    await module.media_cache.cache_snapshot(event_id, b"owner-photo")
    original = module.extract_video_snapshot

    async def decode_then_correct(fn, *args, **kwargs):
        decoded = original(*args, **kwargs)
        async with get_db() as db:
            await db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?", (event_id,))
            await db.commit()
        return decoded

    monkeypatch.setattr(module.asyncio, "to_thread", decode_then_correct)
    await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
    assert await module.media_cache.get_snapshot(event_id) == b"owner-photo"


@pytest.mark.asyncio
async def test_video_photo_metadata_failure_preserves_photo_and_selected_history(clip, monkeypatch):
    event_id = "video-photo-metadata-failed"
    await _seed(event_id)
    await module.media_cache.cache_snapshot(event_id, b"old-photo")
    before = await module.media_cache.get_snapshot_metadata(event_id)
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(
            event_id, [{"candidate_id": "old-selected", "selected": True}]
        )
    original = module.media_cache._write_snapshot_metadata

    async def fail_parent(event, **kwargs):
        if event == event_id:
            raise OSError("metadata disk write failed")
        await original(event, **kwargs)

    monkeypatch.setattr(module.media_cache, "_write_snapshot_metadata", fail_parent)
    assert (
        await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
        == "snapshot_replace_failed"
    )
    assert await module.media_cache.get_snapshot(event_id) == b"old-photo"
    assert await module.media_cache.get_snapshot_metadata(event_id) == before
    async with get_db() as db:
        rows = await DetectionRepository(db).list_snapshot_candidates(event_id)
    assert [(row["candidate_id"], row["selected"]) for row in rows] == [("old-selected", True)]


@pytest.mark.asyncio
async def test_explicit_video_reclassification_can_align_its_new_manual_identity_photo(clip, monkeypatch):
    event_id = "video-photo-explicit-reclassification"
    await _seed(event_id, manual_tagged=True)
    await module.media_cache.cache_snapshot(event_id, b"previous-species")
    monkeypatch.setattr(module.archive_service, "refresh_photograph", AsyncMock())
    assert (
        await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event", automatic=False)
        == "replaced"
    )


@pytest.mark.asyncio
async def test_cancellation_during_photo_commit_keeps_files_and_selected_row_together(clip, monkeypatch):
    event_id = "video-photo-cancel-during-commit"
    await _seed(event_id)
    await module.media_cache.cache_snapshot(event_id, b"old-photo")
    entered = asyncio.Event()
    release = asyncio.Event()
    original = DetectionRepository.replace_snapshot_candidates

    async def delay_after_commit(repo, event, rows):
        await original(repo, event, rows)
        entered.set()
        await release.wait()

    monkeypatch.setattr(DetectionRepository, "replace_snapshot_candidates", delay_after_commit)
    task = asyncio.create_task(module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event"))
    await asyncio.wait_for(entered.wait(), 10)
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with get_db() as db:
        selected = next(
            row for row in await DetectionRepository(db).list_snapshot_candidates(event_id) if row["selected"]
        )
    assert await module.media_cache.get_snapshot(event_id) == await module.media_cache.get_snapshot(
        selected["image_ref"]
    )
    assert module.media_cache.get_active_write_event_ids() == set()
