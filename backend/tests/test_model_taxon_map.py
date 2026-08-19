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
        # Paired form.
        ("Haemorhous cassinii (Cassin's Finch)", "Haemorhous cassinii"),
        ("  Haemorhous cassinii  (Cassin's Finch) ", "Haemorhous cassinii"),
    ],
)
def test_reads_the_scientific_name_out_of_a_label(label, expected):
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


def test_a_bare_two_word_label_is_not_guessed_at():
    """`African crake` and `Cyanistes caeruleus` are the same shape."""
    assert scientific_name_from_label("African crake") is None
    assert scientific_name_from_label("Arctic tern") is None
    assert scientific_name_from_label("Cyanistes caeruleus") is None


def test_a_bare_binomial_is_read_when_the_file_is_known_to_be_scientific():
    assert scientific_name_from_label("Cyanistes caeruleus", assume_scientific=True) == "Cyanistes caeruleus"
    # Still nothing to read from a single word or an empty label.
    assert scientific_name_from_label("Aves", assume_scientific=True) is None


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
        "labelsha-2", ["Cyanistes caeruleus", "African blue tit", "Erithacus rubecula"], assume_scientific=True
    )

    assert stored == 2
    assert mapping.lookup("labelsha-2", 0) == "Cyanistes caeruleus"
    assert mapping.lookup("labelsha-2", 1) is None
    assert mapping.lookup("labelsha-2", 2) == "Erithacus rubecula"


def test_two_models_with_different_label_orders_agree_on_the_bird(mapping):
    """The acceptance test the roadmap asks for."""
    mapping.build("model-a", ["Cyanistes caeruleus", "Erithacus rubecula"], assume_scientific=True)
    mapping.build("model-b", ["Erithacus rubecula", "Cyanistes caeruleus"], assume_scientific=True)

    assert mapping.lookup("model-a", 0) == mapping.lookup("model-b", 1) == "Cyanistes caeruleus"
    assert mapping.lookup("model-a", 1) == mapping.lookup("model-b", 0) == "Erithacus rubecula"


def test_rebuilding_replaces_rather_than_duplicating(mapping):
    mapping.build("labelsha-3", ["Cyanistes caeruleus"], assume_scientific=True)
    mapping.build("labelsha-3", ["Erithacus rubecula"], assume_scientific=True)

    assert mapping.lookup("labelsha-3", 0) == "Erithacus rubecula"
    assert mapping.coverage("labelsha-3")["mapped"] == 1


def test_a_model_that_was_never_built_resolves_to_nothing(mapping):
    """Absent means fall back to the text path, never guess."""
    assert mapping.lookup("never-seen", 0) is None
    assert mapping.has("never-seen") is False


def test_coverage_is_reportable_per_model(mapping):
    mapping.build(
        "labelsha-4", ["Cyanistes caeruleus", "African blue tit", "Erithacus rubecula"], assume_scientific=True
    )

    coverage = mapping.coverage("labelsha-4")

    assert coverage["labels"] == 3
    assert coverage["mapped"] == 2
    assert coverage["complete"] is False


def test_a_fully_mapped_model_reports_complete(mapping):
    mapping.build("labelsha-5", ["Cyanistes caeruleus", "Erithacus rubecula"], assume_scientific=True)

    assert mapping.coverage("labelsha-5")["complete"] is True


@pytest.mark.parametrize("bad_index", [-1, 99999])
def test_an_out_of_range_index_resolves_to_nothing(mapping, bad_index):
    mapping.build("labelsha-6", ["Cyanistes caeruleus"], assume_scientific=True)

    assert mapping.lookup("labelsha-6", bad_index) is None


def test_an_unwritable_location_disables_the_mapping_rather_than_raising(tmp_path):
    unusable = ModelTaxonMap(tmp_path / "missing" / "deeper" / "map.db")
    unusable._parent_is_writable = lambda: False  # type: ignore[method-assign]

    assert unusable.build("labelsha-7", ["Cyanistes caeruleus"], assume_scientific=True) == 0
    assert unusable.lookup("labelsha-7", 0) is None


def test_a_damaged_file_disables_the_mapping_rather_than_raising(tmp_path):
    path = tmp_path / "damaged.db"
    path.write_bytes(b"not a database")
    damaged = ModelTaxonMap(path)

    assert damaged.lookup("labelsha-8", 0) is None
    assert damaged.build("labelsha-8", ["Cyanistes caeruleus"], assume_scientific=True) == 0
