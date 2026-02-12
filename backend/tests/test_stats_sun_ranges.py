from app.routers.stats import _format_clock_range


def test_format_clock_range_orders_by_local_clock_time():
    values = [
        "2026-01-31T08:13",
        "2026-02-12T07:28",
        "2026-02-04T07:41",
    ]
    assert _format_clock_range(values) == "07:28–08:13"


def test_format_clock_range_handles_utc_suffix():
    values = [
        "2026-02-01T17:10:00Z",
        "2026-02-02T16:56:00Z",
    ]
    assert _format_clock_range(values) == "16:56–17:10"


def test_format_clock_range_single_value():
    assert _format_clock_range(["2026-02-12T07:30"]) == "07:30"


def test_format_clock_range_invalid_values():
    assert _format_clock_range(["bad-value", ""]) is None
