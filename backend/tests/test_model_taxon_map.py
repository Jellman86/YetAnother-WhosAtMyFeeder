"""Binding a model's output index to a taxon.

The scientific name is already in the label for every iNaturalist-derived model,
so the mapping is derivable from the model's own file with no external source.
Building it once from the checksum-verified label file, rather than reading that
file on every detection, is what stops an altered labels.txt writing wrong
species into history.
"""

import pytest

from app.services.model_taxon_map import (
    ModelTaxonMap,
    scientific_name_from_label,
)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        # iNaturalist hierarchy: the last two parts are genus and species.
        ("04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus", "Cyanistes caeruleus"),
        ("00000_Animalia_Annelida_Clitellata_Haplotaxida_Lumbricidae_Lumbricus_terrestris", "Lumbricus terrestris"),
    ],
)
def test_the_hierarchy_form_is_read_without_a_declaration(label, expected):
    """It is the one shape a common name cannot take."""
    assert scientific_name_from_label(label) == expected


@pytest.mark.parametrize(
    "label",
    [
        # Common name only: these models carry no scientific name at all.
        "African blue tit",
        "Alpine chough",
        "",
        "   ",
        None,
        "Background",
        # A single word is not a binomial.
        "Aves",
    ],
)
def test_returns_nothing_when_the_label_carries_no_scientific_name(label):
    assert scientific_name_from_label(label) is None


def test_the_paired_form_is_read_only_when_declared_or_binomial_shaped():
    """`Lesser Goldfinch (Female/juvenile)` is the same shape as
    `Haemorhous cassinii (Cassin's Finch)`, so the parenthetical alone proves
    nothing. Undeclared files (sideloaded Coral-style models) read the paired
    form only when the left half is binomial-shaped: a lowercase epithet is
    what a plumage-qualified common name cannot have."""
    paired = "Haemorhous cassinii (Cassin's Finch)"
    plumage = "Lesser Goldfinch (Female/juvenile)"

    assert scientific_name_from_label(paired, label_format="scientific_paired_common") == "Haemorhous cassinii"
    assert (
        scientific_name_from_label("  Haemorhous cassinii  (Cassin's Finch) ", label_format="scientific_paired_common")
        == "Haemorhous cassinii"
    )
    assert scientific_name_from_label(paired) == "Haemorhous cassinii"
    assert scientific_name_from_label(plumage) is None
    assert scientific_name_from_label(plumage, label_format="common_name") is None


def test_a_bare_two_word_label_is_not_guessed_at():
    """`African crake` and `Cyanistes caeruleus` are the same shape."""
    assert scientific_name_from_label("African crake") is None
    assert scientific_name_from_label("Arctic tern") is None
    assert scientific_name_from_label("Cyanistes caeruleus") is None


def test_a_bare_binomial_is_read_when_the_file_is_declared_scientific():
    assert (
        scientific_name_from_label("Cyanistes caeruleus", label_format="scientific_binomial") == "Cyanistes caeruleus"
    )
    # Still nothing to read from a single word or an empty label.
    assert scientific_name_from_label("Aves", label_format="scientific_binomial") is None


def test_a_common_name_declaration_reads_nothing_even_from_a_binomial_shape():
    assert scientific_name_from_label("Cyanistes caeruleus", label_format="common_name") is None


def test_an_unknown_declared_format_resolves_nothing():
    """A registry ahead of the code fails closed rather than guessing."""
    assert scientific_name_from_label("Cyanistes caeruleus", label_format="something_new") is None
    assert (
        scientific_name_from_label(
            "04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus", label_format="something_new"
        )
        is None
    )


@pytest.fixture
def mapping(tmp_path):
    return ModelTaxonMap(tmp_path / "map.db")


