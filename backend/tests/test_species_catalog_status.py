"""Reporting the species catalogue's state and mapping coverage.

Phase 2 diagnostics: the Health surface reports which catalogue release is
active, how many species it holds, and how far each registered model
artifact's outputs are mapped. The activation check resolves a model checksum
directly against SQLite — the machinery that will gate model selection once
label-file authority is retired; until then its verdicts are advisory and
reported rather than enforced.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

from app.services.species_catalog_status import SpeciesCatalogStatus  # noqa: E402

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""


@pytest.fixture
def catalog(tmp_path):
    """A seed with two species and one artifact mapping four outputs, one of
    which is an unresolved gap."""
    pinned = hashlib.sha256(b"status ioc").hexdigest()
    reference = tmp_path / "reference.db"
    connection = sqlite3.connect(reference)
    try:
        connection.executescript(REFERENCE_SCHEMA)
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (pinned,))
        connection.executemany(
            "INSERT INTO taxon VALUES (?, ?, ?)",
            [(1, "Cyanistes caeruleus", "Eurasian Blue Tit"), (2, "Erithacus rubecula", "European Robin")],
        )
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

    mappings = tmp_path / "mappings.json"
    mappings.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "label_files": {
                    "labelsha-status": {
                        "label_format": "common_name",
                        "output_width": 4,
                        "outputs": [
                            {
                                "index": 0,
                                "kind": "species",
                                "label": "Eurasian blue tit",
                                "provider": "ioc-world-bird-list",
                                "taxon": "Cyanistes caeruleus",
                            },
                            {
                                "index": 1,
                                "kind": "species",
                                "label": "European robin",
                                "provider": "ioc-world-bird-list",
                                "taxon": "Erithacus rubecula",
                            },
                            {"index": 2, "kind": "unknown", "label": "Unknown"},
                            {
                                "index": 3,
                                "kind": "species",
                                "label": "Mystery bird",
                                "unresolved": "no catalogue identity",
                            },
                        ],
                    }
                },
                "artifacts": [
                    {
                        "artifact_id": "status_model",
                        "model_sha256": "s" * 64,
                        "labels_sha256": "labelsha-status",
                        "runtime": "onnx",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    path = tmp_path / "catalog.db"
    seed_builder.build(reference, path, manifest_path=manifest, model_mappings_path=mappings)
    return path


def test_status_reports_the_active_release_and_coverage(catalog):
    status = SpeciesCatalogStatus(catalog).status()

    assert status["available"] is True
    assert status["species_count"] == 2
    # The citation and licence travel with the version: the catalogue
    # redistributes work under CC BY terms, and an owner cannot attribute what
    # diagnostics never show them. `name` is not here because the seed builder
    # does not persist it, and a field that is always null is not provenance.
    assert status["active_release"]["sources"] == [
        {
            "id": "ioc-world-bird-list",
            "version": "14.2-test",
            "licence": "CC-BY-3.0",
            "citation": "IOC World Bird List.",
            "url": "https://www.worldbirdnames.org/",
        }
    ]

    artifacts = status["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["registry_id"] == "status_model"
    assert artifacts[0]["output_width"] == 4
    # Two of the four outputs are identified. Index 2 is declared `unknown`
    # and index 3 resolved to nothing, and neither is a mapping: coverage
    # counts identity rather than the presence of a row.
    assert artifacts[0]["mapped_outputs"] == 2
    assert artifacts[0]["unresolved_outputs"] == 2
    assert artifacts[0]["complete"] is False


def test_a_missing_catalogue_reports_unavailable_without_raising(tmp_path):
    status = SpeciesCatalogStatus(tmp_path / "nowhere.db").status()

    assert status == {"available": False, "species_count": 0, "active_release": None, "artifacts": []}


class TestActivationCheck:
    def test_a_registered_complete_artifact_is_ready(self, catalog):
        connection = sqlite3.connect(catalog)
        try:
            # Give every output an identity. A row alone is no longer enough:
            # index 2 is declared `unknown` and index 3 resolved to nothing, so
            # both have to become something the catalogue can name before the
            # artifact is complete.
            connection.execute(
                "UPDATE model_output_taxa SET class_kind='background', source_label='background' WHERE output_index = 2"
            )
            connection.execute("UPDATE model_output_taxa SET class_kind='species', species_id=2 WHERE output_index = 3")
            connection.commit()
        finally:
            connection.close()

        check = SpeciesCatalogStatus(catalog).activation_check("s" * 64, tensor_width=4)

        assert check["verdict"] == "ready"
        assert check["registry_id"] == "status_model"

    def test_an_incomplete_mapping_is_named_as_the_blocker(self, catalog):
        check = SpeciesCatalogStatus(catalog).activation_check("s" * 64, tensor_width=4)

        assert check["verdict"] == "incomplete_mapping"
        # Index 2 is declared `unknown` and index 3 resolved to nothing.
        assert check["unresolved_outputs"] == 2

    def test_a_tensor_width_mismatch_fails_the_check(self, catalog):
        check = SpeciesCatalogStatus(catalog).activation_check("s" * 64, tensor_width=1486)

        assert check["verdict"] == "width_mismatch"
        assert check["output_width"] == 4

    def test_an_unregistered_checksum_fails_the_check(self, catalog):
        check = SpeciesCatalogStatus(catalog).activation_check("f" * 64)

        assert check["verdict"] == "unregistered"

    def test_a_missing_catalogue_reports_unavailable(self, tmp_path):
        check = SpeciesCatalogStatus(tmp_path / "nowhere.db").activation_check("s" * 64)

        assert check["verdict"] == "unavailable"


def test_the_health_payload_carries_the_catalogue(catalog, monkeypatch):
    from app import main as main_module
    from app.services import species_catalog_status as status_module

    monkeypatch.setattr(status_module, "species_catalog_status", SpeciesCatalogStatus(catalog))

    naming = main_module._naming_health()

    assert naming["species_catalog"]["available"] is True
    assert naming["species_catalog"]["species_count"] == 2


def test_a_malformed_source_manifest_degrades_gracefully(catalog):
    """The manifest column is free text; valid-but-wrong JSON must not crash
    the health path or hide a healthy catalogue."""
    connection = sqlite3.connect(catalog)
    try:
        connection.execute("UPDATE catalogue_releases SET source_manifest = '[]'")
        connection.commit()
    finally:
        connection.close()

    status = SpeciesCatalogStatus(catalog).status()

    assert status["available"] is True
    assert status["species_count"] == 2
    assert status["active_release"]["sources"] == []


def test_status_is_cached_until_the_file_changes(catalog):
    service = SpeciesCatalogStatus(catalog)
    first = service.status()

    connection = sqlite3.connect(catalog)
    try:
        connection.execute("INSERT INTO species (rank, status) VALUES ('species', 'accepted')")
        connection.commit()
    finally:
        connection.close()

    assert service.status()["species_count"] == first["species_count"] + 1
