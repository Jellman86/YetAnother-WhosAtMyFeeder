"""Domestic birds are Garden animals only when the owner declares them, by exact identity."""

import json
from typing import get_args

import pytest

from app.models.garden import GardenAutomaticCheck
from app.services.garden_automatic_policy import (
    AutomaticPlan,
    automatic_check_dismisses,
    finish_automatic_check,
    plan_automatic_check,
    saved_check_dismisses,
)
from app.services.garden_domestic_birds import (
    DOMESTIC_BIRDS,
    DomesticBirdKey,
    bird_event_route,
    camera_watches_birds,
    domestic_bird_for_bird_label,
    domestic_bird_for_speciesnet,
    garden_bird_route,
    normalize_domestic_birds,
)
from app.services.garden_visitors import GardenPolicy, Taxon, decide_prediction

CHICKEN_IDS = {"chicken": frozenset({472, 21883})}


def test_every_domestic_bird_maps_to_exact_speciesnet_bird_outputs_in_the_pinned_package():
    from app.repositories.garden_catalog import read_shipped_package

    raw, _ = read_shipped_package()
    outputs = {taxon["id"]: taxon for taxon in json.loads(raw)["outputs"]}
    assert set(DOMESTIC_BIRDS) == set(get_args(DomesticBirdKey))
    seen: set[str] = set()
    for bird in DOMESTIC_BIRDS.values():
        assert bird.speciesnet_taxa and not (bird.speciesnet_taxa & seen)
        seen |= bird.speciesnet_taxa
        for taxon_id in bird.speciesnet_taxa:
            assert outputs[taxon_id]["ranks"][0] == "aves"
    names = {outputs[i]["name"] for i in DOMESTIC_BIRDS["chicken"].speciesnet_taxa}
    assert names == {"domestic chicken", "red junglefowl", "gallus species"}
    # Wild-only relatives stay birds even when chicken is declared.
    assert domestic_bird_for_speciesnet("5d6912b0-e62d-4b80-9cb2-6631478bb237") is None  # grey junglefowl


def test_nothing_is_domestic_until_the_owner_declares_it():
    assert normalize_domestic_birds(None) == []
    assert normalize_domestic_birds(["Chicken", "chicken", " quail "]) == ["chicken", "quail"]
    with pytest.raises(ValueError, match="supported domestic birds"):
        normalize_domestic_birds(["pheasant"])
    with pytest.raises(ValueError):
        normalize_domestic_birds("chicken")


def test_bird_model_identity_is_matched_by_catalogue_id_or_exact_scientific_name_only():
    def match(species_id=None, *names):
        return domestic_bird_for_bird_label(
            species_id=species_id, scientific_names=names, species_ids_by_bird=CHICKEN_IDS
        )

    assert match(472) == "chicken"  # Red Junglefowl's catalogue identity
    assert match(None, "gallus  GALLUS") == "chicken"
    assert match(None, "Anser anser domesticus") == "domestic_goose"
    # Loose names, genera and common names never count.
    assert match(None, "chicken") is None
    assert match(None, "Gallus") is None
    assert match(None, "Red Junglefowl") is None
    assert match(999, "Prunella modularis") is None


@pytest.mark.parametrize(
    ("top", "score", "accepted", "declared", "garden", "expected"),
    [
        ("chicken", 0.9, "chicken", ["chicken"], True, "garden"),
        ("chicken", 0.9, "chicken", [], True, "bird_history"),
        ("chicken", 0.9, "chicken", ["turkey"], True, "bird_history"),
        ("chicken", 0.9, "chicken", ["chicken"], False, "bird_history"),
        # A range filter rejected the top result: it is still the owner's chicken.
        ("chicken", 0.9, None, ["chicken"], True, "garden"),
        # A range fallback accepted a declared bird the raw top did not name.
        (None, 0.9, "chicken", ["chicken"], True, "garden"),
        # A top result below the bird threshold proves nothing on its own.
        ("chicken", 0.4, None, ["chicken"], True, "bird_history"),
    ],
)
def test_bird_events_route_declared_domestic_birds_before_any_range_rejection(
    top, score, accepted, declared, garden, expected
):
    assert bird_event_route(top, score, accepted, declared, threshold=0.7, garden_enabled=garden) == expected


@pytest.mark.parametrize(
    ("domestic", "declared", "watches", "expected"),
    [
        ("chicken", ["chicken"], True, "domestic_bird"),
        ("chicken", ["chicken"], False, "domestic_bird"),
        ("chicken", [], True, "bird_camera"),
        ("chicken", [], False, "wild_bird"),
        (None, ["chicken"], True, "bird_camera"),
        (None, ["chicken"], False, "wild_bird"),
    ],
)
def test_garden_checks_keep_declared_domestic_birds_on_any_camera_and_hand_off_the_rest(
    domestic, declared, watches, expected
):
    assert garden_bird_route(domestic, declared, camera_watches_birds=watches) == expected


def test_an_empty_bird_camera_list_watches_every_camera():
    assert camera_watches_birds("greenhouse", [])
    assert camera_watches_birds("greenhouse", ["greenhouse", "feeder"])
    assert not camera_watches_birds("greenhouse", ["feeder"])


