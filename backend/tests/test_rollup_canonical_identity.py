"""Re-keying the daily rollup without losing what only it remembers.

`species_daily_rollup` persists its grouping key as half the primary key, so it
is the one place a key-format change is not simply recomputed. Rebuilding it
from detections is not available: on a live install 29 rollup rows covering 97
detections predate the oldest surviving detection, so the rollup is the only
record of them.

These tests are about that: no row disappears, no total changes, and a row
whose detections are gone keeps a text key rather than being invented.
"""

import subprocess
import sqlite3
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _alembic(db_path: Path, *args: str) -> None:
    subprocess.run(
        ["alembic", *args],
        cwd=BACKEND,
        check=True,
        capture_output=True,
        env={**__import__("os").environ, "DB_PATH": str(db_path)},
    )


@pytest.fixture
def migrated(tmp_path):
    db_path = tmp_path / "speciesid.db"
    _alembic(db_path, "upgrade", "e2b8c47f91a3")
    return db_path


def _seed(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    connection.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
               frigate_event, camera_name, scientific_name, common_name, taxa_id, species_id)
           VALUES ('2026-08-01 08:00:00',1,0.9,'Dunnock','Bird','evt-1','cam','Prunella modularis','Dunnock',7001,10081)"""
    )
    # A rollup row whose detections still exist, so identity is recoverable.
    connection.execute(
        """INSERT INTO species_daily_rollup (rollup_date, canonical_key, display_name, scientific_name,
               common_name, taxa_id, detection_count, camera_count, avg_confidence, max_confidence,
               min_confidence, first_seen, last_seen)
           VALUES ('2026-08-01','7001','Dunnock','Prunella modularis','Dunnock',7001,5,2,0.8,0.9,0.7,
                   '2026-08-01 08:00:00','2026-08-01 18:00:00')"""
    )
    # A rollup row whose detections are long gone: the only record of those 12.
    connection.execute(
        """INSERT INTO species_daily_rollup (rollup_date, canonical_key, display_name, scientific_name,
               common_name, taxa_id, detection_count, camera_count, avg_confidence, max_confidence,
               min_confidence, first_seen, last_seen)
           VALUES ('2026-07-01','vanished bird','Vanished Bird',NULL,NULL,NULL,12,1,0.6,0.7,0.5,
                   '2026-07-01 08:00:00','2026-07-01 18:00:00')"""
    )
    connection.commit()
    connection.close()


def _rows(db_path: Path) -> list[tuple]:
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(
            "SELECT rollup_date, canonical_key, detection_count, species_id FROM species_daily_rollup"
            " ORDER BY rollup_date"
        ).fetchall()
    finally:
        connection.close()


def _total(db_path: Path) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute("SELECT SUM(detection_count) FROM species_daily_rollup").fetchone()[0]
    finally:
        connection.close()


def test_no_aggregate_history_is_lost(migrated):
    _seed(migrated)
    before = _total(migrated)
    _alembic(migrated, "upgrade", "head")
    assert _total(migrated) == before == 17


def test_every_row_survives(migrated):
    _seed(migrated)
    _alembic(migrated, "upgrade", "head")
    assert len(_rows(migrated)) == 2


def test_a_row_whose_detections_exist_gains_that_identity(migrated):
    _seed(migrated)
    _alembic(migrated, "upgrade", "head")
    row = next(r for r in _rows(migrated) if r[0] == "2026-08-01")
    assert row[3] == 10081
    assert row[1] == "species:10081"


def test_a_row_whose_detections_are_gone_keeps_a_text_key(migrated):
    """It is the only record of those detections; nothing may be invented."""
    _seed(migrated)
    _alembic(migrated, "upgrade", "head")
    row = next(r for r in _rows(migrated) if r[0] == "2026-07-01")
    assert row[3] is None
    assert row[1] == "label:vanished bird"
    assert row[2] == 12


def test_the_migration_reverses_and_keeps_the_totals(migrated):
    _seed(migrated)
    before = _total(migrated)
    _alembic(migrated, "upgrade", "head")
    _alembic(migrated, "downgrade", "-1")
    assert _total(migrated) == before

    # `species_id` is gone after a downgrade, so read only what still exists.
    connection = sqlite3.connect(migrated)
    keys = {row[0] for row in connection.execute("SELECT canonical_key FROM species_daily_rollup")}
    columns = {row[1] for row in connection.execute("PRAGMA table_info(species_daily_rollup)")}
    connection.close()

    assert "species_id" not in columns
    assert not any(key.startswith("species:") or key.startswith("taxon:") for key in keys)


def test_upgrading_again_after_a_downgrade_is_stable(migrated):
    _seed(migrated)
    before = _total(migrated)
    _alembic(migrated, "upgrade", "head")
    _alembic(migrated, "downgrade", "-1")
    _alembic(migrated, "upgrade", "head")
    assert _total(migrated) == before
    assert len(_rows(migrated)) == 2


def test_colliding_rows_are_merged_rather_than_dropped(migrated):
    """Two old keys can land on one new key. Nothing may be lost when they do."""
    _seed(migrated)
    connection = sqlite3.connect(migrated)
    # A second row for the same day and the same bird under its older name.
    connection.execute(
        """INSERT INTO species_daily_rollup (rollup_date, canonical_key, display_name, scientific_name,
               common_name, taxa_id, detection_count, camera_count, avg_confidence, max_confidence,
               min_confidence, first_seen, last_seen)
           VALUES ('2026-08-01','prunella modularis','Dunnock','Prunella modularis','Dunnock',NULL,3,1,0.6,0.7,0.5,
                   '2026-08-01 06:00:00','2026-08-01 07:00:00')"""
    )
    connection.commit()
    connection.close()

    before = _total(migrated)
    _alembic(migrated, "upgrade", "head")

    assert _total(migrated) == before, "merging must not lose detections"
    merged = next(r for r in _rows(migrated) if r[0] == "2026-08-01")
    assert merged[2] == 8, "the merged row carries both counts"
    assert len([r for r in _rows(migrated) if r[0] == "2026-08-01"]) == 1


def test_a_merged_rows_confidence_is_weighted_by_its_detections(migrated):
    _seed(migrated)
    connection = sqlite3.connect(migrated)
    connection.execute(
        """INSERT INTO species_daily_rollup (rollup_date, canonical_key, display_name, scientific_name,
               common_name, taxa_id, detection_count, camera_count, avg_confidence, max_confidence,
               min_confidence, first_seen, last_seen)
           VALUES ('2026-08-01','prunella modularis','Dunnock','Prunella modularis','Dunnock',NULL,3,1,0.6,0.7,0.5,
                   '2026-08-01 06:00:00','2026-08-01 07:00:00')"""
    )
    connection.commit()
    connection.close()
    _alembic(migrated, "upgrade", "head")

    connection = sqlite3.connect(migrated)
    avg = connection.execute(
        "SELECT avg_confidence FROM species_daily_rollup WHERE rollup_date='2026-08-01'"
    ).fetchone()[0]
    connection.close()
    # (0.8*5 + 0.6*3) / 8 = 0.725, not the flat mean of 0.7.
    assert avg == pytest.approx(0.725, abs=1e-6)


def test_a_row_matching_two_identities_is_left_alone(migrated):
    """History disagreeing is not a licence to pick one.

    Nothing else in this phase guesses, and a rollup row is the only record of
    detections that no longer exist, so a wrong identity here is unrecoverable.
    """
    connection = sqlite3.connect(migrated)
    for species_id, event in ((10081, "evt-a"), (9293, "evt-b")):
        connection.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                   frigate_event, camera_name, scientific_name, species_id)
               VALUES ('2026-08-02 08:00:00',1,0.9,'Shared Label','Bird',?,'cam','Ambiguous name',?)""",
            (event, species_id),
        )
    connection.execute(
        """INSERT INTO species_daily_rollup (rollup_date, canonical_key, display_name, scientific_name,
               common_name, taxa_id, detection_count, camera_count, avg_confidence, max_confidence,
               min_confidence, first_seen, last_seen)
           VALUES ('2026-08-02','ambiguous name','Shared Label','Ambiguous name',NULL,NULL,4,1,0.8,0.9,0.7,
                   '2026-08-02 08:00:00','2026-08-02 09:00:00')"""
    )
    connection.commit()
    connection.close()

    _alembic(migrated, "upgrade", "head")

    row = next(r for r in _rows(migrated) if r[0] == "2026-08-02")
    assert row[3] is None, "an ambiguous match must record no identity"
    assert row[1] == "name:ambiguous name"
    assert row[2] == 4, "the detections it remembers are untouched"


