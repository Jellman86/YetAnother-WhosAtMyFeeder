"""Proposal presence must not attribute the same pixels to another bird."""

from itertools import permutations

from app.services.bird_observation_selection import (
    select_bird_observations,
    select_confirmed_bird_observations,
    select_scene_birds,
)
from app.services.bird_physical_confirmation import PhysicalBirdDecision
from app.utils.box_matching import matched_box_count


def proposal(name, box, confidence, *, score=0.0, label=None, frame=1):
    return {
        "candidate_id": name,
        "source_mode": "model_observation",
        "clip_variant": "recording",
        "frame_index": frame,
        "crop_box": box,
        "crop_confidence": confidence,
        "classifier_label": label,
        "classifier_score": score,
    }


def select(rows, decisions=None, *, qualified=True):
    return select_confirmed_bird_observations(
        rows,
        selected_candidate=None,
        finder_qualified=qualified,
        physical_decisions=decisions or {},
    )


def test_recorded_two_bird_frame_keeps_two_confirmed_and_discloses_both_uncertain_regions():
    # Recorded detector geometry and own-crop scores; private photographs are not bundled.
    rows = [
        proposal("left", (1188, 543, 1424, 713), 0.840707, label="Cyanistes caeruleus", score=0.956788),
        proposal("right", (1754, 476, 1932, 650), 0.794037, label="Cyanistes caeruleus", score=0.708021),
        proposal("shared-foot", (1684, 573, 1802, 664), 0.463924),
        proposal("seed-port", (1605, 623, 1661, 659), 0.302040),
    ]
    decisions = {
        "shared-foot": PhysicalBirdDecision("counted", "own_crop_bird"),
        "seed-port": PhysicalBirdDecision("unconfirmed", "insufficient_confirmation"),
    }
    for ordered in permutations(rows):
        result = select(list(ordered), decisions)
        assert (
            matched_box_count([(1180, 545, 1420, 712), (1732, 464, 1940, 647)], [b.box for b in result.birds], 0.5) == 2
        )
        assert len(result.birds) == 2
        assert result.birds[0].species == "Cyanistes caeruleus"
        assert result.count_status == "incomplete"
        assert {r.candidate_id: r.reason for r in result.unconfirmed_regions} == {
            "shared-foot": "shares_counted_pixels",
            "seed-port": "insufficient_confirmation",
        }
        assert result.excluded_regions == ()


def test_known_adjacent_robin_head_and_body_do_not_become_two_birds():
    rows = [proposal("head", (1032, 357, 1122, 471), 0.3682), proposal("body", (1110, 369, 1218, 459), 0.3842)]
    result = select(rows, {r["candidate_id"]: PhysicalBirdDecision("counted", "own_crop_bird") for r in rows})
    assert result.birds == ()
    assert len(result.unconfirmed_regions) == 2
    assert {r.reason for r in result.unconfirmed_regions} == {"individuality_unresolved"}
    assert result.count_status == "incomplete"


def test_isolated_confirmed_weak_bird_does_not_need_a_confident_species_name():
    row = proposal("unknown", (10, 10, 60, 60), 0.35, label="Rare Bird", score=0.25)
    result = select([row], {"unknown": PhysicalBirdDecision("counted", "own_crop_bird")})
    assert len(result.birds) == 1
    assert result.birds[0].species == "Unknown Bird"
    assert result.count_status == "complete"


def test_isolated_weak_proposal_without_confirmation_is_not_an_empty_completed_count():
    result = select([proposal("weak", (10, 10, 60, 60), 0.35)])
    assert result.birds == ()
    assert result.count_status == "incomplete"
    assert result.unconfirmed_regions[0].reason == "confirmation_unavailable"


def test_verified_nonbird_region_is_excluded_before_individuality_checks():
    rows = [proposal("bird", (10, 10, 60, 60), 0.35), proposal("fixture", (50, 10, 90, 60), 0.4)]
    result = select(
        rows,
        {
            "bird": PhysicalBirdDecision("counted", "own_crop_bird"),
            "fixture": PhysicalBirdDecision("excluded", "own_crop_nonbird"),
        },
    )
    assert [b.candidate_id for b in result.birds] == ["bird"]
    assert [r.candidate_id for r in result.excluded_regions] == ["fixture"]
    assert result.unconfirmed_regions == ()


