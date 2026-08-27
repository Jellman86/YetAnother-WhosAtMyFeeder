"""Seeding the species catalogue into /data on first start.

The image carries a checksum-pinned seed catalogue. On startup YA-WAMF copies
it into place only when no catalogue has ever been initialised: an
initialisation marker distinguishes a genuinely fresh install from a database
that has gone missing, because silently replacing a catalogue that may hold
owner enrichments would be data loss wearing a recovery costume.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.services.species_catalog_store import CatalogState, ensure_catalog_ready


@pytest.fixture
def seed(tmp_path):
    """A real seed built by the seed builder from a fixture reference."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import build_species_catalog_seed as seed_builder

    pinned = hashlib.sha256(b"fixture workbook").hexdigest()
    reference = tmp_path / "reference.db"
    connection = sqlite3.connect(reference)
    try:
        connection.executescript(
            """
            CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
            CREATE TABLE taxon_name (
                taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
                PRIMARY KEY (taxon_id, locale)
            ) WITHOUT ROWID;
            """
        )
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (pinned,))
        connection.execute("INSERT INTO taxon VALUES (1, 'Cyanistes caeruleus', 'Eurasian Blue Tit')")
        connection.commit()
    finally:
        connection.close()

    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-19",
                "sources": [
                    {
                        "id": "ioc-world-bird-list",
                        "name": "IOC",
                        "role": "bird-vernacular-names",
                        "version": "14.2-test",
                        "url": "https://www.worldbirdnames.org/",
                        "licence": "CC-BY-3.0",
                        "citation": "IOC World Bird List.",
                        "redistribution": "bundled",
                        "content_sha256": pinned,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    seed_path = tmp_path / "species_catalog_seed.db"
    seed_builder.build(reference, seed_path, manifest_path=manifest)
    return seed_path


@pytest.fixture
def catalog_path(tmp_path):
    return tmp_path / "data" / "species_catalog.db"


def _species_count(path) -> int:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT COUNT(*) FROM species").fetchone()[0]
    finally:
        connection.close()


def test_a_fresh_install_is_seeded_from_the_image(seed, catalog_path):
    result = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert result.state is CatalogState.SEEDED
    assert catalog_path.is_file()
    assert _species_count(catalog_path) == 1
    assert catalog_path.with_suffix(catalog_path.suffix + ".initialized").is_file()


def test_a_second_start_is_a_no_op_and_keeps_owner_data(seed, catalog_path):
    ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)
    connection = sqlite3.connect(catalog_path)
    try:
        connection.execute("INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (1, '', 'Mine')")
        connection.commit()
    finally:
        connection.close()

    result = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert result.state is CatalogState.READY
    connection = sqlite3.connect(catalog_path)
    try:
        overrides = connection.execute("SELECT name FROM species_name_overrides").fetchall()
    finally:
        connection.close()
    assert overrides == [("Mine",)]


def test_a_missing_catalogue_that_was_initialised_before_is_not_reseeded(seed, catalog_path):
    ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)
    catalog_path.unlink()

    result = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert result.state is CatalogState.MISSING
    assert not catalog_path.exists(), "re-seeding would mask the loss of owner enrichments"


def test_a_seed_that_fails_its_digest_is_refused(seed, catalog_path):
    sidecar = seed.with_suffix(seed.suffix + ".sha256")
    sidecar.write_text(f"{'0' * 64}  {seed.name}\n", encoding="utf-8")

    result = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert result.state is CatalogState.SEED_REJECTED
    assert not catalog_path.exists()


def test_without_a_seed_an_empty_migrated_catalogue_is_initialised(catalog_path, tmp_path):
    result = ensure_catalog_ready(catalog_path=catalog_path, seed_path=tmp_path / "no_seed_here.db")

    assert result.state is CatalogState.INITIALIZED_EMPTY
    assert _species_count(catalog_path) == 0


def test_an_adopted_existing_catalogue_gains_the_marker(seed, catalog_path, tmp_path):
    ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)
    marker = catalog_path.with_suffix(catalog_path.suffix + ".initialized")
    marker.unlink()

    result = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert result.state is CatalogState.READY
    assert marker.is_file()


def test_an_empty_shell_catalogue_is_replaced_when_a_seed_appears(seed, catalog_path, tmp_path):
    """The split image shipped no seed at first, leaving an empty migrated
    catalogue behind the marker. There is nothing in it to lose, so a later
    seed-carrying image replaces it instead of honouring the marker forever."""
    empty_first = ensure_catalog_ready(catalog_path=catalog_path, seed_path=tmp_path / "no_seed_yet.db")
    assert empty_first.state is CatalogState.INITIALIZED_EMPTY

    healed = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert healed.state is CatalogState.SEEDED
    assert _species_count(catalog_path) == 1


def test_a_catalogue_with_a_release_is_never_replaced_by_the_seed(seed, catalog_path):
    """Only a genuinely empty shell may be replaced; any release means content."""
    ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)
    connection = sqlite3.connect(catalog_path)
    try:
        connection.execute("INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (1, '', 'Mine')")
        connection.commit()
    finally:
        connection.close()

    again = ensure_catalog_ready(catalog_path=catalog_path, seed_path=seed)

    assert again.state is CatalogState.READY
    connection = sqlite3.connect(catalog_path)
    try:
        assert connection.execute("SELECT name FROM species_name_overrides").fetchall() == [("Mine",)]
    finally:
        connection.close()
