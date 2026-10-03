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
            "presence_source": "bird_crop_detector",
            "bird_box": [10, 20, 50, 50],
            "detector_confidence": 0.9,
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
    outcome = await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
    expected = {
        "manual_photo": "manual_selection_preserved",
        "different_species": "primary_identity_preserved",
        "storage_evicted": "storage_evicted",
        "blocked": "blocked_species",
    }
    assert outcome == expected.get(condition, "owner_identification_preserved")
    assert await module.media_cache.get_snapshot(event_id) == b"owner-photo"
    module.archive_service.refresh_photograph.assert_not_awaited()


@pytest.mark.asyncio
async def test_video_photo_rechecks_identity_after_decode(clip, monkeypatch):
    event_id = "video-photo-correction-during-decode"
    await _seed(event_id)
    await module.media_cache.cache_snapshot(event_id, b"owner-photo")
    original = module.asyncio.to_thread

    async def decode_then_correct(fn, *args, **kwargs):
        decoded = await original(fn, *args, **kwargs)
        if fn is module.extract_video_snapshot:
            async with get_db() as db:
                await db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?", (event_id,))
                await db.commit()
        return decoded

    monkeypatch.setattr(module.asyncio, "to_thread", decode_then_correct)
    outcome = await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
    assert outcome == "owner_identification_preserved"
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


@pytest.mark.asyncio
async def test_replacement_retains_the_previous_photo_without_a_candidate_or_frigate_copy(clip, monkeypatch):
    from io import BytesIO
    from PIL import Image

    event_id = "video-photo-retained-original"
    await _seed(event_id)
    data = BytesIO()
    Image.new("RGB", (80, 60), "yellow").save(data, format="JPEG")
    original = data.getvalue()
    await module.media_cache.cache_snapshot(event_id, original, source="frigate_snapshot_cropped")
    monkeypatch.setattr(module.archive_service, "refresh_photograph", AsyncMock())
    assert await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event") == "replaced"
    async with get_db() as db:
        rows = await DetectionRepository(db).list_snapshot_candidates(event_id)
    photos = [await module.media_cache.get_snapshot(row["image_ref"]) for row in rows]
    assert original in photos
    kept = rows[photos.index(original)]
    assert kept["selected"] is False
    assert kept["clip_variant"] == "retained_snapshot"
    assert kept["classifier_label"] is None


@pytest.mark.asyncio
async def test_retained_photo_keeps_original_bytes_with_bounded_thumbnail(monkeypatch):
    from io import BytesIO
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (1920, 1080), "yellow").save(buffer, "JPEG")
    original = buffer.getvalue()
    retained = await module.retained_snapshot_candidate("evt", original, {"source": "frigate_snapshot"}, [])
    assert retained["image_bytes"] == original
    assert retained["frame_offset_seconds"] is None
    assert retained["classifier_label"] is None
    assert retained["clip_variant"] == "retained_snapshot"
    with Image.open(BytesIO(retained["thumbnail_bytes"])) as thumbnail:
        assert thumbnail.width <= 320
        assert thumbnail.height <= 240
    await module.media_cache.cache_snapshot(retained["image_ref"], original)
    assert await module.retained_snapshot_candidate("evt", original, {}, [retained]) is None


@pytest.mark.asyncio
async def test_retention_uses_saved_hash_without_reading_every_candidate(monkeypatch):
    import hashlib

    photo = b"saved-photo"
    ref = "evt-hash__model_crop__f2__aaaaaaaaaa__image"
    await module.media_cache.cache_snapshot(ref, photo)
    read = AsyncMock(side_effect=AssertionError("hash lookup should not read candidate JPEGs"))
    monkeypatch.setattr(module.media_cache, "get_snapshot", read)
    existing = [{"candidate_id": "known", "image_ref": ref, "content_sha256": hashlib.sha256(photo).hexdigest()}]
    assert await module.retained_snapshot_candidate("evt-hash", photo, {}, existing) is None
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_duplicate_comparison_is_bounded(monkeypatch):
    read = AsyncMock(return_value=b"other-photo")
    monkeypatch.setattr(module.media_cache, "get_snapshot", read)
    existing = [{"candidate_id": f"legacy-{i}", "image_ref": f"legacy-{i}"} for i in range(100)]
    assert await module.retained_snapshot_candidate("evt", b"new-photo", {}, existing) is not None
    assert read.await_count <= 8


