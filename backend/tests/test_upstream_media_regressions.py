"""Reporter scenarios: archived media, stale portraits and visit-owned cache files."""

import os
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from app.auth import AuthContext
from app.config import settings
from app.routers import events, proxy
from app.services import high_quality_snapshot_service as hq
from app.services import media_cache as cache_module
from app.services.archive_service import archive_service
from app.database import get_db, init_db, close_db
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.repositories.maintenance_job_repository import MaintenanceJobRepository


def jpeg(size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "green").save(output, format="JPEG")
    return output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["HEAD", "GET"])
@pytest.mark.parametrize("recording", [False, True])
async def test_archived_video_survives_frigate_retention(tmp_path, monkeypatch, method, recording):
    clip = tmp_path / "archived.mp4"
    clip.write_bytes(b"archived-video" * 100)
    api = FastAPI()
    api.include_router(proxy.router)
    api.dependency_overrides[proxy.get_proxy_auth_context] = lambda: AuthContext("owner")
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(proxy, "require_event_access", AsyncMock())
    monkeypatch.setattr(archive_service, "clip_path", AsyncMock(return_value=None if recording else clip))
    monkeypatch.setattr(archive_service, "recording_path", AsyncMock(return_value=clip if recording else None))
    upstream = AsyncMock(return_value=None)
    monkeypatch.setattr(proxy.frigate_client, "get_event", upstream)
    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404)))
    monkeypatch.setattr(proxy, "get_http_client", lambda: upstream_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        response = await client.request(method, "/frigate/archived/clip.mp4")
    await upstream_client.aclose()
    assert response.status_code == 200
    if method == "GET":
        assert response.content == clip.read_bytes()
    upstream.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_is_included_in_event_media_availability(tmp_path, monkeypatch):
    monkeypatch.setattr(
        events.frigate_client, "get_event_with_error", AsyncMock(return_value=(None, "event_not_found"))
    )
    for name in ("has_snapshot", "has_clip", "has_recording_clip"):
        monkeypatch.setattr(cache_module.media_cache, name, lambda _: False)
    monkeypatch.setattr(archive_service, "snapshot_path", AsyncMock(return_value=tmp_path / "photo.jpg"))
    monkeypatch.setattr(archive_service, "clip_path", AsyncMock(return_value=tmp_path / "clip.mp4"))
    flags = (await events.batch_check_clips(["archived"]))["archived"]
    assert flags == {"has_frigate_event": False, "has_clip": True, "has_snapshot": True}


@pytest.mark.asyncio
async def test_card_uses_archived_photo_when_snapshot_caching_is_off(tmp_path, monkeypatch):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(jpeg((1200, 900)))
    api = FastAPI()
    api.include_router(proxy.router)
    api.dependency_overrides[proxy.get_proxy_auth_context] = lambda: AuthContext("owner")
    monkeypatch.setattr(proxy, "require_event_access", AsyncMock())
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", False)
    monkeypatch.setattr(archive_service, "snapshot_path", AsyncMock(return_value=photo))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/frigate/archived/thumbnail.jpg")
    assert response.status_code == 200
    assert Image.open(BytesIO(response.content)).size == (960, 720)


@pytest.mark.asyncio
async def test_correct_new_full_frame_replaces_unverified_old_crop(monkeypatch):
    service = hq.HighQualitySnapshotService()
    monkeypatch.setattr(service, "enabled", lambda: True)
    monkeypatch.setattr(service, "_wait_for_clip", AsyncMock(return_value=(b"clip", None)))
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_existing_snapshot_is_cropped", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"Cardinalis cardinalis"}))
    candidate = {
        "candidate_id": "new",
        "source_mode": "full_frame",
        "classifier_label": "Cardinalis cardinalis",
        "classifier_score": 0.85,
        "image_bytes": jpeg((1200, 900)),
    }
    monkeypatch.setattr(
        service,
        "generate_snapshot_candidates_from_clip_bytes",
        AsyncMock(return_value={"selected_candidate": candidate, "candidates": [candidate]}),
    )
    for name in ("_persist_snapshot_candidates", "_persist_bird_observations", "_apply_classification_refinement"):
        monkeypatch.setattr(service, name, AsyncMock())
    replace = AsyncMock(return_value=Path("photo.jpg"))
    monkeypatch.setattr(cache_module.media_cache, "replace_snapshot", replace)
    monkeypatch.setattr(archive_service, "refresh_photograph", AsyncMock())
    assert await service._process_event_once("cardinal") == "replaced"
    replace.assert_awaited_once()


@pytest.mark.parametrize("operation", ["age", "orphan", "delete"])
@pytest.mark.asyncio
async def test_alternate_photos_and_sidecars_follow_their_visit(tmp_path, monkeypatch, operation):
    snapshots, clips, previews = (tmp_path / name for name in ("snapshots", "clips", "previews"))
    for path in (snapshots, clips, previews):
        path.mkdir()
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(cache_module, "CLIPS_DIR", clips)
    monkeypatch.setattr(cache_module, "PREVIEWS_DIR", previews)
    service = cache_module.MediaCacheService()
    event = "visit"
    names = [
        "visit.jpg",
        "visit.jpg.meta.json",
        "visit_thumb.jpg",
        "visit__model_crop__f10__0123456789__image.jpg",
        "visit__model_crop__f10__0123456789__image.jpg.meta.json",
        "visit__model_crop__f10__0123456789__thumb_thumb.jpg",
    ]
    for name in names:
        path = snapshots / name
        path.write_bytes(b"fixture")
        old = (datetime.now() - timedelta(days=30)).timestamp()
        os.utime(path, (old, old))
    other = snapshots / "visit_other.jpg"
    other.write_bytes(b"other")
    if operation == "age":
        await service.cleanup_old_media(7, protected_event_ids={event})
    elif operation == "orphan":
        await service.cleanup_orphaned_media({event, "visit_other"})
    else:
        await service.delete_cached_media(event)
    assert other.exists()
    for name in names:
        assert (snapshots / name).exists() is (operation != "delete")


@pytest.mark.asyncio
async def test_photo_intent_survives_full_memory_queue_and_new_service(monkeypatch):
    await init_db()
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES ('durable_photo','cam','2026-01-01',0,0.9,'Robin','bird')"
            )
            await db.commit()
        first = hq.HighQualitySnapshotService()
        monkeypatch.setattr(first, "enabled", lambda: True)
        monkeypatch.setattr(first, "schedule_replacement", lambda *args, **kwargs: False)
        assert await first.schedule_replacement_durable("durable_photo") is True
        replacement = hq.HighQualitySnapshotService()
        monkeypatch.setattr(replacement, "enabled", lambda: True)
        scheduled = []
        monkeypatch.setattr(replacement, "schedule_replacement", lambda event_id: scheduled.append(event_id) or True)
        assert await replacement.recover_durable_jobs() == 1
        assert scheduled == ["durable_photo"]
        async with get_db() as db:
            await ProcessingJobRepository(db).record_success(hq.HQ_PROCESSING_PIPELINE, "durable_photo")
        assert await replacement.recover_durable_jobs() == 0
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event='durable_photo'")
            await db.commit()
        await close_db()


