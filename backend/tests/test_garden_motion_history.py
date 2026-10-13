"""Motion evidence is private, immutable, bounded, and never a bird detection."""

import hashlib
import time

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.models.garden_motion import MotionSource
from app.repositories.garden_repository import GardenRepository


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_identifications")
        await db.execute("DELETE FROM garden_motion_sources")
        await db.execute("DELETE FROM garden_motion_cursors")
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield
    await close_db()


def evidence(*, start=None, image=b"photo"):
    start = start or time.time() - 60
    return MotionSource(
        camera="patio",
        clip_start=start,
        clip_end=start + 10,
        frame_index=25,
        frame_offset=1,
        clip_sha256="a" * 64,
        image_sha256=hashlib.sha256(image).hexdigest(),
        detector_sha256="c" * 64,
        detector_score=0.8,
        box_xywh=(0.1, 0.2, 0.3, 0.4),
    )


@pytest.mark.asyncio
async def test_real_recording_provenance_deduplicates_without_frigate_events_or_bird_writes():
    source = evidence()
    async with get_db() as db:
        repo = GardenRepository(db)
        before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
        first = await repo.capture_motion(source, b"photo")
        assert first is not None
        assert await repo.capture_motion(source, b"photo") is None
        rows = await repo.list("pending", 20, 0)
        assert len(rows) == 1
        assert rows[0].frigate_event is None
        assert rows[0].motion_source == source
        assert await repo.motion_photo(first) == b"photo"
        assert await repo.motion_cursor("patio") == source.clip_end
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == before


@pytest.mark.asyncio
async def test_wrong_photo_hash_never_creates_a_capture_or_advances_the_cursor():
    async with get_db() as db:
        repo = GardenRepository(db)
        with pytest.raises(ValueError):
            await repo.capture_motion(evidence(), b"different")
        assert await repo.count("pending") == 0
        assert await repo.motion_cursor("patio") is None


@pytest.mark.asyncio
async def test_expired_photo_cannot_be_served_but_confirmed_history_survives_cleanup():
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(evidence(), b"photo")
        await repo.review(capture_id, "confirmed")
        await db.execute(
            "UPDATE garden_motion_sources SET expires_at='2000-01-01T00:00:00' WHERE capture_id=?", (capture_id,)
        )
        await db.commit()
        assert await repo.motion_photo(capture_id) is None
        await repo.expire_motion_photos()
        capture = await repo.get(capture_id)
        assert capture and capture.status == "confirmed" and not capture.has_snapshot
        assert capture.motion_source is not None


@pytest.mark.asyncio
async def test_expired_pending_motion_photo_is_omitted_before_cleanup_without_changing_its_review():
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(evidence(start=time.time() - 4 * 86400), b"photo")
        assert await repo.count("pending") == 0
        assert await repo.list("pending", 20, 0) == []
        capture = await repo.get(capture_id)
        assert capture.status == "pending" and not capture.has_snapshot


@pytest.mark.asyncio
async def test_person_veto_erases_motion_photo_and_provenance_and_blocks_redelivery():
    source = evidence()
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(source, b"photo")
        await repo.block_capture(capture_id)
        assert await repo.get(capture_id) is None
        assert await repo.motion_photo(capture_id) is None
        assert await repo.capture_motion(source, b"photo") is None
        assert (await (await db.execute("SELECT COUNT(*) FROM garden_motion_sources")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_late_person_update_revokes_overlapping_motion_only(monkeypatch):
    from app.config import settings
    from app.services.garden_capture_service import garden_capture_service

    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    source = evidence()
    other = evidence(start=source.clip_start - 100)
    async with get_db() as db:
        repo = GardenRepository(db)
        first = await repo.capture_motion(source, b"photo")
        second = await repo.capture_motion(other, b"photo")
    await garden_capture_service.process(
        {
            "type": "update",
            "after": {
                "id": "real-person",
                "camera": "patio",
                "label": "person",
                "start_time": source.clip_start + 1,
                "end_time": source.clip_end + 1,
            },
        }
    )
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.get(first) is None
        assert await repo.motion_photo(first) is None
        assert await repo.get(second) is not None
        assert await repo.capture_motion(source, b"photo") is None


@pytest.mark.asyncio
async def test_unrelated_frigate_false_positive_preserves_independent_motion_review(monkeypatch):
    from app.config import settings
    from app.services.garden_capture_service import garden_capture_service

    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    source = evidence()
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(source, b"photo")
        await repo.review(capture_id, "confirmed")
        await repo.capture("false-dog", "patio", "dog", "2026-10-13T12:00:00", True)
    for label in ("bird", "dog", "car"):
        await garden_capture_service.process(
            {
                "type": "update",
                "after": {
                    "id": "false-" + label,
                    "camera": "patio",
                    "label": label,
                    "false_positive": True,
                    "start_time": source.clip_start,
                    "end_time": source.clip_end,
                },
            }
        )
    async with get_db() as db:
        repo = GardenRepository(db)
        capture = await repo.get(capture_id)
        assert capture and capture.status == "confirmed"
        assert await repo.motion_photo(capture_id) == b"photo"
        assert not any(row.frigate_event == "false-dog" for row in await repo.list("pending", 20, 0))


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-4.0, 11.0])
async def test_person_in_bounded_keyframe_padding_revokes_motion(offset):
    source = evidence()
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(source, b"photo")
        await repo.block_motion_overlap("patio", source.clip_start + offset, source.clip_start + offset + 1)
        assert await repo.get(capture_id) is None
        assert await repo.motion_photo(capture_id) is None


