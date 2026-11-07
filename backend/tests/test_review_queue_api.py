"""Needs your call must cover every detection waiting in its window, not a recent page (#917).

The Dashboard used to count from its newest 50 detections, so an unknown bird fell out of the
queue as soon as 50 others had arrived, and the panel could say nothing was waiting.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.detection_repository import unresolved_species_sql
from app.utils.api_datetime import serialize_storage_datetime, utc_naive_now
from app.utils.canonical_species import UNKNOWN_BIRD_DISPLAY_LABEL, user_facing_species_label

THRESHOLD = 0.6


@pytest_asyncio.fixture(autouse=True)
async def clean_detections(monkeypatch):
    monkeypatch.setattr(settings.classification, "threshold", THRESHOLD)
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        yield
    finally:
        await close_db()


async def seed(
    event: str,
    *,
    name: str = "European Robin",
    category: str | None = None,
    score: float = 0.9,
    age_hours: float = 1,
    hidden: int = 0,
    manual: int = 0,
    scientific: str | None = "Erithacus rubecula",
) -> None:
    at = serialize_storage_datetime(utc_naive_now() - timedelta(hours=age_hours))
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                                    display_name, category_name, scientific_name, is_hidden, manual_tagged)
            VALUES (?, 'cam', ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (event, at, score, name, category if category is not None else name, scientific, hidden, manual),
        )
        await db.commit()


async def seed_established_species() -> None:
    """Enough history that a regular is not also a new-species candidate."""
    for index in range(5):
        await seed(f"history-{index}", age_hours=24 * 20 + index)


async def read_queue(query: str = "") -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/events/review-queue{query}")
    assert response.status_code == 200, response.text
    return response.json()


def events(data: dict) -> list[str]:
    return [item["event"]["frigate_event"] for item in data["items"]]


@pytest.mark.asyncio
async def test_unknown_birds_stay_in_the_queue_however_many_visits_arrive_after_them():
    await seed_established_species()
    for index in range(24):
        await seed(f"unknown-{index}", name="Unknown Bird", age_hours=20 - index / 10, scientific=None)
    for index in range(60):
        await seed(f"named-{index}", age_hours=2 - index / 100)

    data = await read_queue("?limit=500")

    assert data["total"] == 24
    assert len(data["items"]) == 24
    assert {item["reason"] for item in data["items"]} == {"unknown_species"}


@pytest.mark.asyncio
async def test_total_stays_true_when_the_list_is_limited_and_oldest_comes_first():
    await seed_established_species()
    for index in range(9):
        await seed(f"unknown-{index}", name="Unknown Bird", age_hours=9 - index, scientific=None)

    data = await read_queue("?limit=4")

    assert data["total"] == 9
    assert events(data) == ["unknown-0", "unknown-1", "unknown-2", "unknown-3"]


@pytest.mark.asyncio
async def test_only_detections_inside_the_window_are_waiting():
    await seed_established_species()
    await seed("inside", name="Unknown Bird", age_hours=23, scientific=None)
    await seed("outside", name="Unknown Bird", age_hours=25, scientific=None)

    data = await read_queue()

    assert events(data) == ["inside"]
    assert data["window_start"] < data["window_end"]


@pytest.mark.asyncio
async def test_a_score_on_the_threshold_is_named_and_one_below_it_waits():
    await seed_established_species()
    await seed("on-threshold", score=THRESHOLD)
    await seed("below-threshold", score=THRESHOLD - 0.01)

    data = await read_queue()

    assert events(data) == ["below-threshold"]
    assert {item["reason"] for item in data["items"]} == {"low_score"}


@pytest.mark.asyncio
async def test_hidden_and_owner_decided_detections_ask_for_nothing():
    await seed_established_species()
    await seed("hidden", name="Unknown Bird", hidden=1, scientific=None)
    await seed("owner-unknown", name="Unknown Bird", manual=1, scientific=None)
    await seed("owner-low", score=0.1, manual=1)

    data = await read_queue()

    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.parametrize(
    "name, category",
    [
        ("Unknown Bird", "Unknown Bird"),
        ("unknown bird", "unknown bird"),
        ("  Unknown Bird  ", "Unknown Bird"),
        ("background", "background"),
        ("Unidentified", "Unidentified"),
        ("Thrushes and allies", "Thrushes and allies"),
        ("Life", "Life"),
        ("", "background"),
        ("European Robin", "background"),
    ],
)
@pytest.mark.asyncio
async def test_every_label_shown_as_unknown_is_queued_as_unknown(name, category):
    assert user_facing_species_label(name, raw_label=category) == UNKNOWN_BIRD_DISPLAY_LABEL
    await seed_established_species()
    await seed("presented-unknown", name=name, category=category)

    data = await read_queue()

    assert events(data) == ["presented-unknown"]
    assert data["items"][0]["reason"] == "unknown_species"
    assert data["items"][0]["event"]["display_name"] == UNKNOWN_BIRD_DISPLAY_LABEL


@pytest.mark.asyncio
async def test_a_named_species_is_not_mistaken_for_an_unknown_one():
    assert user_facing_species_label("European Robin", raw_label="European Robin") != UNKNOWN_BIRD_DISPLAY_LABEL
    clause, params = unresolved_species_sql("d")
    async with get_db() as db:
        await seed("named", name="European Robin")
        async with db.execute(f"SELECT COUNT(*) FROM detections d WHERE {clause}", params) as cursor:
            assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_a_new_species_older_than_the_window_is_counted_once_and_says_why():
    await seed_established_species()
    await seed("newcomer", name="Hadeda Ibis", age_hours=72, scientific="Bostrychia hagedash", score=0.9)
    await seed("waiting", name="Unknown Bird", age_hours=2, scientific=None)

    data = await read_queue()

    assert data["total"] == 2
    assert events(data) == ["newcomer", "waiting"]
    newcomer = data["items"][0]
    assert newcomer["reason"] == "new_species"
    assert newcomer["species_sightings"] == 1


@pytest.mark.asyncio
async def test_a_detection_qualifying_both_ways_counts_once_with_the_sharper_reason():
    await seed_established_species()
    await seed("both", name="Hadeda Ibis", age_hours=2, scientific="Bostrychia hagedash", score=0.2)

    data = await read_queue()

    assert data["total"] == 1
    assert events(data) == ["both"]
    assert data["items"][0]["reason"] == "new_species"


@pytest.mark.asyncio
async def test_a_limit_reaches_newcomers_and_waiting_detections_in_one_oldest_first_order():
    await seed_established_species()
    await seed("waiting-old", name="Unknown Bird", age_hours=20, scientific=None)
    await seed("newcomer", name="Hadeda Ibis", age_hours=72, scientific="Bostrychia hagedash")
    await seed("waiting-new", name="Unknown Bird", age_hours=1, scientific=None)

    data = await read_queue("?limit=2")

    assert data["total"] == 3
    assert events(data) == ["newcomer", "waiting-old"]


@pytest.mark.asyncio
async def test_guests_cannot_read_the_queue(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "password_hash", "not-a-real-hash")
    monkeypatch.setattr(settings.public_access, "enabled", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/events/review-queue")
    assert response.status_code in {401, 403}
