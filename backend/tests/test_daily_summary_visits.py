from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository

# A window no other test writes into, so the counts are this file's own.
START = datetime(2031, 5, 4, 6, 0, 0)
END = START + timedelta(hours=24)


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


async def _insert(event: str, minutes: float, species: str, camera: str, hidden: bool = False) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged, scientific_name, common_name
            ) VALUES (?, 1, 0.9, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                (START + timedelta(minutes=minutes)).isoformat(sep=" "),
                species,
                species,
                event,
                camera,
                1 if hidden else 0,
                species,
                species,
            ),
        )
        await db.commit()


@pytest_asyncio.fixture
async def seeded():
    rows = [
        # Dunnock on birdcam: 0, 24, 54 seconds is one visit, 40 min a second.
        ("dv-1", 0, "Prunella modularis", "birdcam"),
        ("dv-2", 0.4, "Prunella modularis", "birdcam"),
        ("dv-3", 0.9, "Prunella modularis", "birdcam"),
        ("dv-4", 40, "Prunella modularis", "birdcam"),
        # The same species on another camera at the same time is its own visit.
        ("dv-5", 0.5, "Prunella modularis", "patiocam"),
        # A robin between Dunnock frames does not split the Dunnock visit.
        ("dv-6", 0.6, "Erithacus rubecula", "birdcam"),
        # Hidden frames count for nothing.
        ("dv-7", 100, "Erithacus rubecula", "birdcam", True),
    ]
    for row in rows:
        await _insert(*row)
    yield
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'dv-%'")
        await db.commit()


@pytest.mark.asyncio
async def test_species_counts_carry_visits_by_the_leaderboard_rule(seeded):
    async with get_db() as db:
        rows = await DetectionRepository(db).get_daily_species_counts(START, END)
    by_name = {row["scientific_name"]: row for row in rows}
    assert by_name["Prunella modularis"]["count"] == 5
    # birdcam 0-54 seconds, birdcam 40 min, patiocam 30 seconds.
    assert by_name["Prunella modularis"]["visit_count"] == 3
    assert by_name["Erithacus rubecula"]["count"] == 1
    assert by_name["Erithacus rubecula"]["visit_count"] == 1


@pytest.mark.asyncio
async def test_visit_openings_name_each_visit_once_with_its_camera(seeded):
    async with get_db() as db:
        repo = DetectionRepository(db)
        openings = await repo.get_window_visit_openings(START, END)
        last_seen = await repo.get_camera_last_seen(START, END)
    assert [(item["camera"], int((item["opened_at"] - START).total_seconds())) for item in openings] == [
        ("birdcam", 0),
        ("patiocam", 30),
        ("birdcam", 36),
        ("birdcam", 2400),
    ]
    # The hidden frame at 100 min is not the camera's last sighting.
    assert last_seen["birdcam"] == START + timedelta(minutes=40)
    assert last_seen["patiocam"] == START + timedelta(seconds=30)


@pytest.mark.asyncio
async def test_a_visit_running_when_the_window_opens_counts_once_inside_it(seeded):
    # The window opens at 24 seconds: the visit counts from its first capture inside it.
    async with get_db() as db:
        openings = await DetectionRepository(db).get_window_visit_openings(START + timedelta(seconds=24), END)
    assert [int((item["opened_at"] - START).total_seconds()) for item in openings] == [24, 30, 36, 2400]


@pytest.mark.asyncio
async def test_daily_summary_reports_visits_beside_frames():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/stats/daily-summary")
    assert response.status_code == 200
    body = response.json()
    assert len(body["hourly_visits"]) == 24
    assert body["visit_count"] == sum(body["hourly_visits"])
    # A visit is at least one frame.
    assert body["visit_count"] <= body["total_count"]
    for species in body["top_species"]:
        assert species["visit_count"] <= species["count"]
    if body["camera_visits"] is not None:
        assert sum(camera["visits"] for camera in body["camera_visits"]) <= body["visit_count"]


@pytest.mark.asyncio
async def test_visit_across_midnight_counts_only_on_its_opening_day(seeded):
    async with get_db() as db:
        for event, at in [("midnight-first", "2034-10-02 23:59:45"), ("midnight-next", "2034-10-03 00:00:15")]:
            await db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index,
                   score, display_name, category_name, scientific_name) VALUES (?, 'midnight', ?, 0,
                   0.9, 'Turdus merula', 'Turdus merula', 'Turdus merula')""",
                (event, at),
            )
        await db.commit()
        counts = await DetectionRepository(db).get_daily_visit_counts(
            start_date=datetime(2034, 10, 2), end_date=datetime(2034, 10, 4)
        )
        assert counts == {"2034-10-02": 1}
