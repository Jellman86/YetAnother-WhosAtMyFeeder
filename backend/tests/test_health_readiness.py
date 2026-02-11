import httpx
import pytest
import pytest_asyncio

import app.main as main_module
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_degraded_when_startup_warnings_present(client: httpx.AsyncClient):
    app.state.startup_warnings = [{"phase": "telemetry_start", "error": "boom"}]
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["startup_warnings"]


@pytest.mark.asyncio
async def test_ready_503_when_startup_warnings_present(client: httpx.AsyncClient):
    app.state.startup_warnings = [{"phase": "telemetry_start", "error": "boom"}]
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["startup_warnings"]


@pytest.mark.asyncio
async def test_ready_ok_in_test_mode_without_warnings(client: httpx.AsyncClient):
    app.state.startup_warnings = []
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_ready_503_when_not_testing_and_db_pool_not_initialized(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(main_module, "_is_testing", lambda: False)
    monkeypatch.setattr(main_module, "is_db_pool_initialized", lambda: False)

    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["db_pool_initialized"] is False
