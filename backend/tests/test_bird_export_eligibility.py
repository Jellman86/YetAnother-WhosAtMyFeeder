"""Bird-specific export eligibility from durable positive evidence (#728).

Historical non-bird rows (the squirrels the feeder audit found) must not
reach a bird-specific export, but absent evidence does not prove a
non-bird: rows from models the catalogue does not know keep exporting
exactly as before. Owner corrections replace the model output as the
current identity, so a stale model index must never be applied to them.
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.bird_export_eligibility import is_bird_exportable


@pytest.mark.parametrize(
    ("producing_group", "identity_group", "expected"),
    [
        # Positively evidenced non-birds stay out of bird exports. The
        # producing evidence is bound to the current scientific name when
        # it is gathered, so a nonbird verdict here already describes the
        # row's current identity — including one an owner merely confirmed.
        ("nonbird", "unknown", False),
        ("unknown", "nonbird", False),
        ("nonbird", "nonbird", False),
        # Conflicting positive evidence is not exported either.
        ("bird", "nonbird", False),
        ("nonbird", "bird", False),
        # Known birds, and rows with no evidence either way, keep exporting.
        ("bird", "bird", True),
        ("bird", "unknown", True),
        ("unknown", "bird", True),
        ("unknown", "unknown", True),
    ],
)
def test_eligibility_follows_positive_evidence(producing_group, identity_group, expected):
    assert is_bird_exportable(producing_group=producing_group, identity_group=identity_group) is expected


def _minimal_catalog(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE model_artifacts (id INTEGER PRIMARY KEY, model_sha256 TEXT, output_width INTEGER);
            CREATE TABLE model_output_taxa (
                model_artifact_id INTEGER, output_index INTEGER, class_kind TEXT,
                species_id INTEGER, source_label TEXT, taxonomic_group TEXT
            );
            CREATE TABLE species (species_id INTEGER PRIMARY KEY, rank TEXT);
            CREATE TABLE species_concepts (species_id INTEGER, scientific_name TEXT);
            CREATE TABLE species_aliases (species_id INTEGER, alias TEXT, resolution TEXT);
            """
        )
        connection.execute("INSERT INTO model_artifacts VALUES (7, ?, 4)", ("a" * 64,))
        connection.executemany(
            "INSERT INTO species VALUES (?, 'species')",
            [(1,), (2,), (3,), (4,)],
        )
        connection.executemany(
            "INSERT INTO species_concepts VALUES (?, ?)",
            [
                (1, "Cyanistes caeruleus"),
                (2, "Sciurus carolinensis"),
                (3, "Conflictus exemplum"),
                (4, "Conflictus exemplum"),
            ],
        )
        connection.executemany(
            "INSERT INTO model_output_taxa VALUES (7, ?, 'species', ?, ?, ?)",
            [
                (0, 1, "Cyanistes caeruleus", "bird"),
                (1, 2, "Sciurus carolinensis", "nonbird"),
                (2, 3, "Conflictus exemplum", "bird"),
                (3, 3, "Conflictus exemplum", "nonbird"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_resolver_reports_species_groups_and_artifact_identity(tmp_path):
    from app.services.species_catalog_resolver import SpeciesCatalogResolver

    catalog = tmp_path / "catalog.db"
    _minimal_catalog(catalog)
    resolver = SpeciesCatalogResolver(path=catalog)

    assert resolver.ensure_loaded() is True
    assert resolver.cached_species_group("Cyanistes caeruleus") == "bird"
    assert resolver.cached_species_group("Sciurus carolinensis") == "nonbird"
    assert resolver.cached_species_group("Not in catalogue") == "unknown"
    # Held by two species, and its outputs disagree: no positive evidence.
    assert resolver.cached_species_group("Conflictus exemplum") == "unknown"
    assert resolver.cached_species_group(None) == "unknown"
    assert resolver.model_sha256_for_artifact_id(7) == "a" * 64
    assert resolver.model_sha256_for_artifact_id(999) is None
    assert resolver.model_sha256_for_artifact_id(None) is None
