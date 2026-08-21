"""Shadow-resolving inference through the catalogue beside the label path.

Phase 3 of the catalogue design: every new detection records which model
artifact and output index produced it, and gains a canonical `species_id`
only when the catalogue and the label path agree on the identity. A
disagreement is surfaced in diagnostics, never silently persisted; a missing
catalogue or unregistered model degrades to provenance-free detections
exactly as before.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

from app.services.species_catalog_resolver import SpeciesCatalogResolver  # noqa: E402

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""

MODEL_SHA = "d" * 64


@pytest.fixture
def catalog(tmp_path):
    """A catalogue mapping one artifact: blue tit, a synonym-resolved toad,
    an unknown class, and one unresolved index."""
    ioc_pinned = hashlib.sha256(b"resolver ioc").hexdigest()
    col_pinned = hashlib.sha256(b"resolver col").hexdigest()

    reference = tmp_path / "reference.db"
    connection = sqlite3.connect(reference)
    try:
        connection.executescript(REFERENCE_SCHEMA)
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (ioc_pinned,))
        connection.execute("INSERT INTO taxon VALUES (1, 'Cyanistes caeruleus', 'Eurasian Blue Tit')")
        connection.commit()
    finally:
        connection.close()

    col = tmp_path / "col.json"
    col.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": {"id": "catalogue-of-life", "version": "COL26.7-test", "export_sha256": col_pinned},
                "concepts": [
                    {
                        "scientific_name": "Bufotes balearicus",
                        "kingdom": "Animalia",
                        "label_class": "Amphibia",
                        "col_id": "S1",
                        "col_status": "synonym",
                        "accepted_col_id": "A1",
                        "accepted_scientific_name": "Bufotes viridis",
                    }
                ],
                "unresolved": [],
            }
        ),
        encoding="utf-8",
    )

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
                        "content_sha256": ioc_pinned,
                    },
                    {
                        "id": "catalogue-of-life",
                        "name": "Catalogue of Life",
                        "role": "canonical-taxonomy",
                        "version": "COL26.7-test",
                        "url": "https://www.checklistbank.org/dataset/315777",
                        "licence": "CC-BY-4.0",
                        "citation": "Catalogue of Life, COL26.7.",
                        "redistribution": "build-input",
                        "content_sha256": col_pinned,
                    },
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
                    "labelsha-resolver": {
                        "label_format": "scientific_binomial",
                        "output_width": 4,
                        "outputs": [
                            {
                                "index": 0,
                                "kind": "species",
                                "label": "Cyanistes caeruleus",
                                "provider": "ioc-world-bird-list",
                                "taxon": "Cyanistes caeruleus",
                            },
                            {
                                "index": 1,
                                "kind": "species",
                                "label": "Bufotes balearicus",
                                "provider": "catalogue-of-life",
                                "taxon": "A1",
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
                        "artifact_id": "resolver_model",
                        "model_sha256": MODEL_SHA,
                        "labels_sha256": "labelsha-resolver",
                        "runtime": "onnx",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    path = tmp_path / "catalog.db"
    seed_builder.build(reference, path, manifest_path=manifest, col_concepts_path=col, model_mappings_path=mappings)
    return path


@pytest.fixture
def resolver(catalog):
    return SpeciesCatalogResolver(catalog)


def test_agreement_yields_the_canonical_identity(resolver):
    result = resolver.shadow_resolve(MODEL_SHA, 0, "Cyanistes caeruleus")

    assert result.verdict == "agree"
    assert result.species_id is not None
    assert result.model_artifact_id is not None
    assert result.model_output_index == 0


def test_a_recorded_synonym_counts_as_agreement(resolver):
    """The label path still says Bufotes balearicus; the catalogue knows that
    text as a synonym of the accepted identity, so it is the same bird."""
    result = resolver.shadow_resolve(MODEL_SHA, 1, "Bufotes balearicus")

    assert result.verdict == "agree"
    assert result.species_id is not None


def test_a_disagreement_withholds_the_identity_and_is_counted(resolver):
    result = resolver.shadow_resolve(MODEL_SHA, 0, "Erithacus rubecula", event_id="evt-1")

    assert result.verdict == "mismatch"
    assert result.species_id is None
    assert result.model_artifact_id is not None
    assert result.model_output_index == 0

    stats = resolver.stats()
    assert stats["mismatches"] == 1
    assert stats["last_mismatch"]["event_id"] == "evt-1"
    assert stats["last_mismatch"]["label_scientific"] == "Erithacus rubecula"


def test_a_label_without_a_scientific_name_records_provenance_only(resolver):
    result = resolver.shadow_resolve(MODEL_SHA, 0, None)

    assert result.verdict == "unverified"
    assert result.species_id is None
    assert result.model_artifact_id is not None


def test_a_non_species_class_records_provenance_without_identity(resolver):
    result = resolver.shadow_resolve(MODEL_SHA, 2, None)

    assert result.verdict == "non_species"
    assert result.species_id is None
    assert result.model_output_index == 2


def test_an_unresolved_index_is_a_visible_gap(resolver):
    result = resolver.shadow_resolve(MODEL_SHA, 3, "Mystery bird")

    assert result.verdict == "unresolved_index"
    assert result.species_id is None
    assert result.model_artifact_id is not None


def test_an_unregistered_model_degrades_without_provenance(resolver):
    result = resolver.shadow_resolve("f" * 64, 0, "Cyanistes caeruleus")

    assert result.verdict == "unregistered"
    assert result.species_id is None
    assert result.model_artifact_id is None


def test_a_missing_catalogue_degrades_without_raising(tmp_path):
    missing = SpeciesCatalogResolver(tmp_path / "nowhere.db")

    result = missing.shadow_resolve(MODEL_SHA, 0, "Cyanistes caeruleus")

    assert result.verdict == "unavailable"
    assert result.species_id is None


def test_stats_track_agreements_and_expose_a_snapshot(resolver):
    resolver.shadow_resolve(MODEL_SHA, 0, "Cyanistes caeruleus")
    resolver.shadow_resolve(MODEL_SHA, 0, "Cyanistes Caeruleus")

    stats = resolver.stats()
    assert stats["agreements"] == 2
    assert stats["mismatches"] == 0
