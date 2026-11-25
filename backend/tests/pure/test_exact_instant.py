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
