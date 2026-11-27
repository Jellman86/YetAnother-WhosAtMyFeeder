"""A window's visits and species rows come from one set of captures and count each visit once (#1096)."""

from datetime import datetime, timedelta

import pytest

from app.services.window_visits import VisitMember, summarize_window_visits

START = datetime(2035, 6, 14, 17, 0)


def _member(
    event: str,
    minutes: float,
    display: str | None,
    *,
    visit: str,
    number: int = 1,
    position: int = 1,
    species_key: str | None = "species:42",
    category: str | None = None,
    camera: str = "birdcam",
) -> VisitMember:
    return VisitMember(
        id=int(minutes * 100),
        at=START + timedelta(minutes=minutes),
        camera=camera,
        frigate_event=event,
        display_name=display,
        category_name=display if category is None else category,
        scientific_name="Erithacus rubecula",
        common_name="European Robin",
        taxa_id=None,
        visit_key=(visit, camera, number),
        visit_position=position,
        species_key=species_key,
    )


def _rows(summary) -> dict[str, tuple[int, int, str]]:
    return {row["species"]: (row["visit_count"], row["count"], row["latest_event"]) for row in summary.rows}


@pytest.mark.parametrize("unknown_minutes", [0, 20], ids=["unknown-earlier", "unknown-later"])
def test_an_unknown_visit_that_kept_a_species_key_is_counted_once_and_only_as_unknown(unknown_minutes):
    members = [
        _member("robin-1", 5, "European Robin", visit="species:42", number=1),
        _member("robin-2", 6, "European Robin", visit="species:42", number=1, position=2),
        _member("robin-3", 15, "European Robin", visit="species:42", number=2),
        _member("unknown", unknown_minutes, "Unknown Bird", visit="event:unknown"),
    ]

    summary = summarize_window_visits(members)

    assert len(summary.visits) == 3
    assert [visit.unknown for visit in summary.visits].count(True) == 1
    assert _rows(summary) == {"European Robin": (2, 3, "robin-3"), "Unknown Bird": (1, 1, "unknown")}
    assert sum(row["visit_count"] for row in summary.rows) == len(summary.visits)


@pytest.mark.parametrize(
    ("display", "category"),
    [("European Robin", "Unknown Bird"), ("", "Unknown Bird"), (None, None), ("Great tit and allies", None)],
    ids=["unknown-category", "blank-display", "no-labels", "group-label"],
)
def test_a_visit_is_unknown_when_its_first_capture_is_shown_as_unknown_bird(display, category):
    summary = summarize_window_visits([_member("legacy", 0, display, visit="legacy", category=category)])

    assert [visit.unknown for visit in summary.visits] == [True]
    assert _rows(summary) == {"Unknown Bird": (1, 1, "legacy")}


def test_a_visit_follows_its_first_capture_whatever_its_later_captures_are_called():
    # A visit opened by a capture shown as Unknown bird stays one Unknown visit with all its captures;
    # its later named capture is not split off into the robin's row.
    members = [
        _member("first", 0, "European Robin", visit="v", category="Unknown Bird"),
        _member("second", 0.5, "European Robin", visit="v", position=2),
    ]

    summary = summarize_window_visits(members)

    assert _rows(summary) == {"Unknown Bird": (1, 2, "second")}


def test_visits_are_listed_in_the_order_they_opened_with_their_cameras():
    members = [
        _member("late", 30, "European Robin", visit="a", camera="patiocam"),
        _member("early", 1, "Unknown Bird", visit="b"),
        _member("early-2", 2, "Unknown Bird", visit="b", position=2),
    ]

    summary = summarize_window_visits(members)

    assert [(visit.camera, visit.opened_at, visit.unknown) for visit in summary.visits] == [
        ("birdcam", START + timedelta(minutes=1), True),
        ("patiocam", START + timedelta(minutes=30), False),
    ]


def test_an_empty_window_has_no_visits_and_no_rows():
    summary = summarize_window_visits([])

    assert summary.visits == []
    assert summary.rows == []


def test_a_named_visit_is_named_by_its_newest_named_capture_never_a_group_label():
    members = [
        _member("tit", 0, "Great Tit", visit="species:13"),
        _member("group", 0.25, "Great tit and allies", visit="species:13", position=2),
    ]

    summary = summarize_window_visits(members)

    [row] = summary.rows
    assert (row["species"], row["visit_count"], row["count"], row["latest_event"]) == ("Great Tit", 1, 2, "group")


def test_named_captures_keep_their_catalogue_buckets_whatever_visit_they_share():
    # Visit attribution follows the resolved identity; species rows keep one bucket per catalogue
    # key, as before, and the alias merge after this decides whether they are one bird.
    members = [
        _member("name-only", 0, "Robin", visit="species:42", species_key="name:erithacus rubecula"),
        _member("full", 0.25, "European Robin", visit="species:42", position=2, species_key="species:42"),
    ]

    summary = summarize_window_visits(members)

    assert _rows(summary) == {"Robin": (1, 1, "name-only"), "European Robin": (0, 1, "full")}


def test_rows_come_in_descending_captures_with_ties_by_key():
    members = [
        _member("b-1", 0, "B", visit="species:2", species_key="species:2"),
        _member("a-1", 1, "A", visit="species:1", species_key="species:1"),
        _member("c-1", 2, "C", visit="species:3", species_key="species:3"),
        _member("c-2", 3, "C", visit="species:3", number=2, species_key="species:3"),
    ]

    summary = summarize_window_visits(members)

    assert [row["species"] for row in summary.species] == ["C", "A", "B"]
