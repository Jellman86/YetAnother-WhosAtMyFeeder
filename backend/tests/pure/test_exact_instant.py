"""An exact time on a history read names its offset, so no clock is guessed (#1098)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.api_datetime import parse_exact_instant


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2034-03-10T12:00:00Z", datetime(2034, 3, 10, 12, tzinfo=timezone.utc)),
        ("2034-03-10T12:00Z", datetime(2034, 3, 10, 12, tzinfo=timezone.utc)),
        ("2034-03-10T13:00:00+01:00", datetime(2034, 3, 10, 12, tzinfo=timezone.utc)),
        ("2034-03-10T12:00:00.000001-00:00", datetime(2034, 3, 10, 12, 0, 0, 1, tzinfo=timezone.utc)),
        ("2034-03-10T12:00:00.25Z", datetime(2034, 3, 10, 12, 0, 0, 250000, tzinfo=timezone.utc)),
    ],
)
def test_a_date_and_time_with_an_offset_is_one_instant(value, expected):
    assert parse_exact_instant(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "2034-03-10",
        "2034-03-10T12:00:00",
        "1773144000",
        "2034-03-10 12:00:00Z",
        "2034-03-10T12:00:00+0100",
        "2034-03-10T12:00:00.1234567Z",
        "2034-02-30T12:00:00Z",
        "2034-03-10T12:00:00Z junk",
        "2034-03-10T12:00:00+01:60",
        "2034-03-10T12:00:00+24:00",
        "2034-03-10T12:00:00-99:00",
        "2034-03-10T24:00:00Z",
        "2034-03-10T12:60:00Z",
        "2034-03-10T12:00:60Z",
        "0001-01-01T00:00:00+05:00",
        "9999-12-31T23:59:59-05:00",
        "",
        1773144000,
        None,
    ],
)
def test_anything_less_is_refused(value):
    with pytest.raises(ValueError):
        parse_exact_instant(value)


def test_an_aware_datetime_passes_and_a_naive_one_is_refused():
    aware = datetime(2034, 3, 10, 12, tzinfo=timezone(timedelta(hours=2)))
    assert parse_exact_instant(aware) is aware
    with pytest.raises(ValueError):
        parse_exact_instant(datetime(2034, 3, 10, 12))


@pytest.mark.parametrize(
    "value", ["0001-01-01T05:00:00+05:00", "9999-12-31T18:59:59-05:00", "2034-03-10T12:00:00+23:59"]
)
def test_an_instant_at_the_edge_of_the_calendar_is_kept_when_it_has_a_utc_time(value):
    assert parse_exact_instant(value).astimezone(timezone.utc).tzinfo == timezone.utc


def test_an_aware_datetime_with_no_utc_time_is_refused():
    with pytest.raises(ValueError):
        parse_exact_instant(datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5))))
