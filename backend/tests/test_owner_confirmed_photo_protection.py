"""Owner-confirmed and owner-chosen photographs survive cache limits (#1109)."""

from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta
from io import BytesIO
import os
from pathlib import Path
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
import httpx
from PIL import Image
import pytest
import pytest_asyncio

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.routers import proxy as proxy_router
from app.services import full_visit_clip_service as clips
from app.services import high_quality_snapshot_service as photos
from app.services import media_cache as cache_module
from app.services import media_storage_service as storage_module


def _jpeg_bytes(color: str = "green", size: tuple[int, int] = (320, 240)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest_asyncio.fixture
async def storage_env(tmp_path, monkeypatch):
    db_path = tmp_path / "owner_photos.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(db_path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    for name in ("SNAPSHOTS_DIR", "CLIPS_DIR", "PREVIEWS_DIR"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setattr(cache_module, name, directory)

    media = cache_module.MediaCacheService()
    monkeypatch.setattr(cache_module, "media_cache", media)
    monkeypatch.setattr(storage_module, "get_db", database)
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 1)
    monkeypatch.setattr(storage_module.settings.media_cache, "max_size_mb", 0)
    return db_path, database, media


@pytest.mark.asyncio
async def test_owner_confirmed_capture_keeps_photo_when_species_cap_evicts_clip_and_candidates(
    storage_env, monkeypatch
):
    _, database, media = storage_env
    photo = _jpeg_bytes("blue")
    candidate_ref = "evt-confirmed__model_crop__f1__0123456789__image"
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                datetime.now() - timedelta(minutes=20),
                1,
                0.58,
                "Great Tit",
                "Parus major",
                "evt-confirmed",
                "feeder",
                manual_tagged=True,
                scientific_name="Parus major",
                common_name="Great Tit",
            )
        )
        await repo.create(
            Detection(
                datetime.now() - timedelta(minutes=5),
                1,
                0.95,
                "Great Tit",
                "Parus major",
                "evt-newer",
                "feeder",
                manual_tagged=False,
                scientific_name="Parus major",
                common_name="Great Tit",
            )
        )
    await media.cache_snapshot("evt-confirmed", photo, source="hq_candidate_model_crop")
    await media.cache_thumbnail("evt-confirmed", photo, source="snapshot_derived")
    await media.cache_snapshot(candidate_ref, photo, source="snapshot_candidate")
    await media.cache_clip("evt-confirmed", b"\x00\x00\x00\x18ftypmp42" + b"v" * 4096)
    await media.cache_snapshot("evt-newer", _jpeg_bytes("red"), source="frigate_snapshot")

    first = await storage_module.MediaStorageService().enforce_limits()
    assert first["visits_evicted"] == 1
    assert first["bytes_freed"] > 0

    # Canonical photo + sidecar + thumbnail stay; heavy clip & candidate alternates are gone.
    assert await media.get_snapshot("evt-confirmed") == photo
    assert await media.get_thumbnail("evt-confirmed") == photo
    assert await media.get_snapshot(candidate_ref) is None
    assert media.get_clip_path("evt-confirmed") is None
    assert await media.get_snapshot("evt-newer") is not None
    async with database() as db:
        for pipeline in (photos.HQ_PROCESSING_PIPELINE, clips.FULL_VISIT_PROCESSING_PIPELINE):
            state = await ProcessingJobRepository(db).get(pipeline, "evt-confirmed")
            assert state is not None and state.status == "terminal" and state.last_error == "storage_evicted"

    # A second sweep must not churn or remove the kept photo.
    second = await storage_module.MediaStorageService().enforce_limits()
    assert second["visits_evicted"] == 0
    assert second["bytes_freed"] == 0
    assert await media.get_snapshot("evt-confirmed") == photo

    # Explorer thumbnail and snapshot routes still serve 200 even when Frigate returns 404.
    monkeypatch.setattr(
        proxy_router.frigate_client, "get_snapshot_with_error", AsyncMock(return_value=(None, "snapshot_not_found"))
    )
    app.dependency_overrides[proxy_router.get_proxy_auth_context] = lambda: AuthContext(
        auth_level=AuthLevel.OWNER, username="owner"
    )
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            thumb_resp = await client.get("/api/frigate/evt-confirmed/thumbnail.jpg")
            snap_resp = await client.get("/api/frigate/evt-confirmed/snapshot.jpg")
    finally:
        app.dependency_overrides.pop(proxy_router.get_proxy_auth_context, None)
    assert thumb_resp.status_code == 200
    assert snap_resp.status_code == 200
    assert snap_resp.content == photo


