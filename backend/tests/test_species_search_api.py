from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.config import settings


class _MockClassifier:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels


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
async def test_species_search_hydrates_missing_taxonomy_with_localized_common_name(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier(["Blue Tit"])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Cyanistes caeruleus", "common_name": "Blue Tit", "taxa_id": 1234}),
    ) as mock_get_names, patch(
        "app.routers.species.taxonomy_service.get_localized_common_name",
        new=AsyncMock(return_value="Herrerillo comun"),
    ) as mock_localized:
        response = await client.get(
            "/api/species/search?q=&limit=20&hydrate_missing=true",
            headers={"Accept-Language": "es"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "Blue Tit"
    assert payload[0]["scientific_name"] == "Cyanistes caeruleus"
    assert payload[0]["common_name"] == "Herrerillo comun"
    mock_get_names.assert_awaited_once_with("Blue Tit")
    mock_localized.assert_awaited_once_with(1234, "es")


@pytest.mark.asyncio
async def test_species_search_without_hydration_keeps_missing_names_and_skips_lookup(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier(["Blue Tit"])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Cyanistes caeruleus", "common_name": "Blue Tit", "taxa_id": 1234}),
    ) as mock_get_names:
        response = await client.get("/api/species/search?q=&limit=20")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "Blue Tit"
    assert payload[0]["scientific_name"] is None
    assert payload[0]["common_name"] is None
    mock_get_names.assert_not_awaited()


@pytest.mark.asyncio
async def test_species_search_hydration_failure_is_non_fatal(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier(["Blue Tit"])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(side_effect=RuntimeError("taxonomy unavailable")),
    ) as mock_get_names:
        response = await client.get("/api/species/search?q=&limit=20&hydrate_missing=true")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "Blue Tit"
    assert payload[0]["scientific_name"] is None
    assert payload[0]["common_name"] is None
    mock_get_names.assert_awaited_once_with("Blue Tit")
