"""Guests see confirmed Garden animals under the same public rules as bird detections."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.garden_repository import GardenRepository


@pytest_asyncio.fixture
async def guest_history(monkeypatch):
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "media_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "media_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "show_camera_names", True)
    monkeypatch.setattr(settings.public_access, "show_snapshots", True)
    monkeypatch.setattr(settings.public_access, "show_clips", True)
    monkeypatch.setattr(settings.public_access, "rate_limit_per_minute", 100)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
        yield GardenRepository(db)
    await close_db()


async def add(repo, event_id, *, days_ago=0.0, status="confirmed", camera="greenhouse"):
    at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(tzinfo=None).isoformat()
    await repo.capture(event_id, camera, "cat", at, True)
    await repo.db.execute("UPDATE garden_captures SET status=? WHERE frigate_event=?", (status, event_id))
    await repo.db.commit()
    async with repo.db.execute("SELECT id FROM garden_captures WHERE frigate_event=?", (event_id,)) as cursor:
        return (await cursor.fetchone())[0]


def guest_client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
@pytest.mark.parametrize("asked", ["", "?status=pending", "?status=dismissed", "?status=reviewable"])
async def test_guest_sees_only_confirmed_animals_inside_the_public_history_window(guest_history, asked):
    await add(guest_history, "1700000000.1-recent", days_ago=1)
    await add(guest_history, "1700000000.2-pending", days_ago=1, status="pending")
    await add(guest_history, "1700000000.3-dismissed", days_ago=1, status="dismissed")
    await add(guest_history, "1700000000.4-old", days_ago=30)
    async with guest_client() as client:
        visits = await client.get(f"/api/garden/visits{asked}")
        timeline = await client.get(f"/api/garden/timeline{asked}")
    assert visits.status_code == timeline.status_code == 200, (visits.text, timeline.text)
    assert visits.json()["total"] == timeline.json()["total"] == 1
    capture = timeline.json()["items"][0]
    assert capture["status"] == "confirmed"
    assert visits.json()["visits"][0]["representative"]["id"] == capture["id"]


@pytest.mark.asyncio
async def test_guest_capture_omits_owner_review_controls(guest_history):
    await add(guest_history, "1700000000.1-recent", days_ago=1)
    async with guest_client() as client:
        capture = (await client.get("/api/garden/timeline")).json()["items"][0]
    assert capture["review_token"] is None
    assert capture["automatic_check"] is None
    assert capture["camera"] == "greenhouse"
    assert capture["snapshot_url"] == f"/api/garden/{capture['id']}/snapshot"
    assert capture["clip_event"] == "1700000000.1-recent"


@pytest.mark.asyncio
async def test_guest_camera_names_follow_the_public_camera_switch(guest_history, monkeypatch):
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    await add(guest_history, "1700000000.1-greenhouse", days_ago=1)
    await add(guest_history, "1700000000.2-patio", days_ago=2, camera="patio")
    async with guest_client() as client:
        filtered = (await client.get("/api/garden/timeline?camera=patio")).json()
    # A hidden camera cannot be probed through its filter either.
    assert filtered["total"] == 2
    assert {item["camera"] for item in filtered["items"]} == {"Hidden"}


@pytest.mark.asyncio
async def test_guest_media_follows_the_public_photo_and_clip_switches(guest_history, monkeypatch):
    recent = await add(guest_history, "1700000000.1-recent", days_ago=1)
    await add(guest_history, "1700000000.2-older", days_ago=5)
    monkeypatch.setattr(settings.public_access, "media_historical_days", 3)
    async with guest_client() as client:
        items = {item["id"]: item for item in (await client.get("/api/garden/timeline")).json()["items"]}
        assert len(items) == 2
        older = next(item for item in items.values() if item["id"] != recent)
        assert older["snapshot_url"] is None and older["crop_url"] is None and older["clip_event"] is None
        assert items[recent]["snapshot_url"] and items[recent]["clip_event"]
        monkeypatch.setattr(settings.public_access, "show_snapshots", False)
        monkeypatch.setattr(settings.public_access, "show_clips", False)
        hidden = (await client.get("/api/garden/timeline")).json()["items"]
    assert all(item["snapshot_url"] is None and item["clip_event"] is None for item in hidden)


@pytest.mark.asyncio
async def test_guest_photos_open_only_for_shared_confirmed_captures(guest_history, monkeypatch):
    recent = await add(guest_history, "1700000000.1-recent", days_ago=1)
    pending = await add(guest_history, "1700000000.2-pending", days_ago=1, status="pending")
    dismissed = await add(guest_history, "1700000000.3-dismissed", days_ago=1, status="dismissed")
    old = await add(guest_history, "1700000000.4-old", days_ago=30)
    with patch("app.services.garden_capture_service.frigate_client.get_snapshot", new=AsyncMock(return_value=b"photo")):
        async with guest_client() as client:
            shared = await client.get(f"/api/garden/{recent}/snapshot")
            assert shared.status_code == 200
            assert shared.content == b"photo"
            for capture_id in (pending, dismissed, old, "f" * 32):
                assert (await client.get(f"/api/garden/{capture_id}/snapshot")).status_code == 404
                assert (await client.get(f"/api/garden/{capture_id}/crop")).status_code == 404
            monkeypatch.setattr(settings.public_access, "show_snapshots", False)
            assert (await client.get(f"/api/garden/{recent}/snapshot")).status_code == 404


@pytest.mark.asyncio
async def test_guest_clip_access_admits_shared_confirmed_garden_events(guest_history, monkeypatch):
    from app.auth import AuthContext, AuthLevel
    from app.routers.proxy import require_event_access

    await add(guest_history, "1700000000.1-recent", days_ago=1)
    await add(guest_history, "1700000000.2-pending", days_ago=1, status="pending")
    await add(guest_history, "1700000000.3-old", days_ago=30)
    guest = AuthContext(auth_level=AuthLevel.GUEST)
    await require_event_access("1700000000.1-recent", guest, "en", media="clip")
    for event_id in ("1700000000.2-pending", "1700000000.3-old"):
        with pytest.raises(Exception) as denied:
            await require_event_access(event_id, guest, "en", media="clip")
        assert getattr(denied.value, "status_code", None) == 404
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    with pytest.raises(Exception) as off:
        await require_event_access("1700000000.1-recent", guest, "en", media="clip")
    assert getattr(off.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_guest_visit_captures_list_only_confirmed_members(guest_history):
    await add(guest_history, "1700000000.1-a", days_ago=1)
    await add(guest_history, "1700000000.2-b", days_ago=1 - 10 / 86400)
    await add(guest_history, "1700000000.3-c", days_ago=1 - 20 / 86400, status="pending")
    async with guest_client() as client:
        visit = (await client.get("/api/garden/visits")).json()["visits"][0]
        members = await client.get(f"/api/garden/visits/{visit['id']}/captures?status=reviewable")
    assert visit["capture_count"] == 2
    assert members.status_code == 200, members.text
    assert {item["status"] for item in members.json()["items"]} == {"confirmed"}
    assert members.json()["total"] == 2


@pytest.mark.asyncio
async def test_guest_still_cannot_review_or_read_owner_garden_state(guest_history):
    capture = await add(guest_history, "1700000000.1-recent", days_ago=1)
    async with guest_client() as client:
        for method, path in (
            ("GET", "/api/garden"),
            ("GET", "/api/garden/identification"),
            ("GET", "/api/garden/motion"),
            ("GET", "/api/garden/notifications"),
            ("GET", "/api/garden/crops/storage"),
            ("GET", "/api/garden/species?q=fox"),
            ("POST", f"/api/garden/{capture}/confirm"),
            ("POST", f"/api/garden/{capture}/dismiss"),
            ("POST", f"/api/garden/{capture}/identify"),
            ("POST", "/api/garden/review-batch"),
            ("POST", "/api/garden/dismiss-captures"),
            ("PUT", f"/api/garden/{capture}/species"),
        ):
            assert (await client.request(method, path)).status_code in {401, 403}, (method, path)


@pytest.mark.asyncio
async def test_garden_history_needs_public_access_or_a_login(guest_history, monkeypatch):
    monkeypatch.setattr(settings.public_access, "enabled", False)
    async with guest_client() as client:
        for path in ("/api/garden/visits", "/api/garden/timeline", f"/api/garden/{'f' * 32}/snapshot"):
            assert (await client.get(path)).status_code == 401, path


@pytest.mark.asyncio
async def test_auth_status_tells_visitors_whether_garden_animals_are_shared(guest_history, monkeypatch):
    async with guest_client() as client:
        assert (await client.get("/api/auth/status")).json()["garden_animals_enabled"] is True
        monkeypatch.setattr(settings.system, "beta_garden_animals", False)
        assert (await client.get("/api/auth/status")).json()["garden_animals_enabled"] is False


@pytest.mark.asyncio
async def test_a_visitor_session_reads_nothing_once_public_access_is_off(guest_history, monkeypatch):
    from app.auth import AuthContext, AuthLevel, create_access_token
    from app.routers.proxy import require_event_access

    capture = await add(guest_history, "1700000000.1-recent", days_ago=1)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    token = create_access_token("guest", auth_level="guest")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as client:
        for path in ("/api/garden/visits", "/api/garden/timeline", f"/api/garden/{capture}/snapshot"):
            assert (await client.get(path)).status_code == 403, path
    with pytest.raises(Exception) as denied:
        await require_event_access("1700000000.1-recent", AuthContext(auth_level=AuthLevel.GUEST), "en", media="clip")
    assert getattr(denied.value, "status_code", None) == 404