def test_video_candidate_keeps_tracked_region_provenance():
    from PIL import Image

    result = _result()
    evidence = {**result["_video_snapshot_evidence"], "input_source": "frigate_region_crop"}
    rows = module._candidates(
        "evt", result, evidence, (Image.new("RGB", (40, 30)), Image.new("RGB", (80, 60))), "event"
    )
    assert next(row for row in rows if row["selected"])["source_mode"] == "frigate_region_crop"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    [
        None,
        "hq_full",
        "hq_hint",
        "missing_candidate",
        "different_bytes",
        "low_score",
        "different_label",
        "unverified_presence",
    ],
)
async def test_photo_preflight_skips_decode_only_for_verified_matching_bytes(clip, monkeypatch, problem):
    from unittest.mock import Mock

    event_id = f"photo-preflight-{problem}"
    await _seed(event_id)
    cache = module.media_cache
    await cache.cache_snapshot(event_id, b"verified-photo", source="high_quality_bird_crop")
    ref = f"{event_id}__model_crop__f2__abc__image"
    if problem != "missing_candidate":
        await cache.cache_snapshot(ref, b"other-photo" if problem == "different_bytes" else b"verified-photo")
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(
            event_id,
            [
                {
                    "candidate_id": "chosen",
                    "selected": True,
                    "image_ref": ref,
                    "classifier_label": "Cardinalis cardinalis"
                    if problem == "different_label"
                    else "Baeolophus bicolor",
                    "classifier_score": 0.3 if problem == "low_score" else 0.94,
                    "source_mode": "full_frame"
                    if problem == "hq_full"
                    else "frigate_hint_crop"
                    if problem == "hq_hint"
                    else "model_crop",
                    "crop_box": None if problem == "hq_full" else [10, 20, 50, 50],
                    "crop_strategy": "video_evidence" if problem == "unverified_presence" else "detector_supported",
                    "crop_confidence": None if problem == "unverified_presence" else 0.9,
                }
            ],
        )
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    decode = Mock(wraps=module.extract_video_snapshot)
    monkeypatch.setattr(module, "extract_video_snapshot", decode)
    outcome = await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
    if problem in {None, "hq_full", "hq_hint"}:
        assert outcome == "matching_photo_preserved"
        decode.assert_not_called()
    else:
        assert outcome == "replaced"
        decode.assert_called_once()


@pytest.mark.asyncio
async def test_photo_preflight_does_not_decode_for_an_owner_selected_photo(clip, monkeypatch):
    from unittest.mock import Mock

    event_id = "photo-preflight-owner-choice"
    await _seed(event_id)
    await module.media_cache.cache_snapshot(event_id, b"owner-photo")
    await module.media_cache.set_manual_snapshot_selection(event_id, True)
    decode = Mock(side_effect=AssertionError("owner choice should not decode"))
    monkeypatch.setattr(module, "extract_video_snapshot", decode)
    assert (
        await module.replace_video_snapshot(event_id, clip, _result(), clip_variant="event")
        == "manual_selection_preserved"
    )
    decode.assert_not_called()


@pytest.mark.asyncio
async def test_saved_hash_does_not_prevent_restoring_a_missing_earlier_photo():
    import hashlib

    photo = b"missing-prior-photo"
    row = {"candidate_id": "missing", "content_sha256": hashlib.sha256(photo).hexdigest(), "image_ref": "not-on-disk"}
    restored = await module.retained_snapshot_candidate("restore-earlier", photo, {}, [row])
    assert restored["image_bytes"] == photo
    assert restored["content_sha256"] == row["content_sha256"]


