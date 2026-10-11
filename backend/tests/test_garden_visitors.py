"""Garden decisions stay independent from the existing bird ingest pipeline."""

import math

import pytest

from app.services.garden_visitors import GardenPolicy, Taxon, decide_prediction, route_event
from app.utils.frigate import is_ingest_label


FOX = Taxon("fox", "red fox", ("mammalia", "carnivora", "canidae", "vulpes", "vulpes"))
GREY_FOX = Taxon("grey", "grey fox", ("mammalia", "carnivora", "canidae", "urocyon", "cinereoargenteus"))
CANINE = Taxon("canine", "canine family", ("mammalia", "carnivora", "canidae", "", ""))
HUMAN = Taxon("human", "human", ("mammalia", "primates", "hominidae", "homo", "sapiens"))
BIRD = Taxon("bird", "bird", ("aves", "", "", "", ""))
BLANK = Taxon("blank", "blank", ("", "", "", "", ""))
POLICY = GardenPolicy(enabled=True, cameras=frozenset({"patio"}), labels=frozenset({"animal", "cat", "dog"}))


def test_garden_is_off_by_default_and_requires_camera_and_label_opt_in():
    assert route_event("patio", "cat", GardenPolicy()) == "disabled"
    assert route_event("other", "cat", POLICY) == "camera_excluded"
    assert route_event("patio", "squirrel", POLICY) == "label_excluded"
    assert route_event("patio", " Cat ", POLICY) == "garden"


@pytest.mark.parametrize("label", ["bird", "duck", "goose"])
def test_existing_bird_labels_take_precedence_even_if_selected_for_garden(label):
    policy = GardenPolicy(enabled=True, cameras=frozenset({"patio"}), labels=frozenset({label}))
    assert route_event("patio", label, policy, bird_labels=frozenset({"bird", "duck", "goose"})) == "bird"
    assert is_ingest_label(label, ["bird", "duck", "goose"])
    assert not is_ingest_label("animal", ["bird", "duck", "goose"])


@pytest.mark.parametrize("label", ["person", " HUMAN "])
def test_people_never_reach_garden_classifier_even_if_opted_in(label):
    policy = GardenPolicy(enabled=True, cameras=frozenset({"patio"}), labels=frozenset({"person", "human"}))
    assert route_event("patio", label, policy) == "human_rejected"


def decide(predictions, *, country="GBR", geofence=None):
    return decide_prediction(
        predictions, POLICY, country=country, taxonomy=[FOX, GREY_FOX, CANINE], geofence=geofence or {}
    )


def test_human_winner_or_significant_runner_up_rejects_without_animal_substitution():
    for predictions in ([(HUMAN, 0.8), (FOX, 0.2)], [(FOX, 0.85), (HUMAN, 0.15)]):
        result = decide(predictions)
        assert result.reason == "human_rejected"
        assert result.taxon is None


def test_bird_blank_and_low_confidence_are_not_garden_visits():
    assert decide([(BIRD, 0.95)]).reason == "bird_excluded"
    assert decide([(BLANK, 0.95)]).reason == "non_animal"
    assert decide([(FOX, 0.4)]).reason == "low_confidence"


def test_geofence_rolls_up_top_species_without_selecting_local_runner_up():
    result = decide([(GREY_FOX, 0.9), (FOX, 0.1)], geofence={GREY_FOX.key: {"allow": {"USA": []}}})
    assert result.taxon == CANINE
    assert result.reason == "garden"
    assert result.needs_review
    assert result.geofenced
    assert result.score == 0.9


def test_unknown_country_fails_closed_instead_of_silently_disabling_geofence():
    with pytest.raises(ValueError, match="ISO"):
        decide([(FOX, 0.9)], country="United Kingdom")


def test_geofence_without_a_safe_ancestor_abstains():
    result = decide_prediction(
        [(FOX, 0.9)], POLICY, country="GBR", taxonomy=[FOX], geofence={FOX.key: {"block": {"GBR": []}}}
    )
    assert result.reason == "geofence_unresolved"


def test_allowed_species_keeps_species_identity_and_score():
    result = decide([(FOX, 0.95)])
    assert result.taxon == FOX
    assert not result.needs_review
    assert not result.geofenced


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.1])
def test_invalid_probabilities_fail_closed(score):
    with pytest.raises(ValueError, match="probabilit"):
        decide([(FOX, score)])


def test_unsorted_or_empty_predictions_fail_closed():
    with pytest.raises(ValueError):
        decide([])
    with pytest.raises(ValueError):
        decide([(FOX, 0.1), (GREY_FOX, 0.9)])
