"""Detector outputs are checksum-bound catalogue entries, never a labels file."""

import json
import sqlite3

import pytest

from app.repositories.garden_catalog import GardenCatalog
from app.repositories.garden_detector_catalog import GardenDetectorCatalog, read_detector_package
from app.services.species_catalog_migrations import upgrade_catalog


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "catalog.db"
    upgrade_catalog(path)
    GardenCatalog(path).initialize()
    return GardenDetectorCatalog(path)


def test_detector_mapping_is_idempotent_and_generic_animal_has_a_canonical_taxon(catalogue):
    catalogue.initialize()
    first = catalogue.load()
    catalogue.initialize()
    assert catalogue.load() == first
    assert first["names"] == ["animal", "person", "vehicle"]
    assert first["model_bytes"] == 101228666
    with sqlite3.connect(catalogue.path) as db:
        rows = db.execute(
            "SELECT t.class_kind,t.species_id,t.source_label FROM model_output_taxa t JOIN model_artifacts a ON a.id=t.model_artifact_id WHERE a.registry_id=? ORDER BY t.output_index",
            (first["registry_id"],),
        ).fetchall()
        assert rows[0][0] == "aggregate" and rows[0][1] is not None
        assert rows[1:] == [("background", None, "person"), ("background", None, "vehicle")]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_changed_shipped_mapping_is_rejected_before_catalogue_writes(catalogue, tmp_path):
    package = read_detector_package()
    package["names"] = ["person", "animal", "vehicle"]
    altered = tmp_path / "changed.json"
    altered.write_text(json.dumps(package))
    with pytest.raises(ValueError, match="checksum"):
        catalogue.initialize(altered)


def test_tampered_database_output_order_cannot_run_a_detector(catalogue):
    catalogue.initialize()
    package = catalogue.load()
    with sqlite3.connect(catalogue.path) as db:
        db.execute(
            "UPDATE model_output_taxa SET source_label='person' WHERE output_index=0 AND model_artifact_id=(SELECT id FROM model_artifacts WHERE registry_id=?)",
            (package["registry_id"],),
        )
    with pytest.raises(ValueError, match="mapping"):
        catalogue.load()
