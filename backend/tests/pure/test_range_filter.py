"""The range rule's decisions, with no database, network or model (#696)."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.services.range_filter import (
    MAX_LIST_AGE,
    HotspotRegion,
    RangeCandidate,
    RangeList,
    choose_regions,
    county_list_too_short,
    decide_range_admission,
    filter_state,
    location_key,
    location_precision,
    refresh_due,
    species_verdict,
    validate_range_list,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
ROBIN, JAY, BLACKBIRD, HOUSE_FINCH, MAMMAL = 1, 2, 3, 4, 99
LOCATION = "geo:38.30,-122.70"


def california(**overrides) -> RangeList:
    base = RangeList(
        source="ebird",
        region_code="US-CA-097",
        region_codes=("US-CA-097",),
        region_name="Sonoma County, California, US",
        region_level="county",
        location_key=LOCATION,
        fetched_at=NOW - timedelta(days=2),
        region_species_total=3,
        in_range=frozenset({ROBIN, JAY, HOUSE_FINCH}),
        known=frozenset({ROBIN, JAY, BLACKBIRD, HOUSE_FINCH}),
    )
    return replace(base, **overrides)


def candidate(species_id, score, *, admissible=True, label=None):
    return RangeCandidate(
        label=label or f"species-{species_id}", score=score, species_id=species_id, admissible=admissible
    )


def test_an_in_range_top_prediction_is_kept():
    decision = decide_range_admission([candidate(ROBIN, 0.9)], active_list=california(), threshold=0.7)

    assert decision.outcome == "in_range"
    assert decision.chosen_index == 0


def test_an_out_of_range_top_prediction_falls_back_to_the_best_in_range_candidate_above_threshold():
    candidates = [candidate(BLACKBIRD, 0.91), candidate(MAMMAL, 0.85), candidate(JAY, 0.78), candidate(ROBIN, 0.75)]

    decision = decide_range_admission(candidates, active_list=california(), threshold=0.7)

    assert decision.outcome == "fallback"
    assert decision.chosen_index == 2
    assert decision.original == candidates[0]


def test_an_out_of_range_prediction_with_no_in_range_candidate_above_threshold_is_skipped():
    candidates = [candidate(BLACKBIRD, 0.91), candidate(JAY, 0.4)]

    decision = decide_range_admission(candidates, active_list=california(), threshold=0.7)

    assert decision.outcome == "skipped"
    assert decision.chosen_index is None
    assert decision.reason == "out_of_range"


def test_a_fallback_never_resurrects_a_candidate_another_rule_refused():
    candidates = [candidate(BLACKBIRD, 0.91), candidate(JAY, 0.8, admissible=False)]

    assert decide_range_admission(candidates, active_list=california(), threshold=0.7).outcome == "skipped"


def test_an_unidentifiable_alternative_is_not_a_safe_substitute():
    candidates = [candidate(BLACKBIRD, 0.91), candidate(None, 0.88)]

    assert decide_range_admission(candidates, active_list=california(), threshold=0.7).outcome == "skipped"


@pytest.mark.parametrize("species_id", [None, MAMMAL])
def test_a_label_that_cannot_be_matched_to_ebird_is_never_filtered(species_id):
    decision = decide_range_admission([candidate(species_id, 0.95)], active_list=california(), threshold=0.7)

    assert decision.outcome == "not_filtered"
    assert decision.reason == "unmapped"


def test_without_an_active_list_nothing_is_filtered():
    decision = decide_range_admission([candidate(BLACKBIRD, 0.95)], active_list=None, threshold=0.7)

    assert decision.outcome == "not_filtered"
    assert decision.reason == "inactive"


def test_an_owner_confirmed_species_is_never_filtered():
    decision = decide_range_admission(
        [candidate(BLACKBIRD, 0.95)], active_list=california(), threshold=0.7, owner_confirmed=True
    )

    assert decision.outcome == "not_filtered"
    assert decision.reason == "owner_confirmed"


def test_birdnet_presence_evidence_puts_a_species_in_range_but_cannot_remove_one():
    heard_here = california(heard=frozenset({BLACKBIRD}))

    assert species_verdict(heard_here, BLACKBIRD) == "in_range"
    assert species_verdict(california(heard=frozenset()), ROBIN) == "in_range"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"region_code": "not a region"}, "invalid_region"),
        ({"fetched_at": NOW + timedelta(days=1)}, "future_timestamp"),
        ({"in_range": frozenset(), "region_species_total": 0}, "empty_list"),
        ({"region_species_total": 40000}, "too_large"),
        ({"in_range": frozenset({ROBIN, 1234})}, "inconsistent"),
        ({"region_species_total": 400}, "poorly_mapped"),
    ],
)
def test_a_cached_list_is_validated_before_it_may_filter(change, problem):
    assert validate_range_list(california(**change), now=NOW) == problem
    state = filter_state(
        enabled=True,
        precision="exact",
        ebird_configured=True,
        range_list=california(**change),
        current_location_key=LOCATION,
        now=NOW,
        last_error=None,
    )
    assert (state.filtering, state.reason, state.problem) == (False, "list_unusable", problem)


def test_a_valid_list_passes_validation():
    assert validate_range_list(california(), now=NOW) is None


def state(**overrides):
    values = dict(
        enabled=True,
        precision="exact",
        ebird_configured=True,
        range_list=california(),
        current_location_key=LOCATION,
        now=NOW,
        last_error=None,
    )
    values.update(overrides)
    return filter_state(**values)


def test_filtering_is_active_only_when_switched_on_with_a_fresh_list_for_this_place():
    assert (state().filtering, state().reason) == (True, "active")
    assert (state(enabled=False).filtering, state(enabled=False).reason) == (False, "ready")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"precision": "none"}, "needs_location"),
        ({"ebird_configured": False}, "needs_ebird_key"),
        ({"range_list": None}, "waiting_for_list"),
        ({"range_list": None, "last_error": "ebird_unreachable"}, "lookup_failed"),
        ({"current_location_key": "geo:51.30,0.50"}, "location_changed"),
        ({"range_list": california(fetched_at=NOW - MAX_LIST_AGE - timedelta(hours=1))}, "list_stale"),
    ],
)
def test_every_fail_open_case_names_why_nothing_is_filtered(overrides, reason):
    result = state(**overrides)

    assert result.filtering is False
    assert result.reason == reason


def test_location_precision_reflects_how_finely_the_feeder_is_placed():
    assert location_precision(38.3121, -122.7044, "US") == "exact"
    assert location_precision(38.3, -122.7, "US") == "approximate"
    assert location_precision(None, None, "US") == "country_only"
    assert location_precision(None, None, None) == "none"


def test_location_key_ignores_moves_within_a_garden_and_names_country_only_locations():
    assert location_key("exact", 38.31211, -122.70442, None) == location_key("exact", 38.31249, -122.70401, None)
    assert location_key("country_only", None, None, "GB") == "country:GB"
    assert location_key("none", None, None, None) == "none"


def hotspot(county, distance, state="US-CA", country="US"):
    return HotspotRegion(country=country, state=state, county=county, distance_km=distance)


def test_an_exact_location_uses_its_county_and_any_neighbour_within_reach():
    chosen = choose_regions(
        preferred_level="county",
        precision="exact",
        hotspots=[hotspot("US-CA-041", 7.5), hotspot("US-CA-097", 1.2), hotspot("US-CA-055", 25.0)],
        country_code="US",
    )

    assert chosen == ("county", ("US-CA-097", "US-CA-041"))


def test_an_approximate_location_never_claims_a_county():
    chosen = choose_regions(
        preferred_level="county", precision="approximate", hotspots=[hotspot("US-CA-097", 1.0)], country_code="US"
    )

    assert chosen == ("state", ("US-CA",))


def test_a_country_only_location_uses_the_country_list():
    assert choose_regions(preferred_level="county", precision="country_only", hotspots=[], country_code="GB") == (
        "country",
        ("GB",),
    )


def test_a_failed_hotspot_lookup_falls_back_to_a_configured_country_or_nothing():
    assert choose_regions(preferred_level="state", precision="exact", hotspots=[], country_code="US") == (
        "country",
        ("US",),
    )
    assert choose_regions(preferred_level="state", precision="exact", hotspots=[], country_code=None) is None
    assert choose_regions(preferred_level="state", precision="none", hotspots=[], country_code="US") is None


def test_a_region_without_counties_uses_its_state():
    chosen = choose_regions(
        preferred_level="county", precision="exact", hotspots=[hotspot(None, 0.5, state="GB-ENG")], country_code="GB"
    )

    assert chosen == ("state", ("GB-ENG",))


def test_an_under_birded_county_is_recognised():
    assert county_list_too_short(40) is True
    assert county_list_too_short(412) is False


def test_refresh_is_weekly_immediate_on_a_move_and_backs_off_after_a_failure():
    fresh = california()
    assert refresh_due(None, now=NOW, current_location_key=LOCATION, last_failure_at=None) is True
    assert refresh_due(fresh, now=NOW, current_location_key=LOCATION, last_failure_at=None) is False
    assert refresh_due(fresh, now=NOW + timedelta(days=6), current_location_key=LOCATION, last_failure_at=None) is True
    assert refresh_due(fresh, now=NOW, current_location_key="geo:0.00,0.00", last_failure_at=None) is True
    assert refresh_due(None, now=NOW, current_location_key=LOCATION, last_failure_at=NOW - timedelta(hours=1)) is False