def test_unqualified_finder_never_publishes_a_new_count():
    result = select([proposal("strong", (10, 10, 60, 60), 0.99)], qualified=False)
    assert result.birds == ()
    assert result.count_status == "not_measured"


def test_strong_group_versus_parts_keeps_the_existing_all_or_nothing_ambiguity():
    rows = [
        proposal("group", (0, 0, 300, 100), 0.95),
        proposal("a", (10, 10, 110, 90), 0.7),
        proposal("b", (120, 10, 220, 90), 0.6),
    ]
    result = select(rows)
    assert result.ambiguity_reason == "ambiguous_localization"
    assert result.birds == ()
    assert result.count_status == "ambiguous"


def test_strong_enclosing_box_is_also_ambiguous_when_its_parts_are_mid_band():
    result = select(
        [
            proposal("group", (0, 0, 300, 100), 0.95),
            proposal("a", (10, 10, 110, 90), 0.35),
            proposal("b", (120, 10, 220, 90), 0.4),
        ]
    )
    assert result.ambiguity_reason == "ambiguous_localization"
    assert result.birds == ()


def test_repeated_identical_photo_and_observation_boxes_do_not_create_artificial_uncertainty():
    row = proposal("bird", (10, 10, 60, 60), 0.35)
    duplicate = {**row, "candidate_id": "photo", "source_mode": "model_crop"}
    result = select([row, duplicate], {"bird": PhysicalBirdDecision("counted", "own_crop_bird")})
    assert len(result.birds) == 1
    assert result.unconfirmed_regions == ()


def test_frame_with_more_confirmed_birds_wins_without_combining_frames():
    rows = [
        proposal("a", (10, 10, 60, 60), 0.9),
        proposal("b", (100, 10, 150, 60), 0.8),
        proposal("weak", (145, 10, 180, 60), 0.3),
        proposal("later", (10, 10, 60, 60), 0.9, frame=2),
    ]
    result = select(rows)
    assert result.frame_index == 1
    assert len(result.birds) == 2
    assert len(result.unconfirmed_regions) == 1


def test_confirmation_budget_cannot_silently_cap_strong_bird_counts_to_the_eight_photo_limit():
    rows = [proposal(str(i), (100 * i, 10, 100 * i + 50, 60), 0.8) for i in range(12)]
    assert len(select(rows).birds) == 12


def test_empty_negative_frame_cannot_hide_an_unresolved_positive_frame():
    rows = [
        proposal("group", (0, 0, 300, 100), 0.95),
        proposal("a", (10, 10, 110, 90), 0.7),
        proposal("b", (120, 10, 220, 90), 0.6),
        proposal("fixture", (10, 10, 60, 60), 0.4, frame=2),
    ]
    result = select(rows, {"fixture": PhysicalBirdDecision("excluded", "own_crop_nonbird")})
    assert result.count_status == "ambiguous"
    assert result.frame_index == 1


def test_scene_count_with_a_qualified_finder_counts_only_strong_detections_and_discloses_the_rest():
    rows = [
        proposal("left", (1188, 543, 1424, 713), 0.840707, label="Cyanistes caeruleus", score=0.956788),
        proposal("right", (1754, 476, 1932, 650), 0.794037),
        proposal("shared-foot", (1684, 573, 1802, 664), 0.463924),
        proposal("seed-port", (1605, 623, 1661, 659), 0.302040),
        {**proposal("photo-crop", (1188, 543, 1424, 713), 0.840707), "source_mode": "model_crop"},
    ]
    result = select_scene_birds(rows, selected_candidate=None, confirmed_finder=True)
    assert [bird.candidate_id for bird in result.birds] == ["left", "right"]
    assert result.count_status == "incomplete"
    assert {r.candidate_id: r.reason for r in result.unconfirmed_regions} == {
        "shared-foot": "shares_counted_pixels",
        "seed-port": "confirmation_unavailable",
    }


def test_scene_count_without_a_qualified_finder_keeps_the_earlier_count_unchanged():
    rows = [proposal("a", (0, 0, 50, 50), 0.84), proposal("b", (100, 0, 150, 50), 0.30)]
    result = select_scene_birds(rows, selected_candidate=None, confirmed_finder=False)
    assert result == select_bird_observations(rows, selected_candidate=None)
    assert result.count_status == "legacy"
    assert len(result.birds) == 2
