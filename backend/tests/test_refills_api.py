"""The owner records, lists and deletes feeder refills; guests can do none of it (#946)."""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.auth import create_access_token
from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models.feeder_refill import NewRefill
from app.repositories.feeder_refill_repository import FeederRefillRepository
from app.routers import refills


@pytest_asyncio.fixture
async def owner_api(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "rate_limit_per_minute", 1000)
    monkeypatch.setattr(settings.frigate, "camera", ["birdcam", "greenhousecam"])
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM feeder_refills")
        await db.commit()
    token = create_access_token("owner")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client
    await close_db()


def guest_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


async def stored_count() -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM feeder_refills") as cursor:
            return (await cursor.fetchone())[0]


@pytest.mark.asyncio
async def test_owner_records_a_refill_and_reads_it_back(owner_api):
    at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    created = await owner_api.post(
        "/api/refills",
        json={"refilled_at": iso(at), "camera_name": "birdcam", "source": "manual", "note": "Sunflower <b>hearts</b>"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["outcome"] == "recorded"
    assert body["refill"]["refilled_at"] == iso(at)
    assert body["refill"]["camera_name"] == "birdcam"
    assert body["refill"]["source"] == "manual"
    assert body["refill"]["note"] == "Sunflower <b>hearts</b>"

    listed = await owner_api.get("/api/refills")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"] == [body["refill"]]


@pytest.mark.asyncio
async def test_a_refill_without_a_time_is_recorded_now(owner_api):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    created = await owner_api.post("/api/refills", json={})
    assert created.status_code == 201, created.text
    stored_at = datetime.fromisoformat(created.json()["refill"]["refilled_at"].replace("Z", "+00:00"))
    assert before <= stored_at <= datetime.now(timezone.utc)
    assert created.json()["refill"]["source"] == "api"
    assert created.json()["refill"]["camera_name"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"refilled_at": iso(datetime.now(timezone.utc) + timedelta(days=1))},
        {"camera_name": "frontdoor"},
        {"note": "x" * 300},
        {"refilled_at": "2026-11-28T09:00:00"},
        {"source": "mqtt"},
    ],
)
async def test_a_refill_that_cannot_be_true_is_refused_and_nothing_is_stored(owner_api, body):
    refused = await owner_api.post("/api/refills", json=body)
    assert refused.status_code == 422, refused.text
    assert await stored_count() == 0


@pytest.mark.asyncio
async def test_the_same_automation_event_sent_twice_is_one_refill(owner_api):
    at = datetime.now(timezone.utc) - timedelta(days=1)
    first = await owner_api.post("/api/refills", json={"refilled_at": iso(at), "source_event_id": "ha-door-17"})
    again = await owner_api.post("/api/refills", json={"source_event_id": "ha-door-17", "camera_name": "birdcam"})
    assert first.status_code == 201
    assert again.status_code == 200, again.text
    assert again.json()["outcome"] == "same_event"
    assert again.json()["refill"] == first.json()["refill"]
    assert await stored_count() == 1


@pytest.mark.asyncio
async def test_two_refills_of_one_camera_inside_the_cooldown_are_one_refill(owner_api):
    first = await owner_api.post("/api/refills", json={"camera_name": "birdcam", "source": "manual"})
    second = await owner_api.post("/api/refills", json={"camera_name": "birdcam", "source": "manual"})
    other = await owner_api.post("/api/refills", json={"camera_name": "greenhousecam", "source": "manual"})
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["outcome"] == "within_cooldown"
    assert second.json()["refill"]["id"] == first.json()["refill"]["id"]
    assert other.status_code == 201
    assert await stored_count() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("same_event", [True, False])
async def test_refills_sent_at_once_for_one_trip_store_one_refill(owner_api, same_event):
    sent = await asyncio.gather(
        *(
            owner_api.post("/api/refills", json={"camera_name": "birdcam", "source_event_id": f"burst-{event}"})
            for event in ([0] * 5 if same_event else range(5))
        )
    )
    assert sorted(response.status_code for response in sent) == [200, 200, 200, 200, 201]
    assert {response.json()["outcome"] for response in sent} == {
        "recorded",
        "same_event" if same_event else "within_cooldown",
    }
    assert await stored_count() == 1


@pytest.mark.asyncio
async def test_a_cooldown_event_is_still_deduplicated_after_the_cooldown(owner_api, monkeypatch):
    now = datetime(2026, 11, 28, 9, 0)
    monkeypatch.setattr(refills, "utc_naive_now", lambda: now)
    first = await owner_api.post("/api/refills", json={"camera_name": "birdcam", "source": "manual"})
    payload = {"camera_name": "birdcam", "source_event_id": "ha-door-18"}
    during = await owner_api.post("/api/refills", json=payload)
    assert during.status_code == 200
    assert during.json()["outcome"] == "within_cooldown"

    now += timedelta(minutes=16)
    later = await owner_api.post("/api/refills", json=payload)
    assert later.status_code == 200
    assert later.json() == {"outcome": "same_event", "refill": first.json()["refill"]}
    assert await stored_count() == 1

    assert (await owner_api.delete(f"/api/refills/{first.json()['refill']['id']}")).status_code == 200
    assert (await owner_api.post("/api/refills", json=payload)).status_code == 201


