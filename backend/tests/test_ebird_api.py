import httpx
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_ebird_settings():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_ebird_enabled = settings.ebird.enabled
    original_ebird_api_key = settings.ebird.api_key
    original_lat = settings.location.latitude
    original_lng = settings.location.longitude

    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.ebird.enabled = True
    settings.ebird.api_key = "test-token"
    settings.location.latitude = 51.501
    settings.location.longitude = -0.142

    yield

    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.ebird.enabled = original_ebird_enabled
    settings.ebird.api_key = original_ebird_api_key
    settings.location.latitude = original_lat
    settings.location.longitude = original_lng


@pytest.mark.asyncio
async def test_ebird_notable_tolerates_thumbnail_enrichment_failure(client: httpx.AsyncClient):
    sample = [{
        "speciesCode": "eucdov",
        "comName": "Eurasian Collared-Dove",
        "sciName": "Streptopelia decaocto",
        "obsDt": "2026-03-14 08:30",
        "locName": "Nearby Reserve",
        "howMany": 1,
        "lat": 51.5,
        "lng": -0.14,
        "obsValid": True,
        "obsReviewed": False
    }]

    with patch("app.routers.ebird.ebird_service.get_recent_observations", new=AsyncMock(return_value=sample)), \
         patch("app.routers.ebird.taxonomy_service.get_names", new=AsyncMock(side_effect=RuntimeError("taxonomy failed"))):
        response = await client.get("/api/ebird/notable")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["results"]) == 1
    assert payload["results"][0]["common_name"] == "Eurasian Collared-Dove"
    assert "thumbnail_url" not in payload["results"][0]
