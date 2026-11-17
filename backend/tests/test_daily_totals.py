"""Daily totals outlive cleanup, never count a capture twice, and honour owner corrections (#949)."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories.daily_totals_repository import DailyTotalsRepository

UTC = timezone.utc
NOW = datetime(2036, 3, 1, 12, 0)


@pytest_asyncio.fixture
async def repo(migrated_history_db):
    async with aiosqlite.connect(migrated_history_db) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        yield DailyTotalsRepository(db)


async def capture(repo, event, at, species="Turdus merula", *, hidden=0, camera="birdcam"):
    await repo.db.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
            frigate_event, camera_name, scientific_name, is_hidden)
        VALUES (?, 0, 0.9, ?, ?, ?, ?, ?, ?)""",
        (at, species, species, event, camera, species, hidden),
    )
    await repo.db.commit()


async def blackbird_day(repo, day="2036-02-10"):
    # Two captures 30 s apart are one visit; two hours later is a second. A hidden capture counts for nothing.
    await capture(repo, "bb-1", f"{day} 08:00:00")
    await capture(repo, "bb-2", f"{day} 08:00:30")
    await capture(repo, "bb-3", f"{day} 10:00:00")
    await capture(repo, "bb-hidden", f"{day} 11:00:00", hidden=1)
    await capture(repo, "gt-1", f"{day} 09:00:00", species="Parus major")


def by_species(totals):
    return {total.scientific_name: (total.capture_count, total.visit_count) for total in totals}


@pytest.mark.asyncio
async def test_cleanup_seals_a_day_from_its_rows_before_any_are_removed(repo):
    await blackbird_day(repo)
    cutoff = datetime(2036, 2, 11, 6, 0)
    assert await repo.seal_before(cutoff, zone=UTC, now=NOW) == 1
    await repo.delete_older_than(cutoff)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}
    assert [total.day for total in await repo.totals()] == [date(2036, 2, 10)] * 2


@pytest.mark.asyncio
async def test_a_later_cleanup_never_reduces_a_sealed_day(repo):
    await blackbird_day(repo)
    cutoff = datetime(2036, 2, 11, 6, 0)
    await repo.seal_before(cutoff, zone=UTC, now=NOW)
    await repo.delete_older_than(cutoff)
    # A capture Frigate replays for the cleaned day, or a backfill, cannot change what was counted.
    await capture(repo, "bb-1", "2036-02-10 08:00:00")
    assert await repo.seal_before(cutoff + timedelta(hours=1), zone=UTC, now=NOW) == 0
    await repo.delete_older_than(cutoff + timedelta(hours=1))
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}


@pytest.mark.asyncio
async def test_days_sealed_before_any_tracked_cleanup_are_not_called_complete(repo):
    await blackbird_day(repo, "2036-02-10")
    await blackbird_day_later(repo)
    await repo.seal_before(datetime(2036, 2, 11, 0, 0), zone=UTC, now=NOW)
    await repo.seal_before(datetime(2036, 2, 12, 0, 0), zone=UTC, now=NOW)
    sealed = await repo.sealed_days()
    # An untracked cleanup may already have removed rows from the first day sealed; not from the next.
    assert {day: seal.complete for day, seal in sealed.items()} == {date(2036, 2, 10): False, date(2036, 2, 11): True}


async def blackbird_day_later(repo):
    await capture(repo, "later-1", "2036-02-11 07:00:00")


@pytest.mark.asyncio
async def test_a_day_is_the_instance_local_day(repo):
    berlin = ZoneInfo("Europe/Berlin")
    # 23:30 UTC on the 10th is 00:30 on the 11th in Berlin.
    await capture(repo, "late", "2036-02-10 23:30:00")
    await capture(repo, "early", "2036-02-10 22:30:00")
    await repo.seal_before(datetime(2036, 2, 11, 6, 0), zone=berlin, now=NOW)
    totals = await repo.totals()
    assert {(total.day, total.capture_count) for total in totals} == {(date(2036, 2, 10), 1), (date(2036, 2, 11), 1)}


@pytest.mark.asyncio
async def test_a_visit_across_midnight_counts_once_on_the_day_it_opened(repo):
    await capture(repo, "night-1", "2036-02-10 23:59:40")
    await capture(repo, "night-2", "2036-02-11 00:00:10")
    await repo.seal_before(datetime(2036, 2, 12, 6, 0), zone=UTC, now=NOW)
    totals = {total.day: (total.capture_count, total.visit_count) for total in await repo.totals()}
    assert totals == {date(2036, 2, 10): (1, 1), date(2036, 2, 11): (1, 0)}


@pytest.mark.asyncio
async def test_an_owner_correction_on_a_live_day_is_not_frozen(repo):
    await blackbird_day(repo)
    # Hidden before cleanup reaches the day: the correction is in the sealed totals.
    await repo.db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = 'gt-1'")
    await repo.db.commit()
    await repo.seal_before(datetime(2036, 2, 11, 6, 0), zone=UTC, now=NOW)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2)}


@pytest.mark.asyncio
async def test_frigate_losing_an_event_seals_its_day_first(repo):
    await blackbird_day(repo)
    assert await repo.seal_days_of_events(["bb-3"], zone=UTC, now=NOW) == 1
    await repo.delete_by_frigate_event("bb-3")
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}


@pytest.mark.asyncio
async def test_today_is_never_sealed_while_it_is_still_being_recorded(repo):
    await capture(repo, "today-1", "2036-03-01 08:00:00")
    assert await repo.seal_days_of_events(["today-1"], zone=UTC, now=NOW) == 0
    assert await repo.sealed_days() == {}


@pytest.mark.asyncio
async def test_totals_can_be_read_for_one_species_by_any_of_its_names(repo):
    await blackbird_day(repo)
    await repo.seal_before(datetime(2036, 2, 11, 6, 0), zone=UTC, now=NOW)
    assert by_species(await repo.totals(species_names=["turdus MERULA"])) == {"Turdus merula": (3, 2)}
    assert await repo.totals(species_names=["Erithacus rubecula"]) == []
    assert await repo.totals(date(2036, 2, 11), None) == []


@pytest.mark.asyncio
async def test_deleting_all_history_deletes_the_totals_too(repo):
    await blackbird_day(repo)
    await repo.seal_before(datetime(2036, 2, 11, 6, 0), zone=UTC, now=NOW)
    deleted, _counted = await repo.delete_all_if_count_is(None)
    assert deleted == 5
    assert await repo.totals() == []
    assert await repo.sealed_days() == {}


@pytest.mark.asyncio
async def test_the_frigate_missing_delete_policy_keeps_the_past_days_count(repo, monkeypatch):
    from unittest.mock import AsyncMock

    from app.config import settings
    from app.services import frigate_missing_policy

    await blackbird_day(repo)
    monkeypatch.setattr(settings.maintenance, "frigate_missing_behavior", "delete")
    monkeypatch.setattr(frigate_missing_policy.media_cache, "delete_cached_media", AsyncMock())
    monkeypatch.setenv("TZ", "UTC")
    result = await frigate_missing_policy.apply_missing_policy(
        repo=repo, frigate_event="bb-3", error="not_found", source="test", media_kind="snapshot", checked_at=NOW
    )
    assert result["deleted_count"] == 1
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}
