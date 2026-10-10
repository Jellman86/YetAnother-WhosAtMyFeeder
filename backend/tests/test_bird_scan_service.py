"""Manual scene scans own their media and never replace the primary identification."""

from contextlib import asynccontextmanager
import hashlib
import io
import os
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
from PIL import Image
import pytest
import pytest_asyncio

from app.repositories.bird_observation_repository import BirdObservationRepository
from app.repositories.bird_scan_repository import BirdScanRepository
from app.services.bird_observation_selection import BirdObservation, BirdObservationSelection
from app.services import bird_scan_service as scans
from app.services import high_quality_snapshot_service as hq


@pytest_asyncio.fixture
async def scene(tmp_path, monkeypatch):
    path = tmp_path / "scan.db"
    with sqlite3.connect(os.environ["DB_PATH"]) as source, sqlite3.connect(path) as destination:
        source.backup(destination)

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    image = Image.new("RGB", (120, 80), "green")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    content = buffer.getvalue()
    candidate = {
        "candidate_id": "scan-scene",
        "image_ref": "scan-image",
        "source_mode": "full_frame",
        "snapshot_source": "hq_candidate_full_frame",
        "clip_variant": "event",
        "frame_index": 4,
        "crop_box": None,
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "photo_hidden": False,
    }
    monkeypatch.setattr(scans, "get_db", database)
    monkeypatch.setattr(hq, "get_db", database)
    monkeypatch.setattr(scans.DetectionRepository, "list_snapshot_candidates", AsyncMock(return_value=[candidate]))
    monkeypatch.setattr(scans.media_cache, "get_snapshot", AsyncMock(return_value=content))
    monkeypatch.setattr(scans.media_cache, "get_cached_image_version", AsyncMock(return_value="version-1"))
    monkeypatch.setattr(scans.high_quality_snapshot_service, "_bird_crop_model_available", lambda: True)
    async with database() as db:
        await db.execute(
            "INSERT INTO detections(frigate_event,detection_time,detection_index,score,display_name,category_name,camera_name) "
            "VALUES ('scan-event','2026-10-08 10:00:00',1,0.99,'Owner bird','Owner bird','test-camera')"
        )
        await db.commit()
    service = scans.BirdScanService()
    selection = BirdObservationSelection(
        "event",
        4,
        "scan-scene",
        (BirdObservation("scan-scene__observed__0", (5, 5, 30, 40), 0.9, "House Finch", "House Finch", 0.9),),
    )
    monkeypatch.setattr(service, "_analyze_scene", AsyncMock(return_value=selection))
    yield service, database, candidate
    await service.stop()


@pytest.mark.asyncio
async def test_unrequested_scene_is_not_scanned_and_status_does_not_read_pixels(scene):
    service, _, _ = scene
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "not_scanned" and result["result_count"] is None
    assert result["available"] is True
    scans.media_cache.get_snapshot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"source_mode": "model_crop"},
        {"crop_box": [0, 0, 10, 10]},
        {"snapshot_source": "hq_candidate_frigate_snapshot_fallback"},
        {"photo_hidden": True},
    ],
)
async def test_scan_refuses_cropped_or_removed_scene(scene, change):
    service, _, candidate = scene
    candidate.update(change)
    result = await service.get_status("scan-event", "scan-scene")
    assert result["available"] is False
    with pytest.raises(scans.BirdScanUnavailable):
        await service.enqueue("scan-event", "scan-scene")


@pytest.mark.asyncio
async def test_manual_scan_deduplicates_and_keeps_primary_identity(scene, monkeypatch):
    service, database, _ = scene
    monkeypatch.setattr(scans.settings.media_cache, "automatic_multi_bird_scan", False)
    await service.enqueue("scan-event", "scan-scene")
    await service.enqueue("scan-event", "scan-scene", force=True)
    assert await service.run_next() is True
    assert await service.run_next() is False
    service._analyze_scene.assert_awaited_once()
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "completed" and result["result_count"] == 1
    async with database() as db:
        birds = await BirdObservationRepository(db).list_for_event("scan-event")
        row = await (
            await db.execute("SELECT display_name,score FROM detections WHERE frigate_event='scan-event'")
        ).fetchone()
    assert len(birds) == 1 and row == ("Owner bird", 0.99)