@pytest.mark.asyncio
async def test_maintenance_summary_retains_counters_after_restart():
    await init_db()
    try:
        summary = {
            "id": "durable_summary",
            "kind": "detections",
            "status": "running",
            "processed": 438,
            "new_detections": 241,
            "skipped": 197,
            "errors": 0,
        }
        async with get_db() as db:
            repo = MaintenanceJobRepository(db)
            await repo.save(summary)
            await repo.recover_interrupted()
            saved = await repo.get(summary["id"])
            assert saved["status"] == "failed"
            assert saved["processed"] == 438
            assert saved["new_detections"] == 241
            assert saved["skipped"] == 197
            assert saved["errors"] == 0
            await db.execute("DELETE FROM maintenance_job_history WHERE id=?", (summary["id"],))
            await db.commit()
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_manual_photo_survives_automatic_and_live_snapshot_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    chosen = jpeg((300, 300))
    await service.replace_snapshot("chosen", chosen, manual_selection=True)
    await service.replace_snapshot("chosen", jpeg((400, 400)), automatic=True)
    await service.cache_snapshot("chosen", jpeg((500, 500)))
    assert await service.get_snapshot("chosen") == chosen
    await service.set_manual_snapshot_selection("chosen", False)
    await service.replace_snapshot("chosen", jpeg((400, 400)), automatic=True)
    assert Image.open(BytesIO(await service.get_snapshot("chosen"))).size == (400, 400)


