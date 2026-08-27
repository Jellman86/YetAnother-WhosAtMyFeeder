"""The species-source manifest and its provenance gate.

Phase 0 of the versioned species catalogue freezes where species data may come
from: every source carries a pinned release, a licence, a citation, and an
explicit redistribution decision, and a build that names a source outside that
manifest fails instead of proceeding. See
docs/plans/2026-08-12-versioned-species-catalogue-design.md.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from app.services.species_provenance import (
    REDISTRIBUTION_DECISIONS,
    SourceProvenanceError,
    default_manifest_path,
    load_source_manifest,
    require_build_source,
)

ASSETS = Path(__file__).resolve().parent.parent / "app" / "assets"


def _write_manifest(tmp_path, sources) -> Path:
    path = tmp_path / "species_sources.json"
    path.write_text(json.dumps({"schema_version": 1, "frozen_on": "2026-08-19", "sources": sources}), encoding="utf-8")
    return path


def _source(**overrides) -> dict:
    base = {
        "id": "example-source",
        "name": "Example Source",
        "role": "canonical-taxonomy",
        "version": "1.0",
        "url": "https://example.org/data",
        "licence": "CC-BY-4.0",
        "citation": "Example Source (2026). https://example.org/",
        "redistribution": "build-input",
        "content_sha256": None,
    }
    base.update(overrides)
    return base


class TestShippedManifest:
    def test_the_shipped_manifest_loads_and_is_complete(self):
        sources = load_source_manifest()

        assert {"ioc-world-bird-list", "catalogue-of-life", "ebird-taxonomy", "inaturalist"} <= set(sources)
        for source in sources.values():
            assert source.redistribution in REDISTRIBUTION_DECISIONS
            assert source.citation
            assert source.url

    def test_every_pinned_source_names_its_release(self):
        """A frozen contract with an unpinned source is not frozen."""
        sources = load_source_manifest()

        assert sources["ioc-world-bird-list"].version
        assert sources["catalogue-of-life"].version
        assert sources["ebird-taxonomy"].version

    def test_the_catalogue_of_life_export_is_pinned_by_digest(self):
        """Recorded when the COL26.7 ColDP export was first downloaded; the
        non-bird extraction refuses any other file."""
        sources = load_source_manifest()

        assert sources["catalogue-of-life"].content_sha256
        assert len(sources["catalogue-of-life"].content_sha256) == 64

    def test_the_col_concepts_artifact_matches_the_manifest_pin(self):
        artifact = json.loads((ASSETS / "col_nonbird_concepts.json").read_text(encoding="utf-8"))
        sources = load_source_manifest()

        assert artifact["source"]["export_sha256"] == sources["catalogue-of-life"].content_sha256
        assert artifact["source"]["version"] == sources["catalogue-of-life"].version
        assert artifact["counts"]["resolved"] == len(artifact["concepts"])
        assert artifact["counts"]["unresolved"] == len(artifact["unresolved"])

    def test_the_manifest_matches_the_shipped_reference_database(self):
        """The manifest's IOC checksum is the digest the committed asset was built from."""
        sources = load_source_manifest()

        connection = sqlite3.connect(f"file:{ASSETS / 'species_reference.db'}?mode=ro", uri=True)
        try:
            recorded = dict(connection.execute("SELECT key, value FROM reference_meta").fetchall())
        finally:
            connection.close()

        assert sources["ioc-world-bird-list"].content_sha256 == recorded["source_sha256"]
        assert sources["ioc-world-bird-list"].licence == recorded["source_licence"]

    def test_the_manifest_matches_the_registry_coral_labels(self):
        """The bundled Coral label file is pinned by the same checksum the registry publishes."""
        from app.services.label_integrity import published_labels_sha256

        sources = load_source_manifest()

        assert sources["google-coral-inat-bird-labels"].content_sha256 == published_labels_sha256("mobilenet_v2_birds")

    def test_the_default_path_is_the_shipped_asset(self):
        assert default_manifest_path() == ASSETS / "species_sources.json"


class TestManifestValidation:
    def test_a_duplicate_source_id_is_rejected(self, tmp_path):
        path = _write_manifest(tmp_path, [_source(), _source()])

        with pytest.raises(SourceProvenanceError, match="duplicate"):
            load_source_manifest(path)

    def test_a_missing_licence_is_rejected(self, tmp_path):
        path = _write_manifest(tmp_path, [_source(licence="")])

        with pytest.raises(SourceProvenanceError, match="licence"):
            load_source_manifest(path)

    def test_an_unknown_redistribution_decision_is_rejected(self, tmp_path):
        path = _write_manifest(tmp_path, [_source(redistribution="probably-fine")])

        with pytest.raises(SourceProvenanceError, match="redistribution"):
            load_source_manifest(path)

    def test_an_unspecified_licence_is_only_tolerated_when_redistribution_is_forbidden(self, tmp_path):
        allowed = _write_manifest(tmp_path, [_source(licence="unspecified", redistribution="forbidden")])
        assert load_source_manifest(allowed)

        refused = _write_manifest(tmp_path, [_source(licence="unspecified", redistribution="bundled")])
        with pytest.raises(SourceProvenanceError, match="licence"):
            load_source_manifest(refused)

    def test_a_bundled_source_must_pin_its_version(self, tmp_path):
        path = _write_manifest(tmp_path, [_source(redistribution="bundled", version="")])

        with pytest.raises(SourceProvenanceError, match="version"):
            load_source_manifest(path)


class TestBuildGate:
    def test_an_unknown_source_is_rejected(self, tmp_path):
        sources = load_source_manifest(_write_manifest(tmp_path, [_source()]))

        with pytest.raises(SourceProvenanceError, match="not in the source manifest"):
            require_build_source(sources, "scraped-from-somewhere")

    def test_a_source_the_manifest_forbids_cannot_be_a_build_input(self, tmp_path):
        sources = load_source_manifest(
            _write_manifest(tmp_path, [_source(licence="unspecified", redistribution="forbidden")])
        )

        with pytest.raises(SourceProvenanceError, match="redistribution"):
            require_build_source(sources, "example-source")

    def test_a_runtime_fetch_source_cannot_be_a_build_input(self, tmp_path):
        sources = load_source_manifest(_write_manifest(tmp_path, [_source(redistribution="runtime-fetch")]))

        with pytest.raises(SourceProvenanceError, match="redistribution"):
            require_build_source(sources, "example-source")

    def test_an_input_file_that_does_not_match_the_pinned_checksum_is_rejected(self, tmp_path):
        pinned = hashlib.sha256(b"the release the manifest froze").hexdigest()
        sources = load_source_manifest(_write_manifest(tmp_path, [_source(content_sha256=pinned)]))

        with pytest.raises(SourceProvenanceError, match="checksum"):
            require_build_source(sources, "example-source", content_sha256="a" * 64)

    def test_a_matching_input_passes_and_returns_the_source(self, tmp_path):
        pinned = hashlib.sha256(b"the release the manifest froze").hexdigest()
        sources = load_source_manifest(_write_manifest(tmp_path, [_source(content_sha256=pinned)]))

        source = require_build_source(sources, "example-source", content_sha256=pinned)

        assert source.version == "1.0"

    def test_a_source_with_no_pinned_checksum_accepts_any_input_but_still_gates_licence(self, tmp_path):
        """Catalogue of Life is pinned by DOI before its export is first downloaded."""
        sources = load_source_manifest(_write_manifest(tmp_path, [_source(content_sha256=None)]))

        assert require_build_source(sources, "example-source", content_sha256="b" * 64)
