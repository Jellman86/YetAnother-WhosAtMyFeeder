"""The About page opens on a portrait of this feeder: a few facts it has measured, and its latest visit.

Visits follow the leaderboard's rule, days are the viewer's days, a species seen once is not
announced as an arrival, and a guest is told the facts cover only the shared window.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers.about import busiest_day, newest_arrival
from app.services import visit_film_service as films

CROPS = {"robin_late": "hq_candidate_model_crop", "dunnock_2": "high_quality_bird_crop"}


async def _meta(event_id: str) -> dict | None:
    source = CROPS.get(event_id)
    return {"source": source} if source else None


@pytest_asyncio.fixture
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.execute(
                """
                INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                                        display_name, category_name, is_hidden, manual_tagged)
                VALUES
                -- Two robin visits on the 10th: the 10:05 frame belongs to the 10:00 visit.
                ('robin_1', 'cam1', '2026-09-10 10:00:00', 1, 0.9, 'Robin', 'bird', 0, 0),
                ('robin_2', 'cam1', '2026-09-10 10:05:00', 1, 0.9, 'Robin', 'bird', 0, 0),
                ('robin_3', 'cam1', '2026-09-10 10:30:00', 1, 0.9, 'Robin', 'bird', 0, 0),
                -- 23:30 UTC is the next day an hour east of UTC.
                ('robin_late', 'cam1', '2026-09-11 23:30:00', 1, 0.9, 'Robin', 'bird', 0, 0),
                ('dunnock_1', 'cam1', '2026-09-07 12:00:00', 1, 0.8, 'Dunnock', 'bird', 0, 0),
                ('dunnock_2', 'cam1', '2026-09-11 12:00:00', 1, 0.8, 'Dunnock', 'bird', 0, 0),
                ('dunnock_3', 'cam1', '2026-09-11 12:05:00', 1, 0.8, 'Dunnock', 'bird', 0, 0),
                -- Seen once, first seen last: never announced as the newest arrival.
                ('lion', 'cam1', '2026-09-11 13:00:00', 1, 0.6, 'Mountain Lion', 'bird', 0, 0),
                ('unknown', 'cam1', '2026-09-11 14:00:00', 1, 0.5, 'background', 'bird', 0, 0),
                ('sparrow_hidden', 'cam1', '2026-09-11 15:00:00', 1, 0.7, 'House Sparrow', 'bird', 1, 0)
                """
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.fixture
def media_cache_on(monkeypatch):
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)


def test_the_busiest_day_has_the_most_visits_and_a_tie_goes_to_the_latest():
    assert busiest_day({}) is None
    assert busiest_day({"2026-09-10": 3, "2026-09-11": 3, "2026-09-07": 1}) == ("2026-09-11", 3)


def _species(name, first_seen, detections, confirmed=False):
    return {
        "species": name,
        "common_name": name,
        "scientific_name": None,
        "taxa_id": None,
        "first_seen": datetime.fromisoformat(first_seen),
        "last_seen": datetime.fromisoformat(first_seen),
        "detections": detections,
        "confirmed": confirmed,
    }


def test_the_newest_arrival_is_a_species_seen_often_enough_or_confirmed():
    history = [
        _species("Robin", "2026-09-10", 4),
        _species("Mountain Lion", "2026-09-12", 1),
        _species("background", "2026-09-13", 9),
    ]
    assert newest_arrival(history, ["background"])["species"] == "Robin"
    # A person confirming a single sighting is enough.
    history.append(_species("Goldcrest", "2026-09-14", 1, confirmed=True))
    assert newest_arrival(history, ["background"])["species"] == "Goldcrest"
    assert newest_arrival([], []) is None


@pytest.mark.asyncio
async def test_the_portrait_counts_visits_by_the_viewers_day(seeded_db, media_cache_on, monkeypatch):
    requested = []
    monkeypatch.setattr(
        films.visit_film_service,
        "request",
        AsyncMock(side_effect=lambda event_id: requested.append(event_id) or "pending"),
    )
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/portrait?utc_offset_minutes=60")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scope"] == "all"
    assert body["started_at"].startswith("2026-09-07T12:00:00")
    # Robin 3 (2 on the 10th, 1 on the 12th local), dunnock 2, lion 1, background 1; hidden left out.
    assert body["visits"] == 7
    assert body["detections"] == 9
    assert body["species"] == 3
    # The 11th local: dunnock, lion, background. The robin at 23:30 UTC is on the 12th.
    assert body["busiest_day"] == {"date": "2026-09-11", "visits": 3}
    # The robin arrived on the 10th, after the dunnock; the lion, seen once, is not announced.
    assert body["newest_arrival"]["display_name"] == "Robin"
    assert body["newest_arrival"]["species"] == "Robin"
    latest = body["latest_visit"]
    assert latest["frigate_event"] == "robin_late"
    assert latest["image_url"] == "/api/about/showcase/robin_late.jpg"
    assert latest["film_url"] is None
    assert requested == ["robin_late"]


@pytest.mark.asyncio
async def test_a_made_film_is_offered_with_the_latest_visit(seeded_db, media_cache_on, monkeypatch):
    monkeypatch.setattr(films.visit_film_service, "request", AsyncMock(return_value="ready"))
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/portrait")
    assert res.json()["latest_visit"]["film_url"] == "/api/about/showcase/robin_late.webm"


@pytest.mark.asyncio
async def test_without_a_media_cache_the_portrait_keeps_its_facts_and_drops_the_visit(seeded_db, monkeypatch):
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/about/portrait")
    body = res.json()
    assert body["latest_visit"] is None
    assert body["species"] == 3


@pytest.mark.asyncio
async def test_a_guest_is_told_the_portrait_covers_only_the_shared_window(seeded_db, media_cache_on, monkeypatch):
    monkeypatch.setattr(films.visit_film_service, "request", AsyncMock(return_value="pending"))
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 1)
    # Photographs shared further back than the history: the latest visit still keeps to the history.
    monkeypatch.setattr(settings.public_access, "media_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "media_historical_days", 365)
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/portrait")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scope"] == "shared"
    assert body["shared_days"] == 1
    # Everything seeded is older than the shared window.
    assert body["visits"] == 0 and body["species"] == 0 and body["started_at"] is None
    assert body["latest_visit"] is None and body["newest_arrival"] is None
