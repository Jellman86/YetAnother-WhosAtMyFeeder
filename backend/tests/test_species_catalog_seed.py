"""Building the seed catalogue release from the bundled IOC reference.

The seed is the catalogue a fresh installation starts from. It is built
deterministically from the committed, digest-verified `species_reference.db`,
admitted through the Phase 0 provenance gate, and lands as one *active*
release inside a fully migrated `species_catalog.db`. Rebuilding from the same
input must produce a byte-identical file, because that is the only thing that
makes a recorded digest checkable rather than trusted.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

ASSETS = Path(__file__).resolve().parents[1] / "app" / "assets"


def _fixture_reference(tmp_path, *, source_sha256: str) -> Path:
    """A miniature species_reference.db in the committed asset's schema."""
    path = tmp_path / "species_reference.db"
    connection = sqlite3.connect(path)
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
        connection.executemany(
            "INSERT INTO reference_meta VALUES (?, ?)",
            [("schema_version", "2"), ("source", "ioc-world-bird-list"), ("source_sha256", source_sha256)],
        )
        connection.executemany(
            "INSERT INTO taxon VALUES (?, ?, ?)",
            [
                (1, "Cyanistes caeruleus", "Eurasian Blue Tit"),
                (2, "Erithacus rubecula", "European Robin"),
                (3, "Struthio camelus", None),
            ],
        )
        connection.executemany(
            "INSERT INTO taxon_name VALUES (?, ?, ?)",
            [(1, "de", "Blaumeise"), (1, "it", "Cinciarella"), (2, "de", "Rotkehlchen")],
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _manifest(tmp_path, *, pinned_sha256: str) -> Path:
    path = tmp_path / "species_sources.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-19",
                "sources": [
                    {
                        "id": "ioc-world-bird-list",
                        "name": "IOC World Bird List (Multilingual)",
                        "role": "bird-vernacular-names",
                        "version": "14.2-test",
                        "url": "https://www.worldbirdnames.org/",
                        "licence": "CC-BY-3.0",
                        "citation": "IOC World Bird List. https://www.worldbirdnames.org/",
                        "redistribution": "bundled",
                        "content_sha256": pinned_sha256,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def built(tmp_path):
    pinned = hashlib.sha256(b"the ioc workbook the manifest froze").hexdigest()
    reference = _fixture_reference(tmp_path, source_sha256=pinned)
    manifest = _manifest(tmp_path, pinned_sha256=pinned)
    output = tmp_path / "species_catalog.db"
    seed_builder.build(reference, output, manifest_path=manifest)
    return output


def _query(path, sql, params=()):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def test_the_seed_is_a_migrated_catalogue_with_one_active_release(built):
    tables = {row[0] for row in _query(built, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"alembic_version", "catalogue_releases", "species", "species_concepts", "species_names"} <= tables

    releases = _query(built, "SELECT state, schema_version FROM catalogue_releases")
    assert releases == [("active", 1)]


def test_every_reference_taxon_becomes_a_species_with_a_concept(built):
    assert _query(built, "SELECT COUNT(*) FROM species")[0][0] == 3

    concepts = _query(
        built,
        "SELECT provider, provider_taxon_id, source_release, scientific_name FROM species_concepts ORDER BY id",
    )
    assert concepts[0] == ("ioc-world-bird-list", "Cyanistes caeruleus", "14.2-test", "Cyanistes caeruleus")
    assert len(concepts) == 3


def test_names_carry_language_tags_and_provenance(built):
    names = _query(
        built,
        "SELECT language_tag, name, provider, source_release, preferred FROM species_names"
        " WHERE species_id = (SELECT species_id FROM species_concepts WHERE scientific_name = 'Cyanistes caeruleus')"
        " ORDER BY language_tag",
    )

    assert ("de", "Blaumeise", "ioc-world-bird-list", "14.2-test", 1) in names
    assert ("en", "Eurasian Blue Tit", "ioc-world-bird-list", "14.2-test", 1) in names
    assert ("it", "Cinciarella", "ioc-world-bird-list", "14.2-test", 1) in names


def test_a_taxon_with_no_english_name_still_gets_a_species_row(built):
    ostrich = _query(
        built,
        "SELECT species_id FROM species_concepts WHERE scientific_name = 'Struthio camelus'",
    )
    assert len(ostrich) == 1
    names = _query(built, "SELECT COUNT(*) FROM species_names WHERE species_id = ?", (ostrich[0][0],))
    assert names[0][0] == 0


def test_the_release_records_its_provenance(built):
    manifest_json, content_sha, generated_at = _query(
        built, "SELECT source_manifest, content_sha256, generated_at FROM catalogue_releases"
    )[0]
    recorded = json.loads(manifest_json)

    assert recorded["sources"][0]["id"] == "ioc-world-bird-list"
    assert recorded["sources"][0]["version"] == "14.2-test"
    assert len(content_sha) == 64
    assert generated_at == "2026-08-19T00:00:00Z"


def test_the_build_is_reproducible(tmp_path):
    pinned = hashlib.sha256(b"the ioc workbook the manifest froze").hexdigest()
    reference = _fixture_reference(tmp_path, source_sha256=pinned)
    manifest = _manifest(tmp_path, pinned_sha256=pinned)

    first, second = tmp_path / "one.db", tmp_path / "two.db"
    first_digest = seed_builder.build(reference, first, manifest_path=manifest)
    second_digest = seed_builder.build(reference, second, manifest_path=manifest)

    assert first.read_bytes() == second.read_bytes()
    assert first_digest == second_digest == hashlib.sha256(first.read_bytes()).hexdigest()
    sidecar = first.with_suffix(first.suffix + ".sha256")
    assert sidecar.read_text(encoding="utf-8").split()[0] == first_digest


def test_the_gate_refuses_a_reference_that_is_not_the_pinned_release(tmp_path):
    reference = _fixture_reference(tmp_path, source_sha256="c" * 64)
    manifest = _manifest(tmp_path, pinned_sha256=hashlib.sha256(b"something else").hexdigest())

    with pytest.raises(SystemExit, match="[Pp]rovenance"):
        seed_builder.build(reference, tmp_path / "refused.db", manifest_path=manifest)


def test_foreign_keys_hold_in_the_built_seed(built):
    connection = sqlite3.connect(built)
    try:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_the_committed_reference_builds_a_complete_seed(tmp_path):
    """The real asset, not a fixture: the whole IOC list survives the trip."""
    reference = ASSETS / "species_reference.db"
    if not reference.is_file():
        pytest.skip("bundled reference not present in this checkout")

    output = tmp_path / "seed.db"
    seed_builder.build(reference, output)

    species = _query(output, "SELECT COUNT(*) FROM species")[0][0]
    names = _query(output, "SELECT COUNT(*) FROM species_names")[0][0]
    localized = _query(output, "SELECT COUNT(*) FROM species_names WHERE language_tag != 'en'")[0][0]
    assert species == 11276
    assert localized == 87656
    assert names == 87656 + 11276  # every taxon in the committed list has an English name
    assert _query(output, "SELECT COUNT(*) FROM species_names WHERE language_tag = 'zh'")[0][0] > 10000
