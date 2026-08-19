"""Checking an installed label file against the checksum it was published with.

`labels_sha256` is verified when a model is downloaded and never again, so a
label file altered afterwards is read as authoritative and every detection
classified against it is written to history under the wrong species. This checks
it where it matters, and builds the output-index mapping from a file it has just
proven.
"""

import hashlib

import pytest

from app.services.label_integrity import (
    LabelVerdict,
    build_map_for_verified_labels,
    verify_model_labels,
)


@pytest.fixture
def model_dir(tmp_path):
    directory = tmp_path / "rope_vit_b14_inat21"
    directory.mkdir()
    labels = directory / "labels.txt"
    labels.write_text(
        "00000_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus\n"
        "00001_Animalia_Chordata_Aves_Passeriformes_Turdidae_Erithacus_rubecula\n",
        encoding="utf-8",
    )
    return directory


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_matching_label_file_is_verified(model_dir):
    expected = _digest(model_dir / "labels.txt")

    result = verify_model_labels("rope_vit_b14_inat21", model_dir, expected_sha256=expected)

    assert result.verdict is LabelVerdict.VERIFIED
    assert result.actual_sha256 == expected
    assert result.label_count == 2


def test_an_altered_label_file_is_reported_as_changed(model_dir):
    expected = _digest(model_dir / "labels.txt")
    (model_dir / "labels.txt").write_text("something else entirely\n", encoding="utf-8")

    result = verify_model_labels("rope_vit_b14_inat21", model_dir, expected_sha256=expected)

    assert result.verdict is LabelVerdict.CHANGED
    assert result.actual_sha256 != expected


def test_a_model_with_no_published_checksum_is_unverifiable_not_changed(model_dir):
    """Absence of a checksum is not evidence of tampering, and must not read as it."""
    result = verify_model_labels("custom_model", model_dir, expected_sha256=None)

    assert result.verdict is LabelVerdict.UNVERIFIABLE
    assert result.actual_sha256 == _digest(model_dir / "labels.txt")


def test_a_missing_label_file_is_reported_as_missing(tmp_path):
    empty = tmp_path / "no_labels"
    empty.mkdir()

    result = verify_model_labels("rope_vit_b14_inat21", empty, expected_sha256="a" * 64)

    assert result.verdict is LabelVerdict.MISSING
    assert result.actual_sha256 is None
    assert result.label_count == 0


def test_the_map_is_built_only_from_a_file_that_was_verified(model_dir, tmp_path):
    from app.services.model_taxon_map import ModelTaxonMap

    mapping = ModelTaxonMap(tmp_path / "map.db")
    expected = _digest(model_dir / "labels.txt")
    result = verify_model_labels("rope_vit_b14_inat21", model_dir, expected_sha256=expected)

    stored = build_map_for_verified_labels(result, mapping=mapping)

    assert stored == 2
    assert mapping.lookup(result.actual_sha256, 0) == "Cyanistes caeruleus"
    assert mapping.lookup(result.actual_sha256, 1) == "Erithacus rubecula"


def test_a_changed_file_does_not_get_a_mapping(model_dir, tmp_path):
    """Mapping an altered file would make its wrong names authoritative."""
    from app.services.model_taxon_map import ModelTaxonMap

    mapping = ModelTaxonMap(tmp_path / "map.db")
    result = verify_model_labels("rope_vit_b14_inat21", model_dir, expected_sha256="b" * 64)

    assert result.verdict is LabelVerdict.CHANGED
    assert build_map_for_verified_labels(result, mapping=mapping) == 0
    assert mapping.has(result.actual_sha256 or "") is False


def test_an_unverifiable_file_still_gets_a_mapping(model_dir, tmp_path):
    """A model without a published checksum is normal, and its names are still wanted."""
    from app.services.model_taxon_map import ModelTaxonMap

    mapping = ModelTaxonMap(tmp_path / "map.db")
    result = verify_model_labels("custom_model", model_dir, expected_sha256=None)

    assert build_map_for_verified_labels(result, mapping=mapping) == 2


def test_the_published_checksum_is_read_from_the_registry():
    """The registry is the source of truth; a typo here would be silent."""
    from app.services.label_integrity import published_labels_sha256

    assert published_labels_sha256("mobilenet_v2_birds")
    assert published_labels_sha256("no_such_model_at_all") is None


def test_a_region_variant_resolves_its_own_checksum():
    """`small_birds/eu` has no id of its own; it hangs off its parent."""
    from app.services.label_integrity import published_labels_sha256

    parent_only = published_labels_sha256("small_birds")
    eu = published_labels_sha256("small_birds", region="eu")
    na = published_labels_sha256("small_birds", region="na")

    assert eu and na
    assert eu != na
    # The parent carries no label file of its own, only its regions do.
    assert parent_only is None


def test_a_retired_model_is_unverifiable_rather_than_changed(model_dir):
    """Retired models leave installed files alone, so absence of a checksum is expected."""
    result = verify_model_labels("uniformer_s_eu_common", model_dir)

    assert result.verdict is LabelVerdict.UNVERIFIABLE
