"""Calls heard by weekday and hour: the repository's UTC hour counts and the route that folds them."""

from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.main import app
from app.repositories.audio_history_repository import AudioHistoryRepository

pytestmark = pytest.mark.usefixtures("history_pool")

# The latest Monday 08:00 UTC before today, so every row but the oldest stays inside a 14-day window.
_TODAY = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
ANCHOR = (_TODAY - timedelta(days=_TODAY.weekday() or 7)).replace(hour=8)


def _cell(payload: dict, day_of_week: int, hour: int) -> int:
    return next(
        cell["count"] for cell in payload["cells"] if cell["day_of_week"] == day_of_week and cell["hour"] == hour
    )


async def _seed(rows: list[tuple[datetime, str, float, str, int]]) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for stamp, species, confidence, sensor, hidden in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, is_hidden)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    stamp.replace(tzinfo=None).isoformat(sep=" "),
                    species,
                    confidence,
                    sensor,
                    json.dumps({"nm": sensor}),
                    hidden,
                ),
            )
        await db.commit()


ROWS = [
    (ANCHOR + timedelta(minutes=5), "Dunnock", 0.92, "BirdCam", 0),
    (ANCHOR + timedelta(minutes=40), "Dunnock", 0.55, "BirdCam", 0),
    (ANCHOR + timedelta(minutes=50), "Robin", 0.81, "Garden Mic", 0),
    (ANCHOR + timedelta(hours=2), "Robin", 0.9, "Garden Mic", 0),
    (ANCHOR + timedelta(hours=3), "Wren", 0.9, "BirdCam", 1),
    (ANCHOR - timedelta(days=20), "Dunnock", 0.95, "BirdCam", 0),
]


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def owner_without_auth():
    saved = (settings.auth.enabled, settings.public_access.enabled)
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    settings.auth.enabled, settings.public_access.enabled = saved


@pytest.mark.asyncio
async def test_repository_counts_visible_calls_per_utc_quarter_hour_with_the_history_filters():
    await _seed(ROWS)
    async with get_db() as db:
        repo = AudioHistoryRepository(db)
        start, end = ANCHOR - timedelta(days=1), ANCHOR + timedelta(days=1)
        every = await repo.get_audio_activity_utc_quarter_hour_counts(start_date=start, end_date=end)
        dunnock = await repo.get_audio_activity_utc_quarter_hour_counts(start_date=start, end_date=end, species="dunn")
        confident = await repo.get_audio_activity_utc_quarter_hour_counts(
            start_date=start, end_date=end, min_confidence=0.8
        )
        garden = await repo.get_audio_activity_utc_quarter_hour_counts(start_date=start, end_date=end, source="garden")

    naive = ANCHOR.replace(tzinfo=None)
    quarter = timedelta(minutes=15)
    # 08:05 is in the 08:00 quarter, 08:40 in 08:30 and 08:50 in 08:45. The hidden Wren and the call
    # from 20 days ago are not counted.
    assert every == [(naive, 1), (naive + 2 * quarter, 1), (naive + 3 * quarter, 1), (naive + timedelta(hours=2), 1)]
    assert dunnock == [(naive, 1), (naive + 2 * quarter, 1)]
    assert confident == [(naive, 1), (naive + 3 * quarter, 1), (naive + timedelta(hours=2), 1)]
    assert garden == [(naive + 3 * quarter, 1), (naive + timedelta(hours=2), 1)]


