from pathlib import Path
from contextlib import closing
import sqlite3

import pytest

from app.database import _backup_db


def create_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE saved (value TEXT)")
        db.execute("INSERT INTO saved VALUES ('owner data')")


def test_backup_restores_committed_wal_rows_without_uncommitted_changes(tmp_path):
    database = tmp_path / "speciesid.db"
    with closing(sqlite3.connect(database)) as writer, writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE observations (event TEXT PRIMARY KEY, note TEXT, hidden INTEGER)")
        writer.execute("INSERT INTO observations VALUES ('kept', 'owner note', 1)")
        writer.commit()
        writer.execute("INSERT INTO observations VALUES ('pending', 'not committed', 0)")
        backup = _backup_db(str(database))
        assert backup is not None
        with closing(sqlite3.connect(backup)) as restored:
            assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert restored.execute("SELECT * FROM observations").fetchall() == [("kept", "owner note", 1)]
        writer.rollback()
        assert writer.execute("SELECT COUNT(*) FROM observations").fetchone() == (1,)


def test_backup_db_keeps_only_the_newest_restore_points(tmp_path: Path) -> None:
    database = tmp_path / "speciesid.db"
    create_database(database)
    oldest = tmp_path / "speciesid.pre-migration-20260101T000000Z.db"
    newer = tmp_path / "speciesid.pre-migration-20260201T000000Z.db"
    unrelated = tmp_path / "manual-backup.db"
    oldest.write_bytes(b"oldest")
    newer.write_bytes(b"newer")
    unrelated.write_bytes(b"manual")

    backup_path = _backup_db(str(database), retention=2)

    assert backup_path is not None
    created = Path(backup_path)
    with closing(sqlite3.connect(created)) as restored:
        assert restored.execute("SELECT value FROM saved").fetchone() == ("owner data",)
    assert not oldest.exists()
    assert newer.exists()
    assert unrelated.read_bytes() == b"manual"
    assert sorted(tmp_path.glob("speciesid.pre-migration-*.db")) == sorted([newer, created])


def test_backup_db_never_prunes_the_last_restore_point(tmp_path: Path) -> None:
    database = tmp_path / "speciesid.db"
    create_database(database)

    backup_path = _backup_db(str(database), retention=0)

    assert backup_path is not None
    assert list(tmp_path.glob("speciesid.pre-migration-*.db")) == [Path(backup_path)]


def test_backup_db_does_nothing_when_database_is_missing(tmp_path: Path) -> None:
    database = tmp_path / "speciesid.db"

    assert _backup_db(str(database), retention=2) is None
    assert list(tmp_path.iterdir()) == []


def test_backup_db_does_not_prune_when_new_backup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "speciesid.db"
    create_database(database)
    oldest = tmp_path / "speciesid.pre-migration-20260101T000000Z.db"
    newer = tmp_path / "speciesid.pre-migration-20260201T000000Z.db"
    oldest.write_bytes(b"oldest")
    newer.write_bytes(b"newer")

    def fail_connect(*_args, **_kwargs) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr("app.database.sqlite3.connect", fail_connect)

    assert _backup_db(str(database), retention=1) is None
    assert oldest.read_bytes() == b"oldest"
    assert newer.read_bytes() == b"newer"
    assert not list(tmp_path.glob("*.partial"))


def test_backups_never_overwrite_each_other(tmp_path):
    database = tmp_path / "speciesid.db"
    create_database(database)
    first = _backup_db(str(database))
    second = _backup_db(str(database))
    assert first != second
    assert Path(first).exists() and Path(second).exists()


def test_corrupt_source_does_not_publish_or_prune_restore_points(tmp_path):
    database = tmp_path / "speciesid.db"
    database.write_bytes(b"not sqlite")
    previous = tmp_path / "speciesid.pre-migration-20260101T000000Z.db"
    create_database(previous)
    assert _backup_db(str(database)) is None
    assert sorted(tmp_path.iterdir()) == sorted([database, previous])


def test_locked_database_backup_has_a_deadline_and_leaves_no_partial_file(tmp_path, monkeypatch):
    database = tmp_path / "speciesid.db"
    create_database(database)
    # Simulate an elapsed deadline without slowing the test suite by 30 seconds.
    ticks = iter([0.0, 31.0])
    monkeypatch.setattr("app.database.time.monotonic", lambda: next(ticks))
    with closing(sqlite3.connect(database)) as locked:
        locked.execute("BEGIN EXCLUSIVE")
        assert _backup_db(str(database)) is None
        locked.rollback()
    assert list(tmp_path.iterdir()) == [database]


def test_clock_correction_cannot_prune_the_backup_just_created(tmp_path):
    database = tmp_path / "speciesid.db"
    create_database(database)
    future = tmp_path / "speciesid.pre-migration-20991231T000000Z.db"
    create_database(future)
    current = _backup_db(str(database), retention=1)
    assert Path(current).exists()
    assert not future.exists()