@pytest.mark.asyncio
async def test_deleting_visit_preserves_other_event_named_like_its_thumbnail(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    await service.cache_snapshot("bird", jpeg((300, 300)))
    await service.cache_snapshot("bird_thumb", jpeg((400, 400)))
    await service.delete_cached_media("bird")
    assert await service.get_snapshot("bird_thumb") is not None
    assert (await service.get_snapshot_metadata("bird_thumb"))["event_id"] == "bird_thumb"


@pytest.mark.asyncio
async def test_orphan_cleanup_leaves_an_atomic_write_in_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    temporary = tmp_path / "pending.jpg.012345.tmp"
    temporary.write_bytes(b"in progress")
    await cache_module.MediaCacheService().cleanup_orphaned_media(set())
    assert temporary.exists()


@pytest.mark.asyncio
async def test_retry_backoff_and_final_refresh_survive_old_pass_completion():
    from datetime import timezone

    await init_db()
    event = "revision_race"
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES (?,'cam','2026-01-01',0,0.9,'Robin','bird')",
                (event,),
            )
            await db.commit()
            repo = ProcessingJobRepository(db)
            assert await repo.enqueue(hq.HQ_PROCESSING_PIPELINE, event)
            now = datetime.now(timezone.utc)
            await repo.record_failure(
                hq.HQ_PROCESSING_PIPELINE, event, error="missing", retry_delays_seconds=(3600,), now=now
            )
            assert not await repo.enqueue(hq.HQ_PROCESSING_PIPELINE, event)
            assert event not in await repo.list_due(hq.HQ_PROCESSING_PIPELINE, now)
            assert event in await repo.list_due(hq.HQ_PROCESSING_PIPELINE, now + timedelta(hours=1))
            assert await repo.enqueue(hq.HQ_PROCESSING_PIPELINE, event, force=True)
            await repo.record_success(hq.HQ_PROCESSING_PIPELINE, event, expected_revision=0)
            saved = await repo.get(hq.HQ_PROCESSING_PIPELINE, event)
            assert saved.status == "queued" and saved.revision == 1 and saved.attempt_count == 0
            await repo.record_failure(
                hq.HQ_PROCESSING_PIPELINE, event, expected_revision=0, error="old_error", retry_delays_seconds=(3600,)
            )
            assert (await repo.get(hq.HQ_PROCESSING_PIPELINE, event)).status == "queued"
            await repo.record_success(hq.HQ_PROCESSING_PIPELINE, event, expected_revision=1)
            assert (await repo.get(hq.HQ_PROCESSING_PIPELINE, event)).status == "succeeded"
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event=?", (event,))
            await db.commit()
        await close_db()


@pytest.mark.asyncio
async def test_storage_limit_removes_media_keeps_history_and_stops_regeneration(tmp_path, monkeypatch):
    from app.services.media_storage_service import MediaStorageService

    for name in ("SNAPSHOTS_DIR", "CLIPS_DIR", "PREVIEWS_DIR"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setattr(cache_module, name, directory)
    service = cache_module.MediaCacheService()
    monkeypatch.setattr(cache_module, "media_cache", service)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "per_species_maximum", 1)
    monkeypatch.setattr(settings.media_cache, "max_size_mb", 0)
    await init_db()
    try:
        async with get_db() as db:
            for i, event in enumerate(("limit_old", "limit_new", "limit_favorite")):
                await db.execute(
                    "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES (?,'cam',?,0,0.9,'Robin','bird')",
                    (event, f"2026-01-0{i + 1}"),
                )
                await service.cache_snapshot(event, jpeg((300, 300)))
            await db.execute(
                "INSERT INTO detection_favorites (detection_id) SELECT id FROM detections WHERE frigate_event='limit_favorite'"
            )
            await db.commit()
        result = await MediaStorageService().enforce_limits()
        assert result["visits_evicted"] == 1 and result["bytes_freed"] > 0
        assert await service.get_snapshot("limit_old") is None
        assert await service.get_snapshot("limit_new") is not None
        assert await service.get_snapshot("limit_favorite") is not None
        async with get_db() as db:
            state = await ProcessingJobRepository(db).get(hq.HQ_PROCESSING_PIPELINE, "limit_old")
            assert state.status == "terminal" and state.last_error == "storage_evicted"
            async with db.execute("SELECT COUNT(*) FROM detections WHERE frigate_event LIKE 'limit_%'") as cursor:
                assert (await cursor.fetchone())[0] == 3
    finally:
        async with get_db() as db:
            await db.execute(
                "DELETE FROM detection_favorites WHERE detection_id IN (SELECT id FROM detections WHERE frigate_event LIKE 'limit_%')"
            )
            await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'limit_%'")
            await db.commit()
        await close_db()


