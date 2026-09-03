"""A species with no Wikipedia article must not be searched for again every minute.

On a live install the species page took up to twelve seconds for a bird the
search could not find, and the same birds recurred in the log, because a lookup
that found nothing was cached for one minute like a lookup that had failed. A
request that timed out deserves a quick retry; a search that ran every strategy
and found nothing does not change in the next sixty seconds.
"""

from datetime import datetime, timedelta

import pytest

from app.routers import species as species_router
from app.routers.species import (
    CACHE_TTL_FAILURE,
    CACHE_TTL_NOT_FOUND,
    SpeciesInfo,
    _is_cache_valid,
    _remember_definitive_miss,
)


def _empty(name="Sooty Fox Sparrow") -> SpeciesInfo:
    return SpeciesInfo(
        title=name,
        description=None,
        extract=None,
        thumbnail_url=None,
        wikipedia_url=None,
        source=None,
        source_url=None,
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now(),
    )


@pytest.fixture(autouse=True)
def clean_markers():
    species_router._definitive_misses.clear()
    yield
    species_router._definitive_misses.clear()


def test_a_lookup_that_errored_is_retried_after_a_minute():
    info = _empty()
    assert _is_cache_valid(info, datetime.now() - timedelta(seconds=30), "Sooty Fox Sparrow:en")
    assert not _is_cache_valid(info, datetime.now() - CACHE_TTL_FAILURE - timedelta(seconds=1), "Sooty Fox Sparrow:en")


def test_a_search_that_found_nothing_is_remembered_for_much_longer():
    info = _empty()
    _remember_definitive_miss("Sooty Fox Sparrow:en")
    assert _is_cache_valid(info, datetime.now() - timedelta(hours=6), "Sooty Fox Sparrow:en")
    assert not _is_cache_valid(
        info, datetime.now() - CACHE_TTL_NOT_FOUND - timedelta(seconds=1), "Sooty Fox Sparrow:en"
    )
    assert CACHE_TTL_NOT_FOUND > CACHE_TTL_FAILURE * 60


def test_a_found_article_is_unaffected():
    found = _empty()
    found.extract = "A small brown bird."
    assert _is_cache_valid(found, datetime.now() - timedelta(hours=23), "Sooty Fox Sparrow:en")


@pytest.mark.asyncio
async def test_the_search_reports_whether_its_miss_was_definitive(monkeypatch):
    """Every strategy ran and found nothing: definitive. A strategy raised: not."""
    import httpx

    calls = {"n": 0}

    class Boom(httpx.AsyncClient):
        async def get(self, *a, **k):
            calls["n"] += 1
            raise httpx.ConnectError("down")

    class Empty(httpx.AsyncClient):
        async def get(self, *a, **k):
            calls["n"] += 1
            return httpx.Response(200, json={"query": {"search": []}, "pages": {}})

    async with Boom() as boom:
        title, definitive = await species_router._find_wikipedia_article(boom, "Sooty Fox Sparrow", "en")
    assert title is None and definitive is False

    async with Empty() as empty:
        title, definitive = await species_router._find_wikipedia_article(empty, "Sooty Fox Sparrow", "en")
    assert title is None and definitive is True