@pytest.mark.parametrize(
    ("presence", "route", "naming", "country", "expected"),
    [
        ("animal", "bird_camera", True, True, AutomaticPlan("animal", None, True)),
        ("animal", "bird_camera", False, True, AutomaticPlan("animal", "naming_disabled", False)),
        ("uncertain", "wild_bird", True, True, AutomaticPlan("uncertain", "below_threshold", True)),
        ("uncertain", "wild_bird", True, False, AutomaticPlan("uncertain", "location_required", False)),
        ("bird", "bird_camera", True, True, AutomaticPlan("bird", "bird_camera", False)),
        ("bird", "wild_bird", True, True, AutomaticPlan("bird", "wild_bird", False)),
        ("bird", "domestic_bird", True, True, AutomaticPlan("animal", None, True)),
        ("bird", "domestic_bird", False, True, AutomaticPlan("animal", "naming_disabled", False)),
        ("non_animal", "wild_bird", True, True, AutomaticPlan("non_animal", None, False)),
        ("human_rejected", "domestic_bird", True, True, AutomaticPlan("human_rejected", None, False)),
    ],
)
def test_automatic_plan_treats_a_declared_domestic_bird_as_an_animal(presence, route, naming, country, expected):
    assert plan_automatic_check(presence, route, automatic_naming=naming, country_known=country) == expected


def test_automatic_finish_dismisses_a_species_score_below_the_naming_threshold():
    animal = AutomaticPlan("animal", None, True)
    uncertain = AutomaticPlan("uncertain", "below_threshold", True)
    assert finish_automatic_check(animal, "named", "bird_camera") == ("animal", None)
    assert finish_automatic_check(animal, "person", "bird_camera") == ("human_rejected", None)
    assert finish_automatic_check(animal, "low_confidence", "bird_camera") == ("animal", "below_threshold")
    # A name the catalogue cannot bind waits for a person only when its score would have named it.
    assert finish_automatic_check(animal, "unresolved", "bird_camera", score_below_threshold=False) == (
        "animal",
        "identity_unavailable",
    )
    assert finish_automatic_check(animal, "unresolved", "bird_camera", score_below_threshold=True) == (
        "animal",
        "below_threshold",
    )
    assert finish_automatic_check(uncertain, "bird", "bird_camera") == ("uncertain", "bird_camera")
    assert finish_automatic_check(uncertain, "bird", "wild_bird") == ("uncertain", "wild_bird")
    assert finish_automatic_check(uncertain, "unresolved", "wild_bird") == ("uncertain", "below_threshold")
    # The naming threshold is the owner's floor: an animal scored below it is dismissed, and restorable.
    assert automatic_check_dismisses("animal", "below_threshold")
    assert automatic_check_dismisses("uncertain", "below_threshold")
    assert automatic_check_dismisses("uncertain", "wild_bird")
    assert automatic_check_dismisses("bird", "bird_camera")
    assert automatic_check_dismisses("non_animal", None)
    assert not automatic_check_dismisses("uncertain", "location_required")
    assert not automatic_check_dismisses("animal", "identity_unavailable")
    assert not automatic_check_dismisses("animal", "naming_disabled")


@pytest.mark.parametrize(
    "outcome, reason, score, expected",
    [
        ("animal", "below_threshold", 0.12, True),
        # Saved before unbound low scores counted as below the threshold.
        ("animal", "identity_unavailable", 0.18, True),
        ("animal", "identity_unavailable", 0.93, False),
        ("animal", "identity_unavailable", None, False),
        ("animal", "location_required", 0.12, False),
        ("animal", None, 0.93, False),
        ("uncertain", "below_threshold", 0.4, True),
    ],
)
def test_a_saved_check_dismisses_by_the_current_policy(outcome, reason, score, expected):
    # Only the decision fields matter here; the saved model and photo evidence are not read.
    check = GardenAutomaticCheck.model_construct(
        outcome=outcome,
        checked_at="2026-11-01T19:54:26",
        decision_reason=reason,
        naming_score=score,
        naming_threshold=0.8 if score is not None else None,
    )
    assert saved_check_dismisses(check) is expected


def test_speciesnet_names_a_declared_domestic_bird_wherever_it_is_kept():
    chicken = Taxon(
        "cae9534f-f302-4229-9e11-b91138333d92",
        "domestic chicken",
        ("aves", "galliformes", "phasianidae", "gallus", "gallus domesticus"),
    )
    junglefowl = Taxon(
        "89851bea-765b-431a-bb03-6f821931ebdc",
        "red junglefowl",
        ("aves", "galliformes", "phasianidae", "gallus", "gallus"),
    )
    filler = Taxon("x", "blank", ("", "", "", "", ""))
    # Red junglefowl's wild range excludes Great Britain; a kept chicken is not limited by it.
    geofence = {junglefowl.key: {"allow": {"IND": []}}}

    def decide(taxon, declared):
        return decide_prediction(
            [(taxon, 0.9), (filler, 0.05)],
            GardenPolicy(min_confidence=0.8, domestic_birds=frozenset(declared)),
            country="GBR",
            taxonomy=[],
            geofence=geofence,
        )

    assert decide(chicken, []).reason == "bird_excluded"
    kept = decide(junglefowl, ["chicken"])
    assert kept.reason == "garden" and kept.taxon == junglefowl and not kept.geofenced
    assert decide(junglefowl, ["turkey"]).reason == "bird_excluded"
