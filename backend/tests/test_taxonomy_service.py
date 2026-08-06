import pytest
import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from app.services.taxonomy.taxonomy_service import (
    TAXONOMY_NOT_FOUND_RETRY_SECONDS,
    TaxonomyService,
    _negative_entry_expired,
    _parenthetical_aliases,
)


@pytest.fixture
def taxonomy_service():
    return TaxonomyService()


def test_parenthetical_aliases_are_linear_and_preserve_existing_semantics():
    assert _parenthetical_aliases("Blue Jay (Cyanocitta cristata)") == ("Blue Jay", "Cyanocitta cristata")
    assert _parenthetical_aliases("Blue Jay") == (None, None)
    assert _parenthetical_aliases("(" + "a" * 100_000) == (None, None)


@pytest.mark.asyncio
async def test_get_names_cached(taxonomy_service):
    # Mock cache hit
    mock_cached = {"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "taxa_id": 123}
    with patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=mock_cached)):
        result = await taxonomy_service.get_names("Blue Jay")
        assert result == mock_cached

    # Verify it doesn't call API if cached
    with (
        patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=mock_cached)),
        patch.object(taxonomy_service, "_lookup_inaturalist", AsyncMock()) as mock_lookup,
    ):
        await taxonomy_service.get_names("Blue Jay")
        mock_lookup.assert_not_called()


@pytest.mark.asyncio
async def test_get_names_api_success(taxonomy_service):
    # Mock cache miss then API success
    mock_api_result = {"scientific_name": "Passer domesticus", "common_name": "House Sparrow", "taxa_id": 456}
    with (
        patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=None)),
        patch.object(taxonomy_service, "_lookup_inaturalist", AsyncMock(return_value=mock_api_result)),
        patch.object(taxonomy_service, "_save_to_cache", AsyncMock()) as mock_save,
    ):
        result = await taxonomy_service.get_names("House Sparrow")
        assert result == mock_api_result
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_get_names_not_found(taxonomy_service):
    # Mock cache miss then API failure
    with (
        patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=None)),
        patch.object(taxonomy_service, "_lookup_inaturalist", AsyncMock(return_value=None)),
        patch.object(taxonomy_service, "_save_to_cache", AsyncMock()) as mock_save,
    ):
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
            category_name TEXT,
            display_name TEXT,
            scientific_name TEXT,
            common_name TEXT,
            taxa_id INTEGER
        )
        """
    )
    await db.execute(
        "INSERT INTO detections (category_name, display_name, scientific_name, common_name, taxa_id) VALUES (?, ?, ?, ?, ?)",
        ("Unknown Bird", "Unknown Bird", None, None, None),
    )
    await db.execute(
        "INSERT INTO detections (category_name, display_name, scientific_name, common_name, taxa_id) VALUES (?, ?, ?, ?, ?)",
        ("Blue Jay", "Blue Jay", None, None, None),
    )
    await db.commit()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    with (
        patch("app.services.taxonomy.taxonomy_service.get_db", fake_get_db),
        patch.object(
            taxonomy_service,
            "get_names",
            AsyncMock(
                return_value={"scientific_name": "Cyanocitta cristata", "common_name": "Blue Jay", "taxa_id": 202}
            ),
        ) as mock_get_names,
    ):
        await taxonomy_service.run_background_sync()

    mock_get_names.assert_awaited_once_with("Blue Jay", db=db, force_refresh=True)
    status = taxonomy_service.get_sync_status()
    assert status["total"] == 1
    assert status["processed"] == 1
    assert status["is_running"] is False

    async with db.execute(
        "SELECT scientific_name, common_name, taxa_id FROM detections WHERE display_name = ?", ("Blue Jay",)
    ) as cursor:
        row = await cursor.fetchone()
    assert row == ("Cyanocitta cristata", "Blue Jay", 202)

    async with db.execute(
        "SELECT scientific_name, common_name, taxa_id FROM detections WHERE display_name = ?", ("Unknown Bird",)
    ) as cursor:
        unknown_row = await cursor.fetchone()
    assert unknown_row == (None, None, None)

    await db.close()


@pytest.mark.asyncio
async def test_run_background_sync_prefers_stored_scientific_name_for_repair(taxonomy_service):
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """
        CREATE TABLE detections (
            category_name TEXT,
            display_name TEXT,
            scientific_name TEXT,
            common_name TEXT,
            taxa_id INTEGER
        )
        """
    )
    await db.execute(
        """
        INSERT INTO detections (category_name, display_name, scientific_name, common_name, taxa_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Cyanistes caeruleus", "Herrerillo común", "Cyanistes caeruleus", None, None),
    )
    await db.commit()

    @asynccontextmanager
    async def fake_get_db():
        yield db

    async def lookup(name: str, db=None, force_refresh: bool = False):
        if name == "Cyanistes caeruleus":
            return {
                "scientific_name": "Cyanistes caeruleus",
                "common_name": "Blue Tit",
                "taxa_id": 303,
            }
        return {
            "scientific_name": name,
            "common_name": None,
            "taxa_id": None,
        }

    with (
        patch("app.services.taxonomy.taxonomy_service.get_db", fake_get_db),
        patch.object(
            taxonomy_service,
            "get_names",
            AsyncMock(side_effect=lookup),
        ) as mock_get_names,
    ):
        await taxonomy_service.run_background_sync()

    mock_get_names.assert_awaited_once_with("Cyanistes caeruleus", db=db, force_refresh=True)

    async with db.execute(
        "SELECT scientific_name, common_name, taxa_id FROM detections WHERE display_name = ?",
        ("Herrerillo común",),
    ) as cursor:
        row = await cursor.fetchone()

    assert row == ("Cyanistes caeruleus", "Blue Tit", 303)
    await db.close()


