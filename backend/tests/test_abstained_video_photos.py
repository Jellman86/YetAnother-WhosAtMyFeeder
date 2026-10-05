from unittest.mock import AsyncMock, MagicMock
import hashlib
import json

import pytest
from PIL import Image

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services import auto_video_classifier_service as auto
from app.services import video_snapshot_service as photos
from app.services.high_quality_snapshot_service import HQ_PROCESSING_PIPELINE
from app.utils.api_datetime import utc_naive_now


@pytest.fixture(autouse=True)
def photo_settings(monkeypatch):
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])
    monkeypatch.setattr(photos.archive_service, "refresh_photograph", AsyncMock())


async def seed(event_id, *, manual=False, hidden=False):
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=1,
                score=0.95,
                display_name="Northern Cardinal",
                category_name="Cardinalis cardinalis",
                frigate_event=event_id,
                camera_name="test",
                manual_tagged=manual,
                is_hidden=hidden,
            )
        )
    await photos.media_cache.cache_snapshot(
        event_id, photos._jpeg(Image.new("RGB", (40, 30), "red")), source="frigate_snapshot_cropped"
    )


def candidate(name, *, label="Baeolophus bicolor", mode="model_crop", presence=True):
    return {
        "candidate_id": name,
        "frame_index": 2,
        "clip_variant": "event",
        "source_mode": mode,
        "crop_box": [10, 10, 40, 40] if mode != "full_frame" else None,
        "crop_confidence": 0.9 if presence else None,
        "crop_strategy": "detector_supported" if presence else None,
        "classifier_label": label,
        "classifier_score": 0.93,
        "ranking_score": 1,
        "selected": True,
        "snapshot_source": "hq_candidate_full_frame" if mode == "full_frame" else "hq_candidate_model_crop",
        "image_ref": f"{name}__image",
        "thumbnail_ref": f"{name}__thumb",
        "image_bytes": photos._jpeg(Image.new("RGB", (80, 60), "green")),
        "thumbnail_bytes": photos._jpeg(Image.new("RGB", (80, 60), "green"), thumbnail=True),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("matching", [True, False])
async def test_abstention_reconciles_photo_without_changing_species(tmp_path, monkeypatch, matching):
    event_id = f"abstained-photo-{matching}"
    await seed(event_id)
    row = candidate(
        "matching" if matching else "scene",
        label="Cardinalis cardinalis" if matching else "Unknown",
        mode="model_crop" if matching else "full_frame",
    )
    alignment = None
    if matching:
        alignment = {
            "frame_time": 103.5,
            "box": [0.4, 0.2, 0.1, 0.1],
            "image_sha256": hashlib.sha256(row["image_bytes"]).hexdigest(),
        }
        row.update(clip_variant="frigate_snapshot", frame_index=0, film_alignment=alignment)
    scan = AsyncMock(return_value={"candidates": [row]})
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    monkeypatch.setattr(high_quality_snapshot_service, "generate_snapshot_candidates_from_clip_path", scan)
    outcome = await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4")
    assert outcome == ("replaced" if matching else "full_frame_fallback")
    assert await photos.media_cache.get_snapshot(event_id) == row["image_bytes"]
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)
        rows = await repo.list_snapshot_candidates(event_id)
    assert detection.category_name == "Cardinalis cardinalis"
    assert detection.score == 0.95
    assert next(row for row in rows if row["selected"])["classifier_label"] == row["classifier_label"]
    assert (await photos.media_cache.get_snapshot_metadata(row["image_ref"])).get("film_alignment") == alignment
    assert (await photos.media_cache.get_snapshot_metadata(event_id)).get("film_alignment") == alignment
    photos.archive_service.refresh_photograph.assert_awaited_once_with(event_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["manual_photo", "manual_identity", "hidden", "blocked", "evicted", "missing"])
