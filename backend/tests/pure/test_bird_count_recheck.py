from copy import deepcopy

import pytest

from app.services.bird_count_recheck import choose_count_rechecks, recheck_confirms_seed


LABELS = {"Cardinalis cardinalis": "Cardinalis cardinalis", "Northern Cardinal": "Cardinalis cardinalis"}


def candidate(name, box, *, frame=150, seconds=10.0, confidence=0.032, score=0.155, label="Cardinalis cardinalis"):
    return {
        "candidate_id": name,
        "source_mode": "model_crop",
        "clip_variant": "event",
        "frame_index": frame,
        "frame_offset_seconds": seconds,
        "frame_width": 3840,
        "frame_height": 2160,
        "detector_box": box,
        "crop_box": box,
        "crop_confidence": confidence,
        "classifier_label": label,
        "classifier_score": score,
    }


def evidence():
    return [
        candidate("cardinal", (1235, 1257, 1365, 1413)),
        candidate("donor", (1060, 1220, 1380, 1450), frame=75, seconds=5, confidence=0.72, score=0.75),
        candidate("branch", (3358, 407, 3494, 543), label="Ninox novaeseelandiae", score=0.38),
        candidate("wood", (1148, 1667, 1304, 1840), label="Ramaria stricta", score=0.08),
    ]


def test_nearby_confident_bird_guides_only_the_compatible_weak_region_without_changing_scores():
    rows = evidence()
    original = deepcopy(rows)
    selected = choose_count_rechecks(rows, bird_species=LABELS)
    assert [row["candidate_id"] for row in selected] == ["cardinal"]
    assert rows == original
    assert selected[0]["classifier_score"] == 0.155


@pytest.mark.parametrize(
    "change",
    [
        {"frame_index": 150},
        {"frame_offset_seconds": 10},
        {"frame_offset_seconds": None},
        {"frame_offset_seconds": float("nan")},
        {"frame_offset_seconds": 30},
        {"clip_variant": "full"},
        {"frame_width": 1920},
        {"frame_height": 1080},
        {"crop_confidence": 0.03},
        {"classifier_score": 0.3},
        {"classifier_label": "Ramaria stricta"},
        {"detector_box": (0, 0, 3840, 2160)},
        {"source_mode": "full_frame"},
    ],
)
def test_unrelated_or_unreliable_donor_does_not_trigger_a_scan(change):
    rows = evidence()
    rows[1].update(change)
    assert choose_count_rechecks(rows, bird_species=LABELS) == []


def test_missing_reference_and_non_bird_top_label_do_not_trigger_a_scan():
    assert choose_count_rechecks(evidence(), bird_species={}) == []
    rows = evidence()
    rows[0]["classifier_label"] = "Ramaria stricta"
    assert choose_count_rechecks(rows, bird_species=LABELS) == []


def test_common_and_scientific_aliases_can_guide_the_same_bird():
    rows = evidence()
    rows[1]["classifier_label"] = "Northern Cardinal"
    assert len(choose_count_rechecks(rows, bird_species=LABELS)) == 1


def test_existing_strong_detection_and_duplicate_weak_crops_are_not_rechecked_twice():
    rows = evidence()
    rows.append(dict(rows[0], candidate_id="duplicate"))
    assert len(choose_count_rechecks(rows, bird_species=LABELS)) == 1
    rows.append(dict(rows[0], candidate_id="already-counted", crop_confidence=0.14))
    assert choose_count_rechecks(rows, bird_species=LABELS) == []


def test_rechecks_have_a_fixed_per_bundle_limit():
    rows = []
    for index in range(8):
        box = (index * 200, 100, index * 200 + 100, 200)
        rows.extend(
            [
                candidate(f"weak{index}", box),
                candidate(f"donor{index}", box, frame=75, seconds=5, confidence=0.72, score=0.75),
            ]
        )
    assert len(choose_count_rechecks(rows, bird_species=LABELS)) == 4


def test_already_observed_regions_do_not_exhaust_budget_before_a_missing_bird():
    rows, observations = [], []
    for index in range(6):
        box = (index * 200, 100, index * 200 + 100, 200)
        weak = candidate(f"weak{index}", box)
        rows.extend([weak, candidate(f"donor{index}", box, frame=75, seconds=5, confidence=0.72, score=0.75)])
        if index < 5:
            observations.append(dict(weak, source_mode="model_observation", crop_confidence=0.8))
    selected = choose_count_rechecks(rows, bird_species=LABELS, observations=observations)
    assert [row["candidate_id"] for row in selected] == ["weak5"]


def test_group_sized_observation_does_not_block_rechecking_an_individual():
    rows = evidence()
    group = dict(rows[0], source_mode="model_observation", detector_box=(800, 700, 1500, 1500), crop_confidence=0.9)
    assert len(choose_count_rechecks(rows, bird_species=LABELS, observations=[group])) == 1


@pytest.mark.parametrize(
    "box,confidence,accepted",
    [
        ((1239, 1261, 1370, 1431), 0.557, True),
        ((1239, 1261, 1370, 1431), 0.03, False),
        ((894, 801, 1142, 1098), 0.9, False),
        ((800, 700, 1500, 1500), 0.9, False),
        ((1260, 1300, 1290, 1330), 0.9, False),
        ((1239, 1261, 1370, 1431), float("nan"), False),
        (None, 0.9, False),
    ],
)
def test_regional_result_must_confirm_the_seed_not_a_neighbor_or_group(box, confidence, accepted):
    seed = evidence()[0]
    seed["crop_box"] = (1221, 1246, 1388, 1420)
    assert recheck_confirms_seed(seed, {"detector_box": box, "confidence": confidence}) is accepted
