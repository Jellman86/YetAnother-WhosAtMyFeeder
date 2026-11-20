"""A detection keeps the photo YA-WAMF classified, even when Frigate keeps no media for it.

Frigate discards a stationary or low-confidence event: its end message reports no snapshot and no
clip, and the event is deleted soon after. YA-WAMF already holds the whole frame its bird model
read, so a record moved to Garden, a domestic bird routed straight to Garden, and the missing-media
purge must all use or respect that copy instead of losing the photo. Frigate is mocked at its client.
"""

import hashlib
from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.models.garden import GardenDomesticRoute
from app.models.garden_media import KeptMediaRecord
from app.repositories.detection_repository import DetectionRepository
from app.repositories.garden_repository import GardenRepository
from app.services import media_cache as cache_module
from app.services import media_integrity_scan as scan_module
from app.services.garden_domestic_service import garden_domestic_service
from app.services.garden_media_cache import garden_media_cache
from app.services.media_integrity_scan import run_media_integrity_scan
from test_garden_kept_media import frigate as frigate  # noqa: F401  (autouse Frigate double and Garden settings)

EVENT = "1795166156.230183-07thuv"
CAMERA = "patio"


def jpeg(colour: str, size: tuple[int, int] = (64, 48)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, colour).save(output, format="JPEG")
    return output.getvalue()


CLASSIFIED = jpeg("olive", (96, 54))
CROP = jpeg("red", (16, 16))