def test_automatic_portrait_rejects_weak_localization_and_prefers_matching_detail():
    service = hq.HighQualitySnapshotService()
    full = {
        "candidate_id": "full",
        "source_mode": "full_frame",
        "classifier_label": "Cardinal",
        "classifier_score": 0.85,
        "ranking_score": 0.85,
    }
    weak = {
        "candidate_id": "chairs",
        "source_mode": "model_crop",
        "classifier_label": "Cardinal",
        "classifier_score": 0.99,
        "ranking_score": 0.99,
        "crop_confidence": 0.01,
        "image_width": 400,
        "image_height": 400,
    }
    portrait = {**weak, "candidate_id": "bird", "classifier_score": 0.83, "ranking_score": 0.83, "crop_confidence": 0.5}
    assert service._select_best_trusted_candidate([full, weak], expected_labels={"Cardinal"}) == full
    assert service._select_best_trusted_candidate([full, weak, portrait], expected_labels={"Cardinal"}) == portrait


def test_standard_scan_avoids_tiles_while_intensive_scans_them(monkeypatch):
    from app.services.bird_crop_service import BirdCropService

    service = BirdCropService()
    calls = []
    monkeypatch.setattr(service, "_infer_candidates", lambda model, image: calls.append(image.size) or [])
    image = Image.new("RGB", (3840, 2160))
    monkeypatch.setattr(settings.media_cache, "bird_scan_mode", "standard")
    service._infer_frame_candidates(object(), image)
    assert len(calls) == 1
    calls.clear()
    monkeypatch.setattr(settings.media_cache, "bird_scan_mode", "intensive")
    service._infer_frame_candidates(object(), image)
    assert len(calls) == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["HEAD", "GET"])
async def test_archived_full_visit_precedes_context_and_cached_negative_probe(tmp_path, monkeypatch, method):
    clip = tmp_path / "recording.mp4"
    clip.write_bytes(b"archived-recording" * 100)
    api = FastAPI()
    api.include_router(proxy.router)
    api.dependency_overrides[proxy.get_proxy_auth_context] = lambda: AuthContext("owner")
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", True)
    monkeypatch.setattr(proxy, "require_event_access", AsyncMock())
    context = AsyncMock(side_effect=AssertionError("archive must precede Frigate context"))
    monkeypatch.setattr(proxy, "_get_recording_clip_context", context)
    monkeypatch.setattr(archive_service, "recording_path", AsyncMock(return_value=clip))
    import time

    monkeypatch.setitem(proxy._head_response_cache, "saved_recording", (time.time(), 404))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        response = await client.request(method, "/frigate/saved_recording/recording-clip.mp4")
    assert response.status_code == 200
    assert response.headers["X-YAWAMF-Recording-Clip-Ready"] == "cached"
    if method == "GET":
        assert response.content == clip.read_bytes()
    context.assert_not_awaited()


@pytest.mark.asyncio
async def test_archive_respects_access_and_supports_range_requests(tmp_path, monkeypatch):
    from fastapi import HTTPException

    clip = tmp_path / "range.mp4"
    clip.write_bytes(b"0123456789" * 100)
    api = FastAPI()
    api.include_router(proxy.router)
    api.dependency_overrides[proxy.get_proxy_auth_context] = lambda: AuthContext("owner")
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    lookup = AsyncMock(return_value=clip)
    monkeypatch.setattr(archive_service, "video_path", lookup)
    access = AsyncMock(side_effect=HTTPException(403))
    monkeypatch.setattr(proxy, "require_event_access", access)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://test") as client:
        response = await client.get("/frigate/saved_range/clip.mp4")
        assert response.status_code == 403
        lookup.assert_not_awaited()
        access.side_effect = None
        response = await client.get("/frigate/saved_range/clip.mp4", headers={"Range": "bytes=10-19"})
        assert response.status_code == 206
        assert response.content == b"0123456789"


@pytest.mark.asyncio
async def test_age_cleanup_does_not_recreate_deliberately_expired_photos(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    event = "expired_media"
    await init_db()
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES (?,'cam','2026-01-01',0,0.9,'Robin','bird')",
                (event,),
            )
            await db.commit()
        await service.cache_snapshot(event, jpeg((300, 300)))
        old = (datetime.now() - timedelta(days=30)).timestamp()
        for path in tmp_path.iterdir():
            os.utime(path, (old, old))
        await service.cleanup_old_media(7)
        async with get_db() as db:
            state = await ProcessingJobRepository(db).get(hq.HQ_PROCESSING_PIPELINE, event)
            assert state.status == "terminal" and state.last_error == "storage_evicted"
        assert await service.get_snapshot(event) is None
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event=?", (event,))
            await db.commit()
        await close_db()


