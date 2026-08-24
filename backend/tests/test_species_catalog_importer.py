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


def test_aliases_travel_with_the_release_and_do_not_duplicate(live, tmp_path):
    """A bundle's aliases are remapped and imported; unresolved ones (NULL
    species) are deduplicated explicitly because SQLite's unique constraint
    cannot see two NULLs as equal."""
    connection = sqlite3.connect(live)
    try:
        connection.execute(
            "INSERT INTO species_aliases (alias, alias_kind, species_id, resolution, source)"
            " VALUES ('Mysteria incognita', 'model_label', NULL, 'unresolved', 'catalogue-of-life')"
        )
        connection.commit()
    finally:
        connection.close()

    pinned = hashlib.sha256(b"release with aliases").hexdigest()
    reference = _reference(
        tmp_path / "ref3.db",
        [(1, "Cyanistes caeruleus", "Eurasian Blue Tit")],
        [],
        source_sha256=pinned,
    )
    manifest = _manifest(tmp_path / "m3.json", pinned_sha256=pinned, version="16.0-test")
    bundle_path = tmp_path / "bundle3.db"
    seed_builder.build(reference, bundle_path, manifest_path=manifest)
    connection = sqlite3.connect(bundle_path)
    try:
        connection.execute(
            "INSERT INTO species_aliases (alias, alias_kind, species_id, resolution, source)"
            " VALUES ('Parus caeruleus', 'synonym', 1, 'resolved', 'catalogue-of-life')"
        )
        connection.execute(
            "INSERT INTO species_aliases (alias, alias_kind, species_id, resolution, source)"
            " VALUES ('Mysteria incognita', 'model_label', NULL, 'unresolved', 'catalogue-of-life')"
        )
        # Re-record the content digest so the tampered-bundle guard admits it.
        from app.services.species_catalog_release import release_content_digest

        release = connection.execute(
            "SELECT schema_version, source_manifest, generated_at FROM catalogue_releases"
        ).fetchone()
        connection.execute(
            "UPDATE catalogue_releases SET content_sha256 = ?",
            (
                release_content_digest(
                    connection, schema_version=release[0], source_manifest=release[1], generated_at=release[2]
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    import_release(bundle_path, catalog_path=live)

    tit = _query(live, "SELECT species_id FROM species_concepts WHERE provider_taxon_id = 'Cyanistes caeruleus'")[0][0]
    resolved = _query(live, "SELECT species_id FROM species_aliases WHERE alias = 'Parus caeruleus'")
    assert resolved == [(tit,)]
    unresolved = _query(live, "SELECT COUNT(*) FROM species_aliases WHERE alias = 'Mysteria incognita'")
    assert unresolved[0][0] == 1


def test_a_bundle_with_forged_release_metadata_is_refused(live, bundle):
    """The digest covers the release row's own provenance, not only content."""
    connection = sqlite3.connect(bundle)
    try:
        connection.execute("UPDATE catalogue_releases SET source_manifest = '{\"sources\": []}'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogImportError, match="digest"):
        import_release(bundle, catalog_path=live)


def test_a_divergent_mapping_for_a_registered_artifact_fails_the_import(tmp_path):
    """A same-checksum artifact with a different mapping set is a build defect;
    per the safety model the release fails closed instead of warning."""
    live = _build_mapped_seed(tmp_path, "live_conflict.db", label="Eurasian blue tit")
    bundle = _build_mapped_seed(tmp_path, "bundle_conflict.db", label="European robin")

    with pytest.raises(CatalogImportError, match="different mapping set"):
        import_release(bundle, catalog_path=live)


def _build_mapped_seed(tmp_path, output_name, *, label):
    """Two seeds whose only difference is one mapped label, sharing the
    artifact checksum, so their mapping sets diverge."""
    import json as json_module

    pinned = hashlib.sha256(b"conflict workbook").hexdigest()
    reference_path = tmp_path / "conflict_ref.db"
    if not reference_path.exists():
        _reference(
            reference_path,
            [(1, "Cyanistes caeruleus", "Eurasian Blue Tit"), (2, "Erithacus rubecula", "European Robin")],
            [],
            source_sha256=pinned,
        )
    manifest = _manifest(tmp_path / f"conflict_manifest_{output_name}.json", pinned_sha256=pinned, version="17.0-test")
    mappings = tmp_path / f"conflict_mappings_{output_name}.json"
    taxon = "Cyanistes caeruleus" if label == "Eurasian blue tit" else "Erithacus rubecula"
    mappings.write_text(
        json_module.dumps(
            {
                "schema_version": 1,
                "label_files": {
                    "labelsha-conflict": {
                        "label_format": "common_name",
                        "output_width": 1,
                        "outputs": [
                            {
                                "index": 0,
                                "kind": "species",
                                "label": label,
                                "provider": "ioc-world-bird-list",
                                "taxon": taxon,
                            }
                        ],
                    }
                },
                "artifacts": [
                    {
                        "artifact_id": "conflict_model",
                        "model_sha256": "c" * 64,
                        "labels_sha256": "labelsha-conflict",
                        "runtime": "onnx",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / output_name
    seed_builder.build(reference_path, path, manifest_path=manifest, model_mappings_path=mappings)
    return path


def _build_two_output_seed(
    tmp_path, output_name, *, second_resolved, second_label="European robin", second_present=True
):
    """Two seeds sharing one artifact checksum, differing only in whether the
    second output resolved to a catalogue identity."""
    import json as json_module

    pinned = hashlib.sha256(b"supersession workbook").hexdigest()
    reference_path = tmp_path / "supersession_ref.db"
    if not reference_path.exists():
        _reference(
            reference_path,
            [(1, "Cyanistes caeruleus", "Eurasian Blue Tit"), (2, "Erithacus rubecula", "European Robin")],
            [],
            source_sha256=pinned,
        )
    manifest = _manifest(
        tmp_path / f"supersession_manifest_{output_name}.json", pinned_sha256=pinned, version="18.0-test"
    )
    second = {"index": 1, "kind": "species", "label": second_label}
    if second_resolved:
        second["provider"] = "ioc-world-bird-list"
        second["taxon"] = "Erithacus rubecula"
    else:
        second["unresolved"] = "no catalogue identity"

    mappings = tmp_path / f"supersession_mappings_{output_name}.json"
    mappings.write_text(
        json_module.dumps(
            {
                "schema_version": 1,
                "label_files": {
                    "labelsha-supersession": {
                        "label_format": "common_name",
                        "output_width": 2 if second_present else 1,
                        "outputs": [
                            {
                                "index": 0,
                                "kind": "species",
                                "label": "Eurasian blue tit",
                                "provider": "ioc-world-bird-list",
                                "taxon": "Cyanistes caeruleus",
                            },
                            *([second] if second_present else []),
                        ],
                    }
                },
                "artifacts": [
                    {
                        "artifact_id": "supersession_model",
                        "model_sha256": "d" * 64,
                        "labels_sha256": "labelsha-supersession",
                        "runtime": "onnx",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / output_name
    seed_builder.build(reference_path, path, manifest_path=manifest, model_mappings_path=mappings)
    return path


def _outputs(catalog_path):
    connection = sqlite3.connect(catalog_path)
    try:
        return connection.execute(
            "SELECT output_index, class_kind, species_id, source_label FROM model_output_taxa ORDER BY output_index"
        ).fetchall()
    finally:
        connection.close()


def _mapping_digest(catalog_path):
    connection = sqlite3.connect(catalog_path)
    try:
        return connection.execute("SELECT mapping_set_sha256 FROM model_artifacts").fetchone()[0]
    finally:
        connection.close()


def test_an_output_that_had_no_identity_may_gain_one(tmp_path):
    """A rebuilt mapping that names an output nothing could name before is not
    a correction: no claim is being replaced, because none was made. The
    catalogue recorded `unknown` with the model's own label, and the release
    that can name it should be able to say so."""
    live = _build_two_output_seed(tmp_path, "gain_live.db", second_resolved=False)
    bundle = _build_two_output_seed(tmp_path, "gain_bundle.db", second_resolved=True)
    assert _outputs(live)[1][1:3] == ("unknown", None)
    before_digest = _mapping_digest(live)

    result = import_release(bundle, catalog_path=live)

    assert result.status == "imported"
    index, kind, species_id, label = _outputs(live)[1]
    assert (kind, label) == ("species", "European robin")
    assert species_id is not None
    # The artifact now carries the mapping set it was actually given, so a
    # later import of the same release is a no-op rather than another upgrade.
    assert _mapping_digest(live) != before_digest


def test_an_identity_that_was_recorded_is_never_replaced(tmp_path):
    """The reverse direction is a correction of a claim already made, and that
    still needs a deliberate supersession rather than arriving in a release."""
    live = _build_two_output_seed(tmp_path, "swap_live.db", second_resolved=True)
    bundle = _build_two_output_seed(tmp_path, "swap_bundle.db", second_resolved=False)
    before = _outputs(live)

    with pytest.raises(CatalogImportError, match="different mapping set"):
        import_release(bundle, catalog_path=live)

    assert _outputs(live) == before


def test_an_output_whose_label_changed_is_refused(tmp_path):
    """A different label is a different model output, whatever it resolves to."""
    live = _build_two_output_seed(tmp_path, "label_live.db", second_resolved=False)
    bundle = _build_two_output_seed(
        tmp_path, "label_bundle.db", second_resolved=True, second_label="Something else entirely"
    )
    before = _outputs(live)

    with pytest.raises(CatalogImportError, match="different mapping set"):
        import_release(bundle, catalog_path=live)

    assert _outputs(live) == before


def _artifact_row(catalog_path):
    connection = sqlite3.connect(catalog_path)
    try:
        return connection.execute(
            "SELECT registry_id, mapping_set_sha256, output_width FROM model_artifacts"
        ).fetchone()
    finally:
        connection.close()


def _register_local_artifact(catalog_path, *, model_sha256, labels):
    """Stand in for a model the owner installed themselves, mapped by the
    compatibility importer rather than by a release."""
    from app.services.species_catalog_compatibility import import_local_model_mapping

    return import_local_model_mapping(
        model_id="owner_model",
        model_sha256=model_sha256,
        labels=labels,
        runtime="onnx",
        catalog_path=catalog_path,
    )


def test_a_published_mapping_replaces_one_this_install_derived_for_itself(tmp_path):
    """A model the owner sideloaded gets a mapping derived from its own labels.
    If that model is later published, the reviewed mapping has to be able to
    land: refusing it because it disagrees with a locally derived guess would
    block every future catalogue release for that owner.
    """
    live = _build_two_output_seed(tmp_path, "local_live.db", second_resolved=False)
    connection = sqlite3.connect(live)
    try:
        connection.execute("DELETE FROM model_output_taxa")
        connection.execute("DELETE FROM model_artifacts")
        connection.commit()
    finally:
        connection.close()

    report = _register_local_artifact(live, model_sha256="d" * 64, labels=["Eurasian Blue Tit", "European Robin"])
    assert report.verdict == "imported"
    assert _artifact_row(live)[0].startswith("local:")

    bundle = _build_two_output_seed(tmp_path, "local_bundle.db", second_resolved=True)
    result = import_release(bundle, catalog_path=live)

    assert result.status == "imported"
    registry_id, _, _ = _artifact_row(live)
    # The reviewed mapping now owns the artifact, under its published id.
    assert registry_id == "supersession_model"
    assert [row[3] for row in _outputs(live)] == ["Eurasian blue tit", "European robin"]


def test_a_mapping_that_drops_outputs_is_refused(tmp_path):
    """Fewer outputs for the same model checksum is a build defect. Accepting
    it would leave rows the mapping no longer describes while recording that
    mapping's digest, so the catalogue would claim a mapping it does not hold.
    """
    live = _build_two_output_seed(tmp_path, "shrink_live.db", second_resolved=True)
    bundle = _build_two_output_seed(tmp_path, "shrink_bundle.db", second_resolved=True, second_present=False)
    before = _outputs(live)
    assert len(before) == 2

    with pytest.raises(CatalogImportError, match="different mapping set"):
        import_release(bundle, catalog_path=live)

    assert _outputs(live) == before


def test_repairing_an_already_imported_release_never_writes_a_bundle_species_number(tmp_path):
    """The repair runs before any species mapping is built, so a bundle's own
    species numbering cannot be translated. Restoring a row that carries one
    would bind the output to whichever species holds that number here."""
    # The same release on both sides, so the import takes the already-imported
    # repair path. Output 0 carries an identity, output 1 does not.
    live = _build_two_output_seed(tmp_path, "repair_live.db", second_resolved=False)
    bundle = _build_two_output_seed(tmp_path, "repair_bundle.db", second_resolved=False)

    connection = sqlite3.connect(live)
    try:
        connection.execute("DELETE FROM model_output_taxa")
        connection.commit()
    finally:
        connection.close()

    result = import_release(bundle, catalog_path=live)
    assert result.status == "already_imported"

    restored = _outputs(live)
    # Only the identity-free row comes back; the one carrying a species number
    # is left for a real import to place.
    assert [row[0] for row in restored] == [1]
    assert restored[0][1:3] == ("unknown", None)