@pytest.mark.asyncio
async def test_the_earliest_supported_refill_time_can_be_recorded_and_listed(owner_api):
    earliest = "0001-01-01T00:00:00Z"
    first = await owner_api.post("/api/refills", json={"refilled_at": earliest})
    assert first.status_code == 201, first.text
    second = await owner_api.post("/api/refills", json={"refilled_at": earliest})
    assert second.status_code == 200, second.text
    assert second.json()["outcome"] == "within_cooldown"

    listed = await owner_api.get("/api/refills", params={"end": earliest})
    assert listed.status_code == 200, listed.text
    assert listed.json()["start"] == earliest
    assert listed.json()["items"] == [first.json()["refill"]]


@pytest.mark.asyncio
async def test_the_schema_keeps_one_row_per_automation_event():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM feeder_refills")
            await db.commit()
            repo = FeederRefillRepository(db)
            refill = NewRefill(datetime(2026, 11, 1, 8, 0), None, "api", None, "schema-1")
            async with repo.write_transaction():
                await repo.insert(refill)
            with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
                async with repo.write_transaction():
                    await repo.insert(refill)
            async with db.execute("SELECT COUNT(*) FROM feeder_refills") as cursor:
                assert (await cursor.fetchone())[0] == 1
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                await db.execute(
                    "INSERT INTO feeder_refills (refilled_at, source, created_at) VALUES ('2026-11-01', 'sms', '2026-11-01')"
                )
            await db.rollback()
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_a_refill_transaction_does_not_take_ownership_of_an_existing_transaction(owner_api):
    async with get_db() as db:
        await db.execute("BEGIN")
        try:
            with pytest.raises(RuntimeError, match="idle connection"):
                async with FeederRefillRepository(db).write_transaction():
                    pytest.fail("The existing transaction may not hold a write lock")
            assert db.in_transaction
        finally:
            await db.rollback()


@pytest.mark.asyncio
async def test_the_window_read_is_bounded_and_newest_first(owner_api):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        repo = FeederRefillRepository(db)
        async with repo.write_transaction():
            for days in (1, 2, 3, 45):
                await repo.insert(
                    NewRefill((now - timedelta(days=days)).replace(tzinfo=None), None, "manual", None, None)
                )

    default = (await owner_api.get("/api/refills")).json()
    assert default["total"] == 3
    assert [item["refilled_at"] for item in default["items"]] == [iso(now - timedelta(days=d)) for d in (1, 2, 3)]

    page = (await owner_api.get("/api/refills", params={"limit": 1, "offset": 1})).json()
    assert page["total"] == 3
    assert [item["refilled_at"] for item in page["items"]] == [iso(now - timedelta(days=2))]

    wide = await owner_api.get(
        "/api/refills", params={"start": iso(now - timedelta(days=60)), "end": iso(now - timedelta(days=40))}
    )
    assert [item["refilled_at"] for item in wide.json()["items"]] == [iso(now - timedelta(days=45))]

    too_wide = await owner_api.get("/api/refills", params={"start": iso(now - timedelta(days=401)), "end": iso(now)})
    backwards = await owner_api.get("/api/refills", params={"start": iso(now), "end": iso(now - timedelta(days=1))})
    too_many = await owner_api.get("/api/refills", params={"limit": 501})
    assert too_wide.status_code == backwards.status_code == too_many.status_code == 422


@pytest.mark.asyncio
async def test_deleting_a_refill_removes_it_for_good(owner_api):
    created = (await owner_api.post("/api/refills", json={"source": "manual"})).json()["refill"]
    deleted = await owner_api.delete(f"/api/refills/{created['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"id": created["id"], "deleted": True}
    assert await stored_count() == 0
    again = await owner_api.delete(f"/api/refills/{created['id']}")
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_retrying_a_delete_does_not_delete_the_replacement_refill(owner_api):
    first = (await owner_api.post("/api/refills", json={})).json()["refill"]
    path = f"/api/refills/{first['id']}"
    assert (await owner_api.delete(path)).status_code == 200

    replacement = (await owner_api.post("/api/refills", json={})).json()["refill"]
    assert replacement["id"] != first["id"]
    assert (await owner_api.delete(path)).status_code == 404
    assert await stored_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("refill_id", [0, -1, 2**63])
async def test_delete_refuses_an_id_outside_the_sqlite_rowid_range(owner_api, refill_id):
    refused = await owner_api.delete(f"/api/refills/{refill_id}")
    assert refused.status_code == 422, refused.text


@pytest.mark.asyncio
async def test_a_guest_can_neither_read_nor_write_refills(owner_api):
    created = (await owner_api.post("/api/refills", json={"source": "manual"})).json()["refill"]
    async with guest_client() as guest:
        listed = await guest.get("/api/refills")
        posted = await guest.post("/api/refills", json={"source": "manual"})
        removed = await guest.delete(f"/api/refills/{created['id']}")
    assert listed.status_code == posted.status_code == removed.status_code == 403
    assert await stored_count() == 1


@pytest.mark.asyncio
async def test_a_guest_token_can_neither_read_nor_write_refills(owner_api):
    created = (await owner_api.post("/api/refills", json={"source": "manual"})).json()["refill"]
    headers = {"Authorization": f"Bearer {create_access_token('visitor', 'guest')}"}
    async with guest_client() as guest:
        listed = await guest.get("/api/refills", headers=headers)
        posted = await guest.post("/api/refills", json={"source": "manual"}, headers=headers)
        removed = await guest.delete(f"/api/refills/{created['id']}", headers=headers)
    assert listed.status_code == posted.status_code == removed.status_code == 403
    assert await stored_count() == 1
