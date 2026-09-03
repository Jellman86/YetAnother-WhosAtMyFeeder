"""A name lookup must never wait on iNaturalist while a pooled connection is held.

The pool has five connections. Eleven call sites handed one to the taxonomy
lookup and let it go to the network with a ten second timeout, so one uncached
species could stall everything else needing the database (#392, and the same
disease as #300). Rather than rewrite every caller, the lookup itself now knows
whether the calling task holds a connection: if it does, it answers from cache
and fills the cache off the request, so the next render has the name.
"""

import asyncio

import pytest
import pytest_asyncio

from app.database import close_db, get_db, get_db_pool_status, init_db, pooled_connection_held
from app.services.taxonomy.taxonomy_service import taxonomy_service

NETWORK_DELAY_SECONDS = 0.4


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM taxonomy_translations")
            await db.commit()
        taxonomy_service._background_fills.clear()
        yield
    finally:
        await close_db()


@pytest.fixture
def slow_network(monkeypatch):
    calls: list[tuple[int, str]] = []

    async def slow_inaturalist(taxa_id, lang):
        calls.append((taxa_id, lang))
        await asyncio.sleep(NETWORK_DELAY_SECONDS)
        return f"Blaumeise-{taxa_id}"

    monkeypatch.setattr(taxonomy_service, "_lookup_localized_inaturalist", slow_inaturalist)
    return calls


@pytest.mark.asyncio
async def test_inside_a_hold_the_lookup_answers_from_cache_and_fills_in_the_background(slow_network):
    async with get_db() as db:
        assert pooled_connection_held()
        started = asyncio.get_event_loop().time()
        name = await taxonomy_service.get_localized_common_name(13094, "de", db=db)
        elapsed = asyncio.get_event_loop().time() - started

    assert name is None, "an uncached name is not waited for while a connection is held"
    assert elapsed < NETWORK_DELAY_SECONDS / 2
    assert get_db_pool_status()["hold_ms_max"] < NETWORK_DELAY_SECONDS * 1000 / 2

    await taxonomy_service.wait_for_background_fills()
    assert slow_network == [(13094, "de")]
    assert await taxonomy_service.get_localized_common_name(13094, "de") == "Blaumeise-13094"


@pytest.mark.asyncio
async def test_outside_a_hold_the_lookup_still_waits_for_the_network(slow_network):
    assert not pooled_connection_held()
    name = await taxonomy_service.get_localized_common_name(13094, "de")
    assert name == "Blaumeise-13094"
    assert slow_network == [(13094, "de")]


@pytest.mark.asyncio
async def test_a_page_of_rows_schedules_one_fill_per_name_not_one_per_row(slow_network):
    async with get_db() as db:
        results = await asyncio.gather(
            *(taxonomy_service.get_localized_common_name(13094, "de", db=db) for _ in range(6))
        )
    assert results == [None] * 6
    await taxonomy_service.wait_for_background_fills()
    assert slow_network == [(13094, "de")]


@pytest.mark.asyncio
async def test_a_cached_name_is_returned_inside_a_hold_without_touching_the_network(slow_network):
    async with get_db() as db:
        await taxonomy_service._save_translation_to_cache(13094, "de", "Blaumeise", db=db)
        assert await taxonomy_service.get_localized_common_name(13094, "de", db=db) == "Blaumeise"
    assert slow_network == []
