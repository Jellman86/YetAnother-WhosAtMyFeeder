"""Every model output has a row, and coverage stays honest about it.

Retiring `labels.txt` needs the catalogue to know what every output index is
called. It did not: an output whose species could not be resolved was skipped
entirely, so for 707 of a 10,000-class model's outputs the catalogue held
nothing at all, not even the label text.

Those rows now exist, carrying their label and an explicit `unknown` class.

The trap is that coverage counted rows. Simply adding rows would have taken
every model to "complete" and flipped its activation verdict to `ready` while
707 outputs still had no identity. Coverage therefore counts *identified*
outputs, so the reported numbers do not move: what changes is that the
catalogue can now name an output it cannot identify.
"""

import sqlite3

import pytest

from app.services.species_catalog_status import SpeciesCatalogStatus


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "species_catalog.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE alembic_version (version_num TEXT);
        CREATE TABLE catalogue_releases (id INTEGER PRIMARY KEY, schema_version INTEGER,
            source_manifest TEXT, content_sha256 TEXT, generated_at TEXT, state TEXT);
        CREATE TABLE species (species_id INTEGER PRIMARY KEY, rank TEXT, status TEXT,
            accepted_species_id INTEGER);
        CREATE TABLE model_artifacts (id INTEGER PRIMARY KEY, registry_id TEXT, model_sha256 TEXT,
            mapping_set_sha256 TEXT, output_width INTEGER, runtime TEXT, model_version TEXT, state TEXT);
        CREATE TABLE model_output_taxa (model_artifact_id INTEGER, output_index INTEGER,
            class_kind TEXT, species_id INTEGER, source_label TEXT,
            PRIMARY KEY (model_artifact_id, output_index));
        INSERT INTO catalogue_releases VALUES (1, 1, '{}', 'abc', '2026-08-23T00:00:00Z', 'active');
        INSERT INTO species VALUES (1,'species','accepted',NULL);
        INSERT INTO model_artifacts VALUES (1,'test_model','sha-1',NULL,4,'onnx',NULL,'installed');
        """
    )
    # Four outputs: two identified, one an explicit background class, one unknown.
    connection.executemany(
        "INSERT INTO model_output_taxa VALUES (?,?,?,?,?)",
        [
            (1, 0, "species", 1, "Prunella modularis"),
            (1, 1, "species", 1, "Erithacus rubecula"),
            (1, 2, "background", None, "background"),
            (1, 3, "unknown", None, "Some label nothing resolved"),
        ],
    )
    connection.commit()
    connection.close()
    return path


def test_an_output_the_catalogue_cannot_identify_still_has_its_label(catalogue):
    connection = sqlite3.connect(catalogue)
    label = connection.execute("SELECT source_label FROM model_output_taxa WHERE output_index = 3").fetchone()[0]
    connection.close()
    assert label == "Some label nothing resolved"


def test_coverage_counts_identified_outputs_rather_than_rows(catalogue):
    """Four rows, but one is `unknown`, so three are actually mapped."""
    status = SpeciesCatalogStatus(catalogue).status()
    artifact = status["artifacts"][0]
    assert artifact["output_width"] == 4
    assert artifact["mapped_outputs"] == 3
    assert artifact["unresolved_outputs"] == 1


def test_a_model_with_an_unknown_output_is_not_called_complete(catalogue):
    """Rows for every index must not be mistaken for an identity for every index."""
    status = SpeciesCatalogStatus(catalogue).status()
    assert status["artifacts"][0]["complete"] is False


def test_a_model_with_every_output_identified_is_complete(catalogue):
    connection = sqlite3.connect(catalogue)
    connection.execute("UPDATE model_output_taxa SET class_kind='background' WHERE output_index=3")
    connection.commit()
    connection.close()

    status = SpeciesCatalogStatus(catalogue).status()
    artifact = status["artifacts"][0]
    assert artifact["mapped_outputs"] == 4
    assert artifact["unresolved_outputs"] == 0
    assert artifact["complete"] is True


def test_a_missing_row_still_counts_as_unresolved(catalogue):
    """Absence and `unknown` must both be honest, not only one of them."""
    connection = sqlite3.connect(catalogue)
    connection.execute("DELETE FROM model_output_taxa WHERE output_index = 3")
    connection.commit()
    connection.close()

    artifact = SpeciesCatalogStatus(catalogue).status()["artifacts"][0]
    assert artifact["unresolved_outputs"] == 1
    assert artifact["complete"] is False


def test_an_unknown_output_reads_as_a_gap_rather_than_a_non_species_class(tmp_path):
    """`unknown` and `background` are different claims and must not merge.

    Every output index now has a row, so an index the catalogue cannot identify
    is present rather than absent. Reporting it as `non_species` would assert
    that it is known not to be a species, which is a stronger statement than
    the catalogue can make.
    """
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    path = tmp_path / "species_catalog.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE species (species_id INTEGER PRIMARY KEY, rank TEXT, status TEXT, accepted_species_id INTEGER);
        CREATE TABLE species_concepts (species_id INTEGER, provider TEXT, provider_taxon_id TEXT,
            source_release TEXT, scientific_name TEXT, authorship TEXT, accepted_name_usage TEXT, status TEXT);
        CREATE TABLE species_aliases (alias TEXT, alias_kind TEXT, species_id INTEGER, resolution TEXT,
            source TEXT, confidence REAL);
        CREATE TABLE model_artifacts (id INTEGER PRIMARY KEY, registry_id TEXT, model_sha256 TEXT,
            mapping_set_sha256 TEXT, output_width INTEGER, runtime TEXT, model_version TEXT, state TEXT);
        CREATE TABLE model_output_taxa (model_artifact_id INTEGER, output_index INTEGER, class_kind TEXT,
            species_id INTEGER, source_label TEXT, PRIMARY KEY (model_artifact_id, output_index));
        INSERT INTO model_artifacts VALUES (1,'m','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',NULL,2,'onnx',NULL,'installed');
        INSERT INTO model_output_taxa VALUES (1,0,'background',NULL,'background');
        INSERT INTO model_output_taxa VALUES (1,1,'unknown',NULL,'Some label');
        """
    )
    connection.commit()
    connection.close()

    sha = "b" * 64
    resolver = SpeciesCatalogResolver(path)
    assert resolver.shadow_resolve(sha, 0, None).verdict == "non_species"
    assert resolver.shadow_resolve(sha, 1, "Some label").verdict == "unresolved_index"