@pytest.mark.asyncio
async def test_expiry_removes_unconfirmed_media_and_identity_in_bounded_batches():
    async with get_db() as db:
        repo = GardenRepository(db)
        captures = [
            await repo.capture_motion(evidence(start=time.time() - 4 * 86400 - i * 20), b"photo") for i in range(10)
        ]
        await repo.expire_motion_photos()
        assert sum([await repo.get(key) is None for key in captures]) == 8
        await repo.expire_motion_photos()
        assert await repo.count("pending") == 0


@pytest.mark.asyncio
async def test_confirmation_between_expiry_read_and_write_keeps_confirmed_history(monkeypatch):
    from aiosqlite.context import contextmanager

    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(evidence(start=time.time() - 4 * 86400), b"photo")
        original = db.execute
        interleaved = False

        @contextmanager
        async def execute(sql, parameters=()):
            nonlocal interleaved
            if not interleaved and sql.lstrip().startswith(("UPDATE", "DELETE")):
                interleaved = True
                async with get_db() as owner_db:
                    await owner_db.execute("UPDATE garden_captures SET status='confirmed' WHERE id=?", (capture_id,))
                    await owner_db.commit()
            return await original(sql, parameters)

        monkeypatch.setattr(db, "execute", execute)
        await repo.expire_motion_photos()
        capture = await repo.get(capture_id)
        assert interleaved
        assert capture and capture.status == "confirmed"
        assert capture.motion_source is not None and not capture.has_snapshot


@pytest.mark.asyncio
async def test_motion_photo_budget_refuses_new_data_without_eviction_or_partial_capture(monkeypatch):
    import app.repositories.garden_repository as module

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 1)
    async with get_db() as db:
        repo = GardenRepository(db)
        first = evidence(start=time.time() - 100)
        second = evidence(start=time.time() - 60)
        assert await repo.capture_motion(first, b"photo")
        assert await repo.capture_motion(second, b"photo") is None
        assert await repo.count("pending") == 1
        assert await repo.motion_cursor("patio") == first.clip_end


@pytest.mark.asyncio
async def test_dismissed_photos_stay_restorable_until_a_new_candidate_needs_space(monkeypatch):
    import app.repositories.garden_repository as module

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 2)
    async with get_db() as db:
        repo = GardenRepository(db)
        before = await (await db.execute("SELECT * FROM detections ORDER BY id")).fetchall()
        first = await repo.capture_motion(evidence(start=time.time() - 100), b"photo")
        second = await repo.capture_motion(evidence(start=time.time() - 80), b"photo")
        await repo.review(first, "dismissed")
        await repo.review(second, "dismissed")
        assert await repo.motion_photo(first) == b"photo"
        assert not await repo.motion_storage_full()
        third = await repo.capture_motion(evidence(), b"photo")
        assert third
        old = await repo.get(first)
        assert old and old.status == "dismissed" and not old.has_snapshot and old.motion_source
        assert await repo.motion_photo(first) is None
        assert await repo.motion_photo(second) == b"photo"
        assert (await repo.review(second, "pending")).has_snapshot
        assert (
            await (await db.execute("SELECT COUNT(*) FROM garden_motion_sources WHERE image IS NOT NULL")).fetchone()
        )[0] == 2
        assert await (await db.execute("SELECT * FROM detections ORDER BY id")).fetchall() == before


@pytest.mark.asyncio
async def test_duplicate_and_failed_capture_do_not_reclaim_a_dismissed_photo(monkeypatch):
    import app.repositories.garden_repository as module

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 1)
    async with get_db() as db:
        repo = GardenRepository(db)
        source = evidence(start=time.time() - 100)
        capture_id = await repo.capture_motion(source, b"photo")
        await repo.review(capture_id, "dismissed")
        assert await repo.capture_motion(source, b"photo") is None
        with pytest.raises(ValueError):
            await repo.capture_motion(evidence(), b"wrong")
        assert await repo.motion_photo(capture_id) == b"photo"


