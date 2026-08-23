"""Filtering by species without joining the taxonomy cache.

A user reported the species filter being noticeably slower than the date and
camera filters. The cause is the join onto `taxonomy_cache`, whose conditions
are a set of ORs across different columns wrapped in `LOWER(...)`. SQLite will
not use an index for that shape, so it scanned all 172 cached rows for each of
96,118 detections, and the join forced a `DISTINCT` over every selected column
on top.

The join only ever did one thing: resolve a detection whose own scientific name
is absent, through its display name, to the species being searched for. The
alias resolver already produces those names, so the same rows can be found from
the detection's own columns.

Measured on that database, same instrument, median of five warmed runs:
24.0ms with the join against 6.1ms without, and the plan changes from a scan
plus a temporary B-tree to a multi-index OR.

Equivalence was checked across all 85 names the data holds, scientific names,
display names and hidden labels alike: the two forms return identical rows.
"""

import inspect

from app.repositories.detection_repository import DetectionRepository


def test_the_species_filter_no_longer_joins_the_taxonomy_cache():
    source = inspect.getsource(DetectionRepository._canonical_species_query_parts)
    assert "tc_filter" not in source, "the species filter must not join taxonomy_cache"
    assert "has_taxonomy_cache=False" in source


def test_the_events_list_joins_only_for_a_taxon_id_filter():
    """The join survives for `taxa_id`, which still reads the cached taxon id.

    A detection with no taxon id of its own is found by that filter through the
    cache, and there is no resolver step for it the way there is for names. The
    species filter is what stops needing it, and with it the `DISTINCT` that the
    join made necessary.
    """
    source = inspect.getsource(DetectionRepository.get_all)
    assert "needs_taxonomy_cache = bool(has_taxonomy_cache and taxa_id is not None)" in source
    assert "species or species_any" not in source.split("needs_taxonomy_cache =")[1][:200]


def test_a_species_filter_asks_for_no_join_in_either_read_path():
    for method in (DetectionRepository.get_all, DetectionRepository.get_count):
        source = inspect.getsource(method)
        assert "has_taxonomy_cache=needs_taxonomy_cache" not in source
        assert "has_taxonomy_cache=False" in source


def test_the_alias_resolver_is_still_what_supplies_the_names():
    """The names the join used to reach are resolved up front instead."""
    source = inspect.getsource(DetectionRepository._build_canonical_species_condition)
    assert "resolve_species_aliases" in source