@pytest.mark.asyncio
async def test_unknown_bird_manual_tag_is_not_protected_as_owner_confirmed(storage_env):
    _, database, media = storage_env
    photo = _jpeg_bytes("gray")
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                datetime.now() - timedelta(minutes=20),
                1,
                0.4,
                "Unknown Bird",
                "Unknown Bird",
                "evt-unknown-old",
                "feeder",
                manual_tagged=True,
            )
        )
        await repo.create(
            Detection(
                datetime.now() - timedelta(minutes=5),
                1,
                0.45,
                "Unknown Bird",
                "Unknown Bird",
                "evt-unknown-new",
                "feeder",
                manual_tagged=False,
            )
        )
    await media.cache_snapshot("evt-unknown-old", photo, source="frigate_snapshot")
    await media.cache_snapshot("evt-unknown-new", photo, source="frigate_snapshot")

    result = await storage_module.MediaStorageService().enforce_limits()
    assert result["visits_evicted"] == 1
    assert await media.get_snapshot("evt-unknown-old") is None


@pytest.mark.asyncio
async def test_manual_photo_selection_keeps_canonical_photo_under_byte_budget(storage_env, monkeypatch):
    _, database, media = storage_env
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(storage_module.settings.media_cache, "max_size_mb", 1)
    photo = _jpeg_bytes("yellow")
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                datetime.now() - timedelta(minutes=20),
                1,
                0.9,
                "Great Tit",
                "Parus major",
                "evt-chosen",
                "feeder",
                manual_tagged=False,
            )
        )
    await media.replace_snapshot("evt-chosen", photo, source="hq_candidate_model_crop", manual_selection=True)
    await media.cache_clip("evt-chosen", b"\x00\x00\x00\x18ftypmp42" + b"x" * (1_200_000))

    result = await storage_module.MediaStorageService().enforce_limits()
    assert result["visits_evicted"] == 1
    assert media.get_clip_path("evt-chosen") is None
    assert await media.get_snapshot("evt-chosen") == photo
    assert cache_module.has_manual_snapshot_selection("evt-chosen")


@pytest.mark.asyncio
async def test_confirming_during_sweep_race_still_preserves_canonical_photo(storage_env, monkeypatch):
    db_path, database, media = storage_env
    photo = _jpeg_bytes("purple")
    async with database() as db:
        repo = DetectionRepository(db)
        for idx, ev in enumerate(("evt-race-old", "evt-race-new")):
            await repo.create(
                Detection(
                    datetime.now() - timedelta(minutes=20 - idx * 10),
                    1,
                    0.9,
                    "Great Tit",
                    "Parus major",
                    ev,
                    "feeder",
                )
            )
            await media.cache_snapshot(ev, photo, source="frigate_snapshot")
    await media.cache_clip("evt-race-old", b"\x00\x00\x00\x18ftypmp42" + b"v" * 2048)

    original_select = storage_module.select_media_evictions

    def confirm_after_selection(*args, **kwargs):
        selected = original_select(*args, **kwargs)
        assert "evt-race-old" in selected
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = 'evt-race-old'")
        return selected

    monkeypatch.setattr(storage_module, "select_media_evictions", confirm_after_selection)
    result = await storage_module.MediaStorageService().enforce_limits()
    assert result["visits_evicted"] == 1
    # Clip was evicted, but the photo was preserved by the BEGIN IMMEDIATE recheck!
    assert media.get_clip_path("evt-race-old") is None
    assert await media.get_snapshot("evt-race-old") == photo


