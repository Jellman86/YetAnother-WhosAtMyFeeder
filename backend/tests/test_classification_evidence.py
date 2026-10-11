import pytest

from app.models.classification_evidence import ClassificationEvidence
from app.services.classification_input_provenance import classification_evidence


def test_missing_evidence_stays_unknown_and_frigate_labels_are_not_model_identifications():
    assert classification_evidence({"label": "Robin", "score": 0.9}) is None
    evidence = classification_evidence({"source": "frigate_fallback", "input_source": "full_frame"})
    assert evidence.source == "frigate_sublabel"
    assert not evidence.needs_review


def test_whole_view_identification_needs_review_even_at_high_confidence():
    evidence = classification_evidence({"input_source": "frigate_recording_snapshot", "input_is_cropped": False})
    assert evidence.needs_review
    assert not evidence.can_personalize


def test_crop_coordinates_require_their_own_frame_geometry():
    evidence = classification_evidence(
        {
            "input_source": "recording_snapshot_frigate_hint_crop",
            "input_is_cropped": True,
            "input_box": [20, 30, 90, 100],
            "input_frame_size": [200, 150],
            "input_frame_time": 123.5,
        }
    )
    assert evidence.box == (20, 30, 90, 100)
    assert evidence.frame_size == (200, 150)
    assert not evidence.needs_review
    assert evidence.can_personalize
    assert classification_evidence({"input_source": "provided_crop", "input_is_cropped": True}).box is None


@pytest.mark.parametrize(
    "box,size",
    [
        ([0, 0, 999, 9], [100, 100]),
        ([0, 0, float("nan"), 9], [100, 100]),
        ([9, 9, 0, 0], [100, 100]),
        ([0, 0, 9, 9], None),
    ],
)
def test_invalid_geometry_is_discarded_without_losing_source(box, size):
    evidence = classification_evidence(
        {"input_source": "snapshot_model_crop", "input_is_cropped": True, "input_box": box, "input_frame_size": size}
    )
    assert evidence.source == "snapshot_model_crop"
    assert evidence.box is None


def test_stored_evidence_round_trips_and_rejects_unknown_fields():
    evidence = ClassificationEvidence(source="provided_crop", is_cropped=True)
    assert ClassificationEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    with pytest.raises(ValueError):
        ClassificationEvidence(source="provided_crop", is_cropped=True, arbitrary_secret="no")


def test_unknown_source_does_not_claim_a_crop():
    evidence = classification_evidence({"input_source": "future_unknown_source"})
    assert evidence.is_cropped is None
    assert not evidence.can_personalize
    assert classification_evidence({"input_source": "full_frame"}).needs_review
