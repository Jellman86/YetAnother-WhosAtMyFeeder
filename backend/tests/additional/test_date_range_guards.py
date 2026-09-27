from datetime import date

import pytest
from fastapi import HTTPException


def test_date_range_guard_rejects_ranges_over_365_days():
    from app.routers import events

    with pytest.raises(HTTPException) as exc_info:
        events._enforce_max_date_range(
            start_date=date(2024, 1, 1),
            end_date=date(2025, 1, 2),
        )

    assert exc_info.value.status_code == 400
    assert "365 days" in str(exc_info.value.detail)


def test_date_range_guard_allows_365_day_ranges():
    from app.routers import events

    events._enforce_max_date_range(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
