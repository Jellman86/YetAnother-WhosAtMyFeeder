"""Health and the status tiles read the broker and Frigate connections as measured."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from aiomqtt import MqttError

import app.services.mqtt_service as mqtt_module
from app.config import settings
from app.main import app
from app.services import service_connections
from app.services.frigate_client import frigate_client
from app.services.mqtt_service import MQTTService, mqtt_service

REAL_REFRESH = service_connections._refresh_frigate_reading


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def owner_access():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


def _frigate_answering(monkeypatch, handler):
    """Route the shared Frigate client through a mock transport, as the boundary."""
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(frigate_client, "_client", mock_client)
    return mock_client


@pytest.mark.asyncio
async def test_connections_report_a_broker_that_could_not_be_reached(client, monkeypatch):
    monkeypatch.setattr(settings.frigate, "mqtt_server", "mqtt.invalid")
    now = datetime.now(timezone.utc)
    mqtt_service.connection.attempting(now)
    mqtt_service.connection.failed(now, "[Errno -2] Name or service not known")

    response = await client.get("/api/diagnostics/connections")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mqtt"]["state"] == "disconnected"
    assert body["mqtt"]["server"] == "mqtt.invalid"
    assert body["mqtt"]["last_error"] == "[Errno -2] Name or service not known"
    assert body["frigate"]["state"] == "unchecked"
    assert body["frigate"]["availability"] == "unknown"


@pytest.mark.asyncio
async def test_guest_cannot_read_connections(client):
    settings.auth.enabled = True
    settings.public_access.enabled = True
    response = await client.get("/api/diagnostics/connections")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_unanswered_frigate_is_measured_before_it_is_reported(client, monkeypatch):
    monkeypatch.setattr(service_connections, "_refresh_frigate_reading", REAL_REFRESH)
    calls: list[str] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        raise httpx.ConnectError("Name or service not known", request=request)

    mock_client = _frigate_answering(monkeypatch, refuse)
    try:
        body = (await client.get("/api/diagnostics/connections")).json()
        assert calls == ["/api/version"]
        assert body["frigate"]["state"] == "unreachable"
        assert body["frigate"]["last_failure"] == "connection"
        # A reading under a minute old is reported as it is, not measured again.
        await client.get("/api/diagnostics/connections")
        assert calls == ["/api/version"]
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_a_stale_frigate_reading_is_refreshed(monkeypatch):
    monkeypatch.setattr(service_connections, "_refresh_frigate_reading", REAL_REFRESH)
    old = datetime.now(timezone.utc) - timedelta(minutes=5)
    service_connections.frigate_reachability.record_failure("timeout", old)
    mock_client = _frigate_answering(monkeypatch, lambda request: httpx.Response(200, json="0.16.0"))
    try:
        result = await service_connections.collect_service_connections(refresh_frigate=True)
    finally:
        await mock_client.aclose()
    assert result.frigate.state == "reachable"


@pytest.mark.asyncio
async def test_frigate_requests_record_what_they_saw(monkeypatch):
    mock_client = _frigate_answering(monkeypatch, lambda request: httpx.Response(404))
    try:
        await frigate_client.get("api/events/missing")
        assert service_connections.frigate_reachability.state == "reachable"
    finally:
        await mock_client.aclose()

    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    mock_client = _frigate_answering(monkeypatch, time_out)
    try:
        with pytest.raises(httpx.ReadTimeout):
            await frigate_client.get("api/version")
    finally:
        await mock_client.aclose()
    assert service_connections.frigate_reachability.state == "unreachable"
    assert service_connections.frigate_reachability.last_failure == "timeout"


@pytest.mark.asyncio
async def test_health_is_not_ok_while_the_broker_is_down(client):
    app.state.startup_warnings = []
    now = datetime.now(timezone.utc)
    mqtt_service.connection.failed(now, "refused")
    body = (await client.get("/health")).json()
    assert body["mqtt"]["connection_state"] == "disconnected"
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_is_not_ok_while_frigate_does_not_answer(client):
    app.state.startup_warnings = []
    service_connections.frigate_reachability.record_failure("connection", datetime.now(timezone.utc))
    body = (await client.get("/health")).json()
    assert body["frigate_api"] == {"state": "unreachable", "last_failure": "connection"}
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_workspace_carries_the_measured_connections(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.diagnostics.collect_video_sample_diagnostic",
        AsyncMock(return_value={"available": False}),
    )
    mqtt_service.connection.failed(datetime.now(timezone.utc), "refused")
    body = (await client.get("/api/diagnostics/workspace")).json()
    assert body["connections"]["mqtt"]["state"] == "disconnected"
    assert body["health"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_mqtt_service_reports_a_failed_connection_attempt(monkeypatch):
    service = MQTTService()
    monkeypatch.setattr(settings.frigate, "mqtt_server", "mqtt.invalid")

    class UnreachableBroker:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            raise MqttError("[Errno -2] Name or service not known")

        async def __aexit__(self, *_exc):
            return False

    async def stop_after_first_failure(_delay):
        service.running = False

    monkeypatch.setattr(mqtt_module, "Client", UnreachableBroker)
    monkeypatch.setattr(mqtt_module.asyncio, "sleep", stop_after_first_failure)

    await service.start(event_processor=None)

    status = service.connection.snapshot(server="mqtt.invalid", port=1883)
    assert status.state == "disconnected"
    assert status.last_error == "[Errno -2] Name or service not known"
    assert service.get_status()["connection_state"] == "disconnected"


@pytest.mark.asyncio
async def test_mqtt_service_without_a_broker_address_says_so(monkeypatch):
    service = MQTTService()
    monkeypatch.setattr(settings.frigate, "mqtt_server", "")
    await service.start(event_processor=None)
    assert service.connection.state == "not_configured"