async def test_abstention_photo_preflight_preserves_owner_and_retention(tmp_path, monkeypatch, condition):
    event_id = f"abstention-guard-{condition}"
    if condition != "missing":
        await seed(event_id, manual=condition == "manual_identity", hidden=condition == "hidden")
    if condition == "manual_photo":
        await photos.media_cache.set_manual_snapshot_selection(event_id, True)
    if condition == "blocked":
        monkeypatch.setattr(settings.classification, "blocked_labels", ["Cardinalis cardinalis"])
    if condition == "evicted":
        async with get_db() as db:
            await ProcessingJobRepository(db).mark_storage_evicted(HQ_PROCESSING_PIPELINE, event_id)
            await db.commit()
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    scan = AsyncMock(return_value={"candidates": [candidate("unused")]})
    monkeypatch.setattr(high_quality_snapshot_service, "generate_snapshot_candidates_from_clip_path", scan)
    before = await photos.media_cache.get_snapshot(event_id)
    expected = {
        "manual_photo": "manual_selection_preserved",
        "blocked": "blocked_species",
        "evicted": "storage_evicted",
    }
    assert await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4") == expected.get(
        condition, "owner_identification_preserved"
    )
    assert await photos.media_cache.get_snapshot(event_id) == before
    scan.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", ["wrong_species", "empty_scene", "cropped_scene", "weak_species"])
async def test_abstention_does_not_choose_unverified_or_mismatched_photos(tmp_path, monkeypatch, unsafe):
    event_id = f"abstention-unsafe-{unsafe}"
    await seed(event_id)
    row = candidate(
        "unsafe",
        mode="full_frame" if unsafe in {"empty_scene", "cropped_scene"} else "model_crop",
        presence=unsafe != "empty_scene",
    )
    if unsafe == "cropped_scene":
        row["input_is_cropped"] = True
    if unsafe == "weak_species":
        row.update(classifier_label="Cardinalis cardinalis", classifier_score=0.1)
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    monkeypatch.setattr(
        high_quality_snapshot_service,
        "generate_snapshot_candidates_from_clip_path",
        AsyncMock(return_value={"candidates": [row]}),
    )
    before = await photos.media_cache.get_snapshot(event_id)
    assert (
        await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4")
        == "bird_presence_unconfirmed"
    )
    assert await photos.media_cache.get_snapshot(event_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("correction", ["identity", "manual_photo", "hidden", "evicted"])
@pytest.mark.parametrize("automatic", [True, False])
async def test_abstention_photo_rechecks_owner_after_scan(tmp_path, monkeypatch, correction, automatic):
    event_id = f"abstention-race-{correction}-{automatic}"
    await seed(event_id)
    before = await photos.media_cache.get_snapshot(event_id)

    async def scan(*args, **kwargs):
        if correction == "manual_photo":
            await photos.media_cache.set_manual_snapshot_selection(event_id, True)
        else:
            async with get_db() as db:
                if correction == "evicted":
                    await ProcessingJobRepository(db).mark_storage_evicted(HQ_PROCESSING_PIPELINE, event_id)
                else:
                    statement = (
                        "UPDATE detections SET category_name = 'Other', display_name = 'Other', manual_tagged = 1"
                        if correction == "identity"
                        else "UPDATE detections SET is_hidden = 1"
                    )
                    await db.execute(statement + " WHERE frigate_event = ?", (event_id,))
                await db.commit()
        return {"candidates": [candidate("race-scene", mode="full_frame")]}

    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    monkeypatch.setattr(high_quality_snapshot_service, "generate_snapshot_candidates_from_clip_path", scan)
    outcome = await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4", automatic=automatic)
    if correction == "identity" and not automatic:
        assert outcome == "primary_identity_preserved"
    else:
        assert outcome in {"manual_selection_preserved", "owner_identification_preserved", "storage_evicted"}
    assert await photos.media_cache.get_snapshot(event_id) == before


@pytest.mark.asyncio
async def test_video_abstention_settles_photo_before_completion(monkeypatch):
    service = auto.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[])
    service._update_status = AsyncMock()
    service._wait_for_clip = AsyncMock(return_value=(True, None))
    service._save_results = AsyncMock()
    monkeypatch.setattr(auto.frigate_client, "get_event_with_error", AsyncMock(return_value=({"has_clip": True}, None)))
    broadcast = AsyncMock()
    monkeypatch.setattr(auto.broadcaster, "broadcast", broadcast)
    photo = AsyncMock(return_value="full_frame_fallback")
    monkeypatch.setattr(auto, "reconcile_snapshot_identity", photo, raising=False)
    await service._process_event("abstention-completion", "test", skip_delay=True)
    photo.assert_awaited_once()
    service._save_results.assert_not_awaited()
    completed = [
        call.args[0]["data"]
        for call in broadcast.await_args_list
        if call.args[0]["type"] == "reclassification_completed"
    ]
    assert completed[-1]["outcome"] == "no_result"
    assert completed[-1]["photo_outcome"] == "full_frame_fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize("displayed", [True, False])