@pytest_asyncio.fixture(autouse=True)
async def bird_history(frigate, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(settings.frigate, "garden_domestic_birds", ["chicken"])

    async def clean() -> None:
        await cache_module.media_cache.delete_cached_media(EVENT)
        async with get_db() as db:
            await db.execute("DELETE FROM garden_domestic_routes")
            await db.execute("DELETE FROM garden_captures")
            await db.execute("DELETE FROM detections WHERE frigate_event LIKE ?", (EVENT[:10] + "%",))
            await db.commit()

    await clean()
    yield
    await clean()


async def kept(capture_id: str) -> KeptMediaRecord | None:
    async with get_db() as db:
        return await GardenRepository(db).kept_media_record(capture_id)


async def chicken_record(*, frigate_status: str = "not_retained", event_id: str = EVENT) -> None:
    """A bird record whose Frigate event kept nothing, with the photos YA-WAMF holds for it.

    The bird model classified a whole recording frame; a later high-quality pass replaced the
    record's photo with a crop and retained the original among the photo choices, as it does live.
    """
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections(detection_time,detection_index,score,display_name,category_name,
               frigate_event,camera_name,scientific_name,frigate_status)
               VALUES (datetime('now','-1 hour'),1,0.988,'Gallus gallus','Gallus gallus',?,?,'Gallus gallus',?)""",
            (event_id, CAMERA, frigate_status),
        )
        await db.commit()
    media = cache_module.media_cache
    digest = hashlib.sha256(CLASSIFIED).hexdigest()
    original_ref = f"{event_id}__retained_snapshot__{digest[:12]}__image"
    assert await media.cache_snapshot(original_ref, CLASSIFIED, source="snapshot_candidate")
    assert await media.cache_snapshot(event_id, CROP, source="hq_candidate_model_crop")
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(
            event_id,
            [
                {
                    "candidate_id": original_ref.removesuffix("__image"),
                    "source_mode": "retained_photo",
                    "clip_variant": "retained_snapshot",
                    "snapshot_source": "frigate_recording_frame",
                    "image_ref": original_ref,
                    "content_sha256": digest,
                    "created_at": "2026-11-20 09:17:42",
                },
                {
                    "candidate_id": f"{event_id}__model_crop__f235__0123456789",
                    "source_mode": "model_crop",
                    "clip_variant": "recording",
                    "snapshot_source": "hq_candidate_model_crop",
                    "image_ref": event_id,
                    "content_sha256": hashlib.sha256(CROP).hexdigest(),
                    "selected": True,
                    "created_at": "2026-11-20 09:17:42",
                },
            ],
        )


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_a_record_moved_to_garden_after_frigate_deleted_its_event_keeps_the_classified_frame(frigate):  # noqa: F811
    await chicken_record()
    frigate.gone()
    async with client() as http:
        moved = await http.post(f"/api/events/{EVENT}/move-to-garden")
        assert moved.status_code == 200, moved.text
        capture_id = moved.json()["capture_id"]
        await garden_media_cache.collect_one()

        record = await kept(capture_id)
        assert record.photo_state == "kept"
        assert record.photo_source == "classified_frame"
        assert record.photo_sha256 == hashlib.sha256(CLASSIFIED).hexdigest()
        # Frigate never kept a clip, so Garden says so rather than inventing one.
        assert record.clip_state == "missing" and record.clip_sha256 is None
        photo = await http.get(f"/api/garden/{capture_id}/snapshot")
        assert photo.status_code == 200 and photo.content == CLASSIFIED
        item = (await http.get("/api/garden/timeline?status=confirmed")).json()["items"][0]
    assert item["snapshot_url"] == f"/api/garden/{capture_id}/snapshot"
    assert item["photo_kept"] is True and item["clip_kept"] is False
    # Frigate was never asked for a snapshot it had already said it did not keep.
    assert frigate.calls["snapshot"] == 0


@pytest.mark.asyncio
async def test_a_record_frigate_still_holds_keeps_frigates_snapshot_as_before(frigate):  # noqa: F811
    await chicken_record(frigate_status="present")
    async with client() as http:
        capture_id = (await http.post(f"/api/events/{EVENT}/move-to-garden")).json()["capture_id"]
    await garden_media_cache.collect(capture_id)
    record = await kept(capture_id)
    assert (record.photo_state, record.photo_source) == ("kept", "frigate_snapshot")
    assert record.photo_sha256 == hashlib.sha256(frigate.snapshot).hexdigest()


@pytest.mark.asyncio
async def test_a_garden_photo_recorded_missing_before_this_fix_is_recovered_once_from_yawamfs_copy(frigate):  # noqa: F811
    await chicken_record()
    frigate.gone()
    capture_id = await garden_domestic_service.move_detection(EVENT)
    async with get_db() as db:
        repo = GardenRepository(db)
        capture = await repo.get(capture_id)
        # What the old collector recorded: Frigate had nothing, and nothing else was looked at.
        await repo.save_kept_media(
            capture, KeptMediaRecord(photo_state="missing", photo_source="frigate_snapshot", clip_state="missing")
        )

    await garden_media_cache.collect_one()
    record = await kept(capture_id)
    assert (record.photo_state, record.photo_source) == ("kept", "classified_frame")
    assert record.clip_state == "missing"

    frigate.calls.clear()
    await garden_media_cache.collect_one()
    assert await kept(capture_id) == record
    assert not frigate.calls


@pytest.mark.asyncio
async def test_a_capture_whose_bird_record_holds_no_copy_is_looked_at_once_and_settles(frigate):  # noqa: F811
    await chicken_record()
    await cache_module.media_cache.delete_cached_media(EVENT)
    frigate.gone()
    capture_id = await garden_domestic_service.move_detection(EVENT)
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.save_kept_media(
            await repo.get(capture_id),
            KeptMediaRecord(photo_state="missing", photo_source="frigate_snapshot", clip_state="missing"),
        )
    await garden_media_cache.collect_one()
    record = await kept(capture_id)
    assert (record.photo_state, record.photo_source) == ("missing", "classified_frame")
    frigate.calls.clear()
    await garden_media_cache.collect_one()
    assert not frigate.calls


@pytest.mark.asyncio
async def test_a_domestic_bird_routed_straight_to_garden_keeps_the_whole_frame_the_model_read(frigate):  # noqa: F811
    routed = await garden_domestic_service.route_bird_event(
        event_id=EVENT,
        camera=CAMERA,
        start_time=1795166156.230183,
        has_snapshot=True,
        top={"label": "Gallus gallus", "score": 0.988},
        accepted={"label": "Gallus gallus", "score": 0.988},
        snapshot=CLASSIFIED,
        snapshot_source="frigate_recording_frame",
    )
    assert routed
    async with get_db() as db:
        capture = (await GardenRepository(db).list("confirmed", 5, 0))[0]
    record = await kept(capture.id)
    assert (record.photo_state, record.photo_source) == ("kept", "classified_frame")
    assert record.clip_state is None, "the clip is still Frigate's to keep"

    # Frigate then discards the event, and the photo stays.
    frigate.gone()
    await garden_media_cache.collect_one()
    async with client() as http:
        photo = await http.get(f"/api/garden/{capture.id}/snapshot")
    assert photo.status_code == 200 and photo.content == CLASSIFIED
    record = await kept(capture.id)
    assert (record.photo_state, record.clip_state) == ("kept", "missing")


@pytest.mark.asyncio
async def test_a_domestic_bird_classified_from_a_crop_waits_for_frigates_whole_snapshot(frigate):  # noqa: F811
    assert await garden_domestic_service.route_bird_event(
        event_id=EVENT,
        camera=CAMERA,
        start_time=1795166156.230183,
        has_snapshot=True,
        top={"label": "Gallus gallus", "score": 0.988},
        accepted={"label": "Gallus gallus", "score": 0.988},
        snapshot=CROP,
        snapshot_source="frigate_snapshot_cropped",
    )
    async with get_db() as db:
        capture = (await GardenRepository(db).list("confirmed", 5, 0))[0]
    assert await kept(capture.id) is None
    await garden_media_cache.collect(capture.id)
    record = await kept(capture.id)
    assert (record.photo_state, record.photo_source) == ("kept", "frigate_snapshot")


async def _stale_present_record(event_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections(detection_time,detection_index,score,display_name,category_name,
               frigate_event,camera_name,frigate_status,frigate_last_checked_at)
               VALUES (datetime('now','-1 day'),1,0.9,'Robin','Robin',?,?,'present',datetime('now','-30 days'))""",
            (event_id, CAMERA),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_the_missing_snapshot_purge_never_deletes_a_record_yawamf_holds_its_own_photo_for(monkeypatch):
    without_photo = EVENT[:10] + ".5-nophoto"
    async with get_db() as db:
        # The scan walks every stale row; only these two may be in the batch.
        await db.execute("DELETE FROM detections")
        await db.commit()
    await _stale_present_record(EVENT)
    await _stale_present_record(without_photo)
    assert await cache_module.media_cache.cache_snapshot(EVENT, CLASSIFIED, source="frigate_recording_frame")
    maintenance = settings.maintenance
    monkeypatch.setattr(maintenance, "auto_purge_missing_snapshots", True)
    monkeypatch.setattr(maintenance, "media_integrity_scan_enabled", True)
    monkeypatch.setattr(maintenance, "media_integrity_scan_media", "snapshot")
    monkeypatch.setattr(maintenance, "frigate_missing_behavior", "delete")
    monkeypatch.setattr(scan_module._state, "running", False)

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.17.1")),
        patch.object(
            scan_module.frigate_client, "get_event_with_error", new=AsyncMock(return_value=(None, "event_not_found"))
        ),
    ):
        result = await run_media_integrity_scan()

    assert (result.deleted_count, result.marked_missing_count) == (1, 1)
    async with get_db() as db:
        repo = DetectionRepository(db)
        kept_record = await repo.get_by_frigate_event(EVENT)
        assert await repo.get_by_frigate_event(without_photo) is None
    assert kept_record is not None and kept_record.frigate_status == "missing"
    assert await cache_module.media_cache.get_snapshot(EVENT) == CLASSIFIED


