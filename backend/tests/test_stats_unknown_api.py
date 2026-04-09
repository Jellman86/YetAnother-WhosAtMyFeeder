from datetime import datetime, timedelta, timezone
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


async def _insert_species_bucket_detection(
    event_id: str,
    *,
    detection_time: str,
    taxa_id: int,
    scientific_name: str,
    common_name: str,
    display_name: str,
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
                detection_time,
                1,
                0.88,
                display_name,
                display_name,
                event_id,
                "test-camera",
                scientific_name,
                common_name,
                taxa_id,
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
    sample_dt = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=446665)
    naive_today_timestamp = sample_dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    await _insert_detection_at_timestamp(event_id, naive_today_timestamp)

    try:
        response = await client.get("/api/stats/daily-summary")
        assert response.status_code == 200, response.text
        payload = response.json()

        latest = payload["latest_detection"]
        assert latest["frigate_event"] == event_id
        assert latest["detection_time"] == sample_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
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
async def test_daily_summary_uses_latest_detection_time_for_species_latest_event(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    utc_window_end = datetime(2026, 4, 2, 10, 0, 0)
    monkeypatch.setattr(stats_router, "utc_naive_now", lambda: utc_window_end, raising=False)

    older_event_id = "evt-zulu-older"
    newer_event_id = "evt-alpha-newer"
    taxa_id = 8123

    await _insert_species_bucket_detection(
        older_event_id,
        detection_time="2026-04-02 08:00:00",
        taxa_id=taxa_id,
        scientific_name="Cardinalis cardinalis",
        common_name="Northern Cardinal",
        display_name="Northern Cardinal",
    )
    await _insert_species_bucket_detection(
        newer_event_id,
        detection_time="2026-04-02 09:00:00",
        taxa_id=taxa_id,
        scientific_name="Cardinalis cardinalis",
        common_name="Northern Cardinal",
        display_name="Red Cardinal",
    )

    try:
        response = await client.get("/api/stats/daily-summary")
        assert response.status_code == 200, response.text
        payload = response.json()

        cardinal_rows = [row for row in payload["top_species"] if row["taxa_id"] == taxa_id]
        assert len(cardinal_rows) == 1
        assert cardinal_rows[0]["latest_event"] == newer_event_id
    finally:
        await _delete_detection(older_event_id)
        await _delete_detection(newer_event_id)
        await _delete_taxonomy_cache_entry(taxa_id)


@pytest.mark.asyncio
async def test_daily_summary_unknown_rollup_uses_latest_detection_time_for_latest_event(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    utc_window_end = datetime(2026, 4, 2, 10, 0, 0)
    monkeypatch.setattr(stats_router, "utc_naive_now", lambda: utc_window_end, raising=False)

    older_event_id = "evt-zulu-hidden"
    newer_event_id = "evt-alpha-hidden"

    await _insert_detection_at_timestamp(older_event_id, "2026-04-02 08:00:00")
    async with get_db() as db:
        await db.execute(
            "UPDATE detections SET display_name = ?, category_name = ?, scientific_name = ?, common_name = ?, taxa_id = NULL WHERE frigate_event = ?",
            ("Great tit and allies", "Great tit and allies", "Great tit and allies", "Great tit and allies", older_event_id),
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
                "2026-04-02 09:00:00",
                1,
                0.75,
                "Background",
                "Background",
                newer_event_id,
                "test-camera",
                "Background",
                "Background",
                None,
            ),
        )
        await db.commit()

    try:
        response = await client.get("/api/stats/daily-summary")
        assert response.status_code == 200, response.text
        payload = response.json()

        unknown_rows = [row for row in payload["top_species"] if row["species"] == "Unknown Bird"]
        assert len(unknown_rows) == 1
        assert unknown_rows[0]["latest_event"] == newer_event_id
    finally:
        await _delete_detection(older_event_id)
        await _delete_detection(newer_event_id)


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


def _heatmap_cell(payload: dict, *, day_of_week: int, hour: int) -> int:
    for cell in payload["cells"]:
        if cell["day_of_week"] == day_of_week and cell["hour"] == hour:
            return cell["count"]
    raise AssertionError(f"Missing heatmap cell {day_of_week=}, {hour=}")


def _timeline_point(payload: dict, bucket_start: str) -> dict:
    for point in payload["points"]:
        if point["bucket_start"] == bucket_start:
            return point
    raise AssertionError(f"Missing timeline point {bucket_start=}")


@pytest.mark.asyncio
async def test_activity_heatmap_uses_request_timezone_for_hour_and_weekday_buckets(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    utc_window_end = datetime(2026, 4, 10, 18, 0, 0)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return utc_window_end.replace(tzinfo=tz)
            return cls(
                utc_window_end.year,
                utc_window_end.month,
                utc_window_end.day,
                utc_window_end.hour,
                utc_window_end.minute,
                utc_window_end.second,
            )

    monkeypatch.setattr(stats_router, "datetime", _FakeDateTime)

    previous_local_day_event_id = f"stats-heatmap-prev-{uuid.uuid4().hex[:8]}"
    same_local_day_event_id = f"stats-heatmap-same-{uuid.uuid4().hex[:8]}"
    await _insert_detection_at_timestamp(previous_local_day_event_id, "2026-04-10 02:15:00")
    await _insert_detection_at_timestamp(same_local_day_event_id, "2026-04-10 13:30:00")

    try:
        response = await client.get(
            "/api/stats/detections/activity-heatmap",
            params={"span": "week"},
            headers={"X-Timezone": "America/New_York"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()

        # 2026-04-10 02:15 UTC -> 2026-04-09 22:15 America/New_York (Thursday)
        assert _heatmap_cell(payload, day_of_week=4, hour=22) == 1
        # 2026-04-10 13:30 UTC -> 2026-04-10 09:30 America/New_York (Friday)
        assert _heatmap_cell(payload, day_of_week=5, hour=9) == 1
        # The raw UTC buckets should not be used when a browser timezone is provided.
        assert _heatmap_cell(payload, day_of_week=5, hour=2) == 0
        assert _heatmap_cell(payload, day_of_week=5, hour=13) == 0
    finally:
        await _delete_detection(previous_local_day_event_id)
        await _delete_detection(same_local_day_event_id)


@pytest.mark.asyncio
async def test_daily_summary_uses_request_timezone_for_hourly_distribution(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    utc_window_end = datetime(2026, 4, 10, 18, 0, 0)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return utc_window_end.replace(tzinfo=tz)
            return cls(
                utc_window_end.year,
                utc_window_end.month,
                utc_window_end.day,
                utc_window_end.hour,
                utc_window_end.minute,
                utc_window_end.second,
            )

    monkeypatch.setattr(stats_router, "datetime", _FakeDateTime)
    monkeypatch.setattr(stats_router, "utc_naive_now", lambda: utc_window_end, raising=False)

    previous_local_day_event_id = f"stats-daily-summary-prev-{uuid.uuid4().hex[:8]}"
    await _insert_detection_at_timestamp(previous_local_day_event_id, "2026-04-10 02:15:00")

    try:
        response = await client.get(
            "/api/stats/daily-summary",
            headers={"X-Timezone": "America/New_York"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["hourly_distribution"][22] >= 1
        assert payload["hourly_distribution"][2] == 0
    finally:
        await _delete_detection(previous_local_day_event_id)


@pytest.mark.asyncio
async def test_timeline_uses_request_timezone_for_daily_points_and_compare_series(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    utc_window_end = datetime(2026, 4, 10, 18, 0, 0)

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return utc_window_end.replace(tzinfo=tz)
            return cls(
                utc_window_end.year,
                utc_window_end.month,
                utc_window_end.day,
                utc_window_end.hour,
                utc_window_end.minute,
                utc_window_end.second,
            )

    monkeypatch.setattr(stats_router, "datetime", _FakeDateTime)

    event_id = f"stats-timeline-local-{uuid.uuid4().hex[:8]}"
    await _insert_detection_at_timestamp(event_id, "2026-04-10 02:15:00")

    try:
        response = await client.get(
            "/api/stats/detections/timeline",
            params={"span": "week", "compare_species": ["Common Wood-Pigeon"]},
            headers={"X-Timezone": "America/New_York"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()

        local_bucket = _timeline_point(payload, "2026-04-09T04:00:00Z")
        assert local_bucket["count"] >= 1

        utc_bucket = _timeline_point(payload, "2026-04-10T04:00:00Z")
        assert utc_bucket["count"] == 0

        series = payload["compare_series"][0]
        series_points = {point["bucket_start"]: point["count"] for point in series["points"]}
        assert series_points["2026-04-09T04:00:00Z"] >= 1
        assert series_points["2026-04-10T04:00:00Z"] == 0
    finally:
        await _delete_detection(event_id)
