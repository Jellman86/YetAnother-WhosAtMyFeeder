"""The leaderboard's Today: local midnight to now on every source, compared with yesterday so far (#1097)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.main import app
from app.routers import audio as audio_router
from app.routers import species as species_router
from app.routers import stats as stats_router
from app.routers.species import clear_portraits_cache
from app.services import media_cache as media_cache_module
from app.utils import public_access

pytestmark = pytest.mark.usefixtures("history_pool")

# 23:45 UTC on 10 March 2034 is 00:45 on 11 March in Berlin, so Berlin's today began at 23:00 UTC.
BERLIN_EVENING = datetime(2034, 3, 10, 23, 45)
BERLIN = {"X-Timezone": "Europe/Berlin"}
ROBIN = "Erithacus rubecula"
TIT = "Parus major"
# Seen and heard at the same instants, so every source must agree on what Today holds.
ROWS = {
    "lbt-old": ("2034-03-01 12:00:00", TIT),  # history reaching past yesterday
    "lbt-yesterday": ("2034-03-09 23:20:00", ROBIN),  # 00:20 Berlin on the 10th: yesterday so far
    "lbt-late": ("2034-03-10 22:30:00", ROBIN),  # 23:30 Berlin on the 10th: last 24 hours only
    "lbt-today-1": ("2034-03-10 23:30:00", ROBIN),  # 00:30 Berlin on the 11th
    "lbt-today-2": ("2034-03-10 23:40:00", ROBIN),  # 00:40 Berlin on the 11th
}


class Clock:
    now = BERLIN_EVENING


class FixedDatetime(datetime):
    @classmethod
    def combine(cls, day, clock, tzinfo=None):
        return datetime.combine(day, clock, tzinfo)

    @classmethod
    def now(cls, tz=None):
        instant = Clock.now.replace(tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else Clock.now


async def _insert(rows: dict[str, tuple[str, str]]) -> None:
    async with get_db() as db:
        for event, (moment, species) in rows.items():
            await db.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                    frigate_event, camera_name, is_hidden, manual_tagged, scientific_name, common_name)
                VALUES (?, 1, 0.9, ?, ?, ?, 'birdcam', 0, 0, ?, ?)""",
                (moment, species, species, event, species, species),
            )
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, 0.9, 'BirdCam', '{}', ?)""",
                (moment, species, species),
            )
        await db.commit()


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(Clock, "now", BERLIN_EVENING)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["Unknown Bird"])
    for module in (species_router, audio_router, stats_router, public_access):
        monkeypatch.setattr(module, "datetime", FixedDatetime)
    monkeypatch.delenv("TZ", raising=False)
    clear_portraits_cache()
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.commit()
    await _insert(ROWS)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)
        clear_portraits_cache()
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'lbt-%'")
            await db.execute("DELETE FROM audio_detections")
            await db.commit()


def _as_guest(monkeypatch, days: int) -> None:
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", days)
    monkeypatch.setattr(settings.public_access, "show_audio", True)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")


async def _get(client: httpx.AsyncClient, path: str, headers: dict[str, str] | None = None) -> dict:
    response = await client.get(path, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def _seen(payload: dict, scientific_name: str) -> dict:
    return next(row for row in payload["species"] if row["scientific_name"] == scientific_name)


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_seen_today_counts_from_the_viewers_midnight_and_compares_with_yesterday_so_far(client):
    payload = await _get(client, "/api/leaderboard/species?span=today", BERLIN)

    assert payload["span"] == "today"
    assert _instant(payload["window_start"]) == datetime(2034, 3, 10, 23, 0, tzinfo=timezone.utc)
    assert _instant(payload["window_end"]) == datetime(2034, 3, 10, 23, 45, tzinfo=timezone.utc)
    robin = _seen(payload, ROBIN)
    assert robin["window_count"] == 2
    assert robin["window_prev_count"] == 1
    assert payload["previous_window_complete"] is True
    assert payload["previous_window_mismatch"] is None
    assert payload["window_shortened"] is False


@pytest.mark.asyncio
async def test_last_24_hours_keeps_its_rolling_window_under_day(client):
    payload = await _get(client, "/api/leaderboard/species?span=day", BERLIN)

    assert payload["span"] == "day"
    assert _instant(payload["window_start"]) == datetime(2034, 3, 9, 23, 45, tzinfo=timezone.utc)
    assert _seen(payload, ROBIN)["window_count"] == 3


@pytest.mark.asyncio
async def test_today_without_a_header_is_the_instance_day_then_utc(client, monkeypatch):
    utc_day = await _get(client, "/api/leaderboard/species?span=today")
    assert _instant(utc_day["window_start"]) == datetime(2034, 3, 10, tzinfo=timezone.utc)
    assert _seen(utc_day, ROBIN)["window_count"] == 3

    monkeypatch.setenv("TZ", "Europe/Berlin")
    instance_day = await _get(client, "/api/leaderboard/species?span=today")
    assert _instant(instance_day["window_start"]) == datetime(2034, 3, 10, 23, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_heard_today_counts_the_same_window_as_seen(client):
    seen = await _get(client, "/api/leaderboard/species?span=today", BERLIN)
    heard = await _get(client, "/api/audio/species?span=today", BERLIN)

    assert heard["span"] == "today"
    assert _instant(heard["window_start"]) == _instant(seen["window_start"])
    assert _instant(heard["window_end"]) == _instant(seen["window_end"])
    robin = next(row for row in heard["species"] if row["scientific_name"] == ROBIN)
    assert robin["heard_count"] == 2
    assert robin["heard_prev_count"] == 1
    assert heard["previous_window_complete"] is True


@pytest.mark.asyncio
async def test_timeline_and_heatmaps_chart_today_by_the_hour_from_the_same_midnight(client):
    timeline = await _get(client, "/api/stats/detections/timeline?span=today", BERLIN)
    heatmap = await _get(client, "/api/stats/detections/activity-heatmap?span=today", BERLIN)
    robin_heatmap = await _get(client, f"/api/stats/detections/activity-heatmap?span=today&species={ROBIN}", BERLIN)

    midnight = datetime(2034, 3, 10, 23, 0, tzinfo=timezone.utc)
    assert timeline["bucket"] == "hour"
    assert _instant(timeline["window_start"]) == midnight
    assert sum(point["count"] for point in timeline["points"]) == 2
    assert _instant(heatmap["window_start"]) == midnight
    assert heatmap["total_count"] == 2
    assert robin_heatmap["total_count"] == 2


@pytest.mark.asyncio
async def test_today_never_shows_yesterdays_crop_or_yesterdays_cached_portraits(client, monkeypatch):
    # The only crop is from 23:50 Berlin time yesterday; today's Robin captures have none.
    crops = {"lbt-crop-yesterday": {"source": "hq_candidate_model_crop"}}
    monkeypatch.setattr(media_cache_module.media_cache, "_available", True)
    monkeypatch.setattr(
        media_cache_module.media_cache,
        "get_snapshot_metadata",
        AsyncMock(side_effect=lambda event_id: crops.get(event_id)),
    )
    await _insert({"lbt-crop-yesterday": ("2034-03-10 22:50:00", ROBIN)})

    # Five minutes before Berlin midnight the crop is today's.
    monkeypatch.setattr(Clock, "now", datetime(2034, 3, 10, 22, 55))
    before = await _get(client, "/api/leaderboard/portraits?span=today", BERLIN)
    assert [portrait["frigate_event"] for portrait in before["portraits"]] == ["lbt-crop-yesterday"]

    # After midnight the same request is a new window, inside the cache's five minutes.
    monkeypatch.setattr(Clock, "now", BERLIN_EVENING)
    after = await _get(client, "/api/leaderboard/portraits?span=today", BERLIN)
    assert after["span"] == "today"
    assert after["portraits"] == []


@pytest.mark.asyncio
async def test_today_has_no_trend_on_the_morning_the_clocks_go_forward(client, monkeypatch):
    # Berlin went to summer time at 01:00 UTC on 26 March 2034: today so far is an hour shorter.
    monkeypatch.setattr(Clock, "now", datetime(2034, 3, 26, 9, 0))
    await _insert(
        {"lbt-dst-yesterday": ("2034-03-25 06:00:00", ROBIN), "lbt-dst-today": ("2034-03-26 06:00:00", ROBIN)}
    )

    seen = await _get(client, "/api/leaderboard/species?span=today", BERLIN)
    heard = await _get(client, "/api/audio/species?span=today", BERLIN)

    assert _instant(seen["window_start"]) == datetime(2034, 3, 25, 23, 0, tzinfo=timezone.utc)
    assert seen["previous_window_complete"] is False
    assert seen["previous_window_mismatch"] == "clock_change"
    assert heard["previous_window_complete"] is False
    assert heard["previous_window_mismatch"] == "clock_change"


@pytest.mark.asyncio
async def test_a_guest_today_is_cut_to_the_shared_utc_day_and_says_so(client, monkeypatch):
    # 02:00 UTC on the 11th is 21:00 on the 10th in New York: that today began before the shared UTC day.
    monkeypatch.setattr(Clock, "now", datetime(2034, 3, 11, 2, 0))
    await _insert({"lbt-guest-shared": ("2034-03-11 01:00:00", ROBIN)})
    _as_guest(monkeypatch, days=0)
    new_york = {"X-Timezone": "America/New_York"}

    seen = await _get(client, "/api/leaderboard/species?span=today", new_york)
    heard = await _get(client, "/api/audio/species?span=today", new_york)
    timeline = await _get(client, "/api/stats/detections/timeline?span=today", new_york)

    shared_day = datetime(2034, 3, 11, tzinfo=timezone.utc)
    assert _instant(seen["window_start"]) == shared_day
    assert seen["window_shortened"] is True
    assert seen["previous_window_complete"] is False
    assert seen["previous_window_mismatch"] == "shared_window"
    # The 23:30 and 23:40 UTC captures were today in New York but are outside what a guest may see.
    assert _seen(seen, ROBIN)["window_count"] == 1
    assert _instant(heard["window_start"]) == shared_day
    assert heard["window_shortened"] is True
    assert heard["previous_window_complete"] is False
    assert _instant(timeline["window_start"]) == shared_day


@pytest.mark.asyncio
async def test_a_guest_today_inside_the_shared_window_is_not_shortened(client, monkeypatch):
    _as_guest(monkeypatch, days=7)

    seen = await _get(client, "/api/leaderboard/species?span=today", BERLIN)

    assert _instant(seen["window_start"]) == datetime(2034, 3, 10, 23, 0, tzinfo=timezone.utc)
    assert seen["window_shortened"] is False
    assert _seen(seen, ROBIN)["window_count"] == 2


@pytest.mark.asyncio
async def test_an_unknown_span_is_rejected(client):
    response = await client.get("/api/leaderboard/species?span=yesterday")

    assert response.status_code == 422


KOLKATA = {"X-Timezone": "Asia/Kolkata"}
# 20:00 UTC on 10 March 2034 is 01:30 on Saturday 11 March in Kolkata (UTC+5:30), whose today began
# at 18:30 UTC. Each capture sits a few minutes from a local hour or midnight.
KOLKATA_ROWS = {
    "lbt-in-before-midnight": ("2034-03-10 18:20:00", TIT),  # 23:50 on Friday the 10th
    "lbt-in-after-midnight": ("2034-03-10 18:40:00", TIT),  # 00:10 on Saturday the 11th
    "lbt-in-before-one": ("2034-03-10 19:25:00", TIT),  # 00:55 on the 11th
    "lbt-in-after-one": ("2034-03-10 19:35:00", TIT),  # 01:05 on the 11th
}
FRIDAY, SATURDAY = 5, 6


def _cell(heatmap: dict, day_of_week: int, hour: int) -> int:
    return next(
        cell["count"] for cell in heatmap["cells"] if (cell["day_of_week"], cell["hour"]) == (day_of_week, hour)
    )


@pytest.mark.asyncio
async def test_a_half_hour_zone_puts_each_capture_in_its_own_local_hour_on_the_heatmaps(client, monkeypatch):
    monkeypatch.setattr(Clock, "now", datetime(2034, 3, 10, 20, 0))
    await _insert(KOLKATA_ROWS)

    today = await _get(client, "/api/stats/detections/activity-heatmap?span=today", KOLKATA)
    tit_today = await _get(client, f"/api/stats/detections/activity-heatmap?span=today&species={TIT}", KOLKATA)
    last_day = await _get(client, "/api/stats/detections/activity-heatmap?span=day", KOLKATA)

    for heatmap in (today, tit_today):
        assert _cell(heatmap, SATURDAY, 0) == 2
        assert _cell(heatmap, SATURDAY, 1) == 1
        assert _cell(heatmap, FRIDAY, 23) == 0
    assert _cell(last_day, FRIDAY, 23) == 1
    assert _cell(last_day, SATURDAY, 0) == 2


@pytest.mark.asyncio
async def test_a_half_hour_zone_keys_the_timeline_by_its_own_local_hours(client, monkeypatch):
    monkeypatch.setattr(Clock, "now", datetime(2034, 3, 10, 20, 0))
    await _insert(KOLKATA_ROWS)

    today = await _get(client, f"/api/stats/detections/timeline?span=today&compare_species={TIT}", KOLKATA)
    last_day = await _get(client, "/api/stats/detections/timeline?span=day", KOLKATA)

    assert [(point["bucket_start"], point["label"], point["count"]) for point in today["points"]] == [
        ("2034-03-10T18:30:00Z", "00:00", 2),
        ("2034-03-10T19:30:00Z", "01:00", 1),
    ]
    compare = {point["bucket_start"]: point["count"] for point in today["compare_series"][0]["points"]}
    assert compare == {"2034-03-10T18:30:00Z": 2, "2034-03-10T19:30:00Z": 1}
    by_key = {point["bucket_start"]: point["count"] for point in last_day["points"]}
    assert by_key["2034-03-10T17:30:00Z"] == 1
    assert by_key["2034-03-10T18:30:00Z"] == 2
    assert all(key.endswith(":30:00Z") for key in by_key)