def test_negative_cache_entry_expires_after_the_retry_window():
    """A cached "not found" is a guess and has to be re-tested eventually."""
    now = datetime(2026, 8, 6, 12, 0, 0)
    fresh = now - timedelta(seconds=TAXONOMY_NOT_FOUND_RETRY_SECONDS / 2)
    stale = now - timedelta(seconds=TAXONOMY_NOT_FOUND_RETRY_SECONDS + 60)

    assert _negative_entry_expired(fresh.isoformat(sep=" "), now=now) is False
    assert _negative_entry_expired(stale.isoformat(sep=" "), now=now) is True
    # Both timestamp shapes are in use: datetime.now() writes microseconds,
    # the column default writes CURRENT_TIMESTAMP without them.
    assert _negative_entry_expired(stale.strftime("%Y-%m-%d %H:%M:%S"), now=now) is True
    assert _negative_entry_expired(fresh.strftime("%Y-%m-%d %H:%M:%S"), now=now) is False
    # Unknown or missing timestamps must not pin a negative result forever.
    assert _negative_entry_expired(None, now=now) is True
    assert _negative_entry_expired("not a timestamp", now=now) is True


@pytest.mark.asyncio
async def test_query_cache_treats_an_expired_negative_entry_as_a_miss(taxonomy_service):
    stale = (datetime.now() - timedelta(seconds=TAXONOMY_NOT_FOUND_RETRY_SECONDS + 60)).isoformat(sep=" ")
    fresh = datetime.now().isoformat(sep=" ")

    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """CREATE TABLE taxonomy_cache (
                   scientific_name TEXT, common_name TEXT, taxa_id INTEGER,
                   is_not_found INTEGER, thumbnail_url TEXT, last_updated TEXT)"""
        )
        await db.executemany(
            "INSERT INTO taxonomy_cache VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("Dryobates villosus", None, None, 1, None, stale),
                ("Chloris chloris", None, None, 1, None, fresh),
                ("Parus major", "Great Tit", 145252, 0, None, stale),
            ],
        )
        await db.commit()

        # Expired negative: re-lookup instead of trusting it.
        assert await taxonomy_service._query_cache(db, "Dryobates villosus") is None
        # Fresh negative: still short-circuits, so a real absence is not re-fetched constantly.
        chloris = await taxonomy_service._query_cache(db, "Chloris chloris")
        assert chloris is not None and chloris["is_not_found"] is True
        # A resolved row is unaffected by age.
        parus = await taxonomy_service._query_cache(db, "Parus major")
        assert parus is not None and parus["common_name"] == "Great Tit"