async def test_abstention_reuses_retained_matching_evidence_without_scanning(tmp_path, monkeypatch, displayed):
    event_id = f"abstention-reuse-{displayed}"
    await seed(event_id)
    row = candidate("retained-cardinal", label="Northern Cardinal")
    row.update(clip_variant="frigate_snapshot", frame_index=0)
    alignment = {
        "frame_time": 103.5,
        "box": [0.4, 0.2, 0.1, 0.1],
        "image_sha256": hashlib.sha256(row["image_bytes"]).hexdigest(),
    }
    await photos.media_cache.cache_snapshot(
        row["image_ref"], row["image_bytes"], source="snapshot_candidate", film_alignment=alignment
    )
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(event_id, [row])
    if displayed:
        await photos.media_cache.cache_snapshot(
            event_id, row["image_bytes"], source="video_evidence_crop", film_alignment=alignment
        )
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    scan = AsyncMock()
    monkeypatch.setattr(high_quality_snapshot_service, "generate_snapshot_candidates_from_clip_path", scan)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", False)
    assert await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4") == (
        "matching_photo_preserved" if displayed else "replaced"
    )
    scan.assert_not_awaited()
    assert await photos.media_cache.get_snapshot(event_id) == row["image_bytes"]
    assert (await photos.media_cache.get_snapshot_metadata(row["image_ref"]))["film_alignment"] == alignment
    assert (await photos.media_cache.get_snapshot_metadata(event_id))["film_alignment"] == alignment


@pytest.mark.asyncio
async def test_abstention_drops_stale_film_proof_when_reusing_retained_photo(tmp_path, monkeypatch):
    event_id = "abstention-reuse-stale-proof"
    await seed(event_id)
    row = candidate("stale-proof-cardinal", label="Northern Cardinal")
    await photos.media_cache.cache_snapshot(row["image_ref"], row["image_bytes"], source="snapshot_candidate")
    metadata = await photos.media_cache.get_snapshot_metadata(row["image_ref"])
    metadata["film_alignment"] = {
        "frame_time": 103.5,
        "box": [0.4, 0.2, 0.1, 0.1],
        "image_sha256": "0" * 64,
    }
    await photos.media_cache._write_bytes_atomic(
        photos.media_cache._snapshot_metadata_path(row["image_ref"]), json.dumps(metadata).encode()
    )
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(event_id, [row])
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    scan = AsyncMock()
    monkeypatch.setattr(high_quality_snapshot_service, "generate_snapshot_candidates_from_clip_path", scan)
    assert await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4") == "replaced"
    scan.assert_not_awaited()
    assert await photos.media_cache.get_snapshot(event_id) == row["image_bytes"]
    assert (await photos.media_cache.get_snapshot_metadata(row["image_ref"])).get("film_alignment") is None
    assert (await photos.media_cache.get_snapshot_metadata(event_id)).get("film_alignment") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("retained_file", ["missing", "corrupt", "read_error", "usable"])
