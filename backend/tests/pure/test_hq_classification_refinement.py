from types import SimpleNamespace

import pytest

from app.models.classification_evidence import ClassificationEvidence
from app.services.hq_classification_refinement import (
    choose_hq_classification_refinement,
    crop_labels_disputing_full_frame,
    identity_rests_on_whole_frame,
)


def _candidate(
    frame_index: int,
    label: str,
    score: float,
    *,
    source_mode: str = "frigate_hint_crop",
    candidate_id: str | None = None,
    frame_offset_seconds: float | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id or f"{source_mode}-{frame_index}",
        "frame_index": frame_index,
        "frame_offset_seconds": (
            frame_offset_seconds if frame_offset_seconds is not None else float(frame_index) / 30.0
        ),
        "source_mode": source_mode,
        "classifier_label": label,
        "classifier_score": score,
        "classifier_index": frame_index + 100,
    }


def _detection(**overrides):
    values = {
        "display_name": "Unknown Bird",
        "category_name": "Unknown Bird",
        "scientific_name": None,
        "common_name": None,
        "score": 0.52,
        "manual_tagged": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_promotes_multi_frame_crop_consensus_over_unknown_detection():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Columba palumbus", 0.82),
            _candidate(20, "Columba palumbus", 0.80),
            _candidate(30, "Columba palumbus", 0.61),
            _candidate(10, "Aegithalos caudatus", 0.09, source_mode="full_frame"),
        ],
        minimum_score=0.60,
    )

    assert decision is not None
    assert decision.label == "Columba palumbus"
    assert decision.score == 0.82
    assert decision.supporting_frame_count == 3
    assert decision.reason == "upgrade_unknown_from_crop_consensus"


def test_rejects_single_frame_even_when_two_crop_sources_agree():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Columba palumbus", 0.94, source_mode="frigate_hint_crop"),
            _candidate(10, "Columba palumbus", 0.91, source_mode="model_crop"),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_rejects_adjacent_frames_as_correlated_evidence():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(0, "Columba palumbus", 0.94, frame_offset_seconds=0.0),
            _candidate(1, "Columba palumbus", 0.92, frame_offset_seconds=1 / 30),
            _candidate(2, "Columba palumbus", 0.90, frame_offset_seconds=2 / 30),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_accepts_only_the_temporally_independent_subset():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(0, "Columba palumbus", 0.94, frame_offset_seconds=0.0),
            _candidate(1, "Columba palumbus", 0.93, frame_offset_seconds=1 / 30),
            _candidate(30, "Columba palumbus", 0.82, frame_offset_seconds=1.0),
        ],
        minimum_score=0.60,
    )

    assert decision is not None
    assert decision.supporting_frame_count == 2
    assert decision.median_score == pytest.approx(0.88)


def test_rejects_candidates_without_temporal_provenance():
    candidate = _candidate(10, "Columba palumbus", 0.94)
    candidate.pop("frame_offset_seconds")
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[candidate, _candidate(20, "Columba palumbus", 0.92)],
        minimum_score=0.60,
    )

    assert decision is None


