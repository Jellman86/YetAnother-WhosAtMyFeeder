from pathlib import Path

import pytest

from app.database import _backup_db


def test_backup_db_keeps_only_the_newest_restore_points(tmp_path: Path) -> None:
    database = tmp_path / "speciesid.db"
    database.write_bytes(b"current database")
    oldest = tmp_path / "speciesid.pre-migration-20260101T000000Z.db"
    newer = tmp_path / "speciesid.pre-migration-20260201T000000Z.db"
    unrelated = tmp_path / "manual-backup.db"
    oldest.write_bytes(b"oldest")
    newer.write_bytes(b"newer")
    unrelated.write_bytes(b"manual")

    backup_path = _backup_db(str(database), retention=2)

    assert backup_path is not None
    created = Path(backup_path)
    assert created.read_bytes() == b"current database"
    assert not oldest.exists()
    assert newer.exists()
    assert unrelated.read_bytes() == b"manual"
    assert sorted(tmp_path.glob("speciesid.pre-migration-*.db")) == sorted([newer, created])


def test_backup_db_never_prunes_the_last_restore_point(tmp_path: Path) -> None:
    database = tmp_path / "speciesid.db"
    database.write_bytes(b"current database")

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
    database.write_bytes(b"current database")
    oldest = tmp_path / "speciesid.pre-migration-20260101T000000Z.db"
    newer = tmp_path / "speciesid.pre-migration-20260201T000000Z.db"
    oldest.write_bytes(b"oldest")
    newer.write_bytes(b"newer")

    def fail_copy(_source: Path, _destination: Path) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr("app.database.shutil.copy2", fail_copy)

    assert _backup_db(str(database), retention=1) is None
    assert oldest.read_bytes() == b"oldest"
    assert newer.read_bytes() == b"newer"