@pytest.mark.asyncio
async def test_a_record_frigate_did_not_retain_serves_yawamfs_copy_of_its_photo():
    await chicken_record()
    async with client() as http:
        with patch("app.routers.proxy.get_http_client") as http_client:
            http_client.return_value.get = AsyncMock(
                return_value=httpx.Response(404, request=httpx.Request("GET", "x"))
            )
            response = await http.get(f"/api/frigate/{EVENT}/snapshot.jpg")
    assert response.status_code == 200
    assert response.content == CROP
    assert response.headers["content-type"] == "image/jpeg"


async def _routed_chicken() -> str:
    async with get_db() as db:
        return await GardenRepository(db).save_domestic_capture(
            EVENT,
            CAMERA,
            "2026-11-20T09:15:56.230183",
            True,
            GardenDomesticRoute(
                domestic_bird="chicken", origin="bird_detection", source_label="Gallus gallus", routed_at="now"
            ),
        )


@pytest.mark.asyncio
async def test_keeping_the_classified_frame_never_replaces_a_photo_or_clip_already_kept(frigate):  # noqa: F811
    capture_id = await _routed_chicken()
    await garden_media_cache.collect(capture_id)
    before = await kept(capture_id)
    assert (before.photo_state, before.photo_source, before.clip_state) == ("kept", "frigate_snapshot", "kept")
    assert not await garden_media_cache.keep_classified_frame(capture_id, CLASSIFIED, "frigate_recording_frame")
    assert await kept(capture_id) == before


@pytest.mark.asyncio
async def test_keeping_the_classified_frame_does_not_wait_for_a_collection_in_progress(frigate):  # noqa: F811
    import asyncio

    capture_id = await _routed_chicken()
    async with garden_media_cache._collect_lock:
        kept_now = await asyncio.wait_for(
            garden_media_cache.keep_classified_frame(capture_id, CLASSIFIED, "frigate_recording_frame"), 5
        )
    assert kept_now
    assert (await kept(capture_id)).photo_source == "classified_frame"
