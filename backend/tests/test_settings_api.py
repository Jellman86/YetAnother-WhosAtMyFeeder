import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


@pytest.mark.asyncio
async def test_settings_roundtrip_personalized_rerank_enabled(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    get_before = await client.get("/api/settings")
    assert get_before.status_code == 200, get_before.text
    before_payload = get_before.json()

    assert "personalized_rerank_enabled" in before_payload

    update_payload = {
        "frigate_url": before_payload["frigate_url"],
        "mqtt_server": before_payload["mqtt_server"],
        "classification_threshold": before_payload["classification_threshold"],
        "personalized_rerank_enabled": True,
    }
    post_resp = await client.post("/api/settings", json=update_payload)
    assert post_resp.status_code == 200, post_resp.text

    get_after = await client.get("/api/settings")
    assert get_after.status_code == 200, get_after.text
    after_payload = get_after.json()
    assert after_payload["personalized_rerank_enabled"] is True