@pytest.mark.asyncio
async def test_route_folds_calls_into_the_viewers_weekday_and_hour(client: httpx.AsyncClient):
    await _seed(ROWS)

    response = await client.get("/api/audio/activity-heatmap", params={"days": 14}, headers={"X-Timezone": "UTC"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["cells"]) == 7 * 24
    assert _cell(payload, 1, 8) == 3
    assert _cell(payload, 1, 10) == 1
    assert payload["total_count"] == 4
    assert payload["max_cell_count"] == 3
    assert payload["window_start"].endswith("Z") and payload["window_end"].endswith("Z")


@pytest.mark.asyncio
async def test_route_moves_hours_into_the_requested_time_zone(client: httpx.AsyncClient):
    await _seed(ROWS)

    response = await client.get(
        "/api/audio/activity-heatmap", params={"days": 14}, headers={"X-Timezone": "Asia/Kolkata"}
    )

    payload = response.json()
    # 08:05 UTC is 13:35 in India (UTC+5:30); 08:40 and 08:50 are 14:10 and 14:20. Each call is in
    # the local hour it was heard in, not the one its UTC hour starts in.
    assert _cell(payload, 1, 13) == 1
    assert _cell(payload, 1, 14) == 2
    assert payload["total_count"] == 4


@pytest.mark.asyncio
async def test_route_applies_the_same_filters_as_the_summary(client: httpx.AsyncClient):
    await _seed(ROWS)
    params = {"days": 30, "species": "Dunnock", "source": "BirdCam", "min_confidence": 0.9}

    grid = (await client.get("/api/audio/activity-heatmap", params=params)).json()
    summary = (await client.get("/api/audio/summary", params=params)).json()

    assert grid["total_count"] == summary["total"] == 2


@pytest.mark.asyncio
async def test_route_reads_an_explicit_date_range(client: httpx.AsyncClient):
    await _seed(ROWS)
    params = {
        "start_date": (ANCHOR - timedelta(days=21)).isoformat(),
        "end_date": (ANCHOR - timedelta(days=19)).isoformat(),
    }

    payload = (await client.get("/api/audio/activity-heatmap", params=params)).json()

    assert payload["total_count"] == 1


async def _seed_named(rows: list[tuple[datetime, str, str | None]]) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for stamp, species, scientific_name in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, is_hidden,
                                                 scientific_name)
                   VALUES (?, ?, 0.9, 'BirdCam', '{}', 0, ?)""",
                (stamp.replace(tzinfo=None).isoformat(sep=" "), species, scientific_name),
            )
        await db.commit()


# "Ruff" is a substring of "Ruffed Grouse": the page's search finds both, a species' own grid must not.
NAMED_ROWS = [
    (ANCHOR, "Ruff", "Calidris pugnax"),
    (ANCHOR + timedelta(minutes=10), "Ruff", "Calidris pugnax"),
    (ANCHOR + timedelta(minutes=20), "Kampfläufer", "Calidris pugnax"),
    (ANCHOR + timedelta(hours=1), "Ruffed Grouse", "Bonasa umbellus"),
    (ANCHOR + timedelta(hours=2), "Mystery Warbler", None),
    (ANCHOR + timedelta(hours=2, minutes=5), "Mystery Warbler Two", None),
]


@pytest.mark.asyncio
async def test_scientific_name_limits_the_grid_to_exactly_that_species(client: httpx.AsyncClient):
    await _seed_named(NAMED_ROWS)

    by_name = (await client.get("/api/audio/activity-heatmap", params={"days": 14, "species": "Ruff"})).json()
    exact = (
        await client.get("/api/audio/activity-heatmap", params={"days": 14, "scientific_name": "calidris PUGNAX"})
    ).json()

    assert by_name["total_count"] == 3
    # Every call of the bird, under any common name it was stored with, and nothing else.
    assert exact["total_count"] == 3
    assert _cell(exact, 1, 8) == 3


@pytest.mark.asyncio
async def test_the_summary_names_each_top_species_scientifically_for_the_grid(client: httpx.AsyncClient):
    await _seed_named(NAMED_ROWS)

    summary = (await client.get("/api/audio/summary", params={"days": 14})).json()
    by_name = {row["species"]: row for row in summary["top_species"]}
    grid = (
        await client.get("/api/audio/activity-heatmap", params={"days": 14, "scientific_name": "Bonasa umbellus"})
    ).json()

    assert by_name["Ruffed Grouse"]["scientific_name"] == "Bonasa umbellus"
    assert grid["total_count"] == by_name["Ruffed Grouse"]["count"] == 1
    # A call stored with no scientific name cannot be asked for exactly, so the grid finds none.
    assert by_name["Mystery Warbler"]["scientific_name"] is None
    unnamed = (
        await client.get("/api/audio/activity-heatmap", params={"days": 14, "scientific_name": "Mystery Warbler"})
    ).json()
    assert unnamed["total_count"] == 0


@pytest.mark.asyncio
async def test_scientific_name_narrows_within_the_page_filters(client: httpx.AsyncClient):
    await _seed(ROWS)
    async with get_db() as db:
        await db.execute("UPDATE audio_detections SET scientific_name = 'Prunella modularis' WHERE species = 'Dunnock'")
        await db.commit()

    payload = (
        await client.get(
            "/api/audio/activity-heatmap",
            params={"days": 30, "scientific_name": "Prunella modularis", "min_confidence": 0.9},
        )
    ).json()

    assert payload["total_count"] == 2


@pytest.mark.asyncio
async def test_scientific_name_matches_names_stored_as_birdnet_sent_them(client: httpx.AsyncClient):
    # Ingest keeps BirdNET-Go's ScientificName as sent, so stored names can carry spaces or another case.
    await _seed_named(
        [
            (ANCHOR, "Robin", "Erithacus rubecula"),
            (ANCHOR + timedelta(minutes=5), "Robin", " erithacus RUBECULA "),
        ]
    )

    payload = (
        await client.get("/api/audio/activity-heatmap", params={"days": 14, "scientific_name": "Erithacus rubecula"})
    ).json()

    assert payload["total_count"] == 2


@pytest.mark.asyncio
async def test_route_without_a_header_uses_the_instance_time_zone(client: httpx.AsyncClient, monkeypatch):
    """curl and Home Assistant send no X-Timezone; their hours are the instance's, as their day already is."""
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    await _seed(ROWS)

    payload = (await client.get("/api/audio/activity-heatmap", params={"days": 14})).json()

    assert _cell(payload, 1, 13) == 1
    assert _cell(payload, 1, 14) == 2
    assert _cell(payload, 1, 8) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("one_species", [False, True])
async def test_a_call_just_after_midnight_in_india_is_in_that_days_first_hour(client: httpx.AsyncClient, one_species):
    """00:10 on Wednesday 25 November in India is 18:40 UTC on Tuesday, inside a UTC hour that starts at 23:30
    local on Tuesday. Today's grid, and a species' grid beside it, must put it on Wednesday at 00:00."""
    await _seed_named([(datetime(2026, 11, 24, 18, 40, tzinfo=timezone.utc), "Robin", "Erithacus rubecula")])
    params = {"start_date": "2026-11-24T18:30:00Z", "end_date": "2026-11-25T04:30:00Z"}
    if one_species:
        params["scientific_name"] = "Erithacus rubecula"

    payload = (
        await client.get("/api/audio/activity-heatmap", params=params, headers={"X-Timezone": "Asia/Kolkata"})
    ).json()

    assert _cell(payload, 3, 0) == 1
    assert _cell(payload, 2, 23) == 0
    assert payload["total_count"] == payload["max_cell_count"] == 1