async def test_abstention_scans_once_when_retained_candidates_have_no_usable_photo(
    tmp_path, monkeypatch, retained_file
):
    event_id = f"abstention-unreadable-{retained_file}"
    await seed(event_id)
    retained = candidate(f"old-{retained_file}", label="Cardinalis cardinalis")
    if retained_file != "missing":
        await photos.media_cache.cache_snapshot(
            retained["image_ref"],
            b"not-a-jpeg" if retained_file == "corrupt" else retained["image_bytes"],
            source="snapshot_candidate",
        )
    async with get_db() as db:
        retained_candidates = [retained]
        if retained_file == "missing":
            retained_candidates.append(candidate("second-missing", label="Cardinalis cardinalis"))
        await DetectionRepository(db).replace_snapshot_candidates(event_id, retained_candidates)
    if retained_file == "read_error":
        get_snapshot = photos.media_cache.get_snapshot

        async def unreadable_candidate(reference):
            if reference == retained["image_ref"]:
                raise OSError("Candidate file could not be read")
            return await get_snapshot(reference)

        monkeypatch.setattr(photos.media_cache, "get_snapshot", unreadable_candidate)
    fresh = candidate(f"fresh-{retained_file}", label="Cardinalis cardinalis")
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    scan = AsyncMock(return_value={"candidates": [fresh]})
    monkeypatch.setattr(high_quality_snapshot_service, "generate_snapshot_candidates_from_clip_path", scan)
    assert await photos.reconcile_snapshot_identity(event_id, clip_path=tmp_path / "clip.mp4") == "replaced"
    if retained_file == "usable":
        scan.assert_not_awaited()
    else:
        scan.assert_awaited_once()
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)
        rows = await repo.list_snapshot_candidates(event_id)
    assert detection.category_name == "Cardinalis cardinalis"
    assert detection.score == 0.95
    assert next(row for row in rows if row["selected"])["candidate_id"] == (
        retained["candidate_id"] if retained_file == "usable" else fresh["candidate_id"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("results", [[], [{"label": "Cardinalis cardinalis", "score": 0.95, "index": 1}]])
async def test_snapshot_fallback_reports_photo_outcome(monkeypatch, results):
    event_id = "snapshot-photo-completion"
    await seed(event_id)
    service = auto.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async_background = AsyncMock(return_value=results)
    service._update_status = AsyncMock()
    service._save_results = AsyncMock(return_value=True)
    broadcast = AsyncMock()
    monkeypatch.setattr(auto.broadcaster, "broadcast", broadcast)
    reconcile = AsyncMock(return_value="full_frame_fallback")
    monkeypatch.setattr(auto, "reconcile_snapshot_identity", reconcile)
    error = await service._classify_from_snapshot(event_id, "test")
    assert error == ("snapshot_no_results" if not results else None)
    completion = [
        call.args[0]["data"]
        for call in broadcast.await_args_list
        if call.args[0]["type"] == "reclassification_completed"
    ]
    assert completion[-1]["photo_outcome"] == "full_frame_fallback"


@pytest.mark.asyncio
async def test_abstention_photo_scan_timeout_is_reported_before_completion(monkeypatch):
    service = auto.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[])
    service._update_status = AsyncMock()
    service._wait_for_clip = AsyncMock(return_value=(True, None))
    service._save_results = AsyncMock()
    monkeypatch.setattr(auto.frigate_client, "get_event_with_error", AsyncMock(return_value=({"has_clip": True}, None)))
    broadcast = AsyncMock()
    monkeypatch.setattr(auto.broadcaster, "broadcast", broadcast)
    monkeypatch.setattr(auto, "reconcile_snapshot_identity", AsyncMock(side_effect=TimeoutError()))
    await service._process_event("abstention-scan-timeout", "test", skip_delay=True)
    service._save_results.assert_not_awaited()
    completed = [
        call.args[0]["data"]
        for call in broadcast.await_args_list
        if call.args[0]["type"] == "reclassification_completed"
    ]
    assert completed[-1]["photo_outcome"] == "photo_scan_timeout"
    assert completed[-1]["outcome"] == "no_result"


def test_video_evidence_keeps_bird_presence_for_the_paired_full_frame():
    evidence = {
        "frame_index": 2,
        "frame_width": 80,
        "frame_height": 60,
        "crop_box": [10, 10, 40, 40],
        "bird_box": [12, 12, 35, 35],
        "input_is_cropped": True,
        "input_source": "model_crop",
        "score": 0.94,
        "presence_source": "bird_crop_detector",
        "detector_confidence": 0.9,
    }
    scene = Image.new("RGB", (80, 60), "green")
    rows = photos._candidates(
        "paired-frame", {"label": "Cardinalis cardinalis"}, evidence, (scene.crop(evidence["crop_box"]), scene), "event"
    )
    full = next(row for row in rows if row["source_mode"] == "full_frame")
    assert photos.has_reusable_bird_presence(full)
    assert full["classifier_label"] is None
    assert full["classifier_score"] is None


@pytest.mark.asyncio
async def test_hq_generation_retains_presence_even_when_species_abstains(monkeypatch):
    from app.services.high_quality_snapshot_service import HighQualitySnapshotService

    service = HighQualitySnapshotService()
    full = candidate("hq-full", label="Unknown", mode="full_frame", presence=False)
    crop = candidate("hq-crop", label="Baeolophus bicolor")
    for row in (full, crop):
        row.update(frame_width=80, frame_height=60, classifier_score=0.1, input_is_cropped=row is crop)
    crop["detector_box"] = [10, 10, 40, 40]
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda row: row))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"Cardinalis cardinalis"}))
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))
    bundle = await service._score_and_select_snapshot_candidates("hq-abstention", [full, crop])
    assert bundle["selected_candidate"] is None
    scenes = photos._identity_photo_candidates(bundle["candidates"], {"cardinalis cardinalis"})
    assert [row["candidate_id"] for row in scenes] == ["hq-full"]


