"""Offering the shipped seed to a catalogue that already exists.

`ensure_catalog_ready` seeds only a genuinely fresh install, and rightly: a live
catalogue may hold owner overrides and imported releases, so replacing the file
would lose them. The consequence was that a newer shipped catalogue never
reached an existing install at all. The release importer existed to solve
exactly that and nothing ever called it.

That mattered the moment the catalogue gained bird synonyms: without this the
7,256 new aliases would have reached fresh installs only, and the jackdaw would
still have counted twice everywhere else.

The importer already verifies the schema head, that the bundle holds one
release, its content digest and its foreign keys, and it is idempotent. This
only decides when to offer it, and refuses to make a failure fatal.
"""

import sqlite3
from pathlib import Path

from app.services.species_catalog_store import offer_seed_release


class _Recorder:
    def __init__(self, result=None, error: Exception | None = None):
        self.calls: list[Path] = []
        self._result = result
        self._error = error

    def __call__(self, bundle_path, catalog_path=None):
        self.calls.append(Path(bundle_path))
        if self._error is not None:
            raise self._error
        return self._result


class _Result:
    def __init__(self, status: str, release_id: int | None = 1):
        self.status = status
        self.release_id = release_id


def _catalogue(tmp_path: Path) -> Path:
    path = tmp_path / "species_catalog.db"
    sqlite3.connect(path).close()
    return path


def _seed(tmp_path: Path) -> Path:
    path = tmp_path / "species_catalog_seed.db"
    sqlite3.connect(path).close()
    return path


def test_a_shipped_seed_is_offered_to_an_existing_catalogue(tmp_path):
    recorder = _Recorder(_Result("imported", 7))
    outcome = offer_seed_release(_catalogue(tmp_path), _seed(tmp_path), importer=recorder)
    assert len(recorder.calls) == 1
    assert outcome["status"] == "imported"
    assert outcome["release_id"] == 7


def test_offering_the_same_seed_twice_is_recognised_rather_than_repeated(tmp_path):
    """The importer compares content digests, so this must stay cheap."""
    recorder = _Recorder(_Result("already_imported", 3))
    outcome = offer_seed_release(_catalogue(tmp_path), _seed(tmp_path), importer=recorder)
    assert outcome["status"] == "already_imported"


def test_no_seed_means_nothing_to_offer(tmp_path):
    recorder = _Recorder(_Result("imported"))
    outcome = offer_seed_release(_catalogue(tmp_path), tmp_path / "absent.db", importer=recorder)
    assert recorder.calls == []
    assert outcome["status"] == "no_seed"


def test_no_catalogue_means_the_seeding_path_owns_it(tmp_path):
    recorder = _Recorder(_Result("imported"))
    outcome = offer_seed_release(tmp_path / "absent.db", _seed(tmp_path), importer=recorder)
    assert recorder.calls == []
    assert outcome["status"] == "no_catalogue"


def test_a_failed_import_is_reported_and_never_raised(tmp_path):
    """A catalogue that cannot take a new release still serves the old one."""
    recorder = _Recorder(error=RuntimeError("bundle is a bit off"))
    outcome = offer_seed_release(_catalogue(tmp_path), _seed(tmp_path), importer=recorder)
    assert outcome["status"] == "failed"
    assert "bit off" in outcome["detail"]


def test_the_outcome_is_visible_for_reporting(tmp_path):
    recorder = _Recorder(_Result("imported", 2))
    outcome = offer_seed_release(_catalogue(tmp_path), _seed(tmp_path), importer=recorder)
    assert set(outcome) >= {"status", "release_id", "detail"}
