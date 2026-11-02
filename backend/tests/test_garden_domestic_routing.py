"""A declared domestic bird reaches Garden instead of bird history, and bird records can follow it."""

import copy
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.garden_repository import GardenRepository
from app.services.garden_capture_service import garden_capture_service

EVENT = "domestic-route-1"


@pytest_asyncio.fixture(autouse=True)
async def database():
    original = copy.deepcopy(settings.frigate)
    beta, auth, public = settings.system.beta_garden_animals, settings.auth.enabled, settings.public_access.enabled
    settings.system.beta_garden_animals = True
    settings.frigate.camera = ["greenhousecam", "feeder"]
    settings.frigate.garden_cameras = ["greenhousecam"]
    settings.frigate.garden_domestic_birds = ["chicken"]
    settings.auth.enabled = settings.public_access.enabled = False
    await init_db()
    async with get_db() as db:
        for table in ("garden_domestic_routes", "garden_captures"):
            await db.execute(f"DELETE FROM {table}")
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'domestic-route-%'")
        await db.commit()
    yield
    settings.frigate = original
    settings.system.beta_garden_animals, settings.auth.enabled, settings.public_access.enabled = beta, auth, public
    await close_db()


def bird_event(label="bird", event_type="new", camera="greenhousecam"):
    return {
        "type": event_type,
        "after": {
            "id": EVENT,
            "camera": camera,
            "label": label,
            "start_time": time.time() - 30,
            "has_snapshot": True,
        },
    }


async def detections(event_id=EVENT):
    async with get_db() as db:
        row = await (await db.execute("SELECT COUNT(*) FROM detections WHERE frigate_event=?", (event_id,))).fetchone()
    return row[0]


async def garden_capture():
    async with get_db() as db:
        rows = await GardenRepository(db).list("confirmed", 20, 0)
    return rows[0] if rows else None


async def process(payload, *, top, accepted):
    """Run one Frigate bird event through the real processor with a stubbed classifier."""
    from app.services.event_processor import EventProcessor

    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(return_value=[top])
    with (
        patch("app.services.event_processor.frigate_client") as frigate,
        patch("app.services.event_processor.DetectionService") as detection_service,
        patch("app.services.event_processor.notification_service") as notifications,
        patch("app.services.event_processor.media_cache"),
        patch("app.services.event_processor.Image.open"),
    ):
        frigate.get_snapshot_with_error = AsyncMock(return_value=(b"fakeimage", None))
        service = detection_service.return_value
        service.select_usable_classification.return_value = (accepted, None if accepted else "range")
        service.save_detection = AsyncMock(return_value=(True, True))
        service.get_detection_by_frigate_event = AsyncMock(return_value=None)
        notifications.notify_detection = AsyncMock()
        processor = EventProcessor(classifier)
        enqueue = AsyncMock()
        processor._enqueue_notification_flow = enqueue
        await processor._process_event_payload(payload)
    return service, enqueue


@pytest.mark.asyncio
async def test_a_red_junglefowl_bird_event_becomes_the_owners_chicken_in_garden_not_a_detection():
    junglefowl = {"label": "Gallus gallus", "score": 0.93, "index": 7, "model_sha256": "m" * 64}
    # A range filter rejecting Red Junglefowl in Britain must not lose the owner's chicken.
    service, enqueue = await process(bird_event(), top=junglefowl, accepted=None)
    service.save_detection.assert_not_awaited()
    enqueue.assert_not_awaited()
    assert await detections() == 0
    capture = await garden_capture()
    assert capture is not None and capture.frigate_event == EVENT and capture.camera == "greenhousecam"
    assert capture.status == "confirmed" and capture.label == "bird"
    route = capture.domestic_route
    assert (route.domestic_bird, route.origin, route.source_label, route.source_score) == (
        "chicken",
        "bird_detection",
        "Gallus gallus",
        0.93,
    )
    # Later messages for the event are idempotent, and Frigate's bird label does not revoke it.
    await process(bird_event(event_type="update"), top=junglefowl, accepted=junglefowl)
    await garden_capture_service.process(bird_event(event_type="end"))
    async with get_db() as db:
        assert await GardenRepository(db).count("confirmed") == 1
    # A later person update revokes it, as for any Garden capture.
    await garden_capture_service.process(bird_event(label="person", event_type="update"))
    assert await garden_capture() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("declared", [[], ["turkey"]])
async def test_an_undeclared_chicken_stays_a_bird_detection(declared):
    settings.frigate.garden_domestic_birds = declared
    junglefowl = {"label": "Gallus gallus", "score": 0.93, "index": 7}
    service, _ = await process(bird_event(), top=junglefowl, accepted=junglefowl)
    service.save_detection.assert_awaited_once()
    assert await garden_capture() is None


@pytest.mark.asyncio
async def test_with_garden_off_the_declaration_has_no_effect():
    settings.system.beta_garden_animals = False
    junglefowl = {"label": "Gallus gallus", "score": 0.93, "index": 7}
    service, _ = await process(bird_event(), top=junglefowl, accepted=junglefowl)
    service.save_detection.assert_awaited_once()


