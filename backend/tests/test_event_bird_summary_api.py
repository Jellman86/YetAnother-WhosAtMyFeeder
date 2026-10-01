"""Owner-only per-capture bird summaries on the event list, through real routes and migrated history."""

from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
import json
import os
import sqlite3
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.repositories.bird_observation_repository import BirdObservationRepository
from app.routers import events
from app.routers.proxy import BirdObservationResponse

OWNER = {"Authorization": f"Bearer {create_access_token('owner')}"}


def _bird(db, event, index, species, *, hidden=False, manual=False, detector=0.8, label=None, score=0.9):
    db.execute(
        """INSERT INTO bird_observations (frigate_event, bird_index, candidate_id, clip_variant, frame_index,
           crop_box_json, detector_confidence, species, classifier_label, classifier_score, manual_species, is_hidden)
           VALUES (?, ?, ?, 'event', 150, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event,
            index,
            f"{event}__full_frame__f150__abc__observed__{index}",
            json.dumps([10 + index * 100, 10, 60 + index * 100, 60]),
            detector,
            species,
            label if label is not None else species,
            score,
            int(manual),
            int(hidden),
        ),
    )


@pytest.fixture
def history(monkeypatch, tmp_path):
    path = tmp_path / "history.db"
    today = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM detections")
        for offset, (name, hidden) in enumerate(
            (
                ("flock", 0),
                ("unprocessed", 0),
                ("all-excluded", 0),
                ("corrected", 0),
                ("hint-only", 0),
                ("hidden-parent", 1),
            )
        ):
            db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time,
                   detection_index, score, display_name, category_name, is_hidden)
                   VALUES (?, 'feeder', ?, 1, .9, 'House Finch', 'House Finch', ?)""",
                (name, (today + timedelta(minutes=offset + 1)).replace(tzinfo=None).isoformat(sep=" "), hidden),
            )
        # Two finches are two observations, never folded into one species entry of one bird.
        _bird(db, "flock", 0, "House Finch")
        _bird(db, "flock", 1, "House Finch")
        _bird(db, "flock", 2, "Unknown Bird", label="Poecile hudsonicus", score=0.27)
        _bird(db, "flock", 3, "Unidentified bird")
        _bird(db, "flock", 4, "Northern Cardinal", hidden=True)
        _bird(db, "all-excluded", 0, "House Finch", hidden=True)
        # The owner's correction is the record, whatever the classifier suggested.
        _bird(db, "corrected", 0, "Blue Jay", manual=True, label="Unknown Bird", score=0.12)
        _bird(db, "hint-only", 0, "House Finch", detector=None)
        _bird(db, "hidden-parent", 0, "House Finch")
        db.commit()

    statements: list[str] = []

    @asynccontextmanager
    async def history_db():
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            await db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(events, "get_db", history_db)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.auth, "username", "owner")
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 1)
    monkeypatch.setattr(settings.classification, "unknown_bird_labels", [])
    return path, history_db, statements


async def _events(params: dict, *, owner: bool) -> list[dict]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/events", params=params, headers=OWNER if owner else {})
    assert response.status_code == 200, response.text
    return response.json()


def _by_event(rows: list[dict]) -> dict[str, dict]:
    return {row["frigate_event"]: row for row in rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [None, "detail", "list"])
async def test_owner_summary_counts_stored_decisions_and_keeps_absent_evidence_null(history, fields):
    rows = _by_event(await _events({"include_hidden": "true", **({"fields": fields} if fields else {})}, owner=True))

    assert rows["flock"]["bird_summary"] == {
        "counted": 4,
        "unknown": 2,
        "excluded": 1,
        "species": [{"species": "House Finch", "count": 2}],
        "hint_only": False,
    }
    # No stored observations is not a measured zero.
    assert rows["unprocessed"]["bird_summary"] is None
    assert rows["all-excluded"]["bird_summary"] == {
        "counted": 0,
        "unknown": 0,
        "excluded": 1,
        "species": [],
        "hint_only": False,
    }
    assert rows["corrected"]["bird_summary"]["species"] == [{"species": "Blue Jay", "count": 1}]
    assert rows["corrected"]["bird_summary"]["unknown"] == 0
    assert rows["hint-only"]["bird_summary"]["hint_only"] is True
    assert rows["hidden-parent"]["bird_summary"]["counted"] == 1


@pytest.mark.asyncio
async def test_owner_explicit_field_selection_includes_summary(history):
    rows = _by_event(await _events({"fields": "bird_summary"}, owner=True))
    assert rows["flock"]["bird_summary"]["counted"] == 4
    assert "camera_name" in rows["flock"]


