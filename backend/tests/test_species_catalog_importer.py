"""Importing a catalogue release into a live catalogue, transactionally.

A release bundle is a built catalogue file (what the seed builder produces).
The importer validates it — schema head, exactly one release row, recorded
content digest, foreign-key integrity — then stages and activates it in one
transaction against the live catalogue. An interrupted import leaves the
previous release active and no partial rows behind. Species identity is
stable: a taxon already known through a provider concept keeps its
`species_id`, and identities are never deleted, only superseded.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

from app.services import species_catalog_importer as importer_module  # noqa: E402
from app.services.species_catalog_importer import (  # noqa: E402
    CatalogImportError,
    import_release,
    rollback_to_release,
)

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""


def _reference(path: Path, taxa, names, *, source_sha256: str) -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(REFERENCE_SCHEMA)
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (source_sha256,))
        connection.executemany("INSERT INTO taxon VALUES (?, ?, ?)", taxa)
        connection.executemany("INSERT INTO taxon_name VALUES (?, ?, ?)", names)
        connection.commit()
    finally:
        connection.close()
    return path


def _manifest(path: Path, *, pinned_sha256: str, version: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-19",
                "sources": [
                    {
                        "id": "ioc-world-bird-list",
                        "name": "IOC",
                        "role": "bird-vernacular-names",
                        "version": version,
                        "url": "https://www.worldbirdnames.org/",
                        "licence": "CC-BY-3.0",
                        "citation": "IOC World Bird List.",
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
def live(tmp_path):
    """A live catalogue seeded with release one: blue tit and robin."""
    pinned = hashlib.sha256(b"release one workbook").hexdigest()
    reference = _reference(
        tmp_path / "ref1.db",
        [(1, "Cyanistes caeruleus", "Eurasian Blue Tit"), (2, "Erithacus rubecula", "European Robin")],
        [(1, "de", "Blaumeise")],
        source_sha256=pinned,
    )
    manifest = _manifest(tmp_path / "m1.json", pinned_sha256=pinned, version="14.2-test")
    path = tmp_path / "live_catalog.db"
    seed_builder.build(reference, path, manifest_path=manifest)
    return path


@pytest.fixture
def bundle(tmp_path):
    """Release two: the robin renamed provider-side, the blue tit unchanged,
    and a new species; built as its own bundle file."""
    pinned = hashlib.sha256(b"release two workbook").hexdigest()
    reference = _reference(
        tmp_path / "ref2.db",
        [
            (1, "Cyanistes caeruleus", "Eurasian Blue Tit"),
            (2, "Erithacus rubecula", "Robin"),
            (3, "Struthio camelus", "Common Ostrich"),
        ],
        [(1, "de", "Blaumeise"), (3, "de", "Strauss")],
        source_sha256=pinned,
    )
    manifest = _manifest(tmp_path / "m2.json", pinned_sha256=pinned, version="15.0-test")
    path = tmp_path / "bundle_catalog.db"
    seed_builder.build(reference, path, manifest_path=manifest)
    return path


def _query(path, sql, params=()):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def _active_release(path):
    rows = _query(path, "SELECT id, state FROM catalogue_releases WHERE state = 'active'")
    assert len(rows) == 1
    return rows[0][0]


def test_an_import_stages_and_activates_the_new_release(live, bundle):
    before = _active_release(live)

    result = import_release(bundle, catalog_path=live)

    assert result.status == "imported"
    after = _active_release(live)
    assert after != before
    states = dict(_query(live, "SELECT id, state FROM catalogue_releases"))
    assert states[before] == "retired"


def test_species_identity_is_stable_across_releases(live, bundle):
    tit_before = _query(
        live, "SELECT species_id FROM species_concepts WHERE provider_taxon_id = 'Cyanistes caeruleus'"
    )[0][0]

    result = import_release(bundle, catalog_path=live)

    tit_ids = {
        row[0]
        for row in _query(
            live, "SELECT species_id FROM species_concepts WHERE provider_taxon_id = 'Cyanistes caeruleus'"
        )
    }
    assert tit_ids == {tit_before}
    assert result.species_matched == 2
    assert result.species_added == 1


def test_existing_identities_are_never_deleted(live, bundle):
    species_before = {row[0] for row in _query(live, "SELECT species_id FROM species")}

    import_release(bundle, catalog_path=live)

    species_after = {row[0] for row in _query(live, "SELECT species_id FROM species")}
    assert species_before <= species_after


def test_names_from_both_releases_coexist_with_their_provenance(live, bundle):
    import_release(bundle, catalog_path=live)

    robin_names = _query(
        live,
        "SELECT name, source_release FROM species_names"
        " WHERE language_tag = 'en' AND species_id ="
        " (SELECT species_id FROM species_concepts WHERE provider_taxon_id = 'Erithacus rubecula' LIMIT 1)"
        " ORDER BY source_release",
    )
    assert ("European Robin", "14.2-test") in robin_names
    assert ("Robin", "15.0-test") in robin_names


def test_owner_overrides_survive_an_import(live, bundle):
    connection = sqlite3.connect(live)
    try:
        connection.execute("INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (1, '', 'Mine')")
        connection.commit()
    finally:
        connection.close()

    import_release(bundle, catalog_path=live)

    assert _query(live, "SELECT name FROM species_name_overrides") == [("Mine",)]


def test_importing_the_same_bundle_twice_is_a_no_op(live, bundle):
    first = import_release(bundle, catalog_path=live)
    active = _active_release(live)

    second = import_release(bundle, catalog_path=live)

    assert first.status == "imported"
    assert second.status == "already_imported"
    assert _active_release(live) == active
    assert _query(live, "SELECT COUNT(*) FROM catalogue_releases")[0][0] == 2


def test_an_interrupted_import_leaves_the_previous_release_active(live, bundle, monkeypatch):
    before_release = _active_release(live)
    before_species = _query(live, "SELECT COUNT(*) FROM species")[0][0]
    before_names = _query(live, "SELECT COUNT(*) FROM species_names")[0][0]

    def explode(connection):
        raise RuntimeError("power loss, simulated")

    monkeypatch.setattr(importer_module, "_before_activation", explode)
    with pytest.raises(CatalogImportError, match="power loss"):
        import_release(bundle, catalog_path=live)

    assert _active_release(live) == before_release
    assert _query(live, "SELECT COUNT(*) FROM species")[0][0] == before_species
    assert _query(live, "SELECT COUNT(*) FROM species_names")[0][0] == before_names
    assert _query(live, "SELECT COUNT(*) FROM catalogue_releases")[0][0] == 1


def test_a_bundle_whose_content_digest_lies_is_refused(live, bundle):
    connection = sqlite3.connect(bundle)
    try:
        connection.execute("UPDATE species_names SET name = 'Tampered' WHERE language_tag = 'en'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogImportError, match="digest"):
        import_release(bundle, catalog_path=live)
    assert _query(live, "SELECT COUNT(*) FROM catalogue_releases")[0][0] == 1


def test_a_bundle_without_exactly_one_release_row_is_refused(live, bundle):
    connection = sqlite3.connect(bundle)
    try:
        connection.execute("DELETE FROM catalogue_releases")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogImportError, match="release"):
        import_release(bundle, catalog_path=live)


def test_a_bundle_at_a_different_schema_revision_is_refused(live, bundle):
    connection = sqlite3.connect(bundle)
    try:
        connection.execute("UPDATE alembic_version SET version_num = 'somewhere_else'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogImportError, match="schema"):
        import_release(bundle, catalog_path=live)


def test_rollback_reactivates_a_retired_release(live, bundle):
    original = _active_release(live)
    import_release(bundle, catalog_path=live)

    rollback_to_release(original, catalog_path=live)

    assert _active_release(live) == original
    states = [row[0] for row in _query(live, "SELECT state FROM catalogue_releases ORDER BY id")]
    assert states.count("active") == 1


def test_rollback_to_an_unknown_or_active_release_is_refused(live, bundle):
    import_release(bundle, catalog_path=live)
    active = _active_release(live)

    with pytest.raises(CatalogImportError, match="not a retired release"):
        rollback_to_release(active, catalog_path=live)
    with pytest.raises(CatalogImportError, match="not a retired release"):
        rollback_to_release(9999, catalog_path=live)


def test_rollback_keeps_species_added_by_the_newer_release(live, bundle):
    original = _active_release(live)
    import_release(bundle, catalog_path=live)
    ostrich = _query(live, "SELECT species_id FROM species_concepts WHERE provider_taxon_id = 'Struthio camelus'")

    rollback_to_release(original, catalog_path=live)

    still_there = _query(live, "SELECT species_id FROM species WHERE species_id = ?", (ostrich[0][0],))
    assert len(still_there) == 1
