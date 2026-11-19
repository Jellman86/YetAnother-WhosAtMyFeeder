"""The visit gap is the owner's setting (#1044).

On a busy feeder Great Tits arrive every one to ten seconds, and a fixed 60-second gap merged
more than a hundred arrivals into one visit. The gap is one integer in seconds, read when a query
runs so a save takes effect without a restart, and every grouping follows it: bird visits, the
statistics built on them, Garden animal visits and the guest's view.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.config_models import VisitSettings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models.public_settings import build_public_settings
from app.repositories.garden_repository import GardenRepository
from app.repositories.visit_repository import VisitRepository

START = datetime(2034, 2, 6, 9, 0, 0)
# A Great Tit returning every eight seconds, then a 25-second pause, then two more.
BUSY_FEEDER_SECONDS = [0, 8, 16, 41, 49]


def test_the_gap_defaults_to_one_minute():
    """Nobody's visit counts change because they upgraded."""
    assert VisitSettings().gap_seconds == 60


@pytest.mark.parametrize("value", [5, 60, 300])
def test_the_gap_accepts_five_seconds_to_five_minutes(value):
    assert VisitSettings(gap_seconds=value).gap_seconds == value


@pytest.mark.parametrize("value", [0, 4, 301, -60])
def test_the_gap_refuses_values_outside_five_seconds_to_five_minutes(value):
    with pytest.raises(ValueError):
        VisitSettings(gap_seconds=value)


@pytest.fixture
def gap():
    original = settings.visits.gap_seconds
    yield lambda seconds: setattr(settings.visits, "gap_seconds", seconds)
    settings.visits.gap_seconds = original


def test_the_public_settings_carry_the_gap_so_a_guest_groups_like_the_owner(gap):
    gap(20)
    assert build_public_settings().visit_gap_seconds == 20


@pytest_asyncio.fixture
async def repo():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'gap-test-%'")
        await db.commit()
        yield VisitRepository(db)
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'gap-test-%'")
        await db.commit()
    await close_db()


async def busy_feeder(repo):
    for number, seconds in enumerate(BUSY_FEEDER_SECONDS):
        await repo.db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name,
            category_name, frigate_event, camera_name, scientific_name, is_hidden)
            VALUES (?, 0, 0.9, 'Parus major', 'Parus major', ?, 'feeder', 'Parus major', 0)""",
            ((START + timedelta(seconds=seconds)).isoformat(sep=" "), f"gap-test-{number}"),
        )
    await repo.db.commit()


@pytest.mark.asyncio
async def test_a_shorter_gap_splits_a_busy_feeder_into_more_visits(repo, gap):
    await busy_feeder(repo)
    window = {"start": START, "end": START + timedelta(minutes=5)}

    gap(60)
    visits, total = await repo.list_visits(**window)
    assert total == 1
    assert visits[0]["capture_count"] == 5

    gap(10)
    visits, total = await repo.list_visits(**window)
    assert total == 2
    assert sorted(visit["capture_count"] for visit in visits) == [2, 3]


@pytest.mark.asyncio
async def test_a_capture_exactly_one_gap_after_the_last_stays_in_the_visit(repo, gap):
    await busy_feeder(repo)
    gap(8)
    _, total = await repo.list_visits(start=START, end=START + timedelta(minutes=5))
    # 0, 8, 16 are one gap apart each; 41 and 49 likewise; the 25-second pause splits them.
    assert total == 2


@pytest.mark.asyncio
async def test_species_statistics_follow_the_gap(repo, gap):
    await busy_feeder(repo)
    await repo.db.execute("UPDATE detections SET species_id = 4242 WHERE frigate_event LIKE 'gap-test-%'")
    await repo.db.commit()
    window = {"start": START, "end": START + timedelta(minutes=5)}

    gap(60)
    assert (await repo.species_visit_spans(**window))[4242][0] == 1
    gap(10)
    assert (await repo.species_visit_spans(**window))[4242][0] == 2


@pytest.mark.asyncio
async def test_the_visits_api_reports_the_gap_it_grouped_with(repo, gap, monkeypatch):
    from unittest.mock import AsyncMock

    from app.routers import events

    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    await busy_feeder(repo)
    gap(10)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/visits?start_date=2034-02-06&end_date=2034-02-06")
    assert response.status_code == 200, response.text
    assert response.json()["gap_seconds"] == 10
    assert response.json()["total"] == 2


@pytest_asyncio.fixture
async def garden(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
        yield GardenRepository(db)
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    await close_db()


@pytest.mark.asyncio
async def test_garden_animal_visits_follow_the_same_gap(garden, gap):
    for number, seconds in enumerate(BUSY_FEEDER_SECONDS):
        at = (datetime(2034, 2, 6, tzinfo=timezone.utc) + timedelta(seconds=seconds)).replace(tzinfo=None)
        await garden.capture(f"gap-garden-{number}", "patio", "cat", at.isoformat(), True)
    await garden.db.execute("UPDATE garden_captures SET status='confirmed'")
    await garden.db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        gap(60)
        assert (await client.get("/api/garden/visits")).json()["total"] == 1
        gap(10)
        assert (await client.get("/api/garden/visits")).json()["total"] == 2


@pytest.mark.asyncio
async def test_the_gap_round_trips_through_the_settings_api(gap, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    gap(60)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/settings")).json()["visit_gap_seconds"] == 60
        written = await client.post("/api/settings", json={"visit_gap_seconds": 15})
        assert written.status_code == 200, written.text
        assert settings.visits.gap_seconds == 15
        assert (await client.get("/api/settings")).json()["visit_gap_seconds"] == 15
        assert (await client.get("/api/settings/public")).json()["visit_gap_seconds"] == 15


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [4, 301, 0])
async def test_an_out_of_range_gap_is_refused_and_leaves_the_setting_alone(gap, monkeypatch, value):
    monkeypatch.setattr(settings.auth, "enabled", False)
    gap(60)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/settings", json={"visit_gap_seconds": value})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "visit_gap_seconds"]
    assert settings.visits.gap_seconds == 60
