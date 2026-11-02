"""A crop that cannot be built is retried less and less often, but never abandoned."""

from datetime import datetime, timedelta

from app.services.garden_crop_service import next_crop_retry

NOW = datetime(2026, 11, 2, 12, 0)


def test_the_first_failure_waits_an_hour():
    assert next_crop_retry(None, NOW) == NOW + timedelta(hours=1)


def test_each_repeated_failure_doubles_the_wait():
    assert next_crop_retry(timedelta(hours=1), NOW) == NOW + timedelta(hours=2)
    assert next_crop_retry(timedelta(hours=8), NOW) == NOW + timedelta(hours=16)


def test_the_wait_settles_at_a_day_and_never_gives_up():
    # A Frigate outage can outlast any fixed number of tries; once a day is quiet and recoverable.
    assert next_crop_retry(timedelta(hours=16), NOW) == NOW + timedelta(hours=24)
    assert next_crop_retry(timedelta(hours=24), NOW) == NOW + timedelta(hours=24)


def test_an_unreadable_previous_wait_starts_again_at_an_hour():
    assert next_crop_retry(timedelta(0), NOW) == NOW + timedelta(hours=1)
    assert next_crop_retry(timedelta(hours=-3), NOW) == NOW + timedelta(hours=1)