@pytest.mark.asyncio
async def test_configured_unknown_labels_are_not_named_species(history, monkeypatch):
    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["House Finch"])
    rows = _by_event(await _events({}, owner=True))
    assert rows["flock"]["bird_summary"]["unknown"] == 4
    assert rows["flock"]["bird_summary"]["species"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [None, "detail", "list", "bird_summary", "bird_summary,score"])
async def test_guest_projection_never_reads_or_returns_bird_summary(history, monkeypatch, fields):
    _, _, statements = history
    summaries = AsyncMock(side_effect=AssertionError("guest requests must not read owner bird aggregates"))
    monkeypatch.setattr(BirdObservationRepository, "summaries_for_events", summaries)

    rows = await _events({"fields": fields} if fields else {}, owner=False)

    assert {row["frigate_event"] for row in rows} >= {"flock", "unprocessed"}
    assert all("bird_summary" not in row for row in rows)
    assert not any("bird_observations" in statement for statement in statements)
    summaries.assert_not_called()


@pytest.mark.asyncio
async def test_page_reads_one_bounded_aggregate_per_four_hundred_events(history):
    path, _, statements = history
    today = datetime.combine(date.today(), datetime.min.time())
    with closing(sqlite3.connect(path)) as db:
        db.executemany(
            """INSERT INTO detections (frigate_event, camera_name, detection_time,
               detection_index, score, display_name, category_name)
               VALUES (?, 'feeder', ?, 1, .9, 'House Finch', 'House Finch')""",
            [(f"bulk-{index}", (today + timedelta(seconds=index)).isoformat(sep=" ")) for index in range(450)],
        )
        db.commit()

    rows = await _events({"limit": 500}, owner=True)

    assert len(rows) == 455
    aggregate_reads = [statement for statement in statements if "bird_observations" in statement]
    assert len(aggregate_reads) == 2
    assert all("GROUP BY" in statement for statement in aggregate_reads)


@pytest.mark.asyncio
async def test_empty_page_issues_no_aggregate_query(history):
    _, _, statements = history
    rows = await _events({"species": "Nothing Here"}, owner=True)
    assert rows == []
    assert not any("bird_observations" in statement for statement in statements)


@pytest.mark.asyncio
async def test_duplicate_event_ids_across_parameter_pages_do_not_double_counts(history):
    _, history_db, statements = history
    async with history_db() as db:
        repository = BirdObservationRepository(db)
        expected = await repository.summaries_for_events(["flock"])
        statements.clear()

        actual = await repository.summaries_for_events(["flock", *(["missing"] * 399), "flock"])

    assert actual == expected
    assert len([statement for statement in statements if "bird_observations" in statement]) == 1


@pytest.mark.asyncio
async def test_record_unknown_decisions_match_summary_for_configured_and_noncanonical_labels(history, monkeypatch):
    path, history_db, _ = history
    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["House Finch"])
    with closing(sqlite3.connect(path)) as db:
        _bird(db, "flock", 5, "Life (Life)")
        _bird(db, "flock", 6, "Warblers and allies")
        db.commit()

    async with history_db() as db:
        repository = BirdObservationRepository(db)
        birds = [
            BirdObservationResponse.model_validate(row).model_dump() for row in await repository.list_for_event("flock")
        ]
        summary = (await repository.summaries_for_events(["flock"]))["flock"]

    counted = [bird for bird in birds if not bird["is_hidden"]]
    assert sum(bird["is_unknown"] for bird in counted) == summary["unknown"] == 6
    assert all(bird["is_unknown"] for bird in counted)
    assert birds[4]["is_unknown"] is False


@pytest.mark.asyncio
async def test_summary_follows_current_parents_after_deletion_and_ignores_orphans(history):
    path, history_db, _ = history
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM detections WHERE frigate_event = 'flock'")
        assert db.execute("SELECT COUNT(*) FROM bird_observations WHERE frigate_event = 'flock'").fetchone()[0] == 0
        db.commit()
        # A fault fixture: SQLite ignores this pragma inside an open transaction.
        db.execute("PRAGMA foreign_keys=OFF")
        _bird(db, "orphan", 0, "House Finch")
        db.commit()

    rows = _by_event(await _events({}, owner=True))
    assert "flock" not in rows
    async with history_db() as db:
        assert await BirdObservationRepository(db).summaries_for_events(["orphan", "corrected"]) == {
            "corrected": {
                "counted": 1,
                "unknown": 0,
                "excluded": 0,
                "species": [{"species": "Blue Jay", "count": 1}],
                "hint_only": False,
            }
        }
        assert await BirdObservationRepository(db).summaries_for_events([]) == {}
