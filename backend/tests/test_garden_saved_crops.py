"""Animal crop evidence survives full-photo expiry, never privacy revocation."""

import hashlib
from io import BytesIO
import time

from PIL import Image
import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.models.garden_motion import MotionSource
from app.repositories.garden_repository import GardenRepository
from app.services.garden_crop_service import build_saved_crop


def photograph():
    output = BytesIO()
    Image.new("RGB", (1000, 500), "green").save(output, format="JPEG")
    return output.getvalue()


def crop(image=None, original=None):
    image = photograph() if image is None else image
    return build_saved_crop(
        image,
        box=(0.1, 0.2, 0.3, 0.4),
        expected_sha256=hashlib.sha256(image).hexdigest(),
        source_start=original.motion_source.clip_start if original else 1000.0,
        source_end=original.motion_source.clip_end if original else 1010.0,
    )


def test_saved_crop_binds_the_original_photo_and_geometry_without_metadata():
    evidence, image = crop()
    assert evidence.source_sha256 == hashlib.sha256(photograph()).hexdigest()
    assert evidence.crop_sha256 == hashlib.sha256(image).hexdigest()
    assert evidence.frame_size == (1000, 500)
    assert evidence.box_xywh == (0.1, 0.2, 0.3, 0.4)
    with Image.open(BytesIO(image)) as decoded:
        assert decoded.size == (300, 200)
        assert not decoded.getexif()
    assert len(image) <= 128 * 1024


@pytest.mark.parametrize("box", [(0.9, 0.1, 0.3, 0.3), (0, 0, 0, 1), (0, float("nan"), 1, 1)])
def test_invalid_crop_geometry_never_saves_a_whole_frame(box):
    image = photograph()
    with pytest.raises(ValueError):
        build_saved_crop(
            image, box=box, expected_sha256=hashlib.sha256(image).hexdigest(), source_start=1, source_end=2
        )


def test_a_different_source_photo_cannot_be_attached_to_an_existing_identification():
    with pytest.raises(ValueError, match="source"):
        build_saved_crop(photograph(), box=(0, 0, 1, 1), expected_sha256="a" * 64, source_start=1, source_end=2)


@pytest_asyncio.fixture
async def captured():
    await init_db()
    image = photograph()
    start = time.time() - 60
    source = MotionSource(
        camera="patio",
        clip_start=start,
        clip_end=start + 10,
        frame_index=1,
        frame_offset=1,
        clip_sha256="a" * 64,
        image_sha256=hashlib.sha256(image).hexdigest(),
        detector_sha256="b" * 64,
        detector_score=0.9,
        box_xywh=(0.1, 0.2, 0.3, 0.4),
    )
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
        repo = GardenRepository(db)
        identity = await repo.capture_motion(source, image)
        original = await repo.review(identity, "confirmed")
    yield original, image
    await close_db()


@pytest.mark.asyncio
async def test_confirmed_crop_survives_full_photo_expiry_but_not_person_revocation(captured):
    original, image = captured
    evidence, cropped = crop(image, original)
    # Bind the actual recording span, which remains available after full-photo expiry.
    evidence = evidence.model_copy(
        update={"source_start": original.motion_source.clip_start, "source_end": original.motion_source.clip_end}
    )
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
        await db.execute("UPDATE garden_motion_sources SET expires_at='2000-01-01' WHERE capture_id=?", (original.id,))
        await db.commit()
        await repo.expire_motion_photos()
        assert (await repo.get(original.id)).status == "confirmed"
        assert await repo.motion_photo(original.id) is None
        assert await repo.crop_photo(original.id) == cropped
        await repo.block_motion_overlap("patio", original.motion_source.clip_start, original.motion_source.clip_end)
        assert await repo.crop_photo(original.id) is None
        assert await repo.get(original.id) is None