@pytest.mark.asyncio
async def test_generated_candidate_thumbnails_are_owned_by_the_parent_visit(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    key = "parent__model_crop__f150__0123456789__thumb"
    path = await service.cache_thumbnail(key, jpeg((240, 240)), source="snapshot_candidate")
    assert cache_module.cache_file_event_id(path) == "parent"
    assert cache_module.cache_file_event_id(path.with_suffix(".jpg.meta.json")) == "parent"
    await service.cleanup_orphaned_media({"parent"})
    assert path.exists()
    await service.delete_cached_media("parent")
    assert not path.exists()


def test_saved_photo_backlog_is_counted_beyond_the_visible_page(monkeypatch):
    from app.routers.jobs import JobSnapshotItem, _build_lanes

    monkeypatch.setattr(hq.high_quality_snapshot_service, "get_status", lambda: {"durable_pending": 1524})
    items = [
        JobSnapshotItem(id="photo", kind="high_quality_snapshot", source="automatic", status="queued", phase="waiting")
    ]
    lane = next(lane for lane in _build_lanes(items) if lane.kind == "high_quality_snapshot")
    assert lane.queued == 1524


@pytest.mark.asyncio
async def test_age_cleanup_keeps_old_sidecar_with_recently_accessed_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    await service.cache_snapshot("fresh_photo", jpeg((300, 300)))
    metadata = tmp_path / "fresh_photo.jpg.meta.json"
    old = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(metadata, (old, old))
    await service.cleanup_old_media(7)
    assert await service.get_snapshot("fresh_photo") is not None
    assert metadata.exists()


@pytest.mark.asyncio
async def test_regeneration_keeps_a_newer_manual_photo_from_another_client(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    await service.replace_snapshot("chosen", jpeg((300, 300)), manual_selection=True)
    started_at = (await service.get_snapshot_metadata("chosen"))["updated_at"]
    newer_choice = jpeg((400, 400))
    await service.replace_snapshot("chosen", newer_choice, manual_selection=True)
    await service.replace_snapshot(
        "chosen",
        jpeg((500, 500)),
        clear_manual_selection=True,
        expected_manual_selection_updated_at=started_at,
    )
    assert await service.get_snapshot("chosen") == newer_choice
    assert (await service.get_snapshot_metadata("chosen"))["manual_selection"] is True


@pytest.mark.asyncio
async def test_failed_regeneration_keeps_manual_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    service = cache_module.MediaCacheService()
    chosen = jpeg((300, 300))
    await service.replace_snapshot("chosen", chosen, manual_selection=True)
    started_at = (await service.get_snapshot_metadata("chosen"))["updated_at"]

    async def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(service, "_write_bytes_atomic", fail_write)
    assert (
        await service.replace_snapshot(
            "chosen",
            jpeg((400, 400)),
            clear_manual_selection=True,
            expected_manual_selection_updated_at=started_at,
        )
        is None
    )
    assert await service.get_snapshot("chosen") == chosen
    assert (await service.get_snapshot_metadata("chosen"))["manual_selection"] is True


@pytest.mark.asyncio
async def test_automatic_candidate_refresh_keeps_chosen_photo_and_its_full_scene(tmp_path, monkeypatch):
    from app.repositories.detection_repository import DetectionRepository

    monkeypatch.setattr(cache_module, "SNAPSHOTS_DIR", tmp_path)
    cache = cache_module.MediaCacheService()
    monkeypatch.setattr(hq, "media_cache", cache)
    await init_db()
    event = "chosen_candidate"
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES (?,'cam','2026-01-01',0,0.9,'Robin','bird')",
                (event,),
            )
            await db.commit()
            await DetectionRepository(db).replace_snapshot_candidates(
                event,
                [
                    {
                        "candidate_id": "chosen",
                        "source_mode": "model_crop",
                        "frame_index": 1,
                        "selected": True,
                        "image_ref": "chosen-image",
                    },
                    {
                        "candidate_id": "scene",
                        "source_mode": "full_frame",
                        "frame_index": 1,
                        "image_ref": "chosen-scene",
                    },
                ],
            )
        await cache.cache_snapshot("chosen-image", jpeg((300, 300)))
        await cache.cache_snapshot("chosen-scene", jpeg((900, 600)))
        await cache.replace_snapshot(event, jpeg((300, 300)), manual_selection=True, manual_candidate_id="chosen")
        await hq.HighQualitySnapshotService()._persist_snapshot_candidates(
            event, [{"candidate_id": "new", "source_mode": "model_crop", "frame_index": 2, "selected": True}]
        )
        async with get_db() as db:
            rows = await DetectionRepository(db).list_snapshot_candidates(event)
        assert {row["candidate_id"] for row in rows} == {"chosen", "scene", "new"}
        assert [row["candidate_id"] for row in rows if row["selected"]] == ["chosen"]
        assert await cache.get_snapshot("chosen-image") is not None
        assert await cache.get_snapshot("chosen-scene") is not None
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event=?", (event,))
            await db.commit()
        await close_db()