@pytest.mark.asyncio
async def test_restored_and_confirmed_photos_cannot_be_reclaimed(monkeypatch):
    import app.repositories.garden_repository as module

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 2)
    async with get_db() as db:
        repo = GardenRepository(db)
        ids = [
            await repo.capture_motion(evidence(start=time.time() - 100 - index * 20), b"photo") for index in range(2)
        ]
        for capture_id in ids:
            await repo.review(capture_id, "dismissed")
        await repo.review(ids[0], "pending")
        await repo.review(ids[1], "confirmed")
        assert await repo.motion_storage_full()
        assert await repo.capture_motion(evidence(), b"photo") is None
        assert all([await repo.motion_photo(capture_id) == b"photo" for capture_id in ids])


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["restore", "confirm"])
async def test_reclaimed_motion_photo_cannot_be_restored_or_confirmed_from_a_stale_page(monkeypatch, action):
    import httpx
    import app.repositories.garden_repository as module
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 1)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    async with get_db() as db:
        repo = GardenRepository(db)
        source = evidence(start=time.time() - 100)
        capture_id = await repo.capture_motion(source, b"photo")
        await repo.review(capture_id, "dismissed")
        assert await repo.capture_motion(evidence(), b"photo")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/garden/{capture_id}/{action}")
        assert response.status_code == 409
        assert "photo" in response.json()["detail"].lower()
        assert (await client.get(f"/api/garden/{capture_id}/snapshot")).status_code == 404
        row = (await client.get("/api/garden", params={"status": "dismissed"})).json()["items"][0]
        assert row["snapshot_url"] is None and row["source_kind"] == "motion"
    async with get_db() as db:
        repo = GardenRepository(db)
        assert (await repo.get(capture_id)).status == "dismissed"
        assert await repo.capture_motion(source, b"photo") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["restore", "confirm"])
async def test_reclamation_between_review_read_and_update_cannot_produce_a_photoless_review(monkeypatch, action):
    import httpx
    import app.repositories.garden_repository as module
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 1)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    async with get_db() as db:
        repo = GardenRepository(db)
        capture_id = await repo.capture_motion(evidence(start=time.time() - 100), b"photo")
        await repo.review(capture_id, "dismissed")
    original = GardenRepository.review
    reclaimed = False

    async def interleave(self, identifier, status):
        nonlocal reclaimed
        if identifier == capture_id and status != "dismissed":
            async with get_db() as writer:
                assert await GardenRepository(writer).capture_motion(evidence(), b"photo")
            reclaimed = True
        return await original(self, identifier, status)

    monkeypatch.setattr(GardenRepository, "review", interleave)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/garden/{capture_id}/{action}")).status_code == 409
    assert reclaimed
    async with get_db() as db:
        assert (await GardenRepository(db).get(capture_id)).status == "dismissed"


@pytest.mark.asyncio
async def test_failed_storage_transaction_rolls_back_dismissed_photo_reclamation(monkeypatch):
    import sqlite3
    import app.repositories.garden_repository as module

    monkeypatch.setattr(module, "MOTION_PHOTO_LIMIT", 1)
    async with get_db() as db:
        repo = GardenRepository(db)
        source = evidence(start=time.time() - 100)
        capture_id = await repo.capture_motion(source, b"photo")
        await repo.review(capture_id, "dismissed")
        await db.execute(
            "CREATE TEMP TRIGGER fail_motion_insert BEFORE INSERT ON garden_motion_sources BEGIN SELECT RAISE(ABORT, 'private test write failure'); END"
        )
        try:
            with pytest.raises(sqlite3.IntegrityError):
                await repo.capture_motion(evidence(), b"photo")
        finally:
            await db.execute("DROP TRIGGER fail_motion_insert")
        assert await repo.motion_photo(capture_id) == b"photo"
        assert await repo.count("pending") == 0
        assert await repo.motion_cursor("patio") == source.clip_end


@pytest.mark.asyncio
async def test_owner_reads_motion_photo_without_calling_frigate_and_guest_is_denied(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.auth import create_access_token
    from app.config import settings
    from app.main import app
    from app.services.garden_capture_service import garden_capture_service

    async with get_db() as db:
        capture_id = await GardenRepository(db).capture_motion(evidence(), b"photo")
    mocked = AsyncMock()
    monkeypatch.setattr("app.services.garden_capture_service.frigate_client.get_snapshot", mocked)
    assert await garden_capture_service.snapshot(capture_id) == b"photo"
    mocked.assert_not_awaited()
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    token = create_access_token("guest", auth_level="guest")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer " + token}
    ) as client:
        assert (await client.get(f"/api/garden/{capture_id}/snapshot")).status_code == 403


@pytest.mark.asyncio
async def test_expired_motion_photo_cannot_be_confirmed_from_a_stale_page(monkeypatch):
    import httpx
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    async with get_db() as db:
        capture_id = await GardenRepository(db).capture_motion(evidence(start=time.time() - 4 * 86400), b"photo")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(f"/api/garden/{capture_id}/confirm")).status_code == 409
