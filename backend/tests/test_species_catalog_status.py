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
    assert status["active_release"]["sources"] == [{"id": "ioc-world-bird-list", "version": "14.2-test"}]

    artifacts = status["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["registry_id"] == "status_model"
    assert artifacts[0]["output_width"] == 4
    assert artifacts[0]["mapped_outputs"] == 3
    assert artifacts[0]["unresolved_outputs"] == 1
    assert artifacts[0]["complete"] is False


def test_a_missing_catalogue_reports_unavailable_without_raising(tmp_path):
    status = SpeciesCatalogStatus(tmp_path / "nowhere.db").status()

    assert status == {"available": False, "species_count": 0, "active_release": None, "artifacts": []}


class TestActivationCheck:
    def test_a_registered_complete_artifact_is_ready(self, catalog):
        connection = sqlite3.connect(catalog)
        try:
            # Complete the mapping so the artifact has one row per index.
            connection.execute(
                "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                " VALUES (1, 3, 'species', 2, 'Mystery bird')"
            )
            connection.commit()
        finally:
            connection.close()

        check = SpeciesCatalogStatus(catalog).activation_check("s" * 64, tensor_width=4)

        assert check["verdict"] == "ready"
        assert check["registry_id"] == "status_model"

    def test_an_incomplete_mapping_is_named_as_the_blocker(self, catalog):
        check = SpeciesCatalogStatus(catalog).activation_check("s" * 64, tensor_width=4)

        assert check["verdict"] == "incomplete_mapping"
        assert check["unresolved_outputs"] == 1

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