@pytest.mark.asyncio
async def test_apply_snapshot_candidate_rejects_corrupt_image_bytes(storage_env, monkeypatch):
    _, database, media = storage_env
    good_photo = _jpeg_bytes("orange")
    bad_ref = "evt-apply__model_crop__f1__0123456789__image"
    await media.cache_snapshot("evt-apply", good_photo, source="frigate_snapshot")
    await media.cache_snapshot(bad_ref, b"not-a-valid-jpeg", source="snapshot_candidate")
    monkeypatch.setattr(
        proxy_router,
        "_list_snapshot_candidates",
        AsyncMock(
            return_value=[
                {
                    "candidate_id": "evt-apply__model_crop__f1__0123456789",
                    "image_ref": bad_ref,
                    "snapshot_source": "hq_candidate_model_crop",
                    "photo_hidden": False,
                }
            ]
        ),
    )
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/frigate/evt-apply/snapshot/apply",
                json={"mode": "candidate", "candidate_id": "evt-apply__model_crop__f1__0123456789"},
            )
    finally:
        app.dependency_overrides.pop(require_owner, None)
    assert resp.status_code == 409
    assert await media.get_snapshot("evt-apply") == good_photo


@pytest.mark.asyncio
async def test_apply_revert_original_rejects_corrupt_frigate_bytes(storage_env, monkeypatch):
    _, _database, media = storage_env
    good_photo = _jpeg_bytes("cyan")
    await media.cache_snapshot("evt-revert", good_photo, source="hq_candidate_model_crop")
    monkeypatch.setattr(proxy_router.frigate_client, "get_snapshot", AsyncMock(return_value=b"corrupt-upstream-bytes"))
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/frigate/evt-revert/snapshot/apply",
                json={"mode": "revert_original"},
            )
    finally:
        app.dependency_overrides.pop(require_owner, None)
    assert resp.status_code == 409
    assert await media.get_snapshot("evt-revert") == good_photo


@pytest.mark.asyncio
async def test_get_owner_confirmed_frigate_event_ids_excludes_unknown_and_unconfirmed(storage_env):
    _, database, _media = storage_env
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(datetime.now(), 1, 0.7, "Great Tit", "Parus major", "evt-real", "cam", manual_tagged=True)
        )
        await repo.create(
            Detection(datetime.now(), 1, 0.3, "Unknown Bird", "Unknown Bird", "evt-unk", "cam", manual_tagged=True)
        )
        await repo.create(
            Detection(datetime.now(), 1, 0.9, "Great Tit", "Parus major", "evt-auto", "cam", manual_tagged=False)
        )
        confirmed = await repo.get_owner_confirmed_frigate_event_ids()
    assert confirmed == {"evt-real"}


@pytest.mark.asyncio
async def test_manual_selection_mid_sweep_race_preserves_canonical_photo(storage_env, monkeypatch):
    _, database, media = storage_env
    photo = _jpeg_bytes("magenta")
    async with database() as db:
        repo = DetectionRepository(db)
        for idx, ev in enumerate(("evt-ms-old", "evt-ms-new")):
            await repo.create(
                Detection(
                    datetime.now() - timedelta(minutes=20 - idx * 10),
                    1,
                    0.9,
                    "Great Tit",
                    "Parus major",
                    ev,
                    "feeder",
                )
            )
            await media.cache_snapshot(ev, photo, source="frigate_snapshot")
    await media.cache_clip("evt-ms-old", b"\x00\x00\x00\x18ftypmp42" + b"v" * 2048)

    original_select = storage_module.select_media_evictions

    def select_photo_after_plan(*args, **kwargs):
        selected = original_select(*args, **kwargs)
        assert "evt-ms-old" in selected
        meta_path = cache_module.SNAPSHOTS_DIR / "evt-ms-old.jpg.meta.json"
        meta_path.write_text('{"event_id": "evt-ms-old", "manual_selection": true}', encoding="utf-8")
        return selected

    monkeypatch.setattr(storage_module, "select_media_evictions", select_photo_after_plan)
    result = await storage_module.MediaStorageService().enforce_limits()
    assert result["visits_evicted"] == 1
    assert media.get_clip_path("evt-ms-old") is None
    assert await media.get_snapshot("evt-ms-old") == photo


