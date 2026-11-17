"""Daily totals outlive cleanup, never count a capture twice, and honour owner corrections (#949)."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories import daily_totals_repository
from app.repositories.daily_totals_repository import DailyTotalsRepository

UTC = timezone.utc
NOW = datetime(2036, 3, 1, 12, 0)
CUTOFF = datetime(2036, 2, 11, 6, 0)


@pytest_asyncio.fixture
async def repo(migrated_history_db):
    async with aiosqlite.connect(migrated_history_db) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        yield DailyTotalsRepository(db)


async def capture(repo, event, at, species="Turdus merula", *, hidden=0, species_id=None, display=None):
    cursor = await repo.db.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
            frigate_event, camera_name, scientific_name, is_hidden, species_id)
        VALUES (?, 0, 0.9, ?, ?, ?, 'birdcam', ?, ?, ?)""",
        (at, display or species, display or species, event, species, hidden, species_id),
    )
    await repo.db.commit()
    return cursor.lastrowid


async def favourite(repo, event):
    await repo.db.execute(
        "INSERT INTO detection_favorites (detection_id) SELECT id FROM detections WHERE frigate_event = ?", (event,)
    )
    await repo.db.commit()


async def tracking_started(repo, at: str):
    await repo.db.execute("UPDATE daily_totals_tracking SET started_at = ?", (at,))
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


async def stored(repo) -> set[str]:
    async with repo.db.execute("SELECT frigate_event FROM detections") as cursor:
        return {row[0] for row in await cursor.fetchall()}


@pytest.mark.asyncio
async def test_age_cleanup_seals_each_day_from_its_rows_then_deletes_them(repo):
    await blackbird_day(repo)
    assert await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW) == 5
    assert await stored(repo) == set()
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}
    assert [total.day for total in await repo.totals()] == [date(2036, 2, 10)] * 2


@pytest.mark.asyncio
async def test_age_cleanup_keeps_favourites_and_the_species_floor_inside_the_sealed_total(repo):
    await blackbird_day(repo)
    await favourite(repo, "bb-1")
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW, preserve_favorites=True, species_floor=1)
    # The favourite and the newest Great Tit stay stored, and the day still counts each capture once.
    assert {"bb-1", "gt-1"} <= await stored(repo)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}


@pytest.mark.asyncio
async def test_age_cleanup_deletes_nothing_when_it_cannot_seal(repo, monkeypatch):
    await blackbird_day(repo)

    async def broken(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(repo, "_write_day_totals", broken)
    with pytest.raises(RuntimeError):
        await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    assert len(await stored(repo)) == 5
    assert await repo.sealed_days() == {}


@pytest.mark.asyncio
async def test_a_later_cleanup_never_reduces_a_sealed_day(repo):
    await blackbird_day(repo)
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    # A capture Frigate replays for the cleaned day, or a backfill, cannot change what was counted.
    await capture(repo, "bb-1", "2036-02-10 08:00:00")
    await repo.seal_and_delete_older_than(CUTOFF + timedelta(hours=1), zone=UTC, now=NOW)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}


@pytest.mark.asyncio
async def test_a_day_is_complete_only_when_it_began_after_tracking_started(repo):
    # Frigate-missing deletes before the upgrade may already have thinned any older day, so only a
    # day that began after the upgrade can be called whole, however many cleanups have run since.
    await tracking_started(repo, "2036-02-10 12:00:00")
    await blackbird_day(repo, "2036-02-09")
    await capture(repo, "mid", "2036-02-10 15:00:00")
    await capture(repo, "after", "2036-02-11 07:00:00")
    await repo.seal_and_delete_older_than(datetime(2036, 2, 10, 0, 0), zone=UTC, now=NOW)
    await repo.seal_and_delete_older_than(datetime(2036, 2, 12, 0, 0), zone=UTC, now=NOW)
    sealed = await repo.sealed_days()
    assert {day: seal.complete for day, seal in sealed.items()} == {
        date(2036, 2, 9): False,
        date(2036, 2, 10): False,
        date(2036, 2, 11): True,
    }


