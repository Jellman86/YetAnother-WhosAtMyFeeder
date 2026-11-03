"""Uptime windowing is pure: no database, no clock, no network."""

from datetime import datetime, timedelta, timezone

from app.services.uptime import HEARTBEAT_INTERVAL_MINUTES, build_uptime_window


NOW = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


def _heartbeats(start: datetime, count: int, step_minutes: int = HEARTBEAT_INTERVAL_MINUTES):
    return [start + timedelta(minutes=step_minutes * index) for index in range(count)]


def test_continuous_heartbeats_report_full_uptime():
    samples = _heartbeats(NOW - timedelta(hours=24), 24 * 12 + 1)

    window = build_uptime_window(samples, now=NOW, first_recorded_at=samples[0])

    assert len(window.buckets) == 24
    assert all(bucket.state == "up" for bucket in window.buckets)
    assert window.uptime_ratio == 1.0
    assert window.longest_gap_minutes == 0
    assert window.longest_gap_start is None


def test_a_missing_stretch_marks_those_buckets_down():
    start = NOW - timedelta(hours=24)
    samples = [
        sample
        for sample in _heartbeats(start, 24 * 12 + 1)
        # Two clear hours with nothing recorded.
        if not (start + timedelta(hours=5) <= sample < start + timedelta(hours=7))
    ]

    window = build_uptime_window(samples, now=NOW, first_recorded_at=samples[0])

    down = [bucket for bucket in window.buckets if bucket.state == "down"]
    assert len(down) == 2
    assert window.uptime_ratio < 1.0
    assert window.longest_gap_minutes >= 120
    assert window.longest_gap_start is not None


def test_buckets_before_the_first_ever_sample_are_unknown_not_down():
    # A fresh install has no history; that is not downtime.
    first = NOW - timedelta(hours=3)
    samples = _heartbeats(first, 3 * 12 + 1)

    window = build_uptime_window(samples, now=NOW, first_recorded_at=first)

    assert window.buckets[0].state == "unknown"
    assert all(bucket.state != "down" for bucket in window.buckets)
    # Unknown buckets must not be counted as uptime either.
    assert window.uptime_ratio == 1.0


def test_no_samples_at_all_is_unknown_rather_than_zero_uptime():
    window = build_uptime_window([], now=NOW, first_recorded_at=None)

    assert all(bucket.state == "unknown" for bucket in window.buckets)
    assert window.uptime_ratio is None
    assert window.longest_gap_minutes == 0


def test_samples_outside_the_window_are_ignored():
    old = _heartbeats(NOW - timedelta(days=5), 10)
    recent = _heartbeats(NOW - timedelta(minutes=30), 7)

    window = build_uptime_window(old + recent, now=NOW, first_recorded_at=old[0])

    assert window.buckets[-1].state == "up"
    assert window.buckets[0].state == "down"


def test_naive_timestamps_are_treated_as_utc():
    samples = [sample.replace(tzinfo=None) for sample in _heartbeats(NOW - timedelta(hours=2), 25)]

    window = build_uptime_window(samples, now=NOW, first_recorded_at=samples[0])

    assert window.buckets[-1].state == "up"


def test_window_is_configurable_and_bucket_count_follows():
    samples = _heartbeats(NOW - timedelta(hours=6), 6 * 12 + 1)

    window = build_uptime_window(samples, now=NOW, hours=6, bucket_minutes=30, first_recorded_at=samples[0])

    assert len(window.buckets) == 12
    assert window.bucket_minutes == 30


def test_unsorted_input_does_not_confuse_the_gap_calculation():
    start = NOW - timedelta(hours=4)
    samples = _heartbeats(start, 4 * 12 + 1)
    shuffled = list(reversed(samples))

    ordered_window = build_uptime_window(samples, now=NOW, first_recorded_at=start)
    shuffled_window = build_uptime_window(shuffled, now=NOW, first_recorded_at=start)

    assert ordered_window.longest_gap_minutes == shuffled_window.longest_gap_minutes