@pytest.mark.asyncio
async def test_baseline_repeated_accepted_species_changes_bound_photo_choices(monkeypatch):
    from PIL import Image

    event = "bounded-baseline-photos"
    await _seed(event)
    original = module._jpeg(Image.new("RGB", (80, 60), "red"))
    await module.media_cache.cache_snapshot(event, original, source="frigate_snapshot")
    monkeypatch.setattr(module.archive_service, "refresh_photograph", AsyncMock())
    for i in range(25):
        result = _result()
        result["label"] = f"Accepted bird {i}"
        async with get_db() as db:
            await db.execute(
                "UPDATE detections SET category_name=?,display_name=? WHERE frigate_event=?",
                (result["label"], result["label"], event),
            )
            await db.commit()
        scene = Image.new("RGB", (80, 60), (i * 7, 45, 70))
        candidates = module._candidates(
            event, result, result["_video_snapshot_evidence"], (scene.crop((10, 20, 50, 50)), scene), "event"
        )
        assert (
            await module._commit_video_snapshot(
                event, result, result["_video_snapshot_evidence"], candidates, automatic=True
            )
            == "replaced"
        )
    async with get_db() as db:
        rows = await DetectionRepository(db).list_snapshot_candidates(event)
    assert len(rows) <= 21
    assert len([row for row in rows if row["selected"]]) == 1
    assert all([await module.media_cache.get_snapshot(row["image_ref"]) for row in rows])
    retained = next(row for row in rows if row["source_mode"] == "retained_photo")
    assert await module.media_cache.get_snapshot(retained["image_ref"]) == original


@pytest.mark.asyncio
async def test_replacing_a_reused_candidate_key_keeps_earlier_bytes_and_creation_time():
    import hashlib

    photo = b"earlier-key-photo"
    ref = "reused-key-photo"
    await module.media_cache.cache_snapshot(ref, photo, source="snapshot_candidate")
    row = {
        "candidate_id": "reused",
        "image_ref": ref,
        "selected": True,
        "content_sha256": hashlib.sha256(photo).hexdigest(),
        "created_at": "2026-01-01 00:00:00",
    }
    retained = await module.retained_snapshot_candidate("reuse", photo, {}, [row], replaced_candidate_ids={"reused"})
    assert retained["image_bytes"] == photo
    assert retained["created_at"] == row["created_at"]


@pytest.mark.asyncio
async def test_no_localized_video_photo_reports_its_reason_without_decoding_or_changing_photo(clip, monkeypatch):
    from unittest.mock import Mock

    event_id = "no-localized-video-photo"
    await _seed(event_id)
    await module.media_cache.cache_snapshot(event_id, b"original-photo")
    result = {**_result(), "_video_snapshot_evidence": None}
    decode = Mock(side_effect=AssertionError("no localized photo should not decode"))
    monkeypatch.setattr(module, "extract_video_snapshot", decode)
    assert (
        await module.replace_video_snapshot(event_id, clip, result, clip_variant="event") == "bird_presence_unconfirmed"
    )
    assert await module.media_cache.get_snapshot(event_id) == b"original-photo"
    decode.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "disabled,outcome",
    [
        ("enabled", "media_cache_disabled"),
        ("cache_snapshots", "snapshot_caching_disabled"),
        ("available", "media_cache_unavailable"),
    ],
)
async def test_video_photo_reports_the_exact_cache_gate_before_attempting_work(clip, monkeypatch, disabled, outcome):
    from unittest.mock import Mock

    if disabled == "available":
        monkeypatch.setattr(module.media_cache, "_available", False)
    else:
        monkeypatch.setattr(settings.media_cache, disabled, False)
    decode = Mock(side_effect=AssertionError("disabled cache must not decode the clip"))
    monkeypatch.setattr(module, "extract_video_snapshot", decode)
    assert await module.replace_video_snapshot("cache-gate", clip, _result(), clip_variant="event") == outcome
    decode.assert_not_called()


@pytest.mark.asyncio
async def test_retained_photo_keeps_its_byte_bound_film_alignment():
    import hashlib

    photo = b"earlier-chosen-photo"
    alignment = {"frame_time": 101, "box": [0.1, 0.2, 0.3, 0.4], "image_sha256": hashlib.sha256(photo).hexdigest()}
    retained = await module.retained_snapshot_candidate("earlier-aligned", photo, {"film_alignment": alignment}, [])
    assert retained["film_alignment"] == alignment