@pytest.mark.asyncio
async def test_person_update_after_restart_refreshes_a_revoked_saved_crop_even_with_collection_disabled(
    captured, monkeypatch
):
    from unittest.mock import AsyncMock

    from app.config import settings
    from app.services import garden_motion_privacy
    from app.services.broadcaster import broadcaster
    from app.services.garden_capture_service import GardenCaptureService

    original, image = captured
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        assert await GardenRepository(db).save_crop(original, evidence, cropped)
    await close_db()
    await init_db()
    service = GardenCaptureService()
    await service.initialize()
    monkeypatch.setattr(settings.frigate, "garden_cameras", [])
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)

    async def refresh(message):
        assert message == {"type": "garden_history_changed"}
        assert not garden_motion_privacy.lock.locked()
        async with get_db() as db:
            repo = GardenRepository(db)
            assert await repo.get(original.id) is None
            assert await repo.crop_photo(original.id) is None

    update = AsyncMock(side_effect=refresh)
    monkeypatch.setattr(broadcaster, "broadcast", update)
    person = {
        "type": "update",
        "after": {
            "id": "later-person",
            "camera": "patio",
            "label": "person",
            "start_time": original.motion_source.clip_start,
            "end_time": original.motion_source.clip_end,
        },
    }
    await service.process(person)
    update.assert_awaited_once_with({"type": "garden_history_changed"})
    await service.process(person)
    assert update.await_count == 1


@pytest.mark.asyncio
async def test_a_late_crop_cannot_overwrite_an_owner_dismissal(captured):
    original, image = captured
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.review(original.id, "dismissed")
        assert not await repo.save_crop(original, evidence, cropped)
        assert await repo.crop_photo(original.id) is None


@pytest.mark.asyncio
async def test_crop_media_follows_history_retention(captured):
    from datetime import datetime, timedelta, timezone

    original, image = captured
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
        await repo.delete_older_than(datetime.now(timezone.utc) + timedelta(days=1))
        assert await repo.crop_photo(original.id) is None
        assert (await (await db.execute("SELECT COUNT(*) FROM garden_saved_crops")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_saved_crop_endpoint_is_private_and_never_substitutes_for_an_expired_full_photo(captured, monkeypatch):
    import httpx
    from app.config import settings
    from app.main import app

    original, image = captured
    monkeypatch.setattr(settings.auth, "enabled", False)
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
        await db.execute("UPDATE garden_motion_sources SET expires_at='2000-01-01' WHERE capture_id=?", (original.id,))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/garden/{original.id}/crop")
        assert response.status_code == 200 and response.content == cropped
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        page = (await client.get("/api/garden", params={"status": "confirmed"})).json()
        assert page["items"][0]["snapshot_url"] is None
        assert page["items"][0]["crop_url"] == f"/api/garden/{original.id}/crop"
        assert (await client.get(f"/api/garden/{original.id}/snapshot")).status_code == 404
        monkeypatch.setattr(settings.system, "beta_garden_animals", False)
        assert (await client.get(f"/api/garden/{original.id}/crop")).status_code == 404


@pytest.mark.asyncio
async def test_saved_crop_loads_with_the_owner_media_cookie_without_authorising_other_routes(captured, monkeypatch):
    import httpx
    from app.auth import SESSION_COOKIE, AuthLevel, create_access_token
    from app.config import settings
    from app.main import app

    original, image = captured
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        assert await GardenRepository(db).save_crop(original, evidence, cropped)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings, "api_key", None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/garden/{original.id}/crop"
        assert (await client.get(path)).status_code == 401
        client.cookies.set(SESSION_COOKIE, create_access_token("owner", AuthLevel.OWNER))
        response = await client.get(path)
        assert response.status_code == 200 and response.content == cropped
        assert response.headers["cache-control"] == "private, no-store"
        assert (await client.get("/api/garden/crops/storage")).status_code == 401
        assert (await client.post(f"/api/garden/{original.id}/dismiss")).status_code == 401
        client.cookies.set(SESSION_COOKIE, create_access_token("guest", AuthLevel.GUEST))
        assert (await client.get(path)).status_code == 403
        client.cookies.set(SESSION_COOKIE, "invalid-session")
        assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
async def test_a_corrupt_saved_crop_is_never_served(captured):
    from app.repositories.garden_repository import GardenPhotoUnavailable

    original, image = captured
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
        await db.execute("UPDATE garden_saved_crops SET image=? WHERE capture_id=?", (b"other-photo", original.id))
        await db.commit()
        with pytest.raises(GardenPhotoUnavailable):
            await repo.crop_photo(original.id)


@pytest.mark.asyncio
async def test_crop_budget_reclaims_oldest_preview_and_never_recreates_it_automatically(captured, monkeypatch):
    import app.repositories.garden_repository as module

    original, image = captured
    evidence, cropped = crop(image, original)
    monkeypatch.setattr(module, "CROP_COUNT_LIMIT", 1)
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
        source = original.motion_source.model_copy(
            update={
                "clip_start": original.motion_source.clip_start + 20,
                "clip_end": original.motion_source.clip_end + 20,
            }
        )
        identity = await repo.capture_motion(source, image)
        latest = await repo.review(identity, "confirmed")
        latest_evidence, latest_cropped = crop(image, latest)
        assert await repo.save_crop(latest, latest_evidence, latest_cropped)
        assert await repo.crop_photo(original.id) is None
        assert await repo.crop_photo(latest.id) == cropped
        assert (await repo.crop_storage())["count"] == 1
        assert await repo.next_crop(["patio"]) is None
        assert (await repo.get(original.id)).status == "confirmed"


@pytest.mark.asyncio
async def test_collection_does_not_hold_privacy_lock_during_io_or_resurrect_revoked_photos(captured, monkeypatch):
    from app.config import settings
    from app.services.garden_crop_service import GardenCropService
    from app.services.garden_capture_service import garden_capture_service
    from app.services import garden_motion_privacy

    original, image = captured
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])

    async def revoked(identity):
        assert not garden_motion_privacy.lock.locked()
        async with garden_motion_privacy.lock:
            garden_motion_privacy.invalidate()
            async with get_db() as db:
                await GardenRepository(db).block_capture(identity)
        return image

    monkeypatch.setattr(garden_capture_service, "snapshot", revoked)
    await GardenCropService().collect(original.id)
    async with get_db() as db:
        assert await GardenRepository(db).crop_photo(original.id) is None
        assert (await (await db.execute("SELECT COUNT(*) FROM garden_saved_crops")).fetchone())[0] == 0


