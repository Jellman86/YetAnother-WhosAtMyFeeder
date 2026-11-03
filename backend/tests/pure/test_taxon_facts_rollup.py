"""What the family tree says about each taxon is a pure fold over per-species spans."""

from datetime import datetime

from app.services.taxon_facts import HeardSpan, VisitSpan, combine_species, ordered_members, roll_up

MAR = datetime(2026, 3, 1, 8, 0)
JUN = datetime(2026, 6, 1, 8, 0)
NOV = datetime(2026, 11, 1, 8, 0)


def test_camera_and_garden_visits_add_up_and_keep_the_widest_span() -> None:
    records = combine_species(
        camera={1: VisitSpan(visits=3, first_seen=JUN, last_seen=NOV)},
        garden={1: VisitSpan(visits=2, first_seen=MAR, last_seen=JUN), 2: VisitSpan(1, JUN, JUN)},
        heard={1: HeardSpan(count=40, last_heard=NOV), 3: HeardSpan(count=5, last_heard=MAR)},
    )
    assert records[1].visits == 5
    assert (records[1].first_seen, records[1].last_seen) == (MAR, NOV)
    assert records[1].sources == ("camera", "garden")
    assert records[2].sources == ("garden",)
    # Heard but never seen: a record with no visits, so the tree can still say it was heard.
    assert (records[3].visits, records[3].heard, records[3].first_seen) == (0, 5, None)


def test_a_group_counts_the_species_seen_beneath_it_their_visits_and_the_most_recent_visit() -> None:
    records = combine_species(
        camera={1: VisitSpan(3, JUN, NOV), 2: VisitSpan(7, MAR, JUN)},
        garden={},
        heard={1: HeardSpan(10, NOV), 4: HeardSpan(2, JUN)},
    )
    rolled = roll_up(records, {100: [1, 2, 4], 1: [1], 4: [4]})
    family = rolled[100]
    assert (family.species_seen, family.visits) == (2, 10)
    assert (family.first_seen, family.last_seen) == (MAR, NOV)
    assert (family.heard, family.last_heard) == (12, NOV)
    # The most-seen member first: it illustrates the group.
    assert family.members == (2, 1)
    # A species heard but not seen is not "seen here".
    assert (rolled[4].species_seen, rolled[4].visits, rolled[4].heard) == (0, 0, 2)


def test_a_taxon_with_nothing_beneath_it_is_absent_rather_than_zero() -> None:
    assert roll_up({}, {100: []}) == {}


def test_members_tie_break_on_the_most_recent_visit_then_the_identity() -> None:
    records = combine_species(
        camera={5: VisitSpan(2, MAR, JUN), 6: VisitSpan(2, MAR, NOV), 7: VisitSpan(2, MAR, NOV)}, garden={}, heard={}
    )
    assert ordered_members(records, [5, 6, 7, 99]) == (6, 7, 5)