@pytest.mark.asyncio
async def test_empty_retry_retains_reviewed_birds_but_records_successful_zero(scene):
    service, database, _ = scene
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    async with database() as db:
        repository = BirdObservationRepository(db)
        bird = (await repository.list_for_event("scan-event"))[0]
        await repository.set_species("scan-event", bird["id"], "Blue Jay")
        await repository.set_hidden("scan-event", bird["id"], True)
    service._analyze_scene.return_value = BirdObservationSelection(None, None, None, ())
    await service.enqueue("scan-event", "scan-scene", force=True)
    await service.run_next()
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "completed" and result["result_count"] == 0
    assert result["retained_previous"] is True
    async with database() as db:
        bird = (await BirdObservationRepository(db).list_for_event("scan-event"))[0]
    assert bird["species"] == "Blue Jay" and bird["is_hidden"]


@pytest.mark.asyncio
async def test_replaced_pixels_cannot_receive_old_boxes(scene):
    service, database, _ = scene
    await service.enqueue("scan-event", "scan-scene")
    scans.media_cache.get_snapshot.return_value = b"replaced image"
    await service.run_next()
    async with database() as db:
        state = await BirdScanRepository(db).get("scan-event")
        assert state.status == "failed" and state.error == "media_changed"
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []
    service._analyze_scene.assert_not_awaited()


@pytest.mark.asyncio
async def test_classifier_failure_is_a_failed_job_without_private_error_text(scene):
    service, database, _ = scene
    service._analyze_scene.side_effect = RuntimeError("private provider token")
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "failed" and result["error"] == "scan_failed"
    async with database() as db:
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []


@pytest.mark.asyncio
async def test_pixels_replaced_during_inference_never_receive_stale_boxes(scene):
    service, database, _ = scene
    selection = service._analyze_scene.return_value

    async def replace_pixels(*_args):
        scans.media_cache.get_snapshot.return_value = b"replacement after analysis"
        return selection

    service._analyze_scene.side_effect = replace_pixels
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    async with database() as db:
        state = await BirdScanRepository(db).get("scan-event")
        assert state.status == "failed" and state.error == "media_changed"
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []


@pytest.mark.asyncio
async def test_owner_correction_during_inference_survives_atomic_publication(scene):
    service, database, _ = scene
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    selection = service._analyze_scene.return_value

    async def correct_bird(*_args):
        async with database() as db:
            repository = BirdObservationRepository(db)
            bird = (await repository.list_for_event("scan-event"))[0]
            await repository.set_species("scan-event", bird["id"], "Blue Jay")
            await repository.set_hidden("scan-event", bird["id"], True)
        return selection

    service._analyze_scene.side_effect = correct_bird
    await service.enqueue("scan-event", "scan-scene", force=True)
    await service.run_next()
    async with database() as db:
        bird = (await BirdObservationRepository(db).list_for_event("scan-event"))[0]
        assert bird["species"] == "Blue Jay" and bird["manual_species"] and bird["is_hidden"]
        assert (await BirdScanRepository(db).get("scan-event")).status == "completed"


@pytest.mark.asyncio
async def test_reviewed_other_frame_during_inference_rolls_back_completion(scene):
    from dataclasses import replace

    service, database, _ = scene
    selection = service._analyze_scene.return_value

    async def review_other_frame(*_args):
        async with database() as db:
            repository = BirdObservationRepository(db)
            await repository.replace_generated("scan-event", replace(selection, frame_index=99))
            bird = (await repository.list_for_event("scan-event"))[0]
            await repository.set_species("scan-event", bird["id"], "Blue Jay")
        return selection

    service._analyze_scene.side_effect = review_other_frame
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    async with database() as db:
        bird = (await BirdObservationRepository(db).list_for_event("scan-event"))[0]
        state = await BirdScanRepository(db).get("scan-event")
        assert bird["frame_index"] == 99 and bird["species"] == "Blue Jay"
        assert state.status == "failed" and state.error == "reviewed_other_frame"


