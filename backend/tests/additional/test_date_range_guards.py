"""The end day may be at most 365 days after the start day: up to 366 calendar days, both inclusive.

That holds a whole calendar year, leap years included, which an owner can ask for with a custom range.
"""

from datetime import date

import pytest
from fastapi import HTTPException


def test_date_range_guard_rejects_an_end_day_more_than_365_days_after_the_start():
    from app.routers import events

    with pytest.raises(HTTPException) as exc_info:
        events._enforce_max_date_range(start_date=date(2024, 1, 1), end_date=date(2025, 1, 1))

    assert exc_info.value.status_code == 400
    assert "365 days" in str(exc_info.value.detail)


def test_date_range_guard_allows_a_whole_leap_year():
    from app.routers import events

    events._enforce_max_date_range(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))


def test_date_range_guard_allows_a_year_ago_today_to_today_outside_a_leap_day():
    from app.routers import events

    events._enforce_max_date_range(start_date=date(2025, 3, 1), end_date=date(2026, 3, 1))
