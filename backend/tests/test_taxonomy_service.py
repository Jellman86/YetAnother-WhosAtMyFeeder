import pytest
import aiosqlite
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from app.services.taxonomy.taxonomy_service import (
    TAXONOMY_NOT_FOUND_RETRY_SECONDS,
    TaxonomyLookupUnavailable,
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
                   scientific_name TEXT, common_name TEXT, manual_common_name TEXT, taxa_id INTEGER,
                   is_not_found INTEGER, thumbnail_url TEXT, last_updated TEXT)"""
        )
        await db.executemany(
            "INSERT INTO taxonomy_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("Dryobates villosus", None, None, None, 1, None, stale),
                ("Chloris chloris", None, None, None, 1, None, fresh),
                ("Parus major", "Great Tit", None, 145252, 0, None, stale),
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


@pytest.mark.asyncio
async def test_successful_alias_retry_replaces_the_expired_negative_entry(taxonomy_service):
    stale = (datetime.now() - timedelta(seconds=TAXONOMY_NOT_FOUND_RETRY_SECONDS + 60)).isoformat(sep=" ")
    resolved = {
        "scientific_name": "Cyanistes caeruleus",
        "common_name": "Blue Tit",
        "taxa_id": 303,
        "thumbnail_url": None,
    }
    taxonomy_service._lookup_inaturalist = AsyncMock(return_value=resolved)

    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """CREATE TABLE taxonomy_cache (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   scientific_name TEXT NOT NULL UNIQUE,
                   common_name TEXT, manual_common_name TEXT, taxa_id INTEGER, is_not_found INTEGER,
                   thumbnail_url TEXT, last_updated TEXT)"""
        )
        await db.execute(
            """INSERT INTO taxonomy_cache
               (scientific_name, common_name, taxa_id, is_not_found, thumbnail_url, last_updated)
               VALUES (?, NULL, NULL, 1, NULL, ?)""",
            ("Blue Tit", stale),
        )
        await db.commit()

        assert await taxonomy_service.get_names("Blue Tit", db=db) == resolved
        await db.commit()
        assert await taxonomy_service.get_names("Blue Tit", db=db) == {
            **resolved,
            "is_not_found": False,
        }

        async with db.execute(
            "SELECT scientific_name, common_name, is_not_found FROM taxonomy_cache ORDER BY id"
        ) as cursor:
            rows = await cursor.fetchall()

    taxonomy_service._lookup_inaturalist.assert_awaited_once_with("Blue Tit")
    assert rows == [("Cyanistes caeruleus", "Blue Tit", 0)]


@pytest.mark.asyncio
async def test_get_names_does_not_cache_not_found_when_the_lookup_is_unavailable(taxonomy_service):
    """A provider that cannot answer must not be recorded as "no such species".

    An unreachable or rate-limited provider is unrelated to whether the taxon
    exists. Caching that as not-found leaves a species without its common name
    until something else repairs the row.
    """
    with (
        patch.object(taxonomy_service, "_get_from_cache", AsyncMock(return_value=None)),
        patch.object(
            taxonomy_service,
            "_lookup_inaturalist",
            AsyncMock(side_effect=TaxonomyLookupUnavailable("timeout")),
        ),
        patch.object(taxonomy_service, "_save_to_cache", AsyncMock()) as mock_save,
    ):
        result = await taxonomy_service.get_names("Dryobates pubescens")

    assert result["scientific_name"] == "Dryobates pubescens"
    # The bundled reference answers when the provider cannot, so the species is
    # named rather than left bare. The point of this test is the line below: the
    # outage is still not recorded as "no such species".
    assert result["common_name"] == "Downy Woodpecker"
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_inaturalist_raises_when_the_request_fails(taxonomy_service):
    failing_client = AsyncMock()
    failing_client.get = AsyncMock(side_effect=RuntimeError("connection reset"))

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=failing_client)):
        with pytest.raises(TaxonomyLookupUnavailable):
            await taxonomy_service._lookup_inaturalist("Dryobates pubescens")


@pytest.mark.asyncio
async def test_lookup_inaturalist_returns_none_when_the_provider_reports_no_match(taxonomy_service):
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: {"total_results": 0, "results": []}
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        assert await taxonomy_service._lookup_inaturalist("Nonexistent species") is None


@pytest.mark.asyncio
async def test_lookup_inaturalist_rejects_an_inconsistent_success_payload(taxonomy_service):
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: {"total_results": 1, "results": []}
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        with pytest.raises(TaxonomyLookupUnavailable):
            await taxonomy_service._lookup_inaturalist("Blue Tit")


def _taxa_response(results):
    """An iNaturalist `/v1/taxa` success payload carrying *results*."""
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: {"total_results": len(results), "results": list(results)}
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    return client


def _taxon(taxa_id, name, common, matched_term, rank="species"):
    return {
        "id": taxa_id,
        "name": name,
        "preferred_common_name": common,
        "matched_term": matched_term,
        "rank": rank,
        "default_photo": {"square_url": f"https://example.invalid/{taxa_id}.jpg"},
    }


#: Recorded from `GET /v1/taxa?q=Regulus regulus` on 2026-08-24. The first hit
#: is a different bird on a different continent: it ranks above the exact match
#: because `Regulus calendula` is a synonym of the far more observed
#: Ruby-crowned Kinglet. Goldcrest, the bird actually asked about, is fourth.
_REGULUS_REGULUS_PAGE = [
    _taxon(1289388, "Corthylio calendula", "Ruby-crowned Kinglet", "Regulus calendula"),
    _taxon(19660, "Regulus", "Firecrests, Goldcrests, and Allies", "Regulus", rank="genus"),
    _taxon(117100, "Regulus satrapa", "Golden-crowned Kinglet", "Regulus satrapa"),
    _taxon(793469, "Regulus regulus", "Goldcrest", "Regulus regulus"),
]


@pytest.mark.asyncio
async def test_a_fuzzy_first_hit_that_matched_a_different_name_is_not_taken(taxonomy_service):
    """iNaturalist's `q=` is a search, not a lookup, and its first result is
    whatever ranks highest -- not necessarily the species asked for. Taking it
    unchecked recorded a Goldcrest at a British feeder as a Ruby-crowned
    Kinglet, a bird of North America.
    """
    client = _taxa_response(_REGULUS_REGULUS_PAGE)

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        result = await taxonomy_service._lookup_inaturalist("Regulus regulus")

    assert result["scientific_name"] == "Regulus regulus"
    assert result["common_name"] == "Goldcrest"
    assert result["taxa_id"] == 793469


@pytest.mark.asyncio
async def test_a_query_that_is_itself_a_synonym_still_resolves_to_the_accepted_taxon(taxonomy_service):
    """Rejecting the fuzzy hit must not reject a real rename. A model trained
    on the older name asks for `Regulus calendula`, and that is exactly the
    term this taxon matched on, so it is the right answer."""
    client = _taxa_response(
        [
            _taxon(1289388, "Corthylio calendula", "Ruby-crowned Kinglet", "Regulus calendula"),
            _taxon(
                1289786,
                "Corthylio calendula calendula",
                "Northern Ruby-crowned Kinglet",
                "Regulus calendula calendula",
                rank="subspecies",
            ),
        ]
    )

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        result = await taxonomy_service._lookup_inaturalist("Regulus calendula")

    assert result["scientific_name"] == "Corthylio calendula"
    assert result["taxa_id"] == 1289388


@pytest.mark.asyncio
async def test_a_common_name_query_resolves_to_the_species_not_the_genus(taxonomy_service):
    """Recorded from `q=Ruby-crowned Kinglet`: the genus ranks first because
    its plural common name matched. A genus is not a species, and enrichment
    that returns one loses the bird."""
    client = _taxa_response(
        [
            _taxon(1289298, "Corthylio", "Ruby-crowned Kinglets", "Ruby-crowned Kinglets", rank="genus"),
            _taxon(1289388, "Corthylio calendula", "Ruby-crowned Kinglet", "Ruby-crowned Kinglet"),
        ]
    )

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        result = await taxonomy_service._lookup_inaturalist("Ruby-crowned Kinglet")

    assert result["scientific_name"] == "Corthylio calendula"
    assert result["taxa_id"] == 1289388


@pytest.mark.asyncio
async def test_an_exact_first_hit_is_still_taken(taxonomy_service):
    client = _taxa_response(
        [
            _taxon(144849, "Cyanistes caeruleus", "Eurasian Blue Tit", "Cyanistes caeruleus"),
            _taxon(
                722264,
                "Cyanistes caeruleus caeruleus",
                "Common Blue Tit",
                "Cyanistes caeruleus caeruleus",
                rank="subspecies",
            ),
        ]
    )

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        result = await taxonomy_service._lookup_inaturalist("Cyanistes caeruleus")

    assert result["taxa_id"] == 144849


@pytest.mark.asyncio
async def test_a_page_holding_nothing_that_was_asked_for_reports_no_match(taxonomy_service):
    """Better to name the bird what the model called it than to name it
    something else. No match here leaves the model's own label standing."""
    client = _taxa_response(
        [
            _taxon(19660, "Regulus", "Firecrests, Goldcrests, and Allies", "Regulus", rank="genus"),
            _taxon(117100, "Regulus satrapa", "Golden-crowned Kinglet", "Regulus satrapa"),
        ]
    )

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        assert await taxonomy_service._lookup_inaturalist("Regulus madeirensis") is None


@pytest.mark.asyncio
async def test_the_lookup_asks_for_more_than_one_candidate(taxonomy_service):
    """A single-result page cannot be checked: if the one result is wrong there
    is nothing to fall back to."""
    client = _taxa_response(_REGULUS_REGULUS_PAGE)

    with patch.object(taxonomy_service, "_get_client", AsyncMock(return_value=client)):
        await taxonomy_service._lookup_inaturalist("Regulus regulus")

    assert client.get.await_args.kwargs["params"]["per_page"] > 1
