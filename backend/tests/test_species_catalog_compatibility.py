"""Giving an owner-supplied model a catalogue mapping built from its own labels.

Phase 5's compatibility path. Every model in the registry ships a reviewed
mapping in the release bundle; a model the owner installed themselves has
none, so the resolver reports `unregistered` and its detections never gain a
canonical identity. This importer derives a mapping for such a model by
resolving its label file against the live catalogue, records every output it
could not name rather than guessing one, and marks the result as locally
derived so nothing downstream mistakes it for a reviewed release mapping.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

from app.services.catalogue_labels import catalogue_labels_for_model  # noqa: E402
from app.services.species_catalog_compatibility import (  # noqa: E402
    LOCAL_REGISTRY_PREFIX,
    import_local_model_mapping,
)

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""

#: `Goldcrest` is deliberately both one species' English name and another's
#: scientific name. Real catalogues collide less absurdly — a resurrected genus,
#: a common name reused as a binomial — but the importer has to survive the
#: collision whatever produced it, so the fixture states it outright.
TAXA = [
    (1, "Cyanistes caeruleus", "Eurasian Blue Tit"),
    (2, "Erithacus rubecula", "European Robin"),
    (3, "Haemorhous cassinii", "Cassin's Finch"),
    (4, "Spinus psaltria", "Lesser Goldfinch"),
    (5, "Regulus regulus", "Goldcrest"),
    (6, "Goldcrest", "Not A Real Bird"),
    (7, "Sylvia atricapilla", "Garden Warbler"),
    (8, "Sylvia borin", "Garden Warbler"),
]

PUBLISHED_MODEL_SHA = "b" * 64
LOCAL_MODEL_SHA = "a1b2" + "c" * 60


@pytest.fixture
def catalog(tmp_path):
    pinned = hashlib.sha256(b"compatibility ioc").hexdigest()
    reference = tmp_path / "reference.db"
    connection = sqlite3.connect(reference)
    try:
        connection.executescript(REFERENCE_SCHEMA)
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (pinned,))
        connection.executemany("INSERT INTO taxon VALUES (?, ?, ?)", TAXA)
        connection.commit()
    finally:
        connection.close()

    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-23",
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
                    "labelsha-published": {
                        "label_format": "common_name",
                        "output_width": 2,
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
                        ],
                    }
                },
                "artifacts": [
                    {
                        "artifact_id": "published_model",
                        "model_sha256": PUBLISHED_MODEL_SHA,
                        "labels_sha256": "labelsha-published",
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


def rows_for(catalog_path, model_sha256):
    connection = sqlite3.connect(catalog_path)
    try:
        return connection.execute(
            "SELECT output_index, class_kind, species_id, source_label FROM model_output_taxa"
            " JOIN model_artifacts ON model_artifacts.id = model_output_taxa.model_artifact_id"
            " WHERE LOWER(model_sha256) = ? ORDER BY output_index",
            (model_sha256.lower(),),
        ).fetchall()
    finally:
        connection.close()


def import_labels(catalog_path, labels, model_sha256=LOCAL_MODEL_SHA, model_id="owner_model", **kwargs):
    return import_local_model_mapping(
        model_id=model_id,
        model_sha256=model_sha256,
        labels=labels,
        runtime="onnx",
        catalog_path=catalog_path,
        **kwargs,
    )


class TestResolution:
    def test_common_name_labels_gain_a_catalogue_identity(self, catalog):
        report = import_labels(catalog, ["Eurasian Blue Tit", "European Robin"])

        assert report.verdict == "imported"
        assert report.resolved == 2
        assert report.unresolved == 0
        assert [(row[1], row[2]) for row in rows_for(catalog, LOCAL_MODEL_SHA)] == [("species", 1), ("species", 2)]

    def test_scientific_name_labels_gain_a_catalogue_identity(self, catalog):
        report = import_labels(catalog, ["Cyanistes caeruleus", "Erithacus rubecula"])

        assert report.resolved == 2
        assert [row[2] for row in rows_for(catalog, LOCAL_MODEL_SHA)] == [1, 2]

    def test_a_paired_label_resolves_through_either_half(self, catalog):
        """`Haemorhous cassinii (Cassin's Finch)` announces itself: both halves
        name the same bird, so the two readings agree."""
        report = import_labels(catalog, ["Haemorhous cassinii (Cassin's Finch)"])

        assert report.resolved == 1
        assert rows_for(catalog, LOCAL_MODEL_SHA)[0][2] == 3

    def test_a_plumage_qualified_common_name_binds_to_its_species(self, catalog):
        """The NABirds shape. `Lesser Goldfinch (Female/juvenile)` wears the
        paired form without carrying a scientific name, and the label path has
        always been wrong to read the left half as one. It is still that
        species, and the label text is kept verbatim."""
        report = import_labels(catalog, ["Lesser Goldfinch (Female/juvenile)"])

        assert report.resolved == 1
        index, kind, species_id, source_label = rows_for(catalog, LOCAL_MODEL_SHA)[0]
        assert (kind, species_id) == ("species", 4)
        assert source_label == "Lesser Goldfinch (Female/juvenile)"

    def test_background_and_unknown_classes_are_recorded_as_themselves(self, catalog):
        report = import_labels(catalog, ["Background", "Unknown", "European Robin"])

        assert (report.resolved, report.unresolved) == (1, 0)
        assert [row[1] for row in rows_for(catalog, LOCAL_MODEL_SHA)] == ["background", "unknown", "species"]
        assert report.background == 1


class TestRefusingToGuess:
    def test_a_label_no_source_can_name_is_recorded_without_an_identity(self, catalog):
        report = import_labels(catalog, ["European Robin", "Nonexistent Fantasybird"])

        assert (report.resolved, report.unresolved) == (1, 1)
        index, kind, species_id, source_label = rows_for(catalog, LOCAL_MODEL_SHA)[1]
        assert (kind, species_id, source_label) == ("unknown", None, "Nonexistent Fantasybird")
        assert report.unresolved_outputs == [
            {"index": 1, "label": "Nonexistent Fantasybird", "reason": "no catalogue identity"}
        ]

    def test_two_readings_that_disagree_resolve_to_neither(self, catalog):
        """`Goldcrest` is species 5's English name and species 6's scientific
        name. One reading being confident is not enough when another reading is
        equally confident about a different bird."""
        report = import_labels(catalog, ["Goldcrest"])

        assert (report.resolved, report.unresolved) == (0, 1)
        assert rows_for(catalog, LOCAL_MODEL_SHA)[0][1:3] == ("unknown", None)
        assert report.unresolved_outputs[0]["reason"] == "conflicting identities"

    def test_a_name_two_species_share_resolves_to_neither(self, catalog):
        """Species 7 and 8 are both called `Garden Warbler` here. A name that
        does not pick one bird cannot be recorded as picking one."""
        report = import_labels(catalog, ["Garden Warbler"])

        assert (report.resolved, report.unresolved) == (0, 1)
        assert report.unresolved_outputs[0]["reason"] == "ambiguous"

    def test_a_declared_format_is_honoured_over_the_evidence(self, catalog):
        """When the caller states the file holds common names, a line is read
        only that way — the declaration exists precisely to stop the shape of a
        line being trusted."""
        report = import_labels(catalog, ["Cyanistes caeruleus"], label_format="common_name")

        assert (report.resolved, report.unresolved) == (0, 1)


class TestProtectingWhatIsAlreadyThere:
    def test_a_published_mapping_is_never_replaced(self, catalog):
        before = rows_for(catalog, PUBLISHED_MODEL_SHA)

        report = import_labels(catalog, ["Garden Warbler", "Nonexistent"], model_sha256=PUBLISHED_MODEL_SHA)

        assert report.verdict == "already_mapped"
        assert rows_for(catalog, PUBLISHED_MODEL_SHA) == before

    def test_re_running_the_import_changes_nothing(self, catalog):
        first = import_labels(catalog, ["Eurasian Blue Tit", "European Robin"])
        rows = rows_for(catalog, LOCAL_MODEL_SHA)

        second = import_labels(catalog, ["Eurasian Blue Tit", "European Robin"])

        assert (first.verdict, second.verdict) == ("imported", "already_mapped")
        assert rows_for(catalog, LOCAL_MODEL_SHA) == rows

    def test_a_missing_catalogue_is_reported_not_raised(self, tmp_path):
        report = import_labels(tmp_path / "nowhere.db", ["European Robin"])

        assert report.verdict == "unavailable"

    @pytest.mark.parametrize(
        "labels, model_sha256",
        [
            ([], LOCAL_MODEL_SHA),
            (["European Robin"], "not-a-checksum"),
            (["European Robin"], ""),
            (["   "], LOCAL_MODEL_SHA),
        ],
    )
    def test_an_input_that_cannot_be_trusted_is_refused(self, catalog, labels, model_sha256):
        report = import_labels(catalog, labels, model_sha256=model_sha256)

        assert report.verdict == "refused"
        assert rows_for(catalog, model_sha256 or LOCAL_MODEL_SHA) == []


class TestProvenance:
    def test_the_artifact_is_marked_as_locally_derived(self, catalog):
        import_labels(catalog, ["European Robin"], model_id="my_own_model")

        connection = sqlite3.connect(catalog)
        try:
            registry_id, state, width = connection.execute(
                "SELECT registry_id, state, output_width FROM model_artifacts WHERE LOWER(model_sha256) = ?",
                (LOCAL_MODEL_SHA,),
            ).fetchone()
        finally:
            connection.close()

        assert registry_id == f"{LOCAL_REGISTRY_PREFIX}my_own_model"
        assert (state, width) == ("installed", 1)

    def test_a_locally_derived_mapping_is_not_served_as_catalogue_labels(self, catalog):
        """The labels came out of `labels.txt`. Handing them back as if the
        catalogue had verified them would launder the file we are trying to
        stop trusting."""
        import_labels(catalog, ["Eurasian Blue Tit", "European Robin"])

        assert catalogue_labels_for_model(LOCAL_MODEL_SHA, catalog_path=catalog) is None
        assert catalogue_labels_for_model(PUBLISHED_MODEL_SHA, catalog_path=catalog) == [
            "Eurasian blue tit",
            "European robin",
        ]

    def test_the_report_carries_a_digest_of_what_was_written(self, catalog):
        report = import_labels(catalog, ["European Robin"])

        connection = sqlite3.connect(catalog)
        try:
            stored = connection.execute(
                "SELECT mapping_set_sha256 FROM model_artifacts WHERE LOWER(model_sha256) = ?",
                (LOCAL_MODEL_SHA,),
            ).fetchone()[0]
        finally:
            connection.close()

        assert stored == report.mapping_set_sha256
        assert len(stored) == 64

    def test_the_unresolved_sample_is_capped_but_the_count_is_not(self, catalog):
        labels = [f"Fantasybird {index}" for index in range(40)]

        report = import_labels(catalog, labels)

        assert report.unresolved == 40
        assert len(report.unresolved_outputs) == 20
        assert report.unresolved_outputs[0]["index"] == 0


class TestWiring:
    """What the startup pass does with a real installed model."""

    @pytest.fixture
    def installed(self, catalog, tmp_path, monkeypatch):
        from app.services import species_catalog_compatibility as module

        labels_path = tmp_path / "labels.txt"
        labels_path.write_text("Eurasian Blue Tit\n\nEuropean Robin\n", encoding="utf-8")

        state = {
            "spec": {
                "model_id": "owner_model",
                "labels_path": str(labels_path),
                "runtime": "onnx",
            },
            "checksum": LOCAL_MODEL_SHA,
            "published": None,
        }

        class _ModelManager:
            def get_active_model_spec(self):
                return state["spec"]

        class _Classifier:
            def active_model_sha256(self):
                return state["checksum"]

        monkeypatch.setattr("app.services.model_manager.model_manager", _ModelManager())
        monkeypatch.setattr("app.services.classifier_service.get_classifier", lambda: _Classifier())
        monkeypatch.setattr(
            "app.services.catalogue_labels.published_model_sha256", lambda model_id, region=None: state["published"]
        )
        monkeypatch.setattr(module, "_MODEL_WAIT_ATTEMPTS", 2)
        monkeypatch.setattr(module, "_MODEL_WAIT_SECONDS", 0)
        return state

    @pytest.mark.asyncio
    async def test_an_owner_supplied_model_is_mapped_from_its_label_file(self, catalog, installed):
        from app.services.species_catalog_compatibility import import_mapping_for_installed_model

        report = await import_mapping_for_installed_model(catalog_path=catalog)

        assert (report.verdict, report.resolved, report.output_width) == ("imported", 2, 2)
        assert [row[2] for row in rows_for(catalog, LOCAL_MODEL_SHA)] == [1, 2]

    @pytest.mark.asyncio
    async def test_a_registry_model_is_left_to_its_published_mapping(self, catalog, installed):
        from app.services.species_catalog_compatibility import import_mapping_for_installed_model

        installed["published"] = "b" * 64

        report = await import_mapping_for_installed_model(catalog_path=catalog)

        assert report.verdict == "skipped"
        assert rows_for(catalog, LOCAL_MODEL_SHA) == []

    @pytest.mark.asyncio
    async def test_nothing_is_written_before_the_model_has_loaded(self, catalog, installed):
        from app.services.species_catalog_compatibility import import_mapping_for_installed_model

        installed["checksum"] = None

        report = await import_mapping_for_installed_model(catalog_path=catalog)

        assert (report.verdict, report.reason) == ("skipped", "no model is loaded")
        assert rows_for(catalog, LOCAL_MODEL_SHA) == []

    @pytest.mark.asyncio
    async def test_the_background_pass_gives_up_rather_than_polling_forever(self, catalog, installed):
        from app.services.species_catalog_compatibility import (
            last_local_mapping_report,
            start_background_local_mapping_import,
        )

        installed["checksum"] = None

        await start_background_local_mapping_import()

        assert last_local_mapping_report()["reason"] == "no model is loaded"

    @pytest.mark.asyncio
    async def test_a_label_file_the_loader_would_reject_maps_nothing(self, catalog, installed, tmp_path):
        from app.services.species_catalog_compatibility import import_mapping_for_installed_model

        empty = tmp_path / "empty.txt"
        empty.write_text("\n\n", encoding="utf-8")
        installed["spec"]["labels_path"] = str(empty)

        report = await import_mapping_for_installed_model(catalog_path=catalog)

        assert (report.verdict, report.reason) == ("skipped", "the model has no readable label file")