@pytest.mark.asyncio
async def test_a_day_is_the_instance_local_day(repo):
    berlin = ZoneInfo("Europe/Berlin")
    # 23:30 UTC on the 10th is 00:30 on the 11th in Berlin.
    await capture(repo, "late", "2036-02-10 23:30:00")
    await capture(repo, "early", "2036-02-10 22:30:00")
    await repo.seal_and_delete_older_than(datetime(2036, 2, 11, 6, 0), zone=berlin, now=NOW)
    totals = await repo.totals()
    assert {(total.day, total.capture_count) for total in totals} == {(date(2036, 2, 10), 1), (date(2036, 2, 11), 1)}


@pytest.mark.asyncio
async def test_a_half_hour_zone_seals_by_its_own_midnight(repo):
    kolkata = ZoneInfo("Asia/Kolkata")  # UTC+05:30
    await capture(repo, "before-midnight", "2036-02-10 18:15:00")  # 23:45 on the 10th
    await capture(repo, "after-midnight", "2036-02-10 18:45:00")  # 00:15 on the 11th
    await repo.seal_and_delete_older_than(datetime(2036, 2, 10, 18, 40), zone=kolkata, now=NOW)
    # Only the 10th had a capture before the cutoff; the 11th is still live and its capture stored.
    assert {(total.day, total.capture_count) for total in await repo.totals()} == {(date(2036, 2, 10), 1)}
    assert set(await repo.sealed_days()) == {date(2036, 2, 10)}
    assert await stored(repo) == {"after-midnight"}


@pytest.mark.asyncio
async def test_a_visit_across_midnight_counts_once_on_the_day_it_opened(repo):
    await capture(repo, "night-1", "2036-02-10 23:59:40")
    await capture(repo, "night-2", "2036-02-11 00:00:10")
    await repo.seal_and_delete_older_than(datetime(2036, 2, 12, 6, 0), zone=UTC, now=NOW)
    totals = {total.day: (total.capture_count, total.visit_count) for total in await repo.totals()}
    assert totals == {date(2036, 2, 10): (1, 1), date(2036, 2, 11): (1, 0)}


@pytest.mark.asyncio
async def test_an_owner_correction_before_cleanup_is_in_the_sealed_total(repo):
    await blackbird_day(repo)
    await repo.db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = 'gt-1'")
    await repo.db.commit()
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2)}


@pytest.mark.asyncio
async def test_a_capture_frigate_lost_is_kept_as_its_own_record_and_its_day_stays_live(repo):
    await blackbird_day(repo)
    assert await repo.delete_lost_capture("bb-3", zone=UTC, now=NOW) is True
    assert "bb-3" not in await stored(repo)
    assert await repo.sealed_days() == {}
    lost = await repo.lost_captures()
    assert [(item.frigate_event, item.scientific_name) for item in lost] == [("bb-3", "Turdus merula")]
    # The rest of the day is still live, so a correction made afterwards still counts.
    await repo.db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = 'gt-1'")
    await repo.db.commit()
    # When cleanup reaches the day, the lost capture is folded into its total and its record goes.
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 1)}
    assert await repo.lost_captures() == []


@pytest.mark.asyncio
async def test_a_lost_capture_stored_again_is_no_longer_counted_as_lost(repo):
    # The video classifier can delete an event Frigate still has; backfill or the end-event
    # recovery then stores it again. The record of its loss goes in the same transaction.
    await blackbird_day(repo)
    await repo.delete_lost_capture("bb-3", zone=UTC, now=NOW)
    await capture(repo, "bb-3", "2036-02-10 10:00:00")
    assert await repo.lost_captures() == []
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}


@pytest.mark.asyncio
async def test_a_lost_record_whose_event_is_back_is_ignored_when_read_or_folded(repo):
    # Belt and braces for a row written without the trigger, e.g. restored from an older backup.
    await blackbird_day(repo)
    await repo.db.execute(
        """INSERT INTO lost_captures (frigate_event, detection_time, species_key, scientific_name,
            display_name, lost_at) VALUES ('bb-3', '2036-02-10 10:00:00', 'name:turdus merula',
            'Turdus merula', 'Turdus merula', '2036-02-11 00:00:00')"""
    )
    await repo.db.commit()
    assert await repo.lost_captures() == []
    assert await repo.lost_hourly_counts() == {}
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    assert by_species(await repo.totals()) == {"Turdus merula": (3, 2), "Parus major": (1, 1)}


