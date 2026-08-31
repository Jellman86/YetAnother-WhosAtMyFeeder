"""A rare species must answer by seek, not by reading the whole history (#258).

The reporter measured it precisely: species with thousands of detections
filter instantly, species with under a hundred hang, and adding a date range
fixes the hang. The cause is the time-ordered page walk - the fewer matching
rows, the more of the table it reads before the page fills. The fast path
under test takes one newest-first seek per species term instead, and the
alias resolution that used to scan the detections table on every filtered
request is cached briefly.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository, clear_species_alias_cache


@pytest_asyncio.fixture(autouse=True)
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            rows = []
            for i in range(600):
                rows.append(
                    (
                        f"common_{i}",
                        "cam1",
                        f"2026-08-{(i // 60) % 28 + 1:02d} 10:{(i // 60) // 28:02d}:{i % 60:02d}",
                        1,
                        0.9,
                        "Common Bird",
                        "Common Bird",
                        "Communis avis",
                        111,
                        0,
                    )
                )
            for i, day in enumerate((3, 14, 27)):
                rows.append(
                    (
                        f"rare_{i}",
                        "cam1",
                        f"2026-08-{day:02d} 06:00:00",
                        1,
                        0.4,
                        "Rare Bird",
                        "Rare Bird",
                        "Rarus avis",
                        999,
                        0,
                    )
                )
            rows.append(
                (
                    "rare_hidden",
                    "cam1",
                    "2026-08-28 06:00:00",
                    1,
                    0.4,
                    "Rare Bird",
                    "Rare Bird",
                    "Rarus avis",
                    999,
                    1,
                )
            )
            await db.executemany(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                   display_name, category_name, scientific_name, taxa_id, is_hidden)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_rare_species_filter_returns_all_its_rows_newest_first():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events?species=Rare%20Bird")
        assert res.status_code == 200
        events = [d["frigate_event"] for d in res.json()]
        assert events == ["rare_2", "rare_1", "rare_0"]


@pytest.mark.asyncio
async def test_fast_path_matches_the_general_path_for_a_common_species():
    async with get_db() as db:
        repo = DetectionRepository(db)
        fast = await repo.get_all(species="Common Bird", limit=50, offset=25)
        # A date range disqualifies the fast path, so this is the general
        # query answering the same question.
        general = await repo.get_all(
            species="Common Bird",
            limit=50,
            offset=25,
            start_date=__import__("datetime").datetime(2020, 1, 1),
        )
        assert [d.frigate_event for d in fast] == [d.frigate_event for d in general]
        assert len(fast) == 50


@pytest.mark.asyncio
async def test_fast_path_query_never_scans_the_detections_table():
    async with get_db() as db:
        repo = DetectionRepository(db)
        taxa_ids, names = await repo._collect_species_filter_terms("Rare Bird", None, None)
        query, params = repo._build_species_fast_path_query(
            taxa_ids=taxa_ids,
            names=names,
            limit=50,
            offset=0,
            sort="newest",
            include_hidden=False,
            hidden_only=False,
        )
        async with db.execute("EXPLAIN QUERY PLAN " + query, params) as cursor:
            plan = [str(row[3]) for row in await cursor.fetchall()]
        scans = [line for line in plan if line.startswith("SCAN detections")]
        assert scans == [], plan


@pytest.mark.asyncio
async def test_fast_path_respects_hidden_semantics():
    async with get_db() as db:
        repo = DetectionRepository(db)
        default = await repo.get_all(species="Rare Bird")
        assert all(not d.is_hidden for d in default)
        assert len(default) == 3

        only_hidden = await repo.get_all(species="Rare Bird", hidden_only=True)
        assert [d.frigate_event for d in only_hidden] == ["rare_hidden"]


@pytest.mark.asyncio
async def test_alias_resolution_is_cached_within_the_ttl():
    async with get_db() as db:
        repo = DetectionRepository(db)
        clear_species_alias_cache()
        first = await repo.resolve_species_aliases("Rare Bird")

        calls: list[str] = []
        original_execute = db.execute

        def counting_execute(query, *args, **kwargs):
            calls.append(str(query))
            return original_execute(query, *args, **kwargs)

        db.execute = counting_execute
        second = await repo.resolve_species_aliases("Rare Bird")
        db.execute = original_execute

        assert second == first
        detection_reads = [q for q in calls if "FROM detections" in q]
        assert detection_reads == []