async def bird_record(label="Gallus gallus", event_id="domestic-route-2"):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections(detection_time,detection_index,score,display_name,category_name,
               frigate_event,camera_name,scientific_name) VALUES ('2026-10-31 09:00:00',1,0.91,?,?,?,'feeder',?)""",
            (label, label, event_id, label),
        )
        await db.commit()
    return event_id


@pytest.mark.asyncio
async def test_move_to_garden_hides_the_bird_record_and_names_the_capture_once():
    event_id = await bird_record()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/events/{event_id}/move-to-garden")
        assert response.status_code == 200, response.text
        capture_id = response.json()["capture_id"]
        again = await client.post(f"/api/events/{event_id}/move-to-garden")
        assert again.status_code == 409
        garden = (await client.get("/api/garden", params={"status": "confirmed"})).json()["items"]
        assert [item["id"] for item in garden] == [capture_id]
        assert garden[0]["domestic_route"]["origin"] == "moved_from_birds"
        assert garden[0]["scientific_name"] == "Gallus gallus domesticus"
        options = {item["key"]: item for item in (await client.get("/api/garden/domestic-birds")).json()}
        assert options["chicken"]["declared"] and "Gallus gallus" in options["chicken"]["scientific_names"]
    async with get_db() as db:
        hidden = await (
            await db.execute("SELECT is_hidden FROM detections WHERE frigate_event=?", (event_id,))
        ).fetchone()
    # Hidden, not deleted: showing the bird record again restores it.
    assert hidden == (1,)


@pytest.mark.asyncio
async def test_move_to_garden_refuses_birds_the_owner_has_not_declared():
    event_id = await bird_record("Prunella modularis", "domestic-route-3")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/events/{event_id}/move-to-garden")
    assert response.status_code == 409
    assert await garden_capture() is None
    assert await detections(event_id) == 1


@pytest.mark.asyncio
async def test_domestic_birds_round_trip_through_settings_and_reject_unknown_birds():
    settings.frigate.garden_domestic_birds = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/settings")).json()["garden_domestic_birds"] == []
        saved = await client.post("/api/settings", json={"garden_domestic_birds": ["chicken", "Chicken", "turkey"]})
        assert saved.status_code == 200, saved.text
        assert (await client.get("/api/settings")).json()["garden_domestic_birds"] == ["chicken", "turkey"]
        assert (await client.post("/api/settings", json={"garden_domestic_birds": ["pheasant"]})).status_code == 422
        assert (await client.post("/api/settings", json={"nest_dedupe_minutes": 31})).status_code == 200
    assert settings.frigate.garden_domestic_birds == ["chicken", "turkey"]


async def hidden(event_id):
    async with get_db() as db:
        row = await (await db.execute("SELECT is_hidden FROM detections WHERE frigate_event=?", (event_id,))).fetchone()
    return row[0]


@pytest.mark.asyncio
async def test_keeping_a_bird_declares_it_and_moves_its_visible_records_to_garden_once():
    settings.frigate.garden_domestic_birds = []
    chickens = [await bird_record(event_id=f"domestic-route-k{i}") for i in range(3)]
    already_hidden = await bird_record(event_id="domestic-route-kh")
    async with get_db() as db:
        await db.execute("UPDATE detections SET is_hidden=1 WHERE frigate_event=?", (already_hidden,))
        await db.commit()
    dunnock = await bird_record("Prunella modularis", "domestic-route-kd")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/garden/domestic-birds/chicken/keep")
        assert response.status_code == 200, response.text
        assert response.json() == {"bird": "chicken", "declared": True, "moved": 3, "skipped": 0, "remaining": 0}
        again = await client.post("/api/garden/domestic-birds/chicken/keep")
        assert again.json() == {"bird": "chicken", "declared": False, "moved": 0, "skipped": 0, "remaining": 0}
        garden = (await client.get("/api/garden", params={"status": "confirmed"})).json()["items"]
    assert settings.frigate.garden_domestic_birds == ["chicken"]
    assert len(garden) == 3 and {item["domestic_route"]["origin"] for item in garden} == {"moved_from_birds"}
    # Hidden, not deleted, and only the bird the owner keeps.
    assert [await hidden(event) for event in chickens] == [1, 1, 1]
    assert [await detections(event) for event in chickens] == [1, 1, 1]
    assert await hidden(dunnock) == 0
    assert await hidden(already_hidden) == 1


@pytest.mark.asyncio
async def test_keeping_a_bird_moves_a_bounded_batch_and_says_how_many_remain(monkeypatch):
    from app.services import garden_domestic_service

    monkeypatch.setattr(garden_domestic_service, "KEEP_MOVE_LIMIT", 2)
    for i in range(3):
        await bird_record(event_id=f"domestic-route-b{i}")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.post("/api/garden/domestic-birds/chicken/keep")).json()
        second = (await client.post("/api/garden/domestic-birds/chicken/keep")).json()
    assert (first["moved"], first["remaining"]) == (2, 1)
    assert (second["moved"], second["remaining"]) == (1, 0)


@pytest.mark.asyncio
async def test_only_the_owner_can_keep_a_bird_and_only_a_known_one(monkeypatch):
    from app.auth import create_access_token

    settings.frigate.garden_domestic_birds = []
    event = await bird_record(event_id="domestic-route-ka")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/garden/domestic-birds/pheasant/keep")).status_code == 422
        monkeypatch.setattr(settings.auth, "enabled", True)
        assert (await client.post("/api/garden/domestic-birds/chicken/keep")).status_code == 401
        client.headers["Authorization"] = "Bearer " + create_access_token("garden-guest", auth_level="guest")
        assert (await client.post("/api/garden/domestic-birds/chicken/keep")).status_code == 403
    assert settings.frigate.garden_domestic_birds == []
    assert await hidden(event) == 0
