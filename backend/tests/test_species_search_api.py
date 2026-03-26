from unittest.mock import AsyncMock, patch
import uuid

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.config import settings
from app.database import get_db, init_db, close_db


class _MockClassifier:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


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
    label = f"test-species-{uuid.uuid4().hex[:10]}"
    scientific_name = f"Testus species {uuid.uuid4().hex[:6]}"
    common_name = f"Test Common {uuid.uuid4().hex[:6]}"
    localized_common = f"Prueba Comun {uuid.uuid4().hex[:6]}"

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier([label])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": scientific_name, "common_name": common_name, "taxa_id": 1234}),
    ) as mock_get_names, patch(
        "app.routers.species.taxonomy_service.get_localized_common_name",
        new=AsyncMock(return_value=localized_common),
    ) as mock_localized:
        response = await client.get(
            "/api/species/search?q=&limit=20&hydrate_missing=true",
            headers={"Accept-Language": "es"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == label
    assert payload[0]["scientific_name"] == scientific_name
    assert payload[0]["common_name"] == localized_common
    mock_get_names.assert_awaited_once_with(label)
    mock_localized.assert_awaited_once_with(1234, "es")


@pytest.mark.asyncio
async def test_species_search_without_hydration_keeps_missing_names_and_skips_lookup(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    label = f"test-species-{uuid.uuid4().hex[:10]}"

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier([label])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Cyanistes caeruleus", "common_name": "Blue Tit", "taxa_id": 1234}),
    ) as mock_get_names:
        response = await client.get("/api/species/search?q=&limit=20")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == label
    assert payload[0]["scientific_name"] is None
    assert payload[0]["common_name"] is None
    mock_get_names.assert_not_awaited()


@pytest.mark.asyncio
async def test_species_search_hydration_failure_is_non_fatal(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    label = f"test-species-{uuid.uuid4().hex[:10]}"

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier([label])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(side_effect=RuntimeError("taxonomy unavailable")),
    ) as mock_get_names:
        response = await client.get("/api/species/search?q=&limit=20&hydrate_missing=true")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == label
    assert payload[0]["scientific_name"] is None
    assert payload[0]["common_name"] is None
    mock_get_names.assert_awaited_once_with(label)


@pytest.mark.asyncio
async def test_species_search_hydration_strips_parenthetical_classifier_suffix(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    label = "Cassin's Finch (Adult Male)"

    with patch("app.routers.species.get_classifier", return_value=_MockClassifier([label])), patch(
        "app.routers.species.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Haemorhous cassinii", "common_name": "Cassin's Finch", "taxa_id": 4567}),
    ) as mock_get_names:
        response = await client.get("/api/species/search?q=&limit=20&hydrate_missing=true")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == label
    assert payload[0]["scientific_name"] == "Haemorhous cassinii"
    assert payload[0]["common_name"] == "Cassin's Finch"
    mock_get_names.assert_awaited_once_with("Cassin's Finch")


@pytest.mark.asyncio
async def test_species_search_deduplicates_classifier_alias_labels_to_one_canonical_species(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    taxa_id = 145252

    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Parus major", "Great Tit", taxa_id),
        )
        await db.commit()

    labels = [
        "Great tit",
        "Great tit (Parus major)",
        "Parus major (Great tit)",
    ]

    try:
        with patch("app.routers.species.get_classifier", return_value=_MockClassifier(labels)):
            response = await client.get("/api/species/search?q=great&limit=20")

        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["id"] == "Parus major"
        assert payload[0]["scientific_name"] == "Parus major"
        assert payload[0]["common_name"] == "Great Tit"
        assert payload[0]["display_name"] == "Parus major"
        assert payload[0]["taxa_id"] == taxa_id
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
            await db.commit()