@pytest.mark.asyncio
async def test_new_generation_created_during_inference_rejects_old_publication(scene):
    service, database, _ = scene
    selection = service._analyze_scene.return_value
    generations = []

    async def recreate_capture(job, _content):
        async with database() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event='scan-event'")
            await db.execute(
                "INSERT INTO detections(frigate_event,detection_time,detection_index,score,display_name,category_name,camera_name) "
                "VALUES ('scan-event','2026-10-08',1,0.99,'Owner bird','Owner bird','test-camera')"
            )
            await db.commit()
        await service.enqueue("scan-event", "scan-scene")
        async with database() as db:
            new = await BirdScanRepository(db).claim_next()
            assert new.revision == job.revision
            generations.extend((job.generation, new.generation))
        return selection

    service._analyze_scene.side_effect = recreate_capture
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    async with database() as db:
        assert generations[0] != generations[1]
        assert (await BirdScanRepository(db).get("scan-event")).status == "running"
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [{"image_ref": "other-image"}, {"clip_variant": "recording"}, {"frame_index": 5}])
async def test_status_never_claims_completion_for_different_scene_metadata(scene, changed):
    service, _, candidate = scene
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    candidate.update(changed)
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "not_scanned" and result["result_count"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change_scene", [False, True])
async def test_retry_and_changed_scene_admission_both_respect_pending_limit(scene, monkeypatch, change_scene):
    service, database, candidate = scene
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    monkeypatch.setattr(scans, "MAX_PENDING_SCANS", 0)
    if change_scene:
        candidate["frame_index"] += 1
    with pytest.raises(scans.BirdScanUnavailable, match="queue_full"):
        await service.enqueue("scan-event", "scan-scene", force=not change_scene)
    async with database() as db:
        assert (await BirdScanRepository(db).get("scan-event")).status == "completed"


def _automatic_bundle(service, candidate, *, empty=False, previous=None):
    return {
        "additional_bird_scan_performed": True,
        "bird_selection": BirdObservationSelection(None, None, None, ())
        if empty
        else service._analyze_scene.return_value,
        "candidates": [dict(candidate)],
        "automatic_scan_scenes": [dict(candidate)],
        "selected_candidate": dict(candidate),
        "automatic_scan_expected_revision": previous.revision if previous else None,
        "automatic_scan_expected_generation": previous.generation if previous else None,
    }


@pytest.mark.asyncio
async def test_automatic_successful_zero_is_distinct_from_not_scanned(scene):
    service, database, candidate = scene
    await service.record_automatic("scan-event", _automatic_bundle(service, candidate, empty=True))
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "completed" and result["result_count"] == 0
    assert result["retained_previous"] is False
    async with database() as db:
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_manual", [False, True])
async def test_old_automatic_bundle_never_overwrites_new_manual_work(scene, finish_manual):
    service, database, candidate = scene
    bundle = _automatic_bundle(service, candidate, empty=True)
    await service.enqueue("scan-event", "scan-scene")
    if finish_manual:
        await service.run_next()
    async with database() as db:
        before = await BirdScanRepository(db).get("scan-event")
    await service.record_automatic("scan-event", bundle)
    async with database() as db:
        after = await BirdScanRepository(db).get("scan-event")
        assert after == before
        assert len(await BirdObservationRepository(db).list_for_event("scan-event")) == int(finish_manual)


@pytest.mark.asyncio
async def test_automatic_bundle_cannot_publish_old_boxes_against_replaced_scene(scene):
    service, database, candidate = scene
    bundle = _automatic_bundle(service, candidate)
    replacement = b"new scene after automatic inference"
    candidate["content_sha256"] = hashlib.sha256(replacement).hexdigest()
    scans.media_cache.get_snapshot.return_value = replacement
    scans.media_cache.get_cached_image_version.return_value = "version-2"
    await service.record_automatic("scan-event", bundle)
    async with database() as db:
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []
        assert await BirdScanRepository(db).get("scan-event") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_manual", [False, True])
@pytest.mark.parametrize("missing_scene", [False, True])
async def test_untraceable_automatic_bundle_cannot_overwrite_manual_work(scene, finish_manual, missing_scene):
    from dataclasses import replace

    service, database, candidate = scene
    original = service._analyze_scene.return_value
    stale_bird = replace(
        original.birds[0], species="Stale automatic identity", classifier_label="Stale automatic identity"
    )
    stale_selection = replace(
        original, full_frame_candidate_id=None if missing_scene else "scan-scene", birds=(stale_bird,)
    )
    bundle = _automatic_bundle(service, candidate)
    bundle["bird_selection"] = stale_selection
    if missing_scene:
        bundle["candidates"] = []
        bundle["automatic_scan_scenes"] = []
    await service.enqueue("scan-event", "scan-scene")
    if finish_manual:
        await service.run_next()
    async with database() as db:
        before_state = await BirdScanRepository(db).get("scan-event")
        before_birds = await BirdObservationRepository(db).list_for_event("scan-event")
    if not missing_scene:
        scans.DetectionRepository.list_snapshot_candidates.return_value = []
    await service.record_automatic("scan-event", bundle)
    async with database() as db:
        assert await BirdScanRepository(db).get("scan-event") == before_state
        assert await BirdObservationRepository(db).list_for_event("scan-event") == before_birds


@pytest.mark.asyncio
async def test_observation_write_error_rolls_back_both_rows_and_completion(scene, monkeypatch):
    service, database, _ = scene
    replace_locked = BirdObservationRepository._replace_generated_locked

    async def fail_after_rows(repository, event_id, selection):
        await replace_locked(repository, event_id, selection)
        raise RuntimeError("database result write interrupted")

    monkeypatch.setattr(BirdObservationRepository, "_replace_generated_locked", fail_after_rows)
    await service.enqueue("scan-event", "scan-scene")
    await service.run_next()
    async with database() as db:
        state = await BirdScanRepository(db).get("scan-event")
        assert state.status == "failed" and state.error == "scan_failed"
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []


@pytest.mark.asyncio
async def test_nonempty_automatic_selection_never_borrows_another_frames_full_scene(scene):
    from dataclasses import replace

    service, database, candidate = scene
    bundle = _automatic_bundle(service, candidate)
    bundle["bird_selection"] = replace(bundle["bird_selection"], full_frame_candidate_id=None, frame_index=99)
    await service.record_automatic("scan-event", bundle)
    async with database() as db:
        assert await BirdScanRepository(db).get("scan-event") is None
        birds = await BirdObservationRepository(db).list_for_event("scan-event")
        assert all(bird["frame_index"] == 99 for bird in birds)


@pytest.mark.asyncio
async def test_native_thread_finishes_before_cancellation_returns():
    import asyncio
    import threading

    entered, release = threading.Event(), threading.Event()

    def native_work():
        entered.set()
        assert release.wait(timeout=2), "Test must always release its native work"

    task = asyncio.create_task(scans._native_call(native_work))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Cancellation must not release pixels while the native thread owns them"
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_automatic_zero_retains_legacy_owner_correction_and_reports_retention(scene):
    service, database, candidate = scene
    async with database() as db:
        observations = BirdObservationRepository(db)
        await observations.replace_generated("scan-event", service._analyze_scene.return_value)
        bird = (await observations.list_for_event("scan-event"))[0]
        await observations.set_species("scan-event", bird["id"], "Blue Jay")
    await service.record_automatic("scan-event", _automatic_bundle(service, candidate, empty=True))
    result = await service.get_status("scan-event", "scan-scene")
    assert result["status"] == "completed" and result["result_count"] == 0 and result["retained_previous"]
    async with database() as db:
        bird = (await BirdObservationRepository(db).list_for_event("scan-event"))[0]
        assert bird["species"] == "Blue Jay" and bird["manual_species"]


@pytest.mark.asyncio
async def test_replacement_before_admission_rejects_the_displayed_photo_without_loading_pixels(scene):
    service, database, _ = scene
    scans.media_cache.get_cached_image_version.return_value = "replacement-version"
    with pytest.raises(scans.BirdScanUnavailable, match="media_changed"):
        await service.enqueue("scan-event", "scan-scene", expected_media_version="version-1")
    scans.media_cache.get_snapshot.assert_not_awaited()
    service._analyze_scene.assert_not_awaited()
    async with database() as db:
        assert await BirdScanRepository(db).get("scan-event") is None


@pytest.mark.asyncio
async def test_stale_photo_status_cannot_show_a_completed_scan_for_new_pixels(scene):
    service, _, _ = scene
    scans.media_cache.get_cached_image_version.return_value = "replacement-version"
    await service.enqueue("scan-event", "scan-scene", expected_media_version="replacement-version")
    await service.run_next()
    scans.media_cache.get_snapshot.reset_mock()
    stale = await service.get_status("scan-event", "scan-scene", expected_media_version="version-1")
    assert stale["status"] == "not_scanned" and stale["result_count"] is None
    assert stale["available"] is False and stale["unavailable_reason"] == "media_changed"
    assert stale["updated_at"] is None and stale["error"] is None
    fresh = await service.get_status("scan-event", "scan-scene", expected_media_version="replacement-version")
    assert fresh["status"] == "completed" and fresh["result_count"] == 1
    scans.media_cache.get_snapshot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("scanned_other_moment", [False, True])
async def test_retained_unscanned_incumbent_cannot_be_reported_as_successful_zero(scene, scanned_other_moment):
    service, database, candidate = scene
    bundle = _automatic_bundle(service, candidate, empty=True)
    bundle["automatic_scan_scenes"] = (
        [{**candidate, "candidate_id": "actually-scanned-other-moment", "frame_index": 99}]
        if scanned_other_moment
        else []
    )
    # The selected/persisted incumbent is still a valid photo choice, but only
    # the explicit scene traversal can establish a zero count for its pixels.
    assert bundle["selected_candidate"]["candidate_id"] == "scan-scene"
    await service.record_automatic("scan-event", bundle)
    status = await service.get_status("scan-event", "scan-scene")
    assert status["status"] == "not_scanned" and status["result_count"] is None
    async with database() as db:
        assert await BirdScanRepository(db).get("scan-event") is None
        assert await BirdObservationRepository(db).list_for_event("scan-event") == []


@pytest.mark.asyncio
async def test_a_running_scan_reports_its_step_and_start_and_then_forgets_it(scene, monkeypatch):
    import asyncio

    service, _, _ = scene
    entered, release = asyncio.Event(), asyncio.Event()
    finished = service._analyze_scene.return_value

    async def analyze(job, content):
        service._report(job, "naming", done=2, total=5)
        entered.set()
        await release.wait()
        return finished

    monkeypatch.setattr(service, "_analyze_scene", analyze)
    await service.enqueue("scan-event", "scan-scene")
    worker = asyncio.create_task(service.run_next())
    await entered.wait()

    live = await service.get_status("scan-event", "scan-scene")
    assert live["status"] == "running"
    assert (live["stage"], live["stage_done"], live["stage_total"]) == ("naming", 2, 5)
    assert live["started_at"].endswith("Z") and "T" in live["started_at"]

    release.set()
    await worker
    done = await service.get_status("scan-event", "scan-scene")
    assert done["status"] == "completed"
    assert "stage" not in done and "started_at" not in done
    assert service._progress == {}


@pytest.mark.asyncio
async def test_a_queued_scan_says_how_many_scans_run_first(scene):
    service, database, _ = scene
    async with database() as db:
        await db.execute(
            "INSERT INTO detections(frigate_event,detection_time,detection_index,score,display_name,category_name,camera_name) "
            "VALUES ('scan-event-2','2026-10-08 10:01:00',1,0.99,'Owner bird','Owner bird','test-camera')"
        )
        await db.commit()
    await service.enqueue("scan-event", "scan-scene")
    await service.enqueue("scan-event-2", "scan-scene")

    assert (await service.get_status("scan-event", "scan-scene"))["queue_ahead"] == 0
    assert (await service.get_status("scan-event-2", "scan-scene"))["queue_ahead"] == 1