@pytest.mark.asyncio
@pytest.mark.parametrize("next_is_garden", [False, True])
async def test_byte_budget_sweep_stops_early_when_actual_freed_bytes_satisfy_cap(
    storage_env, monkeypatch, next_is_garden
):
    _, database, media = storage_env
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(storage_module.settings.media_cache, "max_size_mb", 1)
    # Create an older capture with a ~900 KB photo marked manual_selection and a ~200 KB clip,
    # plus a newer ~600 KB capture. Total = ~1.7 MB > 1 MB cap.
    # At planning time, freeing only old's ~200 KB clip leaves ~1.5 MB > 1 MB, so new is also planned.
    # After planning, manual_selection is cleared on old, so evicting old frees ~1.1 MB -> remaining ~600 KB <= 1 MB.
    # The sweep must stop and NOT evict new!
    big_photo = _jpeg_bytes("navy") + (b"\x00" * 900_000)
    new_photo = _jpeg_bytes("teal") + (b"\x00" * 600_000)
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(datetime.now() - timedelta(minutes=20), 1, 0.9, "Great Tit", "Parus major", "evt-old", "cam")
        )
        await repo.create(
            Detection(datetime.now() - timedelta(minutes=5), 1, 0.9, "Great Tit", "Parus major", "evt-new", "cam")
        )
    await media.replace_snapshot("evt-old", big_photo, source="hq_candidate_model_crop", manual_selection=True)
    await media.cache_clip("evt-old", b"\x00\x00\x00\x18ftypmp42" + b"a" * 200_000)
    await media.cache_snapshot("evt-new", new_photo, source="frigate_snapshot")
    next_id = "evt-new"
    evict_garden = AsyncMock()
    if next_is_garden:
        from app.services.garden_media_cache import garden_media_cache

        await media.delete_snapshot("evt-new")
        next_id = storage_module.eviction_key("b" * 32)
        garden_visit = storage_module.CachedVisit(next_id, next_id, datetime.now().isoformat(), len(new_photo))
        monkeypatch.setattr(
            storage_module.MediaStorageService, "_garden_visits", AsyncMock(return_value=[garden_visit])
        )
        monkeypatch.setattr(garden_media_cache, "evict", evict_garden)

    original_select = storage_module.select_media_evictions

    def clear_manual_after_plan(*args, **kwargs):
        selected = original_select(*args, **kwargs)
        assert selected == ["evt-old", next_id]
        meta_path = cache_module.SNAPSHOTS_DIR / "evt-old.jpg.meta.json"
        meta_path.write_text('{"event_id": "evt-old", "manual_selection": false}', encoding="utf-8")
        return selected

    monkeypatch.setattr(storage_module, "select_media_evictions", clear_manual_after_plan)
    result = await storage_module.MediaStorageService().enforce_limits()
    assert result["visits_evicted"] == 1
    assert await media.get_snapshot("evt-old") is None
    if next_is_garden:
        evict_garden.assert_not_awaited()
    else:
        assert await media.get_snapshot("evt-new") == new_photo


@pytest.mark.asyncio
@pytest.mark.parametrize("next_is_garden", [False, True])
async def test_byte_budget_continues_when_late_owner_protection_reduces_actual_bytes_freed(
    storage_env, monkeypatch, next_is_garden
):
    db_path, database, media = storage_env
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(storage_module.settings.media_cache, "max_size_mb", 1)
    photo = _jpeg_bytes("green") + b"\x00" * 650_000
    async with database() as db:
        repo = DetectionRepository(db)
        for index, event_id in enumerate(("evt-oldest", "evt-next", "evt-latest")):
            await repo.create(
                Detection(
                    datetime.now() - timedelta(minutes=30 - index * 10), 1, 0.9, "Robin", "Robin", event_id, "camera"
                )
            )
            if event_id != "evt-next" or not next_is_garden:
                await media.cache_snapshot(event_id, photo if event_id != "evt-latest" else _jpeg_bytes("red"))
    clip_path = await media.cache_clip("evt-oldest", b"\x00\x00\x00\x18ftypmp42" + b"a" * 50_000)
    evict_garden = AsyncMock(return_value={"b" * 32: len(photo)})
    if next_is_garden:
        from app.services.garden_media_cache import garden_media_cache

        garden_id = storage_module.eviction_key("b" * 32)
        garden_visit = storage_module.CachedVisit(
            garden_id, garden_id, (datetime.now() - timedelta(minutes=20)).isoformat(sep=" "), len(photo)
        )
        monkeypatch.setattr(
            storage_module.MediaStorageService, "_garden_visits", AsyncMock(return_value=[garden_visit])
        )
        monkeypatch.setattr(garden_media_cache, "evict", evict_garden)

    service = storage_module.MediaStorageService()
    evict_visit = service._evict_budget_visit

    async def confirm_immediately_before_final_recheck(event_id, paths):
        if event_id == "evt-oldest":
            with sqlite3.connect(db_path) as db:
                db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?", (event_id,))
        return await evict_visit(event_id, paths)

    monkeypatch.setattr(service, "_evict_budget_visit", confirm_immediately_before_final_recheck)
    result = await service.enforce_limits()
    assert result["visits_evicted"] == 2
    assert await media.get_snapshot("evt-oldest") == photo
    assert not clip_path.exists()
    assert await media.get_snapshot("evt-latest") is not None
    if next_is_garden:
        evict_garden.assert_awaited_once_with(["b" * 32])
    else:
        assert await media.get_snapshot("evt-next") is None


