"""The leaderboard must never list one bird twice (#386).

The canonical key prefers catalogue identity, so a detection carrying
`species_id` groups as `species:N` while one still waiting for the identity
backfill groups as `taxon:N`. Those are different strings, and a species with
some rows resolved and some not arrives as two leaderboard lines. The count path
was folded for exactly this in #359; the leaderboard never was, and a reporter
watched the duplicates multiply as each new detection resolved while the older
ones had not.
"""

from datetime import datetime

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository, merge_species_leaderboard_rows


def _row(
    species,
    window_count,
    taxa_id=None,
    prev=0,
    first="2026-09-02 10:00:00",
    last="2026-09-02 12:00:00",
    confidence=0.9,
    cameras=1,
    **extra,
):
    return {
        "species": species,
        "scientific_name": extra.get("scientific_name"),
        "common_name": extra.get("common_name"),
        "taxa_id": taxa_id,
        "window_count": window_count,
        "prev_count": prev,
        "window_first_seen": datetime.fromisoformat(first),
        "window_last_seen": datetime.fromisoformat(last),
        "window_avg_confidence": confidence,
        "window_camera_count": cameras,
    }


def test_the_same_taxon_under_two_identity_keys_becomes_one_line():
    # 86 resolved rows and 3 not-yet-backfilled rows of the same nuthatch.
    merged = merge_species_leaderboard_rows(
        [
            _row(
                "White-breasted Nuthatch",
                86,
                taxa_id=14805,
                prev=40,
                last="2026-09-02 13:03:00",
                confidence=0.98,
                cameras=2,
            ),
            _row(
                "White-breasted Nuthatch",
                3,
                taxa_id=14805,
                prev=0,
                first="2026-09-02 13:20:00",
                last="2026-09-02 13:30:00",
                confidence=1.0,
                cameras=1,
            ),
        ]
    )
    assert len(merged) == 1
    (row,) = merged
    assert row["window_count"] == 89
    assert row["prev_count"] == 40
    assert row["window_first_seen"] == datetime.fromisoformat("2026-09-02 10:00:00")
    assert row["window_last_seen"] == datetime.fromisoformat("2026-09-02 13:30:00")
    # Weighted by count, not a plain mean of two averages.
    assert row["window_avg_confidence"] == pytest.approx((0.98 * 86 + 1.0 * 3) / 89)
    # Two groups' distinct-camera counts cannot be unioned after the fact; the
    # larger is the only figure that cannot overstate what was measured.
    assert row["window_camera_count"] == 2


def test_the_same_name_without_a_taxon_still_merges_and_adopts_it():
    merged = merge_species_leaderboard_rows(
        [
            _row("Dunnock", 5, taxa_id=None),
            _row("dunnock", 2, taxa_id=13988, scientific_name="Prunella modularis"),
        ]
    )
    assert len(merged) == 1
    assert merged[0]["window_count"] == 7
    assert merged[0]["taxa_id"] == 13988
    assert merged[0]["scientific_name"] == "Prunella modularis"


def test_distinct_species_stay_distinct_and_rank_by_window_count():
    merged = merge_species_leaderboard_rows(
        [
            _row("Tufted Titmouse", 3, taxa_id=1),
            _row("Black-capped Chickadee", 256, taxa_id=2),
            _row("Tufted Titmouse", 64, taxa_id=1),
        ]
    )
    assert [(r["species"], r["window_count"]) for r in merged] == [
        ("Black-capped Chickadee", 256),
        ("Tufted Titmouse", 67),
    ]


@pytest_asyncio.fixture
async def seeded():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            rows = []
            for i in range(6):
                # The first four resolved; the newest two still awaiting the backfill.
                rows.append(
                    (
                        f"nut_{i}",
                        "cam1",
                        f"2026-09-02 1{i}:00:00",
                        1,
                        0.95,
                        "White-breasted Nuthatch",
                        "Sitta carolinensis",
                        "Sitta carolinensis",
                        14805,
                        777 if i < 4 else None,
                        0,
                    )
                )
            await db.executemany(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                   display_name, category_name, scientific_name, taxa_id, species_id, is_hidden)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_the_leaderboard_query_itself_returns_one_line_per_bird(seeded):
    async with get_db() as db:
        repo = DetectionRepository(db)
        rows = await repo.get_species_leaderboard_window(
            window_start=datetime(2026, 9, 2, 0, 0, 0),
            window_end=datetime(2026, 9, 3, 0, 0, 0),
            prev_start=datetime(2026, 9, 1, 0, 0, 0),
            prev_end=datetime(2026, 9, 2, 0, 0, 0),
        )
    nuthatch = [r for r in rows if r["species"] == "White-breasted Nuthatch"]
    assert len(nuthatch) == 1, [(r["species"], r["window_count"]) for r in rows]
    assert nuthatch[0]["window_count"] == 6
