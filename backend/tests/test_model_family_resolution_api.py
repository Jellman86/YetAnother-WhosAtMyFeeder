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
def reset_settings():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_country = settings.location.country
    original_override = settings.classification.bird_model_region_override
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.location.country = original_country
    settings.classification.bird_model_region_override = original_override


@pytest.mark.asyncio
async def test_model_family_resolution_api_uses_auto_country_resolution(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.location.country = "GB"
    settings.classification.bird_model_region_override = "auto"

    response = await client.get("/api/models/families/resolved")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["small_birds"]["effective_region"] == "eu"
    assert payload["small_birds"]["selection_source"] == "auto"
    assert payload["medium_birds"]["effective_region"] == "eu"
    assert payload["medium_birds"]["selection_source"] == "auto"


@pytest.mark.asyncio
async def test_model_family_resolution_api_prefers_manual_override(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.location.country = "GB"
    settings.classification.bird_model_region_override = "na"

    response = await client.get("/api/models/families/resolved")
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["small_birds"]["effective_region"] == "na"
    assert payload["small_birds"]["selection_source"] == "manual"