@pytest.mark.asyncio
async def test_byte_budget_counts_garden_bytes_only_once_they_are_removed(storage_env, monkeypatch):
    from app.services.garden_media_cache import garden_media_cache

    _, database, media = storage_env
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(storage_module.settings.media_cache, "max_size_mb", 1)
    photo = _jpeg_bytes("teal") + b"\x00" * 300_000
    async with database() as db:
        for minutes, event_id in ((20, "evt-older"), (10, "evt-newer")):
            await DetectionRepository(db).create(
                Detection(datetime.now() - timedelta(minutes=minutes), 1, 0.9, "Robin", "Robin", event_id, "camera")
            )
            await media.cache_snapshot(event_id, photo)
    capture_id = "c" * 32
    garden_id = storage_module.eviction_key(capture_id)
    garden_visit = storage_module.CachedVisit(
        garden_id, garden_id, (datetime.now() - timedelta(minutes=30)).isoformat(sep=" "), 600_000
    )
    monkeypatch.setattr(storage_module.MediaStorageService, "_garden_visits", AsyncMock(return_value=[garden_visit]))
    # The capture was confirmed or deleted meanwhile, so releasing it removes nothing from disk.
    evict_garden = AsyncMock(return_value={capture_id: 0})
    monkeypatch.setattr(garden_media_cache, "evict", evict_garden)

    result = await storage_module.MediaStorageService().enforce_limits()

    evict_garden.assert_awaited_once_with([capture_id])
    assert await media.get_snapshot("evt-older") is None
    assert await media.get_snapshot("evt-newer") == photo
    assert result["visits_evicted"] == 1
    assert 0 < result["bytes_freed"] < 600_000


