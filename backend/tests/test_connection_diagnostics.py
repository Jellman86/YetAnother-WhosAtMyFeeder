"""Connection diagnostics exercise the values currently being edited without mutating config."""

from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client


@pytest.fixture(autouse=True)
def _no_auth():
    original = (
        settings.auth.enabled,
        settings.frigate.frigate_url,
        settings.frigate.mqtt_password,
    )
    settings.auth.enabled = False
    yield
    (
        settings.auth.enabled,
        settings.frigate.frigate_url,
        settings.frigate.mqtt_password,
    ) = original


@pytest.mark.asyncio
async def test_frigate_diagnostic_uses_url_override_without_mutating_settings(client, monkeypatch):
    settings.frigate.frigate_url = "http://saved-frigate:5000"
    http_client = AsyncMock()
    http_client.get.return_value = httpx.Response(
        200,
        text='"0.16.0"',
        request=httpx.Request("GET", "http://edited-frigate:5000/api/version"),
    )
    monkeypatch.setattr("app.routers.proxy.get_http_client", lambda: http_client)

    response = await client.get(
        "/api/frigate/test",
        params={"url": "http://edited-frigate:5000"},
    )

    assert response.status_code == 200, response.text
    http_client.get.assert_awaited_once()
    assert http_client.get.await_args.args[0] == "http://edited-frigate:5000/api/version"
    assert response.json()["frigate_url"] == "http://edited-frigate:5000"
    assert settings.frigate.frigate_url == "http://saved-frigate:5000"


@pytest.mark.asyncio
async def test_frigate_diagnostic_rejects_unsafe_url_override(client):
    response = await client.get("/api/frigate/test", params={"url": "file:///etc/passwd"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_mqtt_diagnostic_uses_current_form_values_and_preserves_saved_password(client, monkeypatch):
    settings.frigate.mqtt_password = "stored-password"
    test_connection = AsyncMock(return_value=True)
    monkeypatch.setattr("app.services.mqtt_service.mqtt_service.test_connection", test_connection)

    response = await client.post(
        "/api/settings/mqtt/test-publish",
        json={
            "server": "edited-mqtt",
            "port": 2883,
            "auth": True,
            "username": "birder",
            "password": "",
        },
    )

    assert response.status_code == 200, response.text
    test_connection.assert_awaited_once_with(
        server="edited-mqtt",
        port=2883,
        username="birder",
        password="stored-password",
    )


@pytest.mark.asyncio
async def test_birdnet_ingest_diagnostic_waits_for_durable_success(client, monkeypatch):
    add_detection = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "app.services.audio.audio_service.audio_service.add_detection",
        add_detection,
    )

    response = await client.post("/api/settings/birdnet/test")

    assert response.status_code == 200, response.text
    payload = add_detection.await_args.args[0]
    add_detection.assert_awaited_once_with(payload, diagnostic=True)
    assert payload["ScientificName"] == "Cyanistes caeruleus"
    assert isinstance(payload["timestamp"], float)


@pytest.mark.asyncio
async def test_birdnet_ingest_diagnostic_reports_failed_persistence(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.audio.audio_service.audio_service.add_detection",
        AsyncMock(return_value=False),
    )

    response = await client.post("/api/settings/birdnet/test")

    assert response.status_code == 502
    assert response.json()["status"] == "error"
