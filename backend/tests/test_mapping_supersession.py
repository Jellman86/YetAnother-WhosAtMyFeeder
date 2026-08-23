"""Completing a registered artifact's mapping without rewriting it.

An artifact's `mapping_set_sha256` is computed over the whole source mapping,
including outputs nothing could resolve. The stored rows were a filtered subset
of that, so the digest never described what was actually stored.

That only mattered once the unresolved outputs started being recorded. An
existing install then held 9,293 rows for a 10,000-output model under a digest
asserting the mapping was identical to a bundle carrying all 10,000, and the
importer skipped the artifact because the digests matched. The completeness
work reached fresh installs only.

A matching digest means the source mapping is the same, so a row the live
catalogue lacks is absent rather than different, and adding it changes no
identity. A row that would *change* is still refused: that is a mapping
correction and needs its own supersession policy, not this.
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.species_catalog_importer import CatalogImportError, complete_artifact_mapping


@pytest.fixture
def live(tmp_path) -> Path:
    path = tmp_path / "species_catalog.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE model_artifacts (id INTEGER PRIMARY KEY, registry_id TEXT, model_sha256 TEXT,
            mapping_set_sha256 TEXT, output_width INTEGER, runtime TEXT, model_version TEXT, state TEXT);
        CREATE TABLE model_output_taxa (model_artifact_id INTEGER, output_index INTEGER, class_kind TEXT,
            species_id INTEGER, source_label TEXT, PRIMARY KEY (model_artifact_id, output_index));
        INSERT INTO model_artifacts VALUES (1,'m','sha-model','sha-mapping',3,'onnx',NULL,'installed');
        INSERT INTO model_output_taxa VALUES (1,0,'species',10,'Prunella modularis');
        INSERT INTO model_output_taxa VALUES (1,1,'species',20,'Erithacus rubecula');
        """
    )
    connection.commit()
    connection.close()
    return path


def _bundle_rows():
    return [
        {"output_index": 0, "class_kind": "species", "species_id": 10, "source_label": "Prunella modularis"},
        {"output_index": 1, "class_kind": "species", "species_id": 20, "source_label": "Erithacus rubecula"},
        {"output_index": 2, "class_kind": "unknown", "species_id": None, "source_label": "Nothing resolved this"},
    ]


def _rows(path: Path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT output_index, class_kind, species_id, source_label FROM model_output_taxa ORDER BY output_index"
        ).fetchall()
    finally:
        connection.close()


def test_a_missing_output_row_is_added(live):
    connection = sqlite3.connect(live)
    added = complete_artifact_mapping(connection, artifact_row_id=1, bundle_rows=_bundle_rows())
    connection.commit()
    connection.close()

    assert added == 1
    rows = _rows(live)
    assert len(rows) == 3
    assert rows[2] == (2, "unknown", None, "Nothing resolved this")


def test_rows_already_present_are_left_exactly_as_they_are(live):
    connection = sqlite3.connect(live)
    complete_artifact_mapping(connection, artifact_row_id=1, bundle_rows=_bundle_rows())
    connection.commit()
    connection.close()

    rows = _rows(live)
    assert rows[0] == (0, "species", 10, "Prunella modularis")
    assert rows[1] == (1, "species", 20, "Erithacus rubecula")


def test_nothing_to_add_is_not_an_error(live):
    connection = sqlite3.connect(live)
    complete_artifact_mapping(connection, artifact_row_id=1, bundle_rows=_bundle_rows())
    added_again = complete_artifact_mapping(connection, artifact_row_id=1, bundle_rows=_bundle_rows())
    connection.commit()
    connection.close()
    assert added_again == 0


def test_a_row_that_would_change_an_identity_is_refused(live):
    """A correction is not a completion, and must not arrive through this door."""
    rows = _bundle_rows()
    rows[0] = {"output_index": 0, "class_kind": "species", "species_id": 999, "source_label": "Prunella modularis"}

    connection = sqlite3.connect(live)
    try:
        with pytest.raises(CatalogImportError, match="differs"):
            complete_artifact_mapping(connection, artifact_row_id=1, bundle_rows=rows)
    finally:
        connection.close()

    assert _rows(live)[0] == (0, "species", 10, "Prunella modularis"), "the live row is untouched"


def test_a_changed_label_is_also_refused(live):
    rows = _bundle_rows()
    rows[1] = {"output_index": 1, "class_kind": "species", "species_id": 20, "source_label": "Something else"}

    connection = sqlite3.connect(live)
    try:
        with pytest.raises(CatalogImportError, match="differs"):
            complete_artifact_mapping(connection, artifact_row_id=1, bundle_rows=rows)
    finally:
        connection.close()
