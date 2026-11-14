"""Integration failures are logged and answered without credentials carried in a configured URL.

HTTP client errors can quote the request URL, and reverse-proxied integrations are often reached
with basic-auth userinfo, a token query parameter or a token path segment in that URL.
"""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request
from structlog.testing import capture_logs

from app.auth import AuthContext, AuthLevel, require_owner
from app.config import settings
from app.main import app, unhandled_exception_handler

SECRET_URLS = {
    "userinfo": ("https://feeder-user:hunter2-pass@integration.example.test:8443", ("feeder-user", "hunter2-pass")),
    "token_query": ("https://integration.example.test:8443/?token=query-secret-123", ("query-secret-123",)),
    "token_path": ("https://integration.example.test:8443/proxy/path-secret-456", ("path-secret-456",)),
}
REDUCED_HOST = "https://integration.example.test:8443"


def _assert_clean(rendered: str, secrets: tuple[str, ...]) -> None:
    for secret in secrets:
        assert secret not in rendered


def _refusing_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(_transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {request.url}", request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


@pytest.fixture
def as_owner():
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER)
    yield
    app.dependency_overrides.pop(require_owner, None)


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_unhandled_exception_log_and_traceback_keep_url_credentials_out(url_shape):
    url, secrets = SECRET_URLS[url_shape]
    request = Request({"type": "http", "method": "GET", "path": "/api/fixture", "headers": [], "query_string": b""})
    try:
        raise httpx.ConnectError(f"cannot connect to {url}/api/events")
    except httpx.ConnectError as error:
        with capture_logs() as records:
            response = await unhandled_exception_handler(request, error)

    assert response.status_code == 500
    (record,) = [record for record in records if record["event"] == "Unhandled exception"]
    # A traceback rendered later from exc_info would repeat the raw error text.
    assert "exc_info" not in record
    assert "ConnectError" in record["traceback"]
    _assert_clean(json.dumps(records), secrets)
    assert REDUCED_HOST in record["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_home_assistant_state_failure_log_keeps_url_credentials_out(url_shape):
    from app.services.ha_weather import HomeAssistantWeatherSource

    url, secrets = SECRET_URLS[url_shape]
    source = HomeAssistantWeatherSource(
        base_url=url, access_token="ha-token-secret", weather_entity="weather.home", override_entities={}
    )

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect to {request.url}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        with capture_logs() as records:
            assert await source._fetch_state("weather.home", client=client) is None

    assert records
    _assert_clean(json.dumps(records), secrets)


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_media_probe_backstop_log_keeps_url_credentials_out(monkeypatch, url_shape):
    from app.services import media_probe

    url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(
        media_probe, "_collect_video_sample", AsyncMock(side_effect=httpx.ConnectError(f"cannot reach {url}"))
    )
    with capture_logs() as records:
        result = await media_probe.collect_video_sample_diagnostic()

    assert result
    assert records
    _assert_clean(json.dumps(records) + json.dumps(result, default=str), secrets)


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_high_quality_snapshot_recording_fallback_log_keeps_url_credentials_out(monkeypatch, url_shape):
    from app.routers import proxy
    from app.services.high_quality_snapshot_service import high_quality_snapshot_service

    url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(
        proxy, "_get_valid_cached_recording_clip_path", AsyncMock(return_value=(None, "birdcam", 100, 200))
    )
    monkeypatch.setattr(
        proxy, "_fetch_recording_clip_ready", AsyncMock(side_effect=httpx.ConnectError(f"cannot reach {url}/api"))
    )
    with capture_logs() as records:
        assert await high_quality_snapshot_service._load_live_recording_clip_bytes("event_1") is None

    assert records
    _assert_clean(json.dumps(records), secrets)


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_debug_connectivity_reports_frigate_failure_without_url_credentials(monkeypatch, as_owner, url_shape):
    url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.frigate, "frigate_url", url)
    monkeypatch.setattr(settings.auth, "enabled", False)
    _refusing_transport(monkeypatch)

    response = await _request("GET", "/api/debug/connectivity")

    assert response.status_code == 200
    assert response.json()["frigate"]["status"] == "error"
    _assert_clean(response.text, secrets)
    assert REDUCED_HOST in response.json()["frigate"]["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_notification_test_failure_message_keeps_url_credentials_out(monkeypatch, as_owner, url_shape):
    from app.services.notification_service import notification_service

    url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(
        notification_service,
        "_send_discord",
        AsyncMock(side_effect=httpx.ConnectError(f"cannot connect to {url}/webhook")),
    )

    response = await _request("POST", "/api/settings/notifications/test", json={"platform": "discord"})

    assert response.status_code == 502
    _assert_clean(response.text, secrets)
    assert REDUCED_HOST in response.json()["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
@pytest.mark.parametrize("path", ["/api/ebird/nearby", "/api/ebird/notable"])
async def test_ebird_search_failure_message_keeps_url_credentials_out(monkeypatch, url_shape, path):
    from app.services.ebird_service import ebird_service

    url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.ebird, "enabled", True)
    monkeypatch.setattr(settings.ebird, "api_key", "ebird-key-secret")
    monkeypatch.setattr(ebird_service, "resolve_species_code", AsyncMock(return_value=None))
    monkeypatch.setattr(
        ebird_service,
        "get_recent_observations",
        AsyncMock(side_effect=httpx.ConnectError(f"cannot connect to {url}/v2/data/obs")),
    )

    response = await _request("GET", path, params={"lat": 51.5, "lng": -0.1})

    assert response.json()["status"] == "error"
    _assert_clean(response.text, (*secrets, "ebird-key-secret"))


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["reachable", "unreachable"])
async def test_birdnet_reachability_names_only_the_reduced_address(monkeypatch, as_owner, outcome):
    url, secrets = SECRET_URLS["token_path"]
    monkeypatch.setattr(settings.auth, "enabled", False)
    if outcome == "reachable":

        async def answer(_transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, request=request)

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", answer)
    else:
        _refusing_transport(monkeypatch)

    response = await _request("GET", "/api/settings/birdnet/reachability", params={"url": url})

    assert response.status_code == (200 if outcome == "reachable" else 502)
    _assert_clean(response.text, secrets)
    assert REDUCED_HOST in response.json()["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
async def test_full_visit_fetch_failure_log_keeps_frigate_url_credentials_out(monkeypatch, url_shape):
    from app.services import full_visit_clip_service as module

    url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.frigate, "frigate_url", url)
    monkeypatch.setattr(module, "_get_recording_clip_context", AsyncMock(return_value=("birdcam", 100, 200)))
    _refusing_transport(monkeypatch)

    with capture_logs() as records:
        outcome = await module.full_visit_clip_service._fetch_once("event_1", "en", min_duration_seconds=1.0)

    assert outcome == "unavailable"
    assert records
    _assert_clean(json.dumps(records), secrets)
