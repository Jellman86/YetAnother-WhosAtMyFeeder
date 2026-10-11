from app.services.bird_observation_selection import select_bird_observations


def crop(
    candidate_id: str,
    box: tuple[int, int, int, int],
    *,
    frame_index: int = 1,
    clip_variant: str = "event",
    source_mode: str = "model_crop",
    confidence: float = 0.8,
    label: str = "House Finch",
    score: float = 0.9,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "crop_box": box,
        "frame_index": frame_index,
        "clip_variant": clip_variant,
        "source_mode": source_mode,
        "crop_confidence": confidence,
        "classifier_label": label,
        "classifier_score": score,
        "ranking_score": score,
    }


def test_counts_distinct_birds_from_one_frame_without_recounting_later_frames():
    first = crop("finch-one", (10, 10, 60, 60))
    second = crop("cardinal", (90, 10, 140, 60), label="Northern Cardinal")
    repeated = crop("finch-later", (12, 12, 62, 62), frame_index=2)
    full = {"candidate_id": "whole", "source_mode": "full_frame", "clip_variant": "event", "frame_index": 1}

    selection = select_bird_observations([first, second, repeated, full], selected_candidate=first)

    assert selection.full_frame_candidate_id == "whole"
    assert [item.candidate_id for item in selection.birds] == ["finch-one", "cardinal"]


def test_chooses_frame_with_most_birds_and_keeps_same_species_individuals():
    selected = crop("selected", (10, 10, 60, 60), frame_index=1)
    later = [
        crop("a", (10, 10, 60, 60), frame_index=2),
        crop("b", (90, 10, 140, 60), frame_index=2),
        crop("c", (170, 10, 220, 60), frame_index=2),
    ]
    selection = select_bird_observations([selected, *later], selected_candidate=selected)

    assert selection.frame_index == 2
    assert [item.candidate_id for item in selection.birds] == ["a", "b", "c"]


def test_rejects_weak_boxes_and_does_not_count_hint_twice():
    strong = crop("strong", (10, 10, 60, 60))
    hint = crop("hint", (5, 5, 65, 65), source_mode="frigate_hint_crop")
    weak = crop("weak", (90, 10, 140, 60), confidence=0.01)
    duplicate = crop("duplicate", (11, 11, 61, 61))

    selection = select_bird_observations([hint, strong, weak, duplicate], selected_candidate=strong)

    assert [item.candidate_id for item in selection.birds] == ["strong"]


def test_keeps_uncertain_species_as_unidentified_bird():
    uncertain = crop("bird", (10, 10, 60, 60), label="Rare Bird", score=0.24)

    selection = select_bird_observations([uncertain], selected_candidate=uncertain)

    assert len(selection.birds) == 1
    assert selection.birds[0].species == "Unknown Bird"


def test_empty_selection_when_no_localized_evidence():
    selection = select_bird_observations(
        [{"candidate_id": "whole", "source_mode": "full_frame", "frame_index": 1, "clip_variant": "event"}],
        selected_candidate=None,
    )

    assert selection.birds == ()


def test_counts_realistic_low_confidence_and_merges_overlapping_detector_boxes():
    first = crop("bird", (260, 360, 370, 470), confidence=0.22)
    first["detector_box"] = (274, 375, 359, 460)
    duplicate = crop("second_crop_same_bird", (250, 350, 400, 470), confidence=0.11)
    duplicate["detector_box"] = (301, 367, 397, 448)
    other = crop("other_bird", (450, 350, 550, 450), confidence=0.096)
    other["detector_box"] = (455, 355, 545, 445)

    selection = select_bird_observations([first, duplicate, other], selected_candidate=first)

    assert [bird.candidate_id for bird in selection.birds] == ["bird", "other_bird"]
    assert selection.birds[0].box == (274, 375, 359, 460)


def test_failed_whole_frame_scan_on_one_frame_keeps_its_scored_crop_evidence():
    first = crop("first", (10, 10, 60, 60), frame_index=1)
    second = crop("second", (90, 10, 140, 60), frame_index=1)
    observed = crop("observed", (10, 10, 60, 60), frame_index=2, source_mode="model_observation")

    selection = select_bird_observations([first, second, observed], selected_candidate=first)

    assert selection.frame_index == 1
    assert len(selection.birds) == 2


def test_whole_frame_count_keeps_a_different_bird_localized_by_guided_detection():
    guided = crop("guided-titmouse", (10, 10, 60, 60), confidence=0.14)
    observed = crop("observed-cardinal", (90, 10, 140, 60), source_mode="model_observation")

    selection = select_bird_observations([guided, observed], selected_candidate=guided)

    assert [bird.candidate_id for bird in selection.birds] == ["guided-titmouse", "observed-cardinal"]


def test_combining_guided_and_whole_frame_detections_does_not_count_a_bird_twice():
    guided = crop("guided", (10, 10, 60, 60), confidence=0.14)
    observed = crop("observed", (12, 12, 62, 62), source_mode="model_observation")
    weak = crop("weak", (90, 10, 140, 60), confidence=0.03)

    selection = select_bird_observations([guided, observed, weak], selected_candidate=guided)

    assert len(selection.birds) == 1
    assert selection.birds[0].candidate_id == "observed"


def test_enclosing_group_box_does_not_suppress_two_separately_localized_birds():
    group = crop("group", (0, 0, 200, 100), confidence=0.95, score=0.2)
    first = crop("first", (10, 10, 60, 60), confidence=0.7)
    second = crop("second", (130, 10, 180, 60), confidence=0.6)
    duplicate = crop("duplicate", (12, 12, 62, 62), confidence=0.65)
    selection = select_bird_observations([group, first, duplicate, second], selected_candidate=group)
    assert [bird.candidate_id for bird in selection.birds] == ["first", "second"]


def test_overlapping_duplicates_inside_a_large_box_do_not_imply_two_birds():
    group = crop("group", (0, 0, 200, 100), confidence=0.95)
    first = crop("first", (10, 10, 60, 60), confidence=0.7)
    duplicate = crop("duplicate", (12, 12, 62, 62), confidence=0.65)
    selection = select_bird_observations([group, first, duplicate], selected_candidate=group)
    assert len(selection.birds) == 1


def test_bridging_duplicate_does_not_hide_two_disjoint_birds_inside_a_group():
    group = crop("group", (0, 0, 300, 100), confidence=0.95)
    first = crop("first", (10, 10, 110, 90), confidence=0.7)
    second = crop("second", (120, 10, 220, 90), confidence=0.6)
    bridge = crop("bridge", (60, 10, 170, 50), confidence=0.1)
    selection = select_bird_observations([group, first, second, bridge], selected_candidate=group)
    assert [bird.candidate_id for bird in selection.birds] == ["first", "second"]
