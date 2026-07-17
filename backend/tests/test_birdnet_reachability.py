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
    monkeypatch.setattr("app.routers.settings.httpx.AsyncClient", lambda *a, **k: mock_client)

    resp = await client.get("/api/settings/birdnet/reachability")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    mock_client.get.assert_awaited_once()


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