def test_a_newly_written_rollup_row_stores_the_identity_in_its_key(migrated):
    """The key and the column must agree.

    The rollup build originally wrote `species:NNN` into the key while leaving
    the column null, so the two disagreed and the identity could only be had by
    parsing a string.
    """
    import asyncio
    from datetime import date

    import aiosqlite

    from app.repositories.detection_repository import DetectionRepository

    connection = sqlite3.connect(migrated)
    connection.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
               frigate_event, camera_name, scientific_name, common_name, taxa_id, species_id)
           VALUES ('2026-08-05 08:00:00',1,0.9,'Dunnock','Bird','evt-new','cam','Prunella modularis','Dunnock',7001,10081)"""
    )
    connection.commit()
    connection.close()

    _alembic(migrated, "upgrade", "head")

    async def build() -> None:
        async with aiosqlite.connect(migrated) as db:
            await DetectionRepository(db).upsert_daily_rollups(date(2026, 8, 5), date(2026, 8, 5))

    asyncio.run(build())

    connection = sqlite3.connect(migrated)
    row = connection.execute(
        "SELECT canonical_key, species_id FROM species_daily_rollup WHERE rollup_date='2026-08-05'"
    ).fetchone()
    connection.close()

    assert row is not None, "the rollup should have been written"
    assert row[0] == "species:10081"
    assert row[1] == 10081, "the column must carry what the key claims"
