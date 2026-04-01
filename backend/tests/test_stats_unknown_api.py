from datetime import datetime, timezone
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers import stats as stats_router


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


async def _insert_detection_at_timestamp(event_id: str, detection_time: str) -> None:
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
                detection_time,
                1,
                0.93,
                "Common Wood-Pigeon",
                "Columba palumbus",
                event_id,
                "test-camera",
                "Columba palumbus",
                "Common Wood-Pigeon",
                3048,
            ),
        )
        await db.commit()


async def _insert_canonical_detection_with_taxonomy(
    event_id: str,
    *,
    taxa_id: int,
    scientific_name: str,
    common_name: str,
) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id)
            VALUES (?, ?, ?)
            """,
            (scientific_name, common_name, taxa_id),
        )
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
                0.91,
                common_name,
                common_name,
                event_id,
                "test-camera",
                scientific_name,
                common_name,
                taxa_id,
            ),
        )
        await db.commit()


async def _delete_taxonomy_cache_entry(taxa_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
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
        assert latest["detection_time"].endswith("Z")
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
async def test_daily_summary_serializes_naive_detection_time_as_explicit_utc(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"stats-time-{uuid.uuid4().hex[:8]}"
    today = datetime.now(timezone.utc).date()
    naive_today_timestamp = f"{today.isoformat()} 10:23:25.446665"
    await _insert_detection_at_timestamp(event_id, naive_today_timestamp)

    try:
        response = await client.get("/api/stats/daily-summary")
        assert response.status_code == 200, response.text
        payload = response.json()

        latest = payload["latest_detection"]
        assert latest["frigate_event"] == event_id
        assert latest["detection_time"] == f"{today.isoformat()}T10:23:25.446665Z"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_daily_summary_uses_utc_naive_window_for_latest_detection(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    utc_window_end = datetime(2026, 4, 1, 20, 0, 0)
    local_window_end = datetime(2026, 4, 1, 15, 0, 0)

    class _FakeLocalDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return local_window_end.replace(tzinfo=tz)
            return cls(
                local_window_end.year,
                local_window_end.month,
                local_window_end.day,
                local_window_end.hour,
                local_window_end.minute,
                local_window_end.second,
            )

    monkeypatch.setattr(stats_router, "datetime", _FakeLocalDateTime)
    monkeypatch.setattr(stats_router, "utc_naive_now", lambda: utc_window_end, raising=False)

    early_event_id = f"stats-window-early-{uuid.uuid4().hex[:8]}"
    late_event_id = f"stats-window-late-{uuid.uuid4().hex[:8]}"
    await _insert_detection_at_timestamp(early_event_id, "2026-04-01 14:30:00")
    await _insert_detection_at_timestamp(late_event_id, "2026-04-01 19:30:00")

    try:
        response = await client.get("/api/stats/daily-summary")
        assert response.status_code == 200, response.text
        payload = response.json()

        latest = payload["latest_detection"]
        assert latest["frigate_event"] == late_event_id
        assert payload["total_count"] >= 2
    finally:
        await _delete_detection(early_event_id)
        await _delete_detection(late_event_id)


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


@pytest.mark.asyncio
async def test_timeline_compare_canonical_species_with_taxonomy_cache_joins_cleanly(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_id = f"stats-compare-canonical-{uuid.uuid4().hex[:8]}"
    taxa_id = 880000 + int(uuid.uuid4().hex[:4], 16)
    scientific_name = f"Testus canonicalis {uuid.uuid4().hex[:4]}"
    common_name = f"Canonical Bird {uuid.uuid4().hex[:4]}"
    await _insert_canonical_detection_with_taxonomy(
        event_id,
        taxa_id=taxa_id,
        scientific_name=scientific_name,
        common_name=common_name,
    )

    try:
        response = await client.get(
            "/api/stats/detections/timeline",
            params={"span": "month", "compare_species": [scientific_name]},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["compare_series"] is not None
        assert len(payload["compare_series"]) == 1
        series = payload["compare_series"][0]
        assert series["species"] == scientific_name
        assert sum(point["count"] for point in series["points"]) >= 1
    finally:
        await _delete_detection(event_id)
        await _delete_taxonomy_cache_entry(taxa_id)
