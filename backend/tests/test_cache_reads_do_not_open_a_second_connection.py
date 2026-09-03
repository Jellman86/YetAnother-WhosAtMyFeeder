"""Naming a species inside a hold must not open a second pooled connection.

The network guard (#393) stopped lookups waiting on iNaturalist inside a hold,
but the audio helpers then stopped lending the caller's connection to the
cache read as well, so a cache-only English lookup opened a second pooled
connection beside the one the route already held. Quark logged it as
"Nested DB connection acquire depth=2". With five connections and a dashboard
load fanning out a dozen requests, each such request took two.
"""

import pytest
import pytest_asyncio

from app.database import close_db, get_db, get_db_pool_status, init_db
from app.utils.audio_localization import localize_audio_detections, localize_audio_species_name


@pytest_asyncio.fixture(autouse=True)
async def seeded():
    await init_db()
    try:
        async with get_db() as db:
            for table in ("audio_detections", "taxonomy_translations", "taxonomy_cache"):
                await db.execute(f"DELETE FROM {table}")
            await db.execute(
                "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)"
                " VALUES ('Cyanistes caeruleus', 'Eurasian Blue Tit', 13094, 0, CURRENT_TIMESTAMP)"
            )
            await db.execute(
                "INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, scientific_name)"
                " VALUES (CURRENT_TIMESTAMP, 'Blue Tit', 0.8, 'mic1', 'Cyanistes caeruleus')"
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["en", "de"])
async def test_a_caller_holding_a_connection_lends_it_for_the_cache_read(lang):
    before = get_db_pool_status()["nested_acquires"]
    rows = [{"species": "Blue Tit", "scientific_name": "Cyanistes caeruleus"}]
    async with get_db() as db:
        await localize_audio_detections(rows, lang, db)
        await localize_audio_species_name("Blue Tit", lang, db)
        await localize_audio_species_name("Blue Tit", lang, db, confirmed_taxa_id=13094)
    assert get_db_pool_status()["nested_acquires"] == before, "a lookup opened a second connection inside the hold"
    assert rows[0]["species"] == "Eurasian Blue Tit" if lang == "en" else True


@pytest.mark.asyncio
async def test_a_caller_with_no_connection_still_works_and_nests_nothing():
    before = get_db_pool_status()["nested_acquires"]
    rows = [{"species": "Blue Tit", "scientific_name": "Cyanistes caeruleus"}]
    await localize_audio_detections(rows, "en")
    assert rows[0]["species"] == "Eurasian Blue Tit"
    assert get_db_pool_status()["nested_acquires"] == before