@pytest.mark.asyncio
async def test_video_abstention_photo_change_preserves_snapshot_fallback_input(monkeypatch):
    event_id = "abstention-input-before-photo"
    await seed(event_id)
    service = auto.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[])
    service._classifier.classify_async_background = AsyncMock(return_value=[])
    service._update_status = AsyncMock()
    service._wait_for_clip = AsyncMock(return_value=(True, None))
    service._save_results = AsyncMock()
    monkeypatch.setattr(auto.frigate_client, "get_event_with_error", AsyncMock(return_value=({"has_clip": True}, None)))
    monkeypatch.setattr(auto.broadcaster, "broadcast", AsyncMock())

    async def move_photo(*args, **kwargs):
        await photos.media_cache.cache_snapshot(
            event_id, photos._jpeg(Image.new("RGB", (80, 60), "green")), source="hq_candidate_full_frame"
        )
        return "full_frame_fallback"

    monkeypatch.setattr(auto, "reconcile_snapshot_identity", AsyncMock(side_effect=move_photo))
    await service._process_event(event_id, "test", skip_delay=True, source="manual")
    service._classifier.classify_async_background.assert_awaited_once()
    call = service._classifier.classify_async_background.await_args
    image = call.args[0]
    assert image.size == (40, 30)
    assert image.getpixel((10, 10))[0] > 240
    assert call.kwargs["input_context"]["input_source"] == "frigate_snapshot_cropped"
    assert call.kwargs["input_context"]["is_cropped"] is True
    service._save_results.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("clip_available", [True, False])
@pytest.mark.parametrize("weak_snapshot", [True, False])
@pytest.mark.parametrize("owner_photo", [True, False])
async def test_manual_reclassification_repairs_automatic_photo_after_abstention(
    monkeypatch, clip_available, weak_snapshot, owner_photo
):
    event_id = f"manual-abstention-{clip_available}-{weak_snapshot}-{owner_photo}"
    await seed(event_id, manual=True)
    before = await photos.media_cache.get_snapshot(event_id)
    row = candidate("retained-matching-cardinal", label="Cardinalis cardinalis")
    await photos.media_cache.cache_snapshot(row["image_ref"], row["image_bytes"], source="snapshot_candidate")
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(event_id, [row])
    if owner_photo:
        await photos.media_cache.set_manual_snapshot_selection(event_id, True)
    service = auto.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = AsyncMock(return_value=[])
    service._classifier.classify_async_background = AsyncMock(
        return_value=[{"label": "Other", "score": 0.1, "index": 1}] if weak_snapshot else []
    )
    service._load_preferred_clip = AsyncMock(
        return_value=(clip_available, None if clip_available else "clip_unavailable", "event", None)
    )
    service._update_status = AsyncMock()
    service._save_results = AsyncMock()
    monkeypatch.setattr(auto.frigate_client, "get_event_with_error", AsyncMock(return_value=({"has_clip": True}, None)))
    monkeypatch.setattr(auto.frigate_client, "get_snapshot", AsyncMock(return_value=None))
    broadcast = AsyncMock()
    monkeypatch.setattr(auto.broadcaster, "broadcast", broadcast)

    await service._process_event(event_id, "test", skip_delay=True, source="manual")

    assert await photos.media_cache.get_snapshot(event_id) == (before if owner_photo else row["image_bytes"])
    async with get_db() as db:
        detection = await DetectionRepository(db).get_by_frigate_event(event_id)
    assert detection.category_name == "Cardinalis cardinalis"
    assert detection.score == 0.95
    service._save_results.assert_not_awaited()
    completions = [
        call.args[0]["data"]
        for call in broadcast.await_args_list
        if call.args[0]["type"] == "reclassification_completed"
    ]
    assert completions[-1]["photo_outcome"] == ("manual_selection_preserved" if owner_photo else "replaced")
