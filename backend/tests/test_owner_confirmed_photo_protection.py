"""Owner-confirmed and owner-chosen photographs survive cache limits (#1109)."""

from contextlib import asynccontextmanager, closing
from datetime import datetime, timedelta
from io import BytesIO
import os
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
