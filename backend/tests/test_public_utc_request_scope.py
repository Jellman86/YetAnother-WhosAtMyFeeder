from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import httpx
import pytest
from app.config import settings
from app.main import app
from app.routers import events
from app.utils import public_access
from test_public_utc_day_boundaries import clock as clock, history as history


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "/api/events",
        "/api/events?audio_confirmed_only=true",
        "/api/events/count?audio_confirmed_only=true",
        "/api/events/filters?force_refresh=true",
    ],
)
@pytest.mark.parametrize("evidence_day", ["admitted", "next"])
async def test_public_event_audio_keeps_the_admitted_day_across_request_rollover(
    history, clock, monkeypatch, route, evidence_day
):
    start = clock.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    reads = []

    class AdvancingDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            reads.append(None)
            return end - timedelta(seconds=1) if len(reads) == 1 else end + timedelta(seconds=1)

        @classmethod
        def combine(cls, day, time, tzinfo=None):
            return datetime.combine(day, time, tzinfo)

    monkeypatch.setattr(public_access, "datetime", AdvancingDatetime)
    monkeypatch.setattr(settings.public_access, "show_audio", True)
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"utc-camera": "*"})
    monkeypatch.setattr(events, "localize_audio_detections", AsyncMock())
    monkeypatch.setattr(events, "localize_audio_species_name", AsyncMock(return_value="Robin"))
    async with history() as db:
        await db.execute("DELETE FROM detections")
        await db.execute(
            "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name,audio_confirmed,audio_species) VALUES ('last','utc-camera',?,1,.9,'Robin','Robin',1,'Robin')",
            ((end - timedelta(seconds=1)).replace(tzinfo=None).isoformat(sep=" "),),
        )
        await db.execute(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Robin',.9,'micA','{}',0)",
            ((end + timedelta(seconds=1 if evidence_day == "next" else -1)).replace(tzinfo=None).isoformat(sep=" "),),
        )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        result = await client.get(route)
    assert result.status_code == 200, result.text
    confirmed = evidence_day == "admitted"
    if route.startswith("/api/events/count"):
        assert result.json()["count"] == int(confirmed)
    elif route.startswith("/api/events/filters"):
        assert result.json()["totals"]["total"] == 1
        assert result.json()["totals"]["audio_matched"] == int(confirmed)
    else:
        expected = ["last"] if confirmed or "audio_confirmed_only" not in route else []
        assert [row["frigate_event"] for row in result.json()] == expected
        if result.json():
            assert result.json()[0]["audio_confirmed"] is confirmed


@pytest.mark.asyncio
async def test_request_calendar_survives_nested_awaits_and_explicit_later_clock():
    import asyncio
    from app.middleware.public_calendar import PublicCalendarMiddleware

    old = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    new = old + timedelta(seconds=2)
    seen = []

    async def downstream(scope, receive, send):
        seen.append(public_access.public_utc_day(old))
        await asyncio.sleep(0)
        seen.append(await asyncio.create_task(_read_day(new)))
        seen.append(public_access.public_utc_day(new))
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def send(message):
        pass

    await PublicCalendarMiddleware(downstream)({"type": "http"}, AsyncMock(), send)
    assert seen == [old.date()] * 3
    assert public_access.public_utc_day(new) == new.date()


async def _read_day(now):
    return public_access.public_utc_day(now)


@pytest.mark.asyncio
async def test_parallel_request_calendars_are_independent():
    import asyncio
    from app.middleware.public_calendar import PublicCalendarMiddleware

    old = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    new = old + timedelta(seconds=2)
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = {}

    async def downstream(scope, receive, send):
        own, other = scope["times"]
        public_access.public_utc_day(own)
        entered.set()
        await release.wait()
        seen[own.date()] = public_access.public_utc_day(other)
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    middleware = PublicCalendarMiddleware(downstream)
    first = asyncio.create_task(middleware({"type": "http", "times": (old, new)}, AsyncMock(), AsyncMock()))
    await entered.wait()
    second = asyncio.create_task(middleware({"type": "http", "times": (new, old)}, AsyncMock(), AsyncMock()))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    assert seen == {old.date(): old.date(), new.date(): new.date()}


@pytest.mark.asyncio
@pytest.mark.parametrize("finish", ["response", "exception", "cancel"])
async def test_inherited_background_task_stops_using_closed_request_calendar(finish):
    import asyncio
    from app.middleware.public_calendar import PublicCalendarMiddleware

    old = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    new = old + timedelta(seconds=2)
    ready = asyncio.Event()
    release = asyncio.Event()
    background = []

    async def later():
        await release.wait()
        return public_access.public_utc_day(new)

    async def downstream(scope, receive, send):
        assert public_access.public_utc_day(old) == old.date()
        background.append(asyncio.create_task(later()))
        ready.set()
        if finish == "exception":
            raise RuntimeError("fixture")
        if finish == "cancel":
            await asyncio.Event().wait()
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        # Starlette response background tasks run before the ASGI app returns.
        release.set()
        assert await background[0] == new.date()

    request = asyncio.create_task(PublicCalendarMiddleware(downstream)({"type": "http"}, AsyncMock(), AsyncMock()))
    await ready.wait()
    if finish == "cancel":
        request.cancel()
    if finish == "response":
        await request
    else:
        with pytest.raises(RuntimeError if finish == "exception" else asyncio.CancelledError):
            await request
    release.set()
    assert await background[0] == new.date()
    assert public_access.public_utc_day(new) == new.date()


@pytest.mark.asyncio
async def test_stream_chunks_keep_calendar_until_last_body_and_settings_remain_live(monkeypatch):
    from app.middleware.public_calendar import PublicCalendarMiddleware

    old = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    new = old + timedelta(seconds=2)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)

    async def downstream(scope, receive, send):
        assert public_access.public_events_window(old)[1] == new.replace(hour=0, minute=0, second=0)
        await send({"type": "http.response.body", "body": b"chunk", "more_body": True})
        assert public_access.public_utc_day(new) == old.date()
        monkeypatch.setattr(settings.public_access, "show_historical_days", 1)
        assert public_access.public_events_window(new) == (
            old.replace(hour=0, minute=0, second=0) - timedelta(days=1),
            None,
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        assert public_access.public_utc_day(new) == new.date()

    await PublicCalendarMiddleware(downstream)({"type": "http"}, AsyncMock(), AsyncMock())


@pytest.mark.asyncio
async def test_calendar_middleware_leaves_non_http_scopes_unchanged():
    from app.middleware.public_calendar import PublicCalendarMiddleware

    old = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
    new = old + timedelta(seconds=2)

    async def downstream(scope, receive, send):
        assert public_access.public_utc_day(old) == old.date()
        assert public_access.public_utc_day(new) == new.date()

    await PublicCalendarMiddleware(downstream)({"type": "lifespan"}, AsyncMock(), AsyncMock())
