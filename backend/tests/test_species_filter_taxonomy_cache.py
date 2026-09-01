"""A taxon filter must find rows that only the taxonomy cache can identify (#365).

The general query resolves a taxon through the cache -
COALESCE(d.taxa_id, tc_filter.taxa_id) - so a detection whose own taxa_id was
never filled still answers a `taxa:` filter. The seek-per-term fast path added
for #258 checked only the row's own column, so on a database where those ids
are patchy the same filter returned nothing at all - and adding a date range
"fixed" it, because that routes back to the general query.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_db, get_db, init_db
from app.main import app

TAXON = 13988


@pytest_asyncio.fixture(autouse=True)
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.execute("DELETE FROM taxonomy_cache")
            # The row carries a name but never received its own taxon id.
            await db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index,
                   score, display_name, category_name, scientific_name, taxa_id, is_hidden)
                   VALUES ('cache_only', 'cam1', '2026-08-30 09:00:00', 1, 0.9,
                           'Dunnock', 'Dunnock', 'Prunella modularis', NULL, 0)"""
            )
            await db.execute(
                """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id)
                   VALUES ('Prunella modularis', 'Dunnock', ?)""",
                (TAXON,),
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_taxon_filter_finds_a_cache_identified_row_without_a_date_range():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/events?species=taxa:{TAXON}")
        assert res.status_code == 200
        assert [d["frigate_event"] for d in res.json()] == ["cache_only"]


@pytest.mark.asyncio
async def test_the_date_range_answer_and_the_bare_answer_agree():
    """The reporter's own diagnostic: a date range must not change what exists."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bare = await client.get(f"/api/events?species=taxa:{TAXON}")
        dated = await client.get(f"/api/events?species=taxa:{TAXON}&start_date=2020-01-01")
        assert [d["frigate_event"] for d in bare.json()] == [d["frigate_event"] for d in dated.json()]


@pytest.mark.asyncio
async def test_the_cache_branches_are_still_seeks():
    """#258's whole point was that this filter stops reading the table; the
    cache-identified branches must not quietly bring the scan back."""
    from app.repositories.detection_repository import DetectionRepository

    async with get_db() as db:
        repo = DetectionRepository(db)
        taxa_ids, names, cache_names = await repo._collect_species_filter_terms(None, None, TAXON)
        assert cache_names, "expected the cache to contribute names for this taxon"
        query, params = repo._build_species_fast_path_query(
            taxa_ids=taxa_ids,
            names=names,
            cache_names=cache_names,
            limit=50,
            offset=0,
            sort="newest",
            include_hidden=False,
            hidden_only=False,
        )
        async with db.execute("EXPLAIN QUERY PLAN " + query, params) as cursor:
            plan = [str(row[3]) for row in await cursor.fetchall()]
        assert [line for line in plan if line.startswith("SCAN detections")] == [], plan
