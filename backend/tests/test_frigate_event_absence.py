"""Remembering that Frigate no longer has an event.

Frigate's retention is shorter than YA-WAMF's history, so an old detection's
event is gone upstream permanently. The events list checks media availability
for every row it returns, which meant re-asking Frigate for the same absent
events on every page load and logging a warning each time: 958 warnings in 22
hours from 29 events on the reference deployment, for a condition that is
expected and unactionable.

This remembers an absence for a short window so the list path can answer from
memory, and so the fact is logged once per window rather than once per render.
"""

import pytest

from app.services.frigate_event_absence import FrigateEventAbsence


@pytest.fixture
def clock():
    class Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    return Clock()


def test_the_first_sighting_of_an_absence_is_worth_logging(clock):
    absence = FrigateEventAbsence(ttl_seconds=60.0, clock=clock)
    assert absence.record_absent("evt-1") is True


def test_repeat_sightings_within_the_window_are_not_worth_logging(clock):
    absence = FrigateEventAbsence(ttl_seconds=60.0, clock=clock)
    absence.record_absent("evt-1")
    assert absence.record_absent("evt-1") is False
    assert absence.record_absent("evt-1") is False


def test_the_absence_is_worth_logging_again_once_the_window_passes(clock):
    absence = FrigateEventAbsence(ttl_seconds=60.0, clock=clock)
    absence.record_absent("evt-1")
    clock.advance(61.0)
    assert absence.record_absent("evt-1") is True


def test_reporting_starts_afresh_after_frigate_answers_again(clock):
    absence = FrigateEventAbsence(ttl_seconds=60.0, clock=clock)
    absence.record_absent("evt-1")
    absence.record_present("evt-1")
    assert absence.record_absent("evt-1") is True


def test_memory_is_bounded_so_a_long_history_cannot_grow_without_limit(clock):
    absence = FrigateEventAbsence(ttl_seconds=60.0, clock=clock, max_entries=10)
    for index in range(50):
        absence.record_absent(f"evt-{index}")
    assert absence.tracked_count <= 10


def test_a_zero_ttl_reports_every_time_rather_than_silencing_everything(clock):
    absence = FrigateEventAbsence(ttl_seconds=0.0, clock=clock)
    assert absence.record_absent("evt-1") is True
    assert absence.record_absent("evt-1") is True


def test_expired_entries_are_reclaimed_rather_than_retained(clock):
    absence = FrigateEventAbsence(ttl_seconds=60.0, clock=clock)
    for index in range(5):
        absence.record_absent(f"evt-{index}")
    clock.advance(61.0)
    absence.record_absent("evt-fresh")
    assert absence.tracked_count == 1


@pytest.mark.asyncio
async def test_the_events_list_reports_a_gone_event_once_not_once_per_render(monkeypatch, caplog):
    """The reported defect: a warning per absent row, per page load."""
    import logging
    from unittest.mock import AsyncMock

    from app.routers import events as events_router
    from app.services.frigate_event_absence import FrigateEventAbsence

    monkeypatch.setattr(events_router, "frigate_event_absence", FrigateEventAbsence(ttl_seconds=300.0))
    lookup = AsyncMock(return_value=(None, "event_not_found"))
    monkeypatch.setattr(events_router.frigate_client, "get_event_with_error", lookup)

    with caplog.at_level(logging.INFO):
        for _ in range(5):
            result = await events_router.batch_check_clips(["evt-gone"])

    # Frigate stays the source of truth, so it is still asked every time.
    assert lookup.await_count == 5
    mentions = [r for r in caplog.records if "evt-gone" in str(getattr(r, "event_id", ""))]
    assert len(mentions) <= 1, "an expected absence must not be reported on every render"
    assert result["evt-gone"]["has_frigate_event"] is False


@pytest.mark.asyncio
async def test_an_event_frigate_still_has_is_reported_present(monkeypatch):
    from unittest.mock import AsyncMock

    from app.routers import events as events_router
    from app.services.frigate_event_absence import FrigateEventAbsence

    monkeypatch.setattr(events_router, "frigate_event_absence", FrigateEventAbsence(ttl_seconds=300.0))
    lookup = AsyncMock(return_value=({"has_clip": True, "has_snapshot": True}, None))
    monkeypatch.setattr(events_router.frigate_client, "get_event_with_error", lookup)

    await events_router.batch_check_clips(["evt-live"])
    result = await events_router.batch_check_clips(["evt-live"])

    assert lookup.await_count == 2
    assert result["evt-live"]["has_frigate_event"] is True
    assert result["evt-live"]["has_clip"] is True


@pytest.mark.asyncio
async def test_a_restored_event_is_reported_present_immediately(monkeypatch):
    """No stale memory: a 404 during a Frigate restart must not linger."""
    from unittest.mock import AsyncMock

    from app.routers import events as events_router
    from app.services.frigate_event_absence import FrigateEventAbsence

    monkeypatch.setattr(events_router, "frigate_event_absence", FrigateEventAbsence(ttl_seconds=300.0))
    lookup = AsyncMock(return_value=(None, "event_not_found"))
    monkeypatch.setattr(events_router.frigate_client, "get_event_with_error", lookup)
    absent = await events_router.batch_check_clips(["evt-back"])
    assert absent["evt-back"]["has_frigate_event"] is False

    lookup.return_value = ({"has_clip": True, "has_snapshot": True}, None)
    restored = await events_router.batch_check_clips(["evt-back"])
    assert restored["evt-back"]["has_frigate_event"] is True