@pytest.mark.asyncio
async def test_a_visit_keeps_an_older_saved_crop_as_its_representative(captured):
    from app.repositories.garden_visit_repository import GardenVisitRepository

    original, image = captured
    evidence, cropped = crop(image, original)
    async with get_db() as db:
        repo = GardenVisitRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
        source = original.motion_source.model_copy(
            update={
                "clip_start": original.motion_source.clip_start + 20,
                "clip_end": original.motion_source.clip_end + 20,
            }
        )
        second = await repo.capture_motion(source, image)
        await repo.review(second, "confirmed")
        visits, total, captures = await repo.visits(
            start=None, end=None, camera="patio", newest_first=True, status="confirmed", limit=20, offset=0
        )
        assert total == 1 and captures == 2
        assert visits[0]["representative"] == original.id
        members, count = await repo.visit_captures(
            visits[0]["id"], start=None, end=None, camera="patio", status="confirmed", limit=20, offset=0
        )
        assert count == 2 and members[0].id == second


@pytest.mark.asyncio
async def test_confirmed_motion_capture_collects_its_real_crop(captured, monkeypatch):
    from app.config import settings
    from app.services.garden_crop_service import GardenCropService

    original, image = captured
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    await GardenCropService().collect(original.id)
    async with get_db() as db:
        repo = GardenRepository(db)
        saved = await repo.get(original.id)
        assert saved.crop.source_sha256 == original.motion_source.image_sha256
        assert saved.crop.box_xywh == original.motion_source.box_xywh
        assert await repo.crop_photo(original.id)