@pytest.mark.asyncio
async def test_cleanup_never_seals_today(repo):
    await capture(repo, "today-early", "2036-03-01 06:00:00")
    await repo.seal_and_delete_older_than(datetime(2036, 3, 1, 9, 0), zone=UTC, now=NOW)
    assert await repo.sealed_days() == {}


@pytest.mark.asyncio
async def test_a_capture_lost_today_is_kept_too(repo):
    await capture(repo, "today-1", "2036-03-01 08:00:00")
    assert await repo.delete_lost_capture("today-1", zone=UTC, now=NOW) is True
    assert [item.frigate_event for item in await repo.lost_captures()] == ["today-1"]


@pytest.mark.asyncio
async def test_a_favourite_frigate_lost_is_kept_and_records_nothing(repo):
    await blackbird_day(repo)
    await favourite(repo, "bb-3")
    assert await repo.delete_lost_capture("bb-3", zone=UTC, now=NOW, preserve_favorites=True) is False
    assert "bb-3" in await stored(repo)
    assert await repo.lost_captures() == []
    assert await repo.sealed_days() == {}


@pytest.mark.asyncio
async def test_a_hidden_capture_frigate_lost_leaves_no_count(repo):
    await blackbird_day(repo)
    assert await repo.delete_lost_capture("bb-hidden", zone=UTC, now=NOW) is True
    assert await repo.lost_captures() == []


@pytest.mark.asyncio
async def test_totals_find_a_renamed_species_by_its_catalogue_identity(repo):
    await capture(repo, "old-name", "2036-02-10 08:00:00", species="Parus caeruleus", species_id=4242)
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    # Taxonomy now calls it Cyanistes caeruleus; the catalogue identity did not move.
    keys = await repo.species_keys(["Cyanistes caeruleus"], species_ids={4242})
    assert keys == {"species:4242"}
    assert [total.capture_count for total in await repo.totals(species_keys=keys)] == [1]
    assert await repo.species_keys(["Erithacus rubecula"], species_ids=set()) == set()


@pytest.mark.asyncio
async def test_unknown_bird_totals_use_the_same_hidden_label_rule_as_live_counting(repo):
    await capture(repo, "unknown-1", "2036-02-10 08:00:00", species=None, display="Unknown Bird")
    await capture(repo, "background-1", "2036-02-10 08:10:00", species=None, display="background")
    await capture(repo, "robin-1", "2036-02-10 08:20:00", species="Erithacus rubecula")
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    keys = await repo.unknown_species_keys(lambda label: label.casefold() in {"unknown bird", "background"})
    assert sum(total.capture_count for total in await repo.totals(species_keys=keys)) == 2


@pytest.mark.asyncio
async def test_the_first_seal_commits_in_batches_so_ingest_is_not_held(repo, monkeypatch):
    for day in range(1, 8):
        await capture(repo, f"day-{day}", f"2036-02-0{day} 08:00:00")
    commits = 0
    original = repo.db.commit

    async def counting_commit():
        nonlocal commits
        commits += 1
        await original()

    monkeypatch.setattr(daily_totals_repository, "SEAL_BATCH_DAYS", 3)
    monkeypatch.setattr(repo.db, "commit", counting_commit)
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    assert len(await repo.sealed_days()) == 7
    # Seven days in batches of three is three sealing commits, then the delete.
    assert commits >= 3


@pytest.mark.asyncio
async def test_deleting_all_history_deletes_the_totals_and_lost_captures_too(repo):
    await blackbird_day(repo)
    await capture(repo, "lost-later", "2036-02-20 08:00:00")
    await repo.delete_lost_capture("lost-later", zone=UTC, now=NOW)
    await repo.seal_and_delete_older_than(CUTOFF, zone=UTC, now=NOW)
    deleted, _counted = await repo.delete_all_if_count_is(None)
    assert deleted == 0
    assert await repo.totals() == []
    assert await repo.sealed_days() == {}
    assert await repo.lost_captures() == []


@pytest.mark.asyncio
async def test_the_frigate_missing_delete_policy_records_the_lost_capture(repo, monkeypatch):
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
    assert await repo.sealed_days() == {}
    assert [item.frigate_event for item in await repo.lost_captures()] == ["bb-3"]
