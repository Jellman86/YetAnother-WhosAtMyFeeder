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


def _col_concepts(tmp_path, *, export_sha256: str) -> Path:
    path = tmp_path / "col_nonbird_concepts.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": {"id": "catalogue-of-life", "version": "COL26.7-test", "export_sha256": export_sha256},
                "concepts": [
                    {
                        "scientific_name": "Lumbricus terrestris",
                        "kingdom": "Animalia",
                        "label_class": "Clitellata",
                        "col_id": "C1",
                        "col_status": "accepted",
                        "accepted_col_id": "C1",
                        "accepted_scientific_name": "Lumbricus terrestris",
                    },
                    {
                        "scientific_name": "Old synonymus",
                        "kingdom": "Fungi",
                        "label_class": "Agaricomycetes",
                        "col_id": "S1",
                        "col_status": "synonym",
                        "accepted_col_id": "A1",
                        "accepted_scientific_name": "Nova acceptus",
                    },
                ],
                "unresolved": [
                    {
                        "scientific_name": "Mysteria incognita",
                        "kingdom": "Plantae",
                        "label_class": "Magnoliopsida",
                        "reason": "not in the release",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _manifest_with_col(tmp_path, *, ioc_sha256: str, col_sha256: str) -> Path:
    path = tmp_path / "sources_with_col.json"
    payload = json.loads(_manifest(tmp_path, pinned_sha256=ioc_sha256).read_text(encoding="utf-8"))
    payload["sources"].append(
        {
            "id": "catalogue-of-life",
            "name": "Catalogue of Life",
            "role": "canonical-taxonomy",
            "version": "COL26.7-test",
            "url": "https://www.checklistbank.org/dataset/315777",
            "licence": "CC-BY-4.0",
            "citation": "Catalogue of Life, COL26.7.",
            "redistribution": "build-input",
            "content_sha256": col_sha256,
        }
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestColConcepts:
    @pytest.fixture
    def built_with_col(self, tmp_path):
        ioc_pinned = hashlib.sha256(b"the ioc workbook the manifest froze").hexdigest()
        col_pinned = hashlib.sha256(b"the col export the manifest froze").hexdigest()
        reference = _fixture_reference(tmp_path, source_sha256=ioc_pinned)
        manifest = _manifest_with_col(tmp_path, ioc_sha256=ioc_pinned, col_sha256=col_pinned)
        col = _col_concepts(tmp_path, export_sha256=col_pinned)
        output = tmp_path / "seed_with_col.db"
        seed_builder.build(reference, output, manifest_path=manifest, col_concepts_path=col)
        return output

    def test_non_bird_concepts_become_species_beside_the_birds(self, built_with_col):
        assert _query(built_with_col, "SELECT COUNT(*) FROM species")[0][0] == 5  # 3 IOC + 2 CoL

        worm = _query(
            built_with_col,
            "SELECT provider, provider_taxon_id, source_release, scientific_name FROM species_concepts"
            " WHERE scientific_name = 'Lumbricus terrestris'",
        )
        assert worm == [("catalogue-of-life", "C1", "COL26.7-test", "Lumbricus terrestris")]

    def test_a_synonym_resolved_class_keeps_its_label_text_as_an_alias(self, built_with_col):
        alias = _query(
            built_with_col,
            "SELECT a.alias, a.resolution, c.scientific_name FROM species_aliases a"
            " JOIN species_concepts c ON c.species_id = a.species_id WHERE a.alias = 'Old synonymus'",
        )
        assert alias == [("Old synonymus", "resolved", "Nova acceptus")]

    def test_an_unresolved_class_is_recorded_without_a_guess(self, built_with_col):
        rows = _query(
            built_with_col,
            "SELECT species_id, resolution FROM species_aliases WHERE alias = 'Mysteria incognita'",
        )
        assert rows == [(None, "unresolved")]

    def test_the_release_manifest_records_both_sources(self, built_with_col):
        manifest_json = _query(built_with_col, "SELECT source_manifest FROM catalogue_releases")[0][0]
        ids = {source["id"] for source in json.loads(manifest_json)["sources"]}
        assert ids == {"ioc-world-bird-list", "catalogue-of-life"}

    def test_a_col_artifact_that_does_not_match_the_pin_is_refused(self, tmp_path):
        ioc_pinned = hashlib.sha256(b"the ioc workbook the manifest froze").hexdigest()
        reference = _fixture_reference(tmp_path, source_sha256=ioc_pinned)
        manifest = _manifest_with_col(tmp_path, ioc_sha256=ioc_pinned, col_sha256="d" * 64)
        col = _col_concepts(tmp_path, export_sha256="e" * 64)

        with pytest.raises(SystemExit, match="[Pp]rovenance"):
            seed_builder.build(reference, tmp_path / "refused.db", manifest_path=manifest, col_concepts_path=col)


def test_the_committed_assets_build_the_full_catalogue(tmp_path):
    """Both real assets together: every IOC bird plus every resolved non-bird class."""
    reference = ASSETS / "species_reference.db"
    col = ASSETS / "col_nonbird_concepts.json"
    if not reference.is_file() or not col.is_file():
        pytest.skip("bundled assets not present in this checkout")

    output = tmp_path / "full_seed.db"
    seed_builder.build(reference, output, col_concepts_path=col)

    # 7,878 resolved classes collapse onto 7,865 accepted taxa: 12 lumps share an identity.
    assert _query(output, "SELECT COUNT(*) FROM species")[0][0] == 11276 + 7865
    assert _query(output, "SELECT COUNT(*) FROM species_concepts WHERE provider = 'catalogue-of-life'")[0][0] == 7865
    assert _query(output, "SELECT COUNT(*) FROM species_aliases WHERE resolution = 'resolved'")[0][0] == 342
    assert _query(output, "SELECT COUNT(*) FROM species_aliases WHERE resolution = 'unresolved'")[0][0] == 636


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