@pytest.mark.asyncio
async def test_age_cleanup_rechecks_db_and_protects_literal_candidate_shaped_event_id(storage_env, monkeypatch):
    import app.database as db_module

    _, database, media = storage_env
    monkeypatch.setattr(db_module, "get_db", database)
    literal_id = "evt__model_crop__f1__0123456789__image"
    photo = _jpeg_bytes("olive")
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                datetime.now() - timedelta(days=10),
                1,
                0.8,
                "Great Tit",
                "Parus major",
                literal_id,
                "feeder",
                manual_tagged=True,
            )
        )
        await repo.create(
            Detection(
                datetime.now() - timedelta(days=10),
                1,
                0.8,
                "Great Tit",
                "Parus major",
                "evt-live-save",
                "feeder",
                manual_tagged=False,
            )
        )
    await media.cache_snapshot(literal_id, photo, source="frigate_snapshot")
    await media.cache_snapshot("evt-live-save", photo, source="frigate_snapshot")
    old_time = (datetime.now() - timedelta(days=10)).timestamp()
    for path in cache_module.SNAPSHOTS_DIR.iterdir():
        os.utime(path, (old_time, old_time))

    # Simulate an owner selecting a fresh photo on evt-live-save after discovery before locked unlink.
    original_collect = media._collect_media_groups_sync

    def collect_then_owner_chooses(cutoff):
        groups = original_collect(cutoff)
        (cache_module.SNAPSHOTS_DIR / "evt-live-save.jpg").write_bytes(b"fresh-owner-photo")
        (cache_module.SNAPSHOTS_DIR / "evt-live-save.jpg.meta.json").write_text(
            '{"event_id": "evt-live-save", "manual_selection": true}', encoding="utf-8"
        )
        return groups

    monkeypatch.setattr(media, "_collect_media_groups_sync", collect_then_owner_chooses)
    # Pass empty protected_canonical_photo_event_ids to verify DB recheck + literal-ID protection!
    await media.cleanup_old_media(
        retention_days=1,
        protected_event_ids=set(),
        protected_snapshot_event_ids=set(),
        protected_canonical_photo_event_ids=set(),
    )
    assert await media.get_snapshot(literal_id) == photo
    assert await media.get_snapshot("evt-live-save") == b"fresh-owner-photo"


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["storage_sweep", "clear_cached_files"])
async def test_a_deleted_captures_spare_copy_goes_with_its_files_and_a_living_one_stays(
    storage_env, monkeypatch, cleanup
):
    import app.database as db_module
    from app.routers import settings as settings_router
    from app.services import garden_media_cache as garden_module

    _, database, media = storage_env
    monkeypatch.setattr(db_module, "get_db", database)
    monkeypatch.setattr(settings_router, "get_db", database)
    monkeypatch.setattr(settings_router, "media_cache", media)
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(settings_router.settings.media_cache, "retention_days", 0)
    monkeypatch.setattr(garden_module.garden_media_cache, "apply_retention", AsyncMock())
    async with database() as db:
        for event_id in ("evt-deleted", "evt-living"):
            await DetectionRepository(db).create(
                Detection(datetime.now(), 1, 0.9, "Robin", "Robin", event_id, "feeder")
            )
    for event_id in ("evt-deleted", "evt-living"):
        await media.cache_snapshot(event_id, _jpeg_bytes("navy"))
        media._stage_paths_sync([cache_module.SNAPSHOTS_DIR / f"{event_id}.jpg"], cache_module._AGE_STAGED_SUFFIX)
        (cache_module.SNAPSHOTS_DIR / f"{event_id}.jpg").write_bytes(_jpeg_bytes("gray"))
    await media.return_age_staged_files()
    assert media.kept_copies_count == 2

    # What deleting a capture in the UI does: the row goes now, its files with the next orphan pass.
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("evt-deleted")
    if cleanup == "storage_sweep":
        deleted_snapshots = (await storage_module.MediaStorageService().enforce_limits())["orphan_snapshots_deleted"]
    else:
        app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/cache/cleanup")
        finally:
            app.dependency_overrides.pop(require_owner, None)
        assert response.status_code == 200
        deleted_snapshots = response.json()["snapshots_deleted"]

    kept = [path.name for path in cache_module.SNAPSHOTS_DIR.iterdir() if path.name.endswith(".kept.tmp")]
    assert [name.split(".jpg.")[0] for name in kept] == [".evt-living"]
    assert media.kept_copies_count == 1
    assert await media.get_snapshot("evt-deleted") is None
    # The spare copy counts as a removed file, not only as freed space.
    assert deleted_snapshots == 2


async def _spare_copy_for(media, event_id: str) -> Path:
    """A spare copy for this capture's photo, as a return leaves one beside an automatic re-cache."""
    await media.cache_snapshot(event_id, _jpeg_bytes("navy"))
    media._stage_paths_sync([cache_module.SNAPSHOTS_DIR / f"{event_id}.jpg"], cache_module._AGE_STAGED_SUFFIX)
    (cache_module.SNAPSHOTS_DIR / f"{event_id}.jpg").write_bytes(_jpeg_bytes("gray"))
    await media.return_age_staged_files()
    [kept] = [
        path
        for path in cache_module.SNAPSHOTS_DIR.iterdir()
        if path.name.startswith(f".{event_id}.jpg.") and path.name.endswith(".kept.tmp")
    ]
    return kept


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["manual_id", "active_write", "literal_candidate", "variant_literal", "stale_valid_ids"]
)
async def test_a_living_captures_spare_copy_survives_the_orphan_pass(storage_env, monkeypatch, case):
    _, database, media = storage_env
    monkeypatch.setattr(storage_module.settings.media_cache, "per_species_maximum", 0)
    event_id = {
        # The first id read leaves out manual_ rows, so only the locked recheck finds this one.
        "manual_id": "manual_0123456789abcdef",
        # Its row is gone, but a write for it is still running.
        "active_write": "evt-busy",
        # Named like a candidate of evt-lit, which has no row; the literal capture does.
        "literal_candidate": "evt-lit__model_crop__f1__0123456789__image",
        # Ends like a thumbnail of evt-var, which has no row; the literal capture does.
        "variant_literal": "evt-var_thumb",
        # The capture exists, but the id list read before the locks is stale.
        "stale_valid_ids": "evt-stale",
    }[case]
    if case != "active_write":
        async with database() as db:
            await DetectionRepository(db).create(
                Detection(datetime.now(), 1, 0.9, "Robin", "Robin", event_id, "feeder")
            )
    kept = await _spare_copy_for(media, event_id)
    if case == "stale_valid_ids":
        monkeypatch.setattr(DetectionRepository, "get_all_frigate_event_ids", AsyncMock(return_value=[]))

    if case == "active_write":
        async with media._media_write_lease(event_id):
            await storage_module.MediaStorageService().enforce_limits()
    else:
        await storage_module.MediaStorageService().enforce_limits()

    assert kept.exists()
    assert media.kept_copies_count == 1


