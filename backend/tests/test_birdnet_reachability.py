from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _no_auth_and_restore_url():
    original_auth = settings.auth.enabled
    original_url = settings.frigate.birdnet_url
    settings.auth.enabled = False
    yield
    settings.auth.enabled = original_auth
    settings.frigate.birdnet_url = original_url


@pytest.mark.asyncio
async def test_reachability_requires_configured_url(client):
    settings.frigate.birdnet_url = ""
    resp = await client.get("/api/settings/birdnet/reachability")
    assert resp.status_code == 400, resp.text
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_reachability_ok_when_birdnet_answers(client, monkeypatch):
    settings.frigate.birdnet_url = "http://birdnet-go:8080"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = httpx.Response(200)
    client_options = {}

    def _client_factory(*_args, **kwargs):
        client_options.update(kwargs)
        return mock_client

    monkeypatch.setattr("app.routers.settings.httpx.AsyncClient", _client_factory)

    resp = await client.get("/api/settings/birdnet/reachability")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    mock_client.get.assert_awaited_once()
    assert client_options["follow_redirects"] is False


@pytest.mark.asyncio
async def test_reachability_tests_unsaved_url_override_without_mutating_settings(client, monkeypatch):
    settings.frigate.birdnet_url = "http://saved-birdnet:8080"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = httpx.Response(200)
    monkeypatch.setattr("app.routers.settings.httpx.AsyncClient", lambda *_args, **_kwargs: mock_client)

    resp = await client.get(
        "/api/settings/birdnet/reachability",
        params={"url": "http://edited-birdnet:8080"},
    )

    assert resp.status_code == 200, resp.text
    mock_client.get.assert_awaited_once_with("http://edited-birdnet:8080", timeout=10.0)
    assert settings.frigate.birdnet_url == "http://saved-birdnet:8080"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_url",
    [
        "file:///etc/passwd",
        "ftp://birdnet-go:8080",
        "http://user:secret@birdnet-go:8080",
        "http://birdnet-go:8080/#fragment",
    ],
)
async def test_reachability_rejects_unsafe_configured_url(client, unsafe_url):
    settings.frigate.birdnet_url = unsafe_url

    resp = await client.get("/api/settings/birdnet/reachability")

    assert resp.status_code == 400, resp.text
    assert resp.json()["status"] == "error"


@pytest.mark.asyncio
async def test_reachability_fails_when_unreachable(client, monkeypatch):
    settings.frigate.birdnet_url = "http://birdnet-go:8080"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.side_effect = httpx.ConnectError("connection refused")
    monkeypatch.setattr("app.routers.settings.httpx.AsyncClient", lambda *a, **k: mock_client)

    resp = await client.get("/api/settings/birdnet/reachability")
    assert resp.status_code == 502, resp.text
    assert resp.json()["status"] == "error"
