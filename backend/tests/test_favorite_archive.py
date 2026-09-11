"""A favourite is durable (#178): its photograph and clip are archived where no cache operation
reaches, the star reports pending / durable / unavailable / failed honestly, and only
unfavouriting, deleting the visit, or a reset removes the archive."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository, derive_archive_state
from app.services import archive_service as archive_module
from app.services import media_cache as media_cache_module
from app.services.archive_service import (
    CLIP_NAME,
    MANIFEST_NAME,
    MAX_ATTEMPTS,
    SNAPSHOT_NAME,
    ArchiveService,
    retry_due_at,
)

CLIP_BYTES = b"\x00\x00\x00\x20ftypisom" + b"v" * 2048


@pytest_asyncio.fixture
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            # Favourites do not cascade without the foreign-key pragma; own them explicitly.
            await db.execute("DELETE FROM detection_favorites")
            await db.execute("DELETE FROM detections")
            await db.execute(
                """
                INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
                VALUES
                ('fav_cached', 'cam1', '2026-09-11 10:00:00', 1, 0.91, 'Robin', 'bird', 0),
                ('fav_frigate', 'cam1', '2026-09-11 11:00:00', 1, 0.80, 'Dunnock', 'bird', 0),
                ('plain', 'cam1', '2026-09-11 12:00:00', 1, 0.77, 'Blue Tit', 'bird', 0)
                """
            )
            await db.commit()
        yield
        # The API tests enqueue into the process-wide worker; leave nothing queued for other suites.
        await archive_module.archive_service.stop()
        async with get_db() as db:
            await db.execute("DELETE FROM detection_favorites")
            await db.commit()
    finally:
        await close_db()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """A media cache and an archive on disk, side by side and separate."""
    cache = tmp_path / "media_cache"
    for name in ("snapshots", "clips", "previews"):
        (cache / name).mkdir(parents=True)
    monkeypatch.setattr(media_cache_module, "CACHE_BASE_DIR", cache)
    monkeypatch.setattr(media_cache_module, "SNAPSHOTS_DIR", cache / "snapshots")
    monkeypatch.setattr(media_cache_module, "CLIPS_DIR", cache / "clips")
    monkeypatch.setattr(media_cache_module, "PREVIEWS_DIR", cache / "previews")
    archive = tmp_path / "archive"
    monkeypatch.setattr(archive_module, "ARCHIVE_DIR", archive)
    return {"cache": cache, "archive": archive}


def _cache_snapshot(dirs, event_id: str, data: bytes = b"jpegdata", source: str = "hq_candidate_model_crop") -> None:
    (dirs["cache"] / "snapshots" / f"{event_id}.jpg").write_bytes(data)
    (dirs["cache"] / "snapshots" / f"{event_id}.jpg.meta.json").write_text(json.dumps({"source": source}))


def _cache_clip(dirs, event_id: str, data: bytes = CLIP_BYTES) -> None:
    (dirs["cache"] / "clips" / f"{event_id}.mp4").write_bytes(data)


async def _favorite(event_id: str) -> None:
    async with get_db() as db:
        await DetectionRepository(db).favorite_detection(event_id, created_by="owner")


async def _archive_row(event_id: str) -> dict | None:
    async with get_db() as db:
        return await DetectionRepository(db).get_favorite_archive(event_id)


def _frigate(snapshot=(None, "snapshot_not_found"), clip=(False, "clip_not_found"), clip_bytes: bytes | None = None):
    async def download(event_id, dest_path, timeout=20.0):
        if clip_bytes is not None:
            Path(dest_path).write_bytes(clip_bytes)
            return True, None
        return clip

    return (
        patch.object(archive_module.frigate_client, "get_snapshot_with_error", new=AsyncMock(return_value=snapshot)),
        patch.object(archive_module.frigate_client, "download_clip_to_file", new=AsyncMock(side_effect=download)),
    )


# ---- state vocabulary -----------------------------------------------------------------------


def test_the_archive_state_is_one_honest_word():
    assert derive_archive_state("durable", "durable") == "durable"
    assert derive_archive_state("durable", "unavailable") == "durable"  # Frigate had no clip: still kept
    assert derive_archive_state("pending", "durable") == "pending"
    assert derive_archive_state("durable", "failed") == "failed"
    assert derive_archive_state("unavailable", "unavailable") == "unavailable"


def test_retries_back_off_and_stop():
    now = datetime.now(timezone.utc)
    assert retry_due_at(1, now) == now + timedelta(seconds=60)
    assert retry_due_at(4, now) == now + timedelta(seconds=3600)
    assert retry_due_at(7, now) == now + timedelta(seconds=3600)
    assert retry_due_at(MAX_ATTEMPTS, now) is None


# ---- acquisition ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cached_photograph_and_clip_become_durable_without_asking_frigate(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    _cache_clip(dirs, "fav_cached")
    await _favorite("fav_cached")
    service = ArchiveService()
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch as snapshot_mock, clip_patch as clip_mock:
        result = await service.archive_event("fav_cached")
    assert result["state"] == "durable"
    snapshot_mock.assert_not_awaited()
    clip_mock.assert_not_awaited()
    event_dir = dirs["archive"] / "fav_cached"
    assert (event_dir / SNAPSHOT_NAME).read_bytes() == b"jpegdata"
    assert (event_dir / CLIP_NAME).read_bytes() == CLIP_BYTES
    manifest = json.loads((event_dir / MANIFEST_NAME).read_text())
    assert set(manifest["files"]) == {SNAPSHOT_NAME, "snapshot.meta.json", CLIP_NAME}
    assert json.loads((event_dir / "snapshot.meta.json").read_text())["source"] == "hq_candidate_model_crop"
    row = await _archive_row("fav_cached")
    assert row["state"] == "durable"
    assert row["bytes"] == len(b"jpegdata") + len(CLIP_BYTES)
    assert row["archived_at"] is not None
    assert await service.snapshot_path("fav_cached") == event_dir / SNAPSHOT_NAME


@pytest.mark.asyncio
async def test_frigate_without_a_clip_is_unavailable_and_the_favourite_is_still_durable(seeded_db, dirs):
    await _favorite("fav_frigate")
    service = ArchiveService()
    snapshot_patch, clip_patch = _frigate(snapshot=(b"fromfrigate", None), clip=(False, "clip_not_retained"))
    with snapshot_patch, clip_patch:
        result = await service.archive_event("fav_frigate")
    assert result["state"] == "durable"
    row = await _archive_row("fav_frigate")
    assert (row["snapshot_state"], row["clip_state"]) == ("durable", "unavailable")
    assert row["error"] is None
    assert json.loads((dirs["archive"] / "fav_frigate" / "snapshot.meta.json").read_text()) == {
        "source": "frigate_snapshot_cropped"
    }
    assert not (dirs["archive"] / "fav_frigate" / CLIP_NAME).exists()


@pytest.mark.asyncio
async def test_a_partial_download_is_a_failure_that_leaves_no_file_behind(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_frigate")
    await _favorite("fav_frigate")
    service = ArchiveService()
    snapshot_patch, clip_patch = _frigate(clip_bytes=b"tiny")
    with snapshot_patch, clip_patch:
        result = await service.archive_event("fav_frigate")
    assert result["state"] == "failed"
    row = await _archive_row("fav_frigate")
    assert (row["snapshot_state"], row["clip_state"]) == ("durable", "failed")
    assert row["error"] == "clip_partial"
    assert row["attempts"] == 1
    leftovers = [p.name for p in (dirs["archive"] / "fav_frigate").iterdir()]
    assert CLIP_NAME not in leftovers
    assert not any(name.endswith(".tmp") for name in leftovers)
    # The photograph already archived is served; the clip is not.
    assert await service.snapshot_path("fav_frigate") is not None
    assert await service.clip_path("fav_frigate") is None


@pytest.mark.asyncio
async def test_a_full_disk_writes_nothing_and_says_so(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    await _favorite("fav_cached")
    service = ArchiveService()
    with patch.object(service, "_free_bytes", new=AsyncMock(return_value=0)):
        result = await service.archive_event("fav_cached")
    assert result["state"] == "failed"
    row = await _archive_row("fav_cached")
    assert row["error"] == "disk_full"
    assert not (dirs["archive"] / "fav_cached").exists()


@pytest.mark.asyncio
async def test_an_archive_interrupted_before_its_manifest_is_not_served_and_is_completed(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    _cache_clip(dirs, "fav_cached")
    await _favorite("fav_cached")
    service = ArchiveService()
    event_dir = dirs["archive"] / "fav_cached"
    event_dir.mkdir(parents=True)
    (event_dir / SNAPSHOT_NAME).write_bytes(b"jpegdata")  # crashed after the photograph, before the manifest
    assert await service.snapshot_path("fav_cached") is None
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch, clip_patch:
        result = await service.archive_event("fav_cached")
    assert result["state"] == "durable"
    assert (event_dir / MANIFEST_NAME).exists()
    assert await service.snapshot_path("fav_cached") is not None


@pytest.mark.asyncio
async def test_unfavouriting_during_acquisition_leaves_nothing_behind(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    await _favorite("fav_cached")
    service = ArchiveService()

    async def unfavourite_mid_download(event_id, dest_path, timeout=20.0):
        async with get_db() as db:
            await DetectionRepository(db).unfavorite_detection(event_id)
        Path(dest_path).write_bytes(CLIP_BYTES)
        return True, None

    with patch.object(
        archive_module.frigate_client, "download_clip_to_file", new=AsyncMock(side_effect=unfavourite_mid_download)
    ):
        result = await service.archive_event("fav_cached")
    assert result["state"] == "not_favorite"
    assert not (dirs["archive"] / "fav_cached").exists()


@pytest.mark.asyncio
async def test_removal_during_an_acquisition_is_left_to_the_acquisition(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    await _favorite("fav_cached")
    service = ArchiveService()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_download(event_id, dest_path, timeout=20.0):
        started.set()
        await release.wait()
        Path(dest_path).write_bytes(CLIP_BYTES)
        return True, None

    with patch.object(archive_module.frigate_client, "download_clip_to_file", new=AsyncMock(side_effect=slow_download)):
        archiving = asyncio.create_task(service.archive_event("fav_cached"))
        await started.wait()
        async with get_db() as db:
            await DetectionRepository(db).unfavorite_detection("fav_cached")
        # The unfavourite request must not wait on a two-minute download: removal returns at
        # once, and the acquisition sees the row gone and removes the directory itself.
        assert await service.remove("fav_cached") == 0
        release.set()
        result = await archiving
    assert result["state"] == "not_favorite"
    assert not (dirs["archive"] / "fav_cached").exists()


# ---- what may and may not remove it -------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_cleanup_and_clear_never_touch_the_archive_but_the_orphan_sweep_does(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    _cache_clip(dirs, "fav_cached")
    await _favorite("fav_cached")
    service = ArchiveService()
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch, clip_patch:
        await service.archive_event("fav_cached")
    cache = media_cache_module.MediaCacheService()
    await cache.cleanup_old_media(retention_days=1, protected_event_ids=set())
    await cache.cleanup_orphaned_media(valid_event_ids=set())
    await cache.clear_all()
    assert not (dirs["cache"] / "snapshots" / "fav_cached.jpg").exists()
    assert (dirs["archive"] / "fav_cached" / SNAPSHOT_NAME).exists()
    assert (dirs["archive"] / "fav_cached" / CLIP_NAME).exists()

    (dirs["archive"] / "ghost").mkdir()
    (dirs["archive"] / "ghost" / MANIFEST_NAME).write_text("{}")
    swept = await service.orphan_sweep()
    assert swept["removed"] == 1
    assert (dirs["archive"] / "fav_cached").exists()
    assert not (dirs["archive"] / "ghost").exists()


@pytest.mark.asyncio
async def test_reconcile_queues_pending_and_due_failures_only(seeded_db, dirs):
    await _favorite("fav_cached")
    await _favorite("fav_frigate")
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        repo = DetectionRepository(db)
        # fav_frigate failed a minute ago on its first attempt: due (delay is 60 s).
        await repo.update_favorite_archive(
            "fav_frigate",
            snapshot_state="durable",
            clip_state="failed",
            bytes_on_disk=10,
            attempts=1,
            error="clip_timeout",
            archived_at=None,
            updated_at=now - timedelta(seconds=61),
        )
    service = ArchiveService()
    service._running = True
    assert await service.reconcile() == 2
    service = ArchiveService()
    service._running = True
    async with get_db() as db:
        # Spent all its attempts: never queued again without an explicit retry.
        await DetectionRepository(db).update_favorite_archive(
            "fav_frigate",
            snapshot_state="durable",
            clip_state="failed",
            bytes_on_disk=10,
            attempts=MAX_ATTEMPTS,
            error="clip_timeout",
            archived_at=None,
            updated_at=now - timedelta(days=1),
        )
    assert await service.reconcile() == 1


# ---- through the API ------------------------------------------------------------------------------


@pytest.fixture
def owner():
    original = (settings.auth.enabled, settings.auth.initial_setup_complete)
    settings.auth.enabled = False
    settings.auth.initial_setup_complete = True
    yield
    settings.auth.enabled, settings.auth.initial_setup_complete = original


@pytest.mark.asyncio
async def test_favouriting_reports_pending_then_the_record_carries_the_state(seeded_db, dirs, owner):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/events/fav_cached/favorite")
        assert res.status_code == 200, res.text
        assert res.json()["archive_state"] == "pending"
        listing = await client.get("/api/events?event_id=fav_cached")
        assert listing.json()[0]["archive_state"] == "pending"
        plain = await client.get("/api/events?event_id=plain")
        assert plain.json()[0]["archive_state"] is None
        status = await client.get("/api/events/fav_cached/archive")
        assert status.json()["state"] == "pending"


@pytest.mark.asyncio
async def test_a_cleared_cache_still_serves_the_favourite_and_unfavouriting_removes_the_archive(seeded_db, dirs, owner):
    _cache_snapshot(dirs, "fav_cached", data=b"the-photo")
    await _favorite("fav_cached")
    service = archive_module.archive_service
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch, clip_patch:
        await service.archive_event("fav_cached")
    await media_cache_module.MediaCacheService().clear_all()
    with patch.object(
        archive_module.frigate_client,
        "get_snapshot_with_error",
        new=AsyncMock(return_value=(None, "snapshot_not_found")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/frigate/fav_cached/snapshot.jpg")
            assert res.status_code == 200, res.text
            assert res.content == b"the-photo"
            gone = await client.delete("/api/events/fav_cached/favorite")
            assert gone.json()["archive_state"] is None
    assert not (dirs["archive"] / "fav_cached").exists()


@pytest.mark.asyncio
async def test_retry_resets_a_failed_archive_and_queues_it(seeded_db, dirs, owner):
    await _favorite("fav_frigate")
    async with get_db() as db:
        await DetectionRepository(db).update_favorite_archive(
            "fav_frigate",
            snapshot_state="durable",
            clip_state="failed",
            bytes_on_disk=10,
            attempts=MAX_ATTEMPTS,
            error="clip_timeout",
            archived_at=None,
            updated_at=datetime.now(timezone.utc),
        )
    with patch.object(archive_module.archive_service, "enqueue", return_value=True) as enqueue:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/events/fav_frigate/archive/retry")
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "pending"
    assert res.json()["attempts"] == 0
    enqueue.assert_called_once_with("fav_frigate")


# ---- the live photograph, Frigate's timing, and Frigate forgetting ------------------------------


@pytest.mark.asyncio
async def test_a_re_chosen_photograph_is_archived_again(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached", data=b"first-choice")
    await _favorite("fav_cached")
    service = ArchiveService()
    service._running = True
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch, clip_patch:
        await service.archive_event("fav_cached")
    assert (dirs["archive"] / "fav_cached" / SNAPSHOT_NAME).read_bytes() == b"first-choice"

    _cache_snapshot(dirs, "fav_cached", data=b"second-choice", source="frigate_snapshot_cropped")
    assert await service.refresh_photograph("fav_cached") is True
    assert (await _archive_row("fav_cached"))["state"] == "pending"
    with snapshot_patch, clip_patch:
        await service.archive_event("fav_cached")
    assert (dirs["archive"] / "fav_cached" / SNAPSHOT_NAME).read_bytes() == b"second-choice"
    meta = json.loads((dirs["archive"] / "fav_cached" / "snapshot.meta.json").read_text())
    assert meta["source"] == "frigate_snapshot_cropped"
    assert await service.refresh_photograph("plain") is False  # not a favourite: nothing to do


@pytest.mark.asyncio
async def test_the_cache_is_served_before_the_archive(seeded_db, dirs, owner):
    _cache_snapshot(dirs, "fav_cached", data=b"archived-photo")
    await _favorite("fav_cached")
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch, clip_patch:
        await archive_module.archive_service.archive_event("fav_cached")
    # Large enough that the route does not mistake it for a thumbnail-sized stand-in.
    live_photo = b"live-photo-in-cache" + b"\xff" * (96 * 1024)
    _cache_snapshot(dirs, "fav_cached", data=live_photo, source="frigate_snapshot_cropped")
    original = (settings.media_cache.enabled, settings.media_cache.cache_snapshots)
    settings.media_cache.enabled = settings.media_cache.cache_snapshots = True
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/frigate/fav_cached/snapshot.jpg")
    finally:
        settings.media_cache.enabled, settings.media_cache.cache_snapshots = original
    assert res.status_code == 200, res.text
    assert res.content == live_photo


@pytest.mark.asyncio
async def test_a_visit_still_in_progress_is_not_marked_clipless(seeded_db, dirs):
    _cache_snapshot(dirs, "fav_cached")
    await _favorite("fav_cached")
    async with get_db() as db:
        await db.execute(
            "UPDATE detections SET detection_time = ? WHERE frigate_event = 'fav_cached'",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),),
        )
        await db.commit()
    service = ArchiveService()
    snapshot_patch, clip_patch = _frigate(clip=(False, "clip_not_found"))
    with snapshot_patch, clip_patch:
        result = await service.archive_event("fav_cached")
    assert result["state"] == "pending"
    row = await _archive_row("fav_cached")
    assert (row["snapshot_state"], row["clip_state"], row["attempts"]) == ("durable", "pending", 0)
    # The same answer for a visit from two days ago is final.
    async with get_db() as db:
        await db.execute(
            "UPDATE detections SET detection_time = '2026-09-09 10:00:00' WHERE frigate_event = 'fav_cached'"
        )
        await db.commit()
    with snapshot_patch, clip_patch:
        result = await service.archive_event("fav_cached")
    assert result["state"] == "durable"
    assert (await _archive_row("fav_cached"))["clip_state"] == "unavailable"


@pytest.mark.asyncio
async def test_frigate_forgetting_a_favourite_marks_it_missing_even_under_delete(seeded_db, dirs):
    from app.services.frigate_missing_policy import apply_missing_policy

    await _favorite("fav_cached")
    original = settings.maintenance.frigate_missing_behavior
    settings.maintenance.frigate_missing_behavior = "delete"
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            counts = await apply_missing_policy(
                repo=repo, frigate_event="fav_cached", error="event_not_found", source="test", media_kind="event"
            )
            counts_plain = await apply_missing_policy(
                repo=repo, frigate_event="plain", error="event_not_found", source="test", media_kind="event"
            )
            kept = await repo.get_by_frigate_event("fav_cached")
            gone = await repo.get_by_frigate_event("plain")
    finally:
        settings.maintenance.frigate_missing_behavior = original
    assert counts == {"deleted_count": 0, "marked_missing_count": 1, "kept_count": 0}
    assert kept is not None and kept.is_favorite and kept.frigate_status == "missing"
    assert counts_plain["deleted_count"] == 1 and gone is None


@pytest.mark.asyncio
async def test_starring_a_durable_favourite_again_reports_what_it_holds(seeded_db, dirs, owner):
    _cache_snapshot(dirs, "fav_cached")
    _cache_clip(dirs, "fav_cached")
    await _favorite("fav_cached")
    snapshot_patch, clip_patch = _frigate()
    with snapshot_patch, clip_patch:
        await archive_module.archive_service.archive_event("fav_cached")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/events/fav_cached/favorite")
    assert res.json()["archive_state"] == "durable"


@pytest.mark.asyncio
async def test_the_floor_keeps_cached_photographs_but_not_clips(dirs):
    import os

    cache = media_cache_module.MediaCacheService()
    for event in ("floor_evt", "fav_evt", "plain_evt"):
        (dirs["cache"] / "snapshots" / f"{event}.jpg").write_bytes(b"x")
        (dirs["cache"] / "clips" / f"{event}.mp4").write_bytes(b"x")
    old = (datetime.now() - timedelta(days=3)).timestamp()
    for path in list((dirs["cache"] / "snapshots").iterdir()) + list((dirs["cache"] / "clips").iterdir()):
        os.utime(path, (old, old))
    await cache.cleanup_old_media(1, protected_event_ids={"fav_evt"}, protected_snapshot_event_ids={"floor_evt"})
    assert (dirs["cache"] / "snapshots" / "fav_evt.jpg").exists() and (dirs["cache"] / "clips" / "fav_evt.mp4").exists()
    assert (dirs["cache"] / "snapshots" / "floor_evt.jpg").exists()
    assert not (dirs["cache"] / "clips" / "floor_evt.mp4").exists()
    assert not (dirs["cache"] / "snapshots" / "plain_evt.jpg").exists()
