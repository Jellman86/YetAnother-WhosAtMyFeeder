"""Compiling checksum-bound output mappings from label files and the catalogue.

Phase 2 of the catalogue design: every output index of every supported
classifier artifact maps to a canonical species identity or an explicitly
declared non-species class. The compiler reads a checksum-verified label file,
resolves each line through the seed catalogue by its declared grammar, and
emits the machine-readable mapping record the seed build folds into
`model_artifacts` and `model_output_taxa`. Anything uncertain is recorded as
unresolved, never guessed.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_model_output_mappings as compiler  # noqa: E402
import build_species_catalog_seed as seed_builder  # noqa: E402

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""


def _build_seed(tmp_path, *, mappings_path=None, output_name="seed.db"):
    """A seed catalogue with three birds, one CoL non-bird, and a synonym alias."""
    ioc_pinned = hashlib.sha256(b"phase2 ioc").hexdigest()
    col_pinned = hashlib.sha256(b"phase2 col").hexdigest()

    reference = tmp_path / "reference.db"
    if not reference.exists():
        connection = sqlite3.connect(reference)
        try:
            connection.executescript(REFERENCE_SCHEMA)
            connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (ioc_pinned,))
            connection.executemany(
                "INSERT INTO taxon VALUES (?, ?, ?)",
                [
                    (1, "Cyanistes caeruleus", "Eurasian Blue Tit"),
                    (2, "Larus audouinii", "Audouin's Gull"),
                    (3, "Spinus psaltria", "Lesser Goldfinch"),
                ],
            )
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
                        "scientific_name": "Lumbricus terrestris",
                        "kingdom": "Animalia",
                        "label_class": "Clitellata",
                        "col_id": "C1",
                        "col_status": "accepted",
                        "accepted_col_id": "C1",
                        "accepted_scientific_name": "Lumbricus terrestris",
                    },
                    {
                        "scientific_name": "Bufotes balearicus",
                        "kingdom": "Animalia",
                        "label_class": "Amphibia",
                        "col_id": "S1",
                        "col_status": "synonym",
                        "accepted_col_id": "A1",
                        "accepted_scientific_name": "Bufotes viridis",
                    },
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

    path = tmp_path / output_name
    seed_builder.build(
        reference, path, manifest_path=manifest, col_concepts_path=col, model_mappings_path=mappings_path
    )
    return path


@pytest.fixture
def seed(tmp_path):
    return _build_seed(tmp_path)


@pytest.fixture
def resolver(seed):
    return compiler.CatalogResolver(seed)


def _kinds(rows):
    return [(row.index, row.kind, row.provider, row.taxon) for row in rows]


class TestMapLabels:
    def test_a_hierarchy_label_resolves_through_its_concept(self, resolver):
        rows = compiler.map_labels(
            ["04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus"],
            "scientific_hierarchy",
            resolver,
        )

        assert _kinds(rows) == [(0, "species", "ioc-world-bird-list", "Cyanistes caeruleus")]

    def test_a_declared_binomial_resolves_a_non_bird_through_catalogue_of_life(self, resolver):
        rows = compiler.map_labels(["Lumbricus terrestris"], "scientific_binomial", resolver)

        assert _kinds(rows) == [(0, "species", "catalogue-of-life", "C1")]

    def test_a_synonym_label_resolves_through_its_alias(self, resolver):
        """iNat21 still says Bufotes balearicus; the catalogue knows it as a
        synonym of Bufotes viridis and maps the index to that identity."""
        rows = compiler.map_labels(["Bufotes balearicus"], "scientific_binomial", resolver)

        assert _kinds(rows) == [(0, "species", "catalogue-of-life", "A1")]

    def test_a_common_name_resolves_through_the_english_names(self, resolver):
        rows = compiler.map_labels(["Eurasian blue tit"], "common_name", resolver)

        assert _kinds(rows) == [(0, "species", "ioc-world-bird-list", "Cyanistes caeruleus")]

    def test_a_stripped_apostrophe_still_resolves(self, resolver):
        """The European label files write `Audouins gull`; IOC writes
        `Audouin's Gull`. The Phase 0 inventory measured this as the dominant
        unresolved cause, so the compiler matches apostrophe-insensitively."""
        rows = compiler.map_labels(["Audouins gull"], "common_name", resolver)

        assert _kinds(rows) == [(0, "species", "ioc-world-bird-list", "Larus audouinii")]

    def test_a_plumage_parenthetical_is_stripped_for_matching(self, resolver):
        rows = compiler.map_labels(
            ["Lesser Goldfinch (Female/juvenile)", "Lesser Goldfinch (ID: 447)"],
            "common_name",
            resolver,
        )

        assert _kinds(rows) == [
            (0, "species", "ioc-world-bird-list", "Spinus psaltria"),
            (1, "species", "ioc-world-bird-list", "Spinus psaltria"),
        ]

    def test_background_and_unknown_are_declared_classes_not_species(self, resolver):
        rows = compiler.map_labels(["background", "Unknown"], "common_name", resolver)

        assert [(row.index, row.kind) for row in rows] == [(0, "background"), (1, "unknown")]
        assert all(row.provider is None for row in rows)

    def test_an_unmatched_label_is_recorded_unresolved_not_guessed(self, resolver):
        rows = compiler.map_labels(["Common chaffinch"], "common_name", resolver)

        assert rows[0].kind == "species"
        assert rows[0].provider is None
        assert rows[0].unresolved == "no catalogue identity"
        assert rows[0].label == "Common chaffinch"

    def test_a_scientific_label_never_matches_by_common_name(self, resolver):
        """`Eurasian Blue Tit` as a *binomial-format* line is label noise, not
        an identity; grammar discipline holds at compile time too."""
        rows = compiler.map_labels(["Eurasian Blue Tit"], "scientific_binomial", resolver)

        assert rows[0].unresolved


class TestAmbiguity:
    def test_a_normalized_collision_fails_closed(self, tmp_path, seed):
        """Two catalogue names that collapse to the same normalized form make
        that form unusable; only an exact match may resolve either."""
        connection = sqlite3.connect(seed)
        try:
            connection.execute("INSERT INTO species (species_id, rank, status) VALUES (99, 'species', 'accepted')")
            connection.execute(
                "INSERT INTO species_concepts (species_id, provider, provider_taxon_id, source_release, scientific_name)"
                " VALUES (99, 'ioc-world-bird-list', 'Larus audouinix', '14.2-test', 'Larus audouinix')"
            )
            connection.execute(
                "INSERT INTO species_names (species_id, language_tag, name, name_kind, preferred, provider, source_release)"
                " VALUES (99, 'en', 'Audoui''ns Gull', 'vernacular', 1, 'ioc-world-bird-list', '14.2-test')"
            )
            connection.commit()
        finally:
            connection.close()
        resolver = compiler.CatalogResolver(seed)

        rows = compiler.map_labels(["Audouins gull"], "common_name", resolver)

        assert rows[0].unresolved == "ambiguous after normalization"


def _mappings_json(tmp_path, outputs=None, taxon_override=None):
    path = tmp_path / "model_output_mappings.json"
    rows = outputs or [
        {
            "index": 0,
            "kind": "species",
            "label": "Eurasian blue tit",
            "provider": "ioc-world-bird-list",
            "taxon": taxon_override or "Cyanistes caeruleus",
        },
        {"index": 1, "kind": "background", "label": "background"},
        {"index": 2, "kind": "species", "label": "Common chaffinch", "unresolved": "no catalogue identity"},
        {"index": 3, "kind": "species", "label": "Bufotes balearicus", "provider": "catalogue-of-life", "taxon": "A1"},
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "label_files": {"labelsha-fake": {"label_format": "common_name", "output_width": 4, "outputs": rows}},
                "artifacts": [
                    {
                        "artifact_id": "fake_model",
                        "model_sha256": "m" * 64,
                        "labels_sha256": "labelsha-fake",
                        "runtime": "onnx",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _query(path, sql, params=()):
    connection = sqlite3.connect(path)
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


class TestSeedIntegration:
    @pytest.fixture
    def built(self, tmp_path):
        return _build_seed(tmp_path, mappings_path=_mappings_json(tmp_path), output_name="seed_mapped.db")

    def test_the_artifact_is_registered_with_its_checksums(self, built):
        rows = _query(built, "SELECT registry_id, model_sha256, output_width, runtime, state FROM model_artifacts")
        assert rows == [("fake_model", "m" * 64, 4, "onnx", "registered")]
        mapping_set = _query(built, "SELECT mapping_set_sha256 FROM model_artifacts")[0][0]
        assert mapping_set and len(mapping_set) == 64

    def test_indices_resolve_to_catalogue_identities(self, built):
        tit = _query(
            built,
            "SELECT t.species_id FROM model_output_taxa t WHERE t.output_index = 0",
        )[0][0]
        concept = _query(
            built,
            "SELECT scientific_name FROM species_concepts WHERE species_id = ? AND provider = 'ioc-world-bird-list'",
            (tit,),
        )
        assert concept == [("Cyanistes caeruleus",)]

        toad = _query(built, "SELECT species_id FROM model_output_taxa WHERE output_index = 3")[0][0]
        accepted = _query(built, "SELECT scientific_name FROM species_concepts WHERE species_id = ?", (toad,))
        assert accepted == [("Bufotes viridis",)]

    def test_a_declared_non_species_class_has_no_identity(self, built):
        rows = _query(built, "SELECT class_kind, species_id FROM model_output_taxa WHERE output_index = 1")
        assert rows == [("background", None)]

    def test_an_unresolved_class_is_a_row_that_says_it_is_unknown(self, built):
        """A gap used to be an absent row, which lost the label with it.

        Every output index now has a row, so the catalogue holds what the model
        calls an output even when it cannot say what it is. The gap is still a
        gap: the row says `unknown` and coverage counts identity, not rows.
        """
        indices = {row[0] for row in _query(built, "SELECT output_index FROM model_output_taxa")}
        width = _query(built, "SELECT output_width FROM model_artifacts")[0][0]
        assert indices == set(range(width)), "every output index is present"

        unknown = _query(
            built,
            "SELECT output_index, species_id, source_label FROM model_output_taxa WHERE class_kind = 'unknown'",
        )
        assert [row[0] for row in unknown] == [2]
        assert unknown[0][1] is None, "an unknown output claims no identity"
        assert unknown[0][2], "but it keeps the label the model uses"

    def test_a_mapping_that_references_an_unknown_concept_refuses_the_build(self, tmp_path):
        mappings = _mappings_json(tmp_path, taxon_override="Nonexistus maximus")

        with pytest.raises(SystemExit, match="does not hold"):
            _build_seed(tmp_path, mappings_path=mappings, output_name="refused.db")

    def test_the_build_stays_reproducible_with_mappings(self, tmp_path):
        first = _build_seed(tmp_path, mappings_path=_mappings_json(tmp_path), output_name="one.db")
        second = _build_seed(tmp_path, mappings_path=_mappings_json(tmp_path), output_name="two.db")

        assert first.read_bytes() == second.read_bytes()


class TestImporterCarry:
    def test_mappings_travel_with_a_release_and_species_ids_are_remapped(self, tmp_path):
        from app.services.species_catalog_importer import import_release

        live = _build_seed(tmp_path, output_name="live.db")
        bundle = _build_seed(tmp_path, mappings_path=_mappings_json(tmp_path), output_name="bundle.db")

        import_release(bundle, catalog_path=live)

        artifact = _query(live, "SELECT id, model_sha256, output_width FROM model_artifacts")
        assert len(artifact) == 1 and artifact[0][1] == "m" * 64
        tit = _query(live, "SELECT species_id FROM model_output_taxa WHERE output_index = 0")[0][0]
        concept = _query(
            live,
            "SELECT scientific_name FROM species_concepts WHERE species_id = ? AND provider = 'ioc-world-bird-list'",
            (tit,),
        )
        assert concept == [("Cyanistes caeruleus",)]

    def test_an_already_registered_artifact_keeps_its_mapping(self, tmp_path):
        from app.services.species_catalog_importer import import_release

        live = _build_seed(tmp_path, mappings_path=_mappings_json(tmp_path), output_name="live2.db")
        bundle = _build_seed(tmp_path, mappings_path=_mappings_json(tmp_path), output_name="bundle2.db")

        result = import_release(bundle, catalog_path=live)

        assert result.status == "already_imported" or result.status == "imported"
        assert _query(live, "SELECT COUNT(*) FROM model_artifacts")[0][0] == 1
        # One row per output index, so the unresolved index counts too.
        assert _query(live, "SELECT COUNT(*) FROM model_output_taxa")[0][0] == 4


ASSETS = Path(__file__).resolve().parents[1] / "app" / "assets"


def test_the_committed_mappings_cover_every_classifier_artifact():
    """The freeze gate for Phase 2: a registry change without regenerated
    mappings fails here, so the committed record cannot fall behind."""
    from app.services.model_registry_inventory import registry_artifacts

    mappings = json.loads((ASSETS / "model_output_mappings.json").read_text(encoding="utf-8"))
    classifiers = {a.artifact_id: a for a in registry_artifacts() if a.artifact_kind == "classifier"}
    listed = {a["artifact_id"]: a for a in mappings["artifacts"]}

    assert set(listed) == set(classifiers)
    for artifact_id, artifact in classifiers.items():
        assert listed[artifact_id]["model_sha256"] == artifact.sha256, artifact_id
        assert listed[artifact_id]["labels_sha256"] == artifact.labels_sha256, artifact_id
        entry = mappings["label_files"][artifact.labels_sha256]
        assert entry["label_format"] == artifact.label_format, artifact_id
        assert entry["output_width"] > 0


def test_the_committed_mapping_coverage_is_what_was_measured():
    """Pinned from the compile; a change here is a review event, not drift
    (see docs/reviews/2026-08-20-model-output-mapping-coverage.md).

    Recompiled once the seed the mappings are built against started carrying
    the Catalogue of Life bird synonyms: 131 outputs naming a superseded genus
    gained the identity they always had at runtime, and none changed.
    """
    mappings = json.loads((ASSETS / "model_output_mappings.json").read_text(encoding="utf-8"))

    total = mapped = declared = unresolved = 0
    for entry in mappings["label_files"].values():
        total += entry["output_width"]
        for row in entry["outputs"]:
            if "unresolved" in row:
                unresolved += 1
            elif row["kind"] == "species":
                mapped += 1
            else:
                declared += 1

    assert total == 23332
    assert mapped == 21781
    assert declared == 3  # two Unknown classes and one background class
    assert unresolved == 1548


def test_the_committed_assets_build_a_fully_mapped_catalogue(tmp_path):
    """All three real assets together: ten registered artifacts whose resolved
    indices point at real catalogue identities."""
    reference = ASSETS / "species_reference.db"
    col = ASSETS / "col_nonbird_concepts.json"
    mappings = ASSETS / "model_output_mappings.json"
    if not (reference.is_file() and col.is_file() and mappings.is_file()):
        pytest.skip("bundled assets not present in this checkout")

    output = tmp_path / "full_seed.db"
    seed_builder.build(reference, output, col_concepts_path=col, model_mappings_path=mappings)

    assert _query(output, "SELECT COUNT(*) FROM model_artifacts")[0][0] == 10
    # One row per output index across every artifact, unresolved ones included.
    assert _query(output, "SELECT COUNT(*) FROM model_output_taxa")[0][0] == 34746
    orphans = _query(
        output,
        "SELECT COUNT(*) FROM model_output_taxa t WHERE t.species_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM species s WHERE s.species_id = t.species_id)",
    )
    assert orphans == [(0,)]


def test_a_hyphen_and_an_american_spelling_do_not_hide_a_bird_from_the_catalogue():
    """Measured against the shipped mappings: 35 of the 180 unresolved labels on the
    bird models are ordinary species the catalogue holds under a different hyphen or
    the British spelling. `Western Screech-Owl` is IOC's `Western Screech Owl` and
    `Gray Catbird` is its `Grey Catbird`; neither is a different bird.
    """
    from app.services.model_taxon_map import normalize_common_name

    assert normalize_common_name("Western Screech-Owl") == normalize_common_name("Western Screech Owl")
    assert normalize_common_name("Black-crowned Night-Heron") == normalize_common_name("Black-crowned Night Heron")
    assert normalize_common_name("Gray Catbird") == normalize_common_name("Grey Catbird")
    assert normalize_common_name("Blue-gray Gnatcatcher") == normalize_common_name("Blue-grey Gnatcatcher")
    assert normalize_common_name("Gray-crowned Rosy-Finch") == normalize_common_name("Grey-crowned Rosy Finch")


def test_a_label_that_lost_its_accents_still_finds_the_bird():
    """Model label files are frequently written in plain ASCII. `Ruppells vulture`
    is IOC's `R\u00fcppell\u2019s Vulture` and `Krupers nuthatch` its `Kr\u00fcper\u2019s Nuthatch`.
    """
    from app.services.model_taxon_map import normalize_common_name

    assert normalize_common_name("Ruppells vulture") == normalize_common_name("R\u00fcppell\u2019s Vulture")
    assert normalize_common_name("Krupers nuthatch") == normalize_common_name("Kr\u00fcper\u2019s Nuthatch")


def test_normalising_still_refuses_to_make_two_birds_one():
    """The folding is spelling only. It must not reorder or drop words, and it must
    not fold a word that merely contains a colour name, or `Grayson` and `Greyson`
    style collisions would start merging real species.
    """
    from app.services.model_taxon_map import normalize_common_name

    assert normalize_common_name("Great Grey Owl") != normalize_common_name("Grey Great Owl")
    assert normalize_common_name("Grey Heron") != normalize_common_name("Heron")
    # `gray` inside a longer word is not the colour and must survive untouched.
    assert normalize_common_name("Grayling") == "grayling"


def test_the_mapping_build_and_the_compatibility_importer_normalise_alike():
    """One normaliser, two callers. The published mappings and a locally
    derived one have to agree on when two spellings are the same name; two
    copies of the rule could drift and quietly stop agreeing."""
    import build_model_output_mappings as build_module

    from app.services.model_taxon_map import normalize_common_name

    assert build_module._normalize_common is normalize_common_name
    assert normalize_common_name("Cassin\u2019s Finch") == "cassins finch"
    assert normalize_common_name("Lesser Goldfinch (Female/juvenile)") == "lesser goldfinch"
    assert normalize_common_name("  Great   Grey  Owl ") == "great grey owl"
