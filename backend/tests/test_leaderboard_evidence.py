from datetime import datetime, timedelta, timezone
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.services.leaderboard_window import previous_window_is_complete


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def open_access():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


async def _insert_detection(
    event_id: str,
    display_name: str,
    detection_time: datetime,
    *,
    manual_tagged: bool = False,
    audio_confirmed: bool = False,
) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged, audio_confirmed
            ) VALUES (?, 1, 0.8, ?, ?, ?, 'test-camera', 0, ?, ?)
            """,
            (
                detection_time.replace(tzinfo=None).isoformat(sep=" "),
                display_name,
                display_name,
                event_id,
                1 if manual_tagged else 0,
                1 if audio_confirmed else 0,
            ),
        )
        await db.commit()


async def _delete_events(prefix: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE ?", (f"{prefix}%",))
        await db.commit()


def test_previous_window_is_incomplete_when_history_starts_inside_it():
    prev_start = datetime(2026, 7, 29)
    assert previous_window_is_complete(history_start=datetime(2026, 8, 27), prev_start=prev_start) is False


def test_previous_window_is_complete_when_history_reaches_back_past_it():
    prev_start = datetime(2026, 7, 29)
    assert previous_window_is_complete(history_start=datetime(2026, 7, 1), prev_start=prev_start) is True
    assert previous_window_is_complete(history_start=prev_start, prev_start=prev_start) is True


def test_previous_window_is_incomplete_without_any_history():
    assert previous_window_is_complete(history_start=None, prev_start=datetime(2026, 7, 29)) is False


@pytest.mark.asyncio
async def test_leaderboard_species_counts_confirmed_and_call_matched_detections(client: httpx.AsyncClient):
    prefix = f"lb-evidence-{uuid.uuid4().hex[:8]}"
    species = f"Evidence Finch {prefix}"
    now = datetime.now(timezone.utc)
    await _insert_detection(f"{prefix}-1", species, now - timedelta(hours=2), manual_tagged=True)
    await _insert_detection(f"{prefix}-2", species, now - timedelta(hours=3), audio_confirmed=True)
    await _insert_detection(f"{prefix}-3", species, now - timedelta(hours=4))
    # Outside the window: must not count as evidence for this month.
    await _insert_detection(f"{prefix}-4", species, now - timedelta(days=45), manual_tagged=True)

    try:
        response = await client.get("/api/leaderboard/species?span=month")
        assert response.status_code == 200, response.text
        rows = [row for row in response.json()["species"] if row["species"] == species]
        assert len(rows) == 1
        assert rows[0]["window_count"] == 3
        assert rows[0]["window_prev_count"] == 1
        assert rows[0]["window_confirmed_count"] == 1
        assert rows[0]["window_audio_confirmed_count"] == 1
    finally:
        await _delete_events(prefix)


@pytest.mark.asyncio
async def test_leaderboard_species_reports_whether_the_previous_window_was_recorded(client: httpx.AsyncClient):
    prefix = f"lb-history-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    await _insert_detection(f"{prefix}-old", f"Old Bird {prefix}", now - timedelta(days=70))
    await _insert_detection(f"{prefix}-new", f"New Bird {prefix}", now - timedelta(hours=1))

    try:
        response = await client.get("/api/leaderboard/species?span=month")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["history_start"] is not None
        assert payload["history_start"].endswith("Z")
        assert payload["previous_window_complete"] is True
    finally:
        await _delete_events(prefix)


@pytest.mark.asyncio
async def test_leaderboard_unknown_bird_counts_its_previous_window(client: httpx.AsyncClient):
    prefix = f"lb-unknown-prev-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    await _insert_detection(f"{prefix}-now", "Unknown Bird", now - timedelta(hours=1))
    await _insert_detection(f"{prefix}-prev", "Unknown Bird", now - timedelta(days=40))

    try:
        response = await client.get("/api/leaderboard/species?span=month")
        assert response.status_code == 200, response.text
        rows = [row for row in response.json()["species"] if row["species"] == "Unknown Bird"]
        assert len(rows) == 1
        assert rows[0]["window_prev_count"] >= 1
    finally:
        await _delete_events(prefix)
