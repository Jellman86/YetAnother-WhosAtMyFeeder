"""Concurrency contracts for optional integrations sharing the ingest event loop."""

import asyncio
import threading
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services.ha_weather import HomeAssistantWeatherSource
from app.services.weather_service import WeatherService


@pytest.mark.asyncio
async def test_weather_burst_shares_one_read_and_returns_independent_values(monkeypatch):
    service = WeatherService()
    monkeypatch.setattr(settings.ha_weather, "enabled", False)

    async def fetch():
        await asyncio.sleep(0)
        return {"temperature": 12.0}

    fetcher = AsyncMock(side_effect=fetch)
    monkeypatch.setattr(service, "_fetch_current_weather", fetcher, raising=False)
    results = await asyncio.gather(*(service.get_current_weather() for _ in range(20)))
    assert fetcher.await_count == 1
    results[0]["temperature"] = 999
    assert await service.get_current_weather() == {"temperature": 12.0}


@pytest.mark.asyncio
async def test_weather_config_change_and_expiry_refresh_without_stale_fallback(monkeypatch):
    service = WeatherService()
    monkeypatch.setattr(settings.ha_weather, "enabled", False)
    monkeypatch.setattr(settings.location, "latitude", 51.0)
    now = [100.0]
    monkeypatch.setattr("app.services.weather_service.monotonic", lambda: now[0])
    fetcher = AsyncMock(side_effect=[{"temperature": 12.0}, {"temperature": 13.0}, {}, {"temperature": 14.0}])
    monkeypatch.setattr(service, "_fetch_current_weather", fetcher, raising=False)
    assert await service.get_current_weather() == {"temperature": 12.0}
    monkeypatch.setattr(settings.location, "latitude", 52.0)
    assert await service.get_current_weather() == {"temperature": 13.0}
    now[0] += 31.0
    assert await service.get_current_weather() == {}
    assert await service.get_current_weather() == {}
    now[0] += 6.0
    assert await service.get_current_weather() == {"temperature": 14.0}


@pytest.mark.asyncio
async def test_ha_entities_are_concurrent_deduplicated_and_share_client(monkeypatch):
    source = HomeAssistantWeatherSource(
        base_url="http://ha.invalid",
        access_token="dummy",
        weather_entity="weather.home",
        override_entities={"temperature": "sensor.temp", "rain": "sensor.rain", "precipitation": "sensor.rain"},
    )
    started = []
    clients = []

    async def fetch(entity, *, client=None):
        started.append(entity)
        clients.append(client)
        await asyncio.sleep(0)
        assert len(started) == 3
        if entity == "weather.home":
            return {"state": "rainy", "attributes": {"temperature": 8}}
        return {"state": "unknown" if entity == "sensor.temp" else "2", "attributes": {}}

    monkeypatch.setattr(source, "_fetch_state", fetch)
    result = await source.get_current_weather()
    assert result == {"condition_text": "Rain", "rain": 2.0, "precipitation": 2.0}
    assert len({id(client) for client in clients}) == 1
    assert clients[0] is not None


@pytest.mark.asyncio
async def test_ai_event_clip_decode_runs_outside_event_loop(monkeypatch):
    from app.routers.ai import _load_ai_analysis_frames
    from app.routers import ai

    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(ai.frigate_client, "get_clip_with_error", AsyncMock(return_value=(b"video", None)))
    event_loop_thread = threading.get_ident()

    def extract(*args, **kwargs):
        assert threading.get_ident() != event_loop_thread
        return [b"frame"]

    monkeypatch.setattr(ai.ai_service, "extract_frames_from_clip", extract)
    assert await _load_ai_analysis_frames("evt", frame_count=5, lang="en") == ([b"frame"], "event")


@pytest.mark.asyncio
async def test_weather_cancelled_read_releases_waiting_detection(monkeypatch):
    service = WeatherService()
    entered = asyncio.Event()
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await asyncio.Event().wait()
        return {"temperature": 12.0}

    monkeypatch.setattr(service, "_fetch_current_weather", fetch)
    first = asyncio.create_task(service.get_current_weather())
    await entered.wait()
    second = asyncio.create_task(service.get_current_weather())
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await asyncio.wait_for(second, timeout=1) == {"temperature": 12.0}
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("access_token", "replacement-token"),
        ("base_url", "http://replacement.invalid"),
        ("weather_entity", "weather.other"),
        ("temperature_entity", "sensor.other"),
    ],
)
async def test_weather_ha_config_change_invalidates_cached_read(monkeypatch, field, value):
    service = WeatherService()
    monkeypatch.setattr(settings.ha_weather, "enabled", True)
    monkeypatch.setattr(settings.ha_weather, "base_url", "http://ha.invalid")
    monkeypatch.setattr(settings.ha_weather, "access_token", "dummy")
    monkeypatch.setattr(settings.ha_weather, "weather_entity", "weather.home")
    fetcher = AsyncMock(side_effect=[{"temperature": 12.0}, {}])
    monkeypatch.setattr(service, "_fetch_current_weather", fetcher)
    assert await service.get_current_weather() == {"temperature": 12.0}
    monkeypatch.setattr(settings.ha_weather, field, value)
    assert await service.get_current_weather() == {}
    assert fetcher.await_count == 2


@pytest.mark.asyncio
async def test_ha_timeout_preserves_other_readings_and_closes_client(monkeypatch):
    import httpx
    from app.services import ha_weather

    original_client = httpx.AsyncClient
    clients = []

    async def respond(request):
        if request.url.path.endswith("sensor.temp"):
            raise httpx.ReadTimeout("sensor timed out", request=request)
        return httpx.Response(200, json={"state": "sunny", "attributes": {"temperature": 20, "wind_speed": 4}})

    def client_factory(**kwargs):
        client = original_client(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(ha_weather.httpx, "AsyncClient", client_factory)
    source = HomeAssistantWeatherSource(
        base_url="http://ha.invalid",
        access_token="dummy",
        weather_entity="weather.home",
        override_entities={"temperature": "sensor.temp"},
    )
    assert await source.get_current_weather() == {"condition_text": "Clear sky", "wind_speed": 4.0}
    assert len(clients) == 1
    assert clients[0].is_closed
