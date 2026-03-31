from datetime import datetime, timezone
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app


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
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


async def _insert_hidden_group_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.81,
                "Great tit and allies",
                "Great tit and allies",
                event_id,
                "test-camera",
                "Great tit and allies",
                "Great tit and allies",
                None,
            ),
        )
        await db.commit()


async def _delete_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


@pytest.mark.asyncio
async def test_daily_summary_aggregates_hidden_noncanonical_labels_as_unknown_bird(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"stats-unknown-{uuid.uuid4().hex[:8]}"
    await _insert_hidden_group_detection(event_id)

    try:
        response = await client.get("/api/stats/daily-summary")
        assert response.status_code == 200, response.text
        payload = response.json()

        latest = payload["latest_detection"]
        assert latest["frigate_event"] == event_id
        assert latest["display_name"] == "Unknown Bird"
        assert latest["category_name"] == "Unknown Bird"
        assert latest["scientific_name"] is None
        assert latest["common_name"] is None
        assert latest["taxa_id"] is None

        species = payload["top_species"]
        unknown_rows = [row for row in species if row["species"] == "Unknown Bird"]
        assert len(unknown_rows) == 1
        assert unknown_rows[0]["count"] == 1
        assert unknown_rows[0]["latest_event"] == event_id
        assert not any(row["species"] == "Great tit and allies" for row in species)
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_timeline_compare_unknown_bird_includes_hidden_noncanonical_labels(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"stats-compare-{uuid.uuid4().hex[:8]}"
    await _insert_hidden_group_detection(event_id)

    try:
        response = await client.get(
            "/api/stats/detections/timeline",
            params={"span": "week", "compare_species": ["Unknown Bird"]},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["compare_series"] is not None
        assert len(payload["compare_series"]) == 1
        series = payload["compare_series"][0]
        assert series["species"] == "Unknown Bird"
        assert sum(point["count"] for point in series["points"]) == 1
    finally:
        await _delete_detection(event_id)
