"""The Explorer reads Garden captures by time, beside birds but never as birds."""

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.garden_repository import GardenRepository


@pytest_asyncio.fixture(autouse=True)
async def database(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield
    await close_db()


async def seed() -> dict[str, str]:
    """One capture per Explorer-relevant state, an hour apart on 13 October."""
    rows = {
        "fox": ("patio", "2026-10-13T08:00:00", True, "confirmed"),
        "cat": ("patio", "2026-10-13T09:00:00", True, "pending"),
        "badger": ("lawn", "2026-10-13T10:00:00", True, "pending"),
        "photoless": ("patio", "2026-10-13T11:00:00", False, "pending"),
        "rain": ("patio", "2026-10-13T12:00:00", True, "dismissed"),
        "hedgehog": ("patio", "2026-10-13T13:00:00", False, "confirmed"),
        "person": ("patio", "2026-10-13T14:00:00", True, "pending"),
    }
    async with get_db() as db:
        repo = GardenRepository(db)
        for event, (camera, observed, photo, _status) in rows.items():
            await repo.capture(event, camera, "cat", observed, photo)
        for event, (_camera, _observed, _photo, status) in rows.items():
            await db.execute("UPDATE garden_captures SET status=? WHERE frigate_event=?", (status, event))
        await db.commit()
        await repo.block("person", create=False)
        ids = await (await db.execute("SELECT frigate_event, id FROM garden_captures")).fetchall()
    return {event: capture_id for event, capture_id in ids if event}


async def timeline(**params) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/api/garden/timeline", params=params)


@pytest.mark.asyncio
async def test_timeline_lists_confirmed_and_reviewable_captures_newest_first():
    ids = await seed()
    response = await timeline(start="2026-10-13T00:00:00Z", end="2026-10-13T23:59:59Z")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    page = response.json()
    # Dismissed, blocked and photoless pending captures are not history worth showing.
    assert [item["id"] for item in page["items"]] == [ids["hedgehog"], ids["badger"], ids["cat"], ids["fox"]]
    assert page["total"] == 4
    assert page["items"][0]["status"] == "confirmed" and page["items"][0]["snapshot_url"] is None
    assert page["items"][-1]["observed_at"] == "2026-10-13T08:00:00Z"


@pytest.mark.asyncio
async def test_timeline_honours_window_camera_order_and_paging():
    ids = await seed()
    window = await timeline(start="2026-10-13T08:30:00Z", end="2026-10-13T10:30:00Z")
    assert [item["id"] for item in window.json()["items"]] == [ids["badger"], ids["cat"]]

    lawn = await timeline(camera="lawn")
    assert [item["id"] for item in lawn.json()["items"]] == [ids["badger"]]

    oldest = (await timeline(order="oldest", limit=2, offset=1)).json()
    assert [item["id"] for item in oldest["items"]] == [ids["cat"], ids["badger"]]
    assert oldest["total"] == 4 and oldest["limit"] == 2 and oldest["offset"] == 1


@pytest.mark.asyncio
async def test_timeline_rejects_a_reversed_window():
    await seed()
    response = await timeline(start="2026-10-14T00:00:00Z", end="2026-10-13T00:00:00Z")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_timeline_is_owner_only_and_follows_the_beta_switch(monkeypatch):
    await seed()
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.auth, "enabled", True)
    assert (await timeline()).status_code in {401, 403}

    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    assert (await timeline()).status_code == 404


@pytest.mark.asyncio
async def test_reading_the_timeline_writes_nothing():
    await seed()
    async with get_db() as db:
        before = await (await db.execute("SELECT * FROM garden_captures ORDER BY id")).fetchall()
        birds = await (await db.execute("SELECT count(*) FROM detections")).fetchone()
    await timeline()
    async with get_db() as db:
        assert await (await db.execute("SELECT * FROM garden_captures ORDER BY id")).fetchall() == before
        assert await (await db.execute("SELECT count(*) FROM detections")).fetchone() == birds
