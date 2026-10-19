"""Large histories must not scan every taxonomy row for each capture (#762)."""

from datetime import datetime, timedelta

import aiosqlite
import pytest

from app.repositories.detection_repository import DetectionRepository
from tests.test_detection_repository import _create_detections_table, _create_taxonomy_tables


@pytest.mark.asyncio
async def test_leaderboard_uses_indexed_taxonomy_lookups_within_instruction_budget():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        # The released schema already supplies these expression indexes.
        await db.execute("CREATE INDEX taxonomy_scientific ON taxonomy_cache(LOWER(scientific_name))")
        await db.execute("CREATE INDEX taxonomy_common ON taxonomy_cache(LOWER(common_name))")
        await db.execute("CREATE INDEX detection_time ON detections(detection_time)")
        await db.executemany(
            "INSERT INTO taxonomy_cache(scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            [(f"Scientific {i}", f"Common {i}", i + 1) for i in range(1000)],
        )
        start = datetime(2026, 9, 1)
        await db.executemany(
            """INSERT INTO detections(detection_time, detection_index, score, display_name,
                category_name, frigate_event, camera_name, scientific_name)
                VALUES (?, 1, .8, ?, 'bird', ?, 'feeder', ?)""",
            [
                (start + timedelta(minutes=i * 2), f"Common {i % 10}", f"event{i}", f"Scientific {i % 10}")
                for i in range(1000)
            ],
        )
        await db.commit()
        instructions = 0

        def budget() -> int:
            nonlocal instructions
            instructions += 1000
            return int(instructions > 5_000_000)

        # An instruction bound is independent of machine speed. A cross product
        # exhausts it; indexed lookups plus the existing visit sorts fit easily.
        await db.set_progress_handler(budget, 1000)
        try:
            rows = await DetectionRepository(db).get_species_leaderboard_window(
                start, start + timedelta(days=30), start - timedelta(days=30), start
            )
        finally:
            await db.set_progress_handler(None, 0)
        assert len(rows) == 10
        assert sum(row["window_count"] for row in rows) == 1000
        assert sum(row["window_visit_count"] for row in rows) == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scientific_name", "display_name", "expected"),
    [
        ("GENUS ONE", "Wrong display", [1]),
        (None, "genus one", [1]),
        (None, "shared common", [1, 2]),
        # The same taxonomy row matching scientific and common names is joined once.
        (None, "genus three", [3]),
        ("", "shared common", []),
        ("Missing", "shared common", []),
        (None, "Missing", []),
    ],
)
async def test_indexed_taxonomy_join_preserves_scientific_precedence_and_legacy_matches(
    scientific_name: str | None, display_name: str, expected: list[int]
):
    async with aiosqlite.connect(":memory:") as db:
        await _create_taxonomy_tables(db)
        await db.execute("CREATE TABLE captures(scientific_name TEXT, display_name TEXT)")
        await db.execute("INSERT INTO captures VALUES (?, ?)", (scientific_name, display_name))
        await db.executemany(
            "INSERT INTO taxonomy_cache(scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            [("Genus one", "Shared common", 1), ("Genus two", "Shared common", 2), ("Genus three", "Genus three", 3)],
        )
        join = DetectionRepository._taxonomy_join_sql(detection_alias="capture", taxonomy_alias="taxonomy")
        async with db.execute(
            f"SELECT taxonomy.taxa_id FROM captures capture {join} ORDER BY taxonomy.taxa_id"
        ) as cursor:
            matches = [row[0] for row in await cursor.fetchall() if row[0] is not None]
        assert matches == expected