def test_builds_a_mapping_from_a_label_file(mapping):
    labels = [
        "04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus",
        "00001_Animalia_Chordata_Aves_Passeriformes_Turdidae_Erithacus_rubecula",
    ]

    stored = mapping.build("labelsha-1", labels)

    assert stored == 2
    assert mapping.lookup("labelsha-1", 0) == "Cyanistes caeruleus"
    assert mapping.lookup("labelsha-1", 1) == "Erithacus rubecula"


def test_indices_are_positions_in_the_file_including_unmapped_ones(mapping):
    """Index 2 must still mean the third line even though line 2 has no binomial."""
    stored = mapping.build(
        "labelsha-2",
        ["Cyanistes caeruleus", "African blue tit", "Erithacus rubecula"],
        label_format="scientific_binomial",
    )

    assert stored == 2
    assert mapping.lookup("labelsha-2", 0) == "Cyanistes caeruleus"
    assert mapping.lookup("labelsha-2", 1) is None
    assert mapping.lookup("labelsha-2", 2) == "Erithacus rubecula"


def test_two_models_with_different_label_orders_agree_on_the_bird(mapping):
    """The acceptance test the roadmap asks for."""
    mapping.build("model-a", ["Cyanistes caeruleus", "Erithacus rubecula"], label_format="scientific_binomial")
    mapping.build("model-b", ["Erithacus rubecula", "Cyanistes caeruleus"], label_format="scientific_binomial")

    assert mapping.lookup("model-a", 0) == mapping.lookup("model-b", 1) == "Cyanistes caeruleus"
    assert mapping.lookup("model-a", 1) == mapping.lookup("model-b", 0) == "Erithacus rubecula"


def test_rebuilding_replaces_rather_than_duplicating(mapping):
    mapping.build("labelsha-3", ["Cyanistes caeruleus"], label_format="scientific_binomial")
    mapping.build("labelsha-3", ["Erithacus rubecula"], label_format="scientific_binomial")

    assert mapping.lookup("labelsha-3", 0) == "Erithacus rubecula"
    assert mapping.coverage("labelsha-3")["mapped"] == 1


def test_a_model_that_was_never_built_resolves_to_nothing(mapping):
    """Absent means fall back to the text path, never guess."""
    assert mapping.lookup("never-seen", 0) is None
    assert mapping.has("never-seen") is False


def test_coverage_is_reportable_per_model(mapping):
    mapping.build(
        "labelsha-4",
        ["Cyanistes caeruleus", "African blue tit", "Erithacus rubecula"],
        label_format="scientific_binomial",
    )

    coverage = mapping.coverage("labelsha-4")

    assert coverage["labels"] == 3
    assert coverage["mapped"] == 2
    assert coverage["complete"] is False


def test_a_fully_mapped_model_reports_complete(mapping):
    mapping.build("labelsha-5", ["Cyanistes caeruleus", "Erithacus rubecula"], label_format="scientific_binomial")

    assert mapping.coverage("labelsha-5")["complete"] is True


@pytest.mark.parametrize("bad_index", [-1, 99999])
def test_an_out_of_range_index_resolves_to_nothing(mapping, bad_index):
    mapping.build("labelsha-6", ["Cyanistes caeruleus"], label_format="scientific_binomial")

    assert mapping.lookup("labelsha-6", bad_index) is None


def test_an_unwritable_location_disables_the_mapping_rather_than_raising(tmp_path):
    unusable = ModelTaxonMap(tmp_path / "missing" / "deeper" / "map.db")
    unusable._parent_is_writable = lambda: False  # type: ignore[method-assign]

    assert unusable.build("labelsha-7", ["Cyanistes caeruleus"], label_format="scientific_binomial") == 0
    assert unusable.lookup("labelsha-7", 0) is None


def test_a_damaged_file_disables_the_mapping_rather_than_raising(tmp_path):
    path = tmp_path / "damaged.db"
    path.write_bytes(b"not a database")
    damaged = ModelTaxonMap(path)

    assert damaged.lookup("labelsha-8", 0) is None
    assert damaged.build("labelsha-8", ["Cyanistes caeruleus"], label_format="scientific_binomial") == 0
