import pytest
import aiosqlite
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from app.services.taxonomy.taxonomy_service import TaxonomyService

@pytest.fixture
def taxonomy_service():
    return TaxonomyService()

@pytest.mark.asyncio
async def test_get_names_cached(taxonomy_service):
    # Mock cache hit
    mock_cached = {
        "scientific_name": "Cyanocitta cristata",
        "common_name": "Blue Jay",
        "taxa_id": 123
    }
    with patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=mock_cached)):
        result = await taxonomy_service.get_names("Blue Jay")
        assert result == mock_cached
        
    # Verify it doesn't call API if cached
    with patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=mock_cached)), \
         patch.object(taxonomy_service, "_lookup_inaturalist", AsyncMock()) as mock_lookup:
        await taxonomy_service.get_names("Blue Jay")
        mock_lookup.assert_not_called()

@pytest.mark.asyncio
async def test_get_names_api_success(taxonomy_service):
    # Mock cache miss then API success
    mock_api_result = {
        "scientific_name": "Passer domesticus",
        "common_name": "House Sparrow",
        "taxa_id": 456
    }
    with patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=None)), \
         patch.object(taxonomy_service, "_lookup_inaturalist", AsyncMock(return_value=mock_api_result)), \
         patch.object(taxonomy_service, "_save_to_cache", AsyncMock()) as mock_save:
        
        result = await taxonomy_service.get_names("House Sparrow")
        assert result == mock_api_result
        mock_save.assert_called_once()

@pytest.mark.asyncio
async def test_get_names_not_found(taxonomy_service):
    # Mock cache miss then API failure
    with patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=None)), \
         patch.object(taxonomy_service, "_lookup_inaturalist", AsyncMock(return_value=None)), \
         patch.object(taxonomy_service, "_save_to_cache", AsyncMock()) as mock_save:
        
        result = await taxonomy_service.get_names("Unknown Species")
        assert result["scientific_name"] == "Unknown Species"
        assert result["common_name"] is None
        # Should save the failure to cache
        mock_save.assert_called_once()
        assert mock_save.call_args[0][0]["is_not_found"] is True


@pytest.mark.asyncio
async def test_run_background_sync_skips_unknown_bird_rows(taxonomy_service):
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """
        CREATE TABLE detections (
            display_name TEXT,
            scientific_name TEXT,
            common_name TEXT,
            taxa_id INTEGER
        )
        """
    )
    await db.execute(
        "INSERT INTO detections (display_name, scientific_name, common_name, taxa_id) VALUES (?, ?, ?, ?)",
        ("Unknown Bird", None, None, None)
    )
    await db.execute(
        "INSERT INTO detections (display_name, scientific_name, common_name, taxa_id) VALUES (?, ?, ?, ?)",
        ("Blue Jay", None, None, None)
    )
    await db.commit()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    with patch("app.services.taxonomy.taxonomy_service.get_db", fake_get_db), patch.object(
        taxonomy_service,
        "get_names",
        AsyncMock(return_value={
            "scientific_name": "Cyanocitta cristata",
            "common_name": "Blue Jay",
            "taxa_id": 202
        })
    ) as mock_get_names:
        await taxonomy_service.run_background_sync()

    mock_get_names.assert_awaited_once_with("Blue Jay", db=db)
    status = taxonomy_service.get_sync_status()
    assert status["total"] == 1
    assert status["processed"] == 1
    assert status["is_running"] is False

    async with db.execute(
        "SELECT scientific_name, common_name, taxa_id FROM detections WHERE display_name = ?",
        ("Blue Jay",)
    ) as cursor:
        row = await cursor.fetchone()
    assert row == ("Cyanocitta cristata", "Blue Jay", 202)

    async with db.execute(
        "SELECT scientific_name, common_name, taxa_id FROM detections WHERE display_name = ?",
        ("Unknown Bird",)
    ) as cursor:
        unknown_row = await cursor.fetchone()
    assert unknown_row == (None, None, None)

    await db.close()