def test_rejects_low_confidence_multi_frame_crop_consensus():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Turdus fuscater", 0.14),
            _candidate(20, "Turdus fuscater", 0.13),
            _candidate(30, "Turdus fuscater", 0.12),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_never_replaces_manual_identification():
    decision = choose_hq_classification_refinement(
        detection=_detection(manual_tagged=True),
        candidates=[
            _candidate(10, "Columba palumbus", 0.96),
            _candidate(20, "Columba palumbus", 0.95),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_does_not_replace_a_conflicting_known_species():
    decision = choose_hq_classification_refinement(
        detection=_detection(
            display_name="Wood Pigeon",
            category_name="Columba palumbus",
            scientific_name="Columba palumbus",
            common_name="Wood Pigeon",
            score=0.87,
        ),
        candidates=[
            _candidate(10, "Turdus fuscater", 0.93),
            _candidate(20, "Turdus fuscater", 0.91),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_reinforces_same_known_species_only_when_score_materially_improves():
    detection = _detection(
        display_name="Wood Pigeon",
        category_name="Columba palumbus",
        scientific_name="Columba palumbus",
        common_name="Wood Pigeon",
        score=0.82,
    )
    candidates = [
        _candidate(10, "Columba_palumbus", 0.88),
        _candidate(20, "Columba palumbus", 0.86),
    ]

    decision = choose_hq_classification_refinement(
        detection=detection,
        candidates=candidates,
        minimum_score=0.60,
    )

    assert decision is not None
    assert decision.label == "Columba palumbus"
    assert decision.reason == "reinforce_existing_from_crop_consensus"


def test_rejects_ambiguous_competing_multi_frame_consensus():
    decision = choose_hq_classification_refinement(
        detection=_detection(),
        candidates=[
            _candidate(10, "Columba palumbus", 0.80),
            _candidate(20, "Columba palumbus", 0.78),
            _candidate(30, "Streptopelia decaocto", 0.76),
            _candidate(40, "Streptopelia decaocto", 0.75),
        ],
        minimum_score=0.60,
    )

    assert decision is None


def test_the_decision_names_the_model_that_scored_its_winning_crop():
    candidates = [_candidate(frame, "Columba palumbus", 0.82) for frame in (10, 20, 30)]
    for candidate in candidates:
        candidate["classifier_model_sha256"] = "c" * 64

    decision = choose_hq_classification_refinement(detection=_detection(), candidates=candidates, minimum_score=0.60)

    assert decision is not None
    assert decision.model_sha256 == "c" * 64


def _persisted_row(
    source_mode: str,
    label: str | None,
    score: float | None,
    crop_confidence: float | None,
    frame_index: int = 0,
) -> dict:
    return {
        "candidate_id": f"{source_mode}-f{frame_index}-{score}",
        "source_mode": source_mode,
        "frame_index": frame_index,
        "frame_offset_seconds": frame_index / 29.97,
        "classifier_label": label,
        "classifier_score": score,
        "classifier_index": 3775 if label == "Pica pica" else 2610,
        "crop_confidence": crop_confidence,
    }


# Detection 1564's photo choices: a greenhouse visit whose whole frames read as Pica pica while
# every crop of the birds read as Columba palumbus, in frames 255 and 510, 8.5 s apart.
WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS = [
    _persisted_row("model_crop", "Columba palumbus", 0.977, 0.35, 510),
    _persisted_row("model_crop", "Columba palumbus", 0.957, 0.45, 510),
    _persisted_row("model_crop", "Columba palumbus", 0.942, 0.85, 255),
    _persisted_row("model_crop", "Columba palumbus", 0.854, 0.80, 255),
    _persisted_row("full_frame", "Pica pica", 0.768, None, 765),
    _persisted_row("full_frame", "Pica pica", 0.726, 0.45, 510),
    _persisted_row("full_frame", "Pica pica", 0.462, 0.85, 255),
    _persisted_row("retained_photo", None, None, None),
]
PIGEON_CROPS_FROM_ONE_FRAME = [
    row
    for row in WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS
    if row["source_mode"] != "model_crop" or row["frame_index"] == 255
]


def _whole_frame_magpie(**overrides):
    values = {
        "display_name": "Eurasian Magpie",
        "category_name": "Pica pica",
        "scientific_name": "Pica pica",
        "common_name": "Eurasian Magpie",
        "score": 0.7245,
        "classification_input": ClassificationEvidence(source="frigate_recording_frame", is_cropped=False),
    }
    values.update(overrides)
    return _detection(**values)


def test_crops_that_name_another_species_contradict_a_whole_frame_label():
    assert crop_labels_disputing_full_frame(["Pica pica"], WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS) == ["Columba palumbus"]
    assert crop_labels_disputing_full_frame(["Pica pica"], PIGEON_CROPS_FROM_ONE_FRAME) == ["Columba palumbus"]


def test_any_identity_name_that_a_crop_shares_is_agreement():
    labels = ["Common Wood-Pigeon", "Columba palumbus"]

    assert not crop_labels_disputing_full_frame(labels, WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS)


@pytest.mark.parametrize(
    "source", ["frigate_recording_frame", "hq_candidate_full_frame", "high_quality_snapshot", "frigate_snapshot"]
)
def test_crop_consensus_corrects_a_name_read_from_an_uncropped_whole_frame(source):
    detection = _whole_frame_magpie(classification_input=ClassificationEvidence(source=source, is_cropped=False))

    decision = choose_hq_classification_refinement(
        detection=detection, candidates=WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS, minimum_score=0.65
    )

    assert decision is not None
    assert decision.label == "Columba palumbus"
    assert decision.score == 0.977
    assert decision.supporting_frame_count == 2
    assert decision.median_score == pytest.approx(0.9595)
    assert decision.source_mode == "model_crop"
    assert decision.reason == "correct_whole_frame_from_crop_consensus"
    assert identity_rests_on_whole_frame(detection)


@pytest.mark.parametrize(
    ("overrides", "owner_species_chosen"),
    [
        ({"manual_tagged": True}, False),
        ({}, True),
        ({"classification_input": ClassificationEvidence(source="owner_species_choice")}, False),
        # Crop-based and video-based identifications are never replaced.
        (
            {
                "classification_input": ClassificationEvidence(
                    source="hq_candidate_model_crop", is_cropped=True, supporting_frames=2
                )
            },
            False,
        ),
        (
            {
                "classification_input": ClassificationEvidence(
                    source="full_frame", is_cropped=False, supporting_frames=6
                )
            },
            False,
        ),
        ({"classification_input": ClassificationEvidence(source="video_evidence_full_frame", is_cropped=False)}, False),
        ({"classification_input": ClassificationEvidence(source="frigate_sublabel")}, False),
        ({"classification_input": ClassificationEvidence(source="frigate_thumbnail", is_cropped=False)}, False),
        # Unrecorded or unknown cropping is not proof of a whole frame.
        ({"classification_input": ClassificationEvidence(source="frigate_recording_frame")}, False),
        ({"classification_input": None}, False),
    ],
    ids=[
        "manual-tag",
        "owner-species-choice",
        "owner-source",
        "crop-consensus",
        "video",
        "video-evidence-photo",
        "frigate-sublabel",
        "frigate-thumbnail",
        "cropping-unknown",
        "no-input",
    ],
)
def test_crop_consensus_never_replaces_a_protected_or_non_whole_frame_name(overrides, owner_species_chosen):
    detection = _whole_frame_magpie(**overrides)

    assert not identity_rests_on_whole_frame(detection, owner_species_chosen=owner_species_chosen)
    assert (
        choose_hq_classification_refinement(
            detection=detection,
            candidates=WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS,
            minimum_score=0.65,
            owner_species_chosen=owner_species_chosen,
        )
        is None
    )


def test_whole_frame_name_survives_a_single_frame_or_weak_crop_consensus():
    weak = [
        {**row, "classifier_score": 0.62} if row["source_mode"] == "model_crop" else row
        for row in WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS
    ]

    for candidates in (PIGEON_CROPS_FROM_ONE_FRAME, weak):
        assert (
            choose_hq_classification_refinement(
                detection=_whole_frame_magpie(), candidates=candidates, minimum_score=0.65
            )
            is None
        )


def test_whole_frame_name_is_not_replaced_by_an_unknown_crop_consensus():
    unknown = [
        {**row, "classifier_label": "Unknown Bird"} if row["source_mode"] == "model_crop" else row
        for row in WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS
    ]

    assert choose_hq_classification_refinement(detection=_whole_frame_magpie(), candidates=unknown) is None


def test_a_whole_frame_that_agrees_with_a_crop_is_not_contradicted():
    assert not crop_labels_disputing_full_frame(["Columba palumbus"], WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS)
    assert not crop_labels_disputing_full_frame(["columba_palumbus"], WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS)


def test_one_agreeing_crop_corroborates_a_whole_frame_in_a_mixed_scene():
    rows = [
        _persisted_row("model_crop", "Columba palumbus", 0.95, 0.9),
        _persisted_row("frigate_hint_crop", "Pica pica", 0.81, None),
        _persisted_row("full_frame", "Pica pica", 0.77, None),
    ]

    assert not crop_labels_disputing_full_frame(["Pica pica"], rows)


def test_a_whole_frame_is_not_contradicted_when_the_event_has_no_named_crop():
    whole_frames_only = [row for row in WHOLE_FRAME_MAGPIE_OVER_PIGEON_CROPS if row["source_mode"] != "model_crop"]
    unnamed_crops = [
        _persisted_row("model_crop", "Unknown Bird", 0.4, 0.9),
        _persisted_row("frigate_hint_crop", None, None, None),
        _persisted_row("model_observation", "Columba palumbus", 0.9, 0.9),
    ]

    assert not crop_labels_disputing_full_frame(["Pica pica"], whole_frames_only)
    assert not crop_labels_disputing_full_frame(["Pica pica"], unnamed_crops)
    assert not crop_labels_disputing_full_frame(["Pica pica"], [])
