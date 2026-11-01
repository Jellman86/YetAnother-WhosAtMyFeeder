"""Pure input selection: Frigate hints aligned to a frame, and honest input provenance.

No classifier, crop detector or model is constructed; each case is the decision alone.
"""

import pytest

from app.services.inference.input_selection import (
    ClassifiedInputProvenance,
    attach_classification_input_provenance,
    input_context_extra,
    normalize_classification_input_context,
    resolved_classification_input_provenance,
    tracked_frigate_box_for_frame,
    video_frame_input_context,
)


def _context(**fields):
    return normalize_classification_input_context({"is_cropped": False, **fields})


def test_an_untrusted_context_normalises_to_an_empty_one():
    assert normalize_classification_input_context(None) == normalize_classification_input_context({})
    assert normalize_classification_input_context({"is_cropped": "not a bool"}).is_cropped is False


def test_extra_hints_are_read_from_the_context():
    context = _context(frigate_box=[0.1, 0.2, 0.3, 0.4])

    assert input_context_extra(context, "frigate_box") == [0.1, 0.2, 0.3, 0.4]
    assert input_context_extra(context, "is_cropped") is False
    assert input_context_extra(context, "absent") is None


def test_a_tracked_box_follows_the_nearest_path_point_and_refuses_a_distant_one():
    context = _context(
        frigate_box=[0.1, 0.1, 0.2, 0.2],
        frigate_path_data=[[[0.2, 0.3], 100.0], [[0.8, 0.9], 102.0]],
        clip_start_timestamp=100.0,
    )

    assert tracked_frigate_box_for_frame(context, frame_offset_seconds=0.0) == pytest.approx([0.1, 0.1, 0.2, 0.2])
    assert tracked_frigate_box_for_frame(context, frame_offset_seconds=2.0) == pytest.approx([0.7, 0.7, 0.2, 0.2])
    assert tracked_frigate_box_for_frame(context, frame_offset_seconds=1.0) is None
    assert tracked_frigate_box_for_frame(context, frame_offset_seconds=None) is None


def test_a_recording_frame_drops_untimed_hints_but_keeps_the_subject_region():
    context = _context(
        clip_variant="recording",
        frigate_box=[0.4, 0.4, 0.1, 0.1],
        frigate_region=[0.3, 0.3, 0.3, 0.3],
    )

    frame = video_frame_input_context(context, frame_offset_seconds=3.0, image_size=(1000, 1000))

    assert input_context_extra(frame, "frigate_box") is None
    assert input_context_extra(frame, "frigate_region") is None
    assert input_context_extra(frame, "event_subject_region") == pytest.approx([0.3, 0.3, 0.3, 0.3])


@pytest.mark.parametrize(
    ("fields", "diagnostics", "expected"),
    [
        ({}, {"crop_applied": True, "crop_reason": "frigate_box"}, ("snapshot_frigate_hint_crop", True)),
        (
            {"input_source": "frigate_recording_snapshot"},
            {"crop_applied": True, "crop_reason": "frigate_snapshot_scaled_crop"},
            ("recording_snapshot_frigate_hint_crop", True),
        ),
        ({}, {"crop_applied": True, "crop_reason": "rfdetr"}, ("snapshot_model_crop", True)),
        ({"input_source": " Video_Frame "}, {"crop_applied": False}, ("video_frame", False)),
        ({"is_cropped": True}, {}, ("provided_crop", True)),
        ({}, {}, ("full_frame", False)),
    ],
)
def test_provenance_names_the_image_that_was_actually_classified(fields, diagnostics, expected):
    provenance = resolved_classification_input_provenance(
        input_context=_context(**fields), crop_diagnostics=diagnostics
    )

    assert provenance == ClassifiedInputProvenance(*expected)


def test_frame_identity_is_attached_only_when_the_crop_came_from_that_frame():
    context = _context(recording_frame_time=5.0, source_image_sha256="abc")
    other_frame = {"crop_applied": True, "crop_reason": "rfdetr", "input_box": [1, 2, 3, 4], "source_same_frame": False}
    same_frame = {**other_frame, "source_same_frame": True}

    from_other = attach_classification_input_provenance(
        [{"label": "Robin"}, "not a result"], input_context=context, crop_diagnostics=other_frame
    )
    from_same = attach_classification_input_provenance(
        [{"label": "Robin"}], input_context=context, crop_diagnostics=same_frame
    )

    assert from_other[0] == {
        "label": "Robin",
        "input_source": "snapshot_model_crop",
        "input_is_cropped": True,
        "input_box": [1, 2, 3, 4],
    }
    assert from_other[1] == "not a result"
    assert from_same[0]["input_frame_time"] == 5.0
    assert from_same[0]["input_frame_sha256"] == "abc"
