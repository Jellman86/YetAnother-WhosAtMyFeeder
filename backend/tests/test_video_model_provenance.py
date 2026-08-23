"""Which model produced a video classification, and saying so.

The Deep Video Analysis card names the model that produced the result. A user
reported it sometimes missing. Two causes, both real:

* The snapshot fallback path builds its results through a plain ranking helper
  that carries no provenance, so no model id was recorded at all. Measured on a
  live install: 11 completed classifications with a null model id, every one of
  them from a snapshot source.
* A regional model's id is `parent/region`, and region variants are nested under
  their parent in the registry without an id of their own. An exact-id lookup
  therefore finds nothing, so anyone running a regional model gets no name.
"""

import pytest

from app.routers.events import _video_classification_model_name


def test_a_top_level_model_resolves_to_its_name():
    assert _video_classification_model_name("rope_vit_b14_inat21")


def test_a_region_variant_resolves_rather_than_vanishing():
    """`small_birds/eu` is nested under `small_birds`, which owns the id."""
    name = _video_classification_model_name("small_birds/eu")
    assert name, "a regional model must still name itself"


def test_a_region_variant_name_distinguishes_the_region():
    eu = _video_classification_model_name("small_birds/eu")
    na = _video_classification_model_name("small_birds/na")
    assert eu and na and eu != na, f"regions must be distinguishable: {eu!r} vs {na!r}"


def test_an_unknown_model_id_is_reported_rather_than_hidden():
    """§5: showing nothing invents a state. The id itself is honest."""
    assert _video_classification_model_name("some_model_we_retired") == "some_model_we_retired"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_no_model_id_stays_absent(value):
    assert _video_classification_model_name(value) is None


def test_provenance_never_overwrites_what_the_classifier_already_reported():
    from app.services.auto_video_classifier_service import attach_classification_provenance

    top = {"index": 1, "score": 0.5, "label": "x", "model_id": "from_classifier", "input_source": "model_crop"}
    result = attach_classification_provenance(top, input_source="frigate_snapshot_cropped", model_id="active_model")
    assert result["model_id"] == "from_classifier"
    assert result["input_source"] == "model_crop"


def test_provenance_records_the_active_model_when_the_classifier_did_not():
    from app.services.auto_video_classifier_service import attach_classification_provenance

    result = attach_classification_provenance(
        {"index": 1, "score": 0.5, "label": "x"},
        input_source="frigate_snapshot_cropped",
        model_id="rope_vit_b14_inat21",
    )
    assert result["model_id"] == "rope_vit_b14_inat21"
    assert result["input_source"] == "frigate_snapshot_cropped"


def test_provenance_leaves_the_model_id_out_when_it_is_unknown():
    from app.services.auto_video_classifier_service import attach_classification_provenance

    result = attach_classification_provenance({"label": "x"}, input_source="frigate_snapshot_cropped", model_id=None)
    assert "model_id" not in result
    assert result["input_source"] == "frigate_snapshot_cropped"


def test_provenance_does_not_mutate_the_classifier_result():
    from app.services.auto_video_classifier_service import attach_classification_provenance

    top = {"label": "x"}
    attach_classification_provenance(top, input_source="frigate_snapshot_cropped", model_id="m")
    assert top == {"label": "x"}
