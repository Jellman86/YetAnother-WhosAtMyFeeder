"""Budget deletion must not guess ownership of live literal variant names."""

import asyncio
from datetime import datetime
import sqlite3

import pytest

from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.services import full_visit_clip_service as clips
from app.services import media_cache as cache
from app.services import media_storage_service as storage
from test_full_visit_budget_eviction import budget_visit_history as budget_visit_history


ALIASES = (
    "_recording",
    "_thumb",
    "_preview",
    "__model_crop__f1__c0__0123456789__image",
    "__full_frame__final__0123456789__image",
    "__model_crop__final__c2__0123456789__image",
)


async def create_alias(database, alias, *, favorite=False):
    async with database() as db:
        repo = DetectionRepository(db)
        await repo.create(Detection(datetime.now(), 1, 0.9, "Robin", "Robin", alias, "camera"))
        detection = await repo.get_by_frigate_event(alias)
        if favorite:
            await db.execute(
                "INSERT INTO detection_favorites(detection_id,created_by) VALUES (?,'owner')", (detection.id,)
            )
            await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ALIASES)
@pytest.mark.parametrize("favorite", [False, True])
@pytest.mark.parametrize("cap", ["species", "bytes"])
async def test_budget_preserves_live_literal_alias_and_parent(budget_visit_history, monkeypatch, suffix, favorite, cap):
    database, media, _ = budget_visit_history
    alias = "budget-old" + suffix
    await create_alias(database, alias, favorite=favorite)
    path = await media.cache_clip(alias, b"fixture clip" * 180000)
    assert cache.cache_file_event_id(path) == "budget-old"
    if cap == "bytes":
        monkeypatch.setattr(clips.settings.media_cache, "per_species_maximum", 0)
        monkeypatch.setattr(clips.settings.media_cache, "max_size_mb", 1)
    await storage.MediaStorageService().enforce_limits()
    assert path.exists()
    assert await media.get_snapshot("budget-old") is not None
    async with database() as db:
        assert await DetectionRepository(db).get_by_frigate_event(alias) is not None
        assert await ProcessingJobRepository(db).get(clips.FULL_VISIT_PROCESSING_PIPELINE, "budget-old") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("favorite", [False, True])
async def test_budget_rechecks_literal_parent_created_after_selection(budget_visit_history, monkeypatch, favorite):
    database, media, _ = budget_visit_history
    alias = "budget-old_recording"
    path = await media.cache_clip(alias, b"fixture clip" * 1000)
    async with database() as db:
        db_path = (await (await db.execute("PRAGMA database_list")).fetchone())[2]
    original_select = storage.select_media_evictions

    def create_parent(*args, **kwargs):
        selected = original_select(*args, **kwargs)
        assert "budget-old" in selected
        with sqlite3.connect(db_path) as db:
            db.execute(
                "INSERT INTO detections (detection_time,detection_index,score,category_name,display_name,frigate_event,camera_name) "
                "VALUES (datetime('now'),1,0.9,'Robin','Robin',?,'camera')",
                (alias,),
            )
            if favorite:
                db.execute(
                    "INSERT INTO detection_favorites(detection_id,created_by) "
                    "SELECT id,'owner' FROM detections WHERE frigate_event=?",
                    (alias,),
                )
        return selected

    monkeypatch.setattr(storage, "select_media_evictions", create_parent)
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 0
    assert path.exists()
    assert await media.get_snapshot("budget-old") is not None


@pytest.mark.asyncio
async def test_budget_preserves_active_literal_writer_without_parent(budget_visit_history):
    _, media, _ = budget_visit_history
    entered, release = asyncio.Event(), asyncio.Event()

    async def chunks():
        yield b"fixture" * 1000
        entered.set()
        await release.wait()
        yield b"finished" * 1000

    writer = asyncio.create_task(media.cache_clip_streaming("budget-old_recording", chunks()))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 0
        assert await media.get_snapshot("budget-old") is not None
    finally:
        release.set()
    path = await writer
    assert path.exists()
    # Once there is neither another parent nor an admitted writer, normal eviction resumes.
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 1
    assert not path.exists()


@pytest.mark.asyncio
async def test_budget_resumes_after_literal_parent_removed(budget_visit_history):
    database, media, _ = budget_visit_history
    alias = "budget-old_thumb"
    await create_alias(database, alias)
    path = await media.cache_clip(alias, b"fixture" * 1000)
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 0
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event(alias)
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 1
    assert not path.exists()


@pytest.mark.asyncio
async def test_budget_evicts_generated_candidate_sidecars_when_no_literal_parent(budget_visit_history):
    _, media, _ = budget_visit_history
    candidate = "budget-old" + ALIASES[-1]
    image = await media.get_snapshot("budget-old")
    snapshot = await media.cache_snapshot(candidate, image)
    thumbnail = await media.cache_thumbnail(candidate, image)
    paths = [snapshot, thumbnail, snapshot.with_suffix(".jpg.meta.json"), thumbnail.with_suffix(".jpg.meta.json")]
    assert all(path.exists() and cache.cache_file_event_id(path) == "budget-old" for path in paths)
    result = await asyncio.wait_for(storage.MediaStorageService().enforce_limits(), 2)
    assert result["visits_evicted"] == 1
    assert not any(path.exists() for path in paths)
    assert await media.get_snapshot("budget-new") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("favorite", [False, True])
async def test_budget_preserves_literal_candidate_with_thumbnail_only(budget_visit_history, favorite):
    database, media, _ = budget_visit_history
    alias = "budget-old" + ALIASES[-1]
    await create_alias(database, alias, favorite=favorite)
    image = await media.get_snapshot("budget-old")
    thumbnail = await media.cache_thumbnail(alias, image)
    metadata = thumbnail.with_suffix(".jpg.meta.json")
    assert thumbnail.name == alias + "_thumb.jpg"
    assert cache.cache_file_event_id(thumbnail) == "budget-old"
    assert (await storage.MediaStorageService().enforce_limits())["visits_evicted"] == 0
    assert thumbnail.exists() and metadata.exists()
    async with database() as db:
        assert await DetectionRepository(db).get_by_frigate_event(alias) is not None