@pytest.mark.asyncio
async def test_cache_cleanup_route_protects_owner_confirmed_and_sweeps_orphans(storage_env, monkeypatch):
    import app.database as db_module
    from app.routers import settings as settings_router
    from app.services import garden_media_cache as garden_module

    _, database, media = storage_env
    monkeypatch.setattr(db_module, "get_db", database)
    monkeypatch.setattr(settings_router, "get_db", database)
    monkeypatch.setattr(settings_router, "media_cache", media)
    monkeypatch.setattr(settings_router.settings.media_cache, "retention_days", 1)
    monkeypatch.setattr(settings_router.settings.media_cache, "per_species_minimum", 0)
    monkeypatch.setattr(settings_router.settings.media_cache, "per_species_maximum", 0)
    monkeypatch.setattr(settings_router.settings.media_cache, "max_size_mb", 0)
    monkeypatch.setattr(garden_module.garden_media_cache, "apply_retention", AsyncMock())

    photo = _jpeg_bytes("gold")
    cand_ref = "evt-route-confirmed__model_crop__f1__0123456789__image"
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                datetime.now() - timedelta(days=5),
                1,
                0.8,
                "Great Tit",
                "Parus major",
                "evt-route-confirmed",
                "feeder",
                manual_tagged=True,
            )
        )
        await repo.create(
            Detection(
                datetime.now() - timedelta(days=5),
                1,
                0.3,
                "Unknown Bird",
                "Unknown Bird",
                "evt-route-unknown",
                "feeder",
                manual_tagged=True,
            )
        )

    await media.cache_snapshot("evt-route-confirmed", photo, source="frigate_snapshot")
    await media.cache_snapshot(cand_ref, photo, source="snapshot_candidate")
    await media.cache_clip("evt-route-confirmed", b"\x00\x00\x00\x18ftypmp42" + b"v" * 2048)
    await media.cache_snapshot("evt-route-unknown", photo, source="frigate_snapshot")
    await media.cache_snapshot("evt-orphan", photo, source="frigate_snapshot")
    await media.cache_clip("evt-orphan", b"\x00\x00\x00\x18ftypmp42" + b"o" * 2048)

    old_time = (datetime.now() - timedelta(days=5)).timestamp()
    for directory in (cache_module.SNAPSHOTS_DIR, cache_module.CLIPS_DIR):
        for path in directory.iterdir():
            if not path.name.startswith("evt-orphan"):
                os.utime(path, (old_time, old_time))

    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/cache/cleanup")
    finally:
        app.dependency_overrides.pop(require_owner, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    # Confirmed photo kept; its candidate & clip aged out; unknown bird aged out; orphan snapshot + clip swept.
    assert await media.get_snapshot("evt-route-confirmed") == photo
    assert await media.get_snapshot(cand_ref) is None
    assert media.get_clip_path("evt-route-confirmed") is None
    assert await media.get_snapshot("evt-route-unknown") is None
    assert await media.get_snapshot("evt-orphan") is None
    assert media.get_clip_path("evt-orphan") is None
    assert body["snapshots_deleted"] >= 3
    assert body["clips_deleted"] >= 2
    assert body["bytes_freed"] > 0