@pytest.mark.asyncio
async def test_auto_naming_and_saved_pixels_commit_together(captured, monkeypatch):
    from app.models.garden import GardenAutomaticCheck, GardenIdentification, GardenPresenceMass
    from app.utils.api_datetime import utc_naive_now

    original, image = captured
    async with get_db() as db:
        repo = GardenRepository(db)
        source = original.motion_source.model_copy(
            update={
                "clip_start": original.motion_source.clip_start + 20,
                "clip_end": original.motion_source.clip_end + 20,
            }
        )
        identity = await repo.capture_motion(source, image)
        pending = await repo.get(identity)
        evidence, cropped = crop(image, pending)
        named = GardenIdentification(
            outcome="suggestion",
            reason="confident",
            review="accepted",
            automatic=True,
            name="Red fox",
            score=0.95,
            country="GBR",
            variant="4.0.3a",
            provider="cpu",
            devices=["CPUExecutionProvider"],
            model_sha256="a" * 64,
            package_sha256="b" * 64,
            image_sha256=source.image_sha256,
            output_index=0,
            input_kind="tracked_crop",
            box_xywh=source.box_xywh,
            frame_size=(1000, 500),
            identified_at=utc_naive_now().isoformat(),
        )
        result = GardenAutomaticCheck(
            outcome="animal",
            checked_at=utc_naive_now().isoformat(),
            image_sha256=source.image_sha256,
            variant="4.0.3a",
            model_sha256="a" * 64,
            package_sha256="b" * 64,
            mass=GardenPresenceMass(bird=0.0, animal=1.0, human=0.0, non_animal=0.0, other=0.0),
            devices=["CPUExecutionProvider"],
        )
        write = repo.save_crop

        async def during(*args, **kwargs):
            assert kwargs["commit"] is False
            async with get_db() as reader:
                before = await GardenRepository(reader).get(identity)
                assert before.status == "pending" and before.crop is None
            return await write(*args, **kwargs)

        monkeypatch.setattr(repo, "save_crop", during)
        assert await repo.save_automatic_naming(pending, result, named, crop=(evidence, cropped))
    async with get_db() as db:
        saved = await GardenRepository(db).get(identity)
        assert saved.status == "confirmed" and saved.identification.automatic and saved.crop is not None


@pytest.mark.asyncio
async def test_manual_confirmation_succeeds_when_crop_collection_is_unavailable(captured, monkeypatch):
    import httpx
    from app.config import settings
    from app.main import app
    from app.services.garden_capture_service import garden_capture_service

    original, image = captured
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])

    async def unavailable(_identity):
        raise ValueError("source unavailable")

    monkeypatch.setattr(garden_capture_service, "snapshot", unavailable)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/garden/{original.id}/confirm")
        assert response.status_code == 200 and response.json()["status"] == "confirmed"
    async with get_db() as db:
        assert await GardenRepository(db).crop_photo(original.id) is None


@pytest.mark.asyncio
async def test_frigate_crops_use_only_the_aligned_clean_frame_and_keep_person_revocation(captured, monkeypatch):
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.services.frigate_client import frigate_client
    from app.services.garden_crop_service import GardenCropService
    from datetime import datetime, timezone

    original, image = captured
    start = original.motion_source.clip_start + 20
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    monkeypatch.setattr(settings.frigate, "garden_labels", ["cat"])
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.capture(
            "clean-crop-1",
            "patio",
            "cat",
            datetime.fromtimestamp(start, timezone.utc).replace(tzinfo=None).isoformat(),
            True,
        )
        pending = (await repo.list("pending", 1, 0))[0]
        confirmed = await repo.review(pending.id, "confirmed")
    monkeypatch.setattr(
        frigate_client,
        "get_event",
        AsyncMock(
            return_value={
                "camera": "patio",
                "label": "cat",
                "start_time": start,
                "end_time": start + 10,
                "data": {"snapshot_frame_time": start + 2, "box": [0.1, 0.2, 0.3, 0.4]},
            }
        ),
    )
    monkeypatch.setattr(frigate_client, "get_alignment_snapshot_with_error", AsyncMock(return_value=(image, None)))
    unsafe = AsyncMock(side_effect=AssertionError("Saved event JPEG has unknown alignment"))
    monkeypatch.setattr(frigate_client, "get_snapshot", unsafe)
    await GardenCropService().collect(confirmed.id)
    unsafe.assert_not_awaited()
    async with get_db() as db:
        repo = GardenRepository(db)
        saved = await repo.get(confirmed.id)
        assert saved.crop.source_kind == "frigate_clean" and saved.crop.frame_time == start + 2
        assert saved.crop.source_sha256 == hashlib.sha256(image).hexdigest()
        await repo.block_motion_overlap("patio", start + 1, start + 3)
        assert await repo.get(confirmed.id) is None
        assert await repo.crop_photo(confirmed.id) is None
