from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.visit_repository import VisitRepository
from app.services.visit_grouping import valid_event_bounds


START = datetime(2033, 10, 3, 10, 42, 21)


@pytest_asyncio.fixture
async def repo():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'visit-test-%'")
        await db.commit()
        yield VisitRepository(db)
        await db.execute("DELETE FROM detections WHERE frigate_event LIKE 'visit-test-%'")
        await db.commit()
    await close_db()


async def capture(
    repo, number, seconds, *, camera="birdcam", species="Turdus merula", hidden=0, favorite=False, species_id=None
):
    event = f"visit-test-{number}"
    cursor = await repo.db.execute(
        """INSERT INTO detections (detection_time, detection_index, score, display_name,
        category_name, frigate_event, camera_name, scientific_name, is_hidden, species_id)
        VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            (START + timedelta(seconds=seconds)).isoformat(sep=" "),
            0.7 + number / 1000,
            species,
            species,
            event,
            camera,
            species,
            hidden,
            species_id,
        ),
    )
    if favorite:
        await repo.db.execute("INSERT INTO detection_favorites (detection_id) VALUES (?)", (cursor.lastrowid,))
    await repo.db.commit()
    return event


@pytest.mark.asyncio
async def test_blackbird_burst_is_one_visit_before_pagination(repo):
    for number, seconds in enumerate([0, 24, 31, 41, 57, 63, 79, 83, 87, 103, 123, 138, 146]):
        await capture(repo, number, seconds)
    await capture(repo, 20, 70, species="Erithacus rubecula")
    await capture(repo, 21, 75, camera="patio")
    visits, total = await repo.list_visits(start=START, end=START + timedelta(hours=1), limit=1)
    assert total == 3
    assert visits[0]["capture_count"] == 13
    assert visits[0]["visit_id"] == "visit-test-0"
    await capture(repo, 22, 150)
    visits, total = await repo.list_visits(start=START, end=START + timedelta(hours=1), limit=1)
    assert visits[0]["visit_id"] == "visit-test-0"
    assert visits[0]["capture_count"] == 14
    captures, count = await repo.visit_captures("visit-test-0", start=START, end=START + timedelta(hours=1), limit=5)
    assert count == 14
    assert len(captures) == 5


@pytest.mark.asyncio
async def test_unique_catalogue_identity_bridges_legacy_rows(repo):
    await capture(repo, 0, 0, species_id=777)
    await capture(repo, 1, 20)
    visits, total = await repo.list_visits(start=START, end=START + timedelta(minutes=1))
    assert total == 1
    assert visits[0]["capture_count"] == 2


@pytest.mark.asyncio
async def test_running_end_time_keeps_overlapping_short_events_together(repo):
    first = await capture(repo, 0, 0)
    await repo.save_event_bounds(
        first,
        START.replace(tzinfo=timezone.utc).timestamp(),
        (START + timedelta(minutes=4)).replace(tzinfo=timezone.utc).timestamp(),
    )
    await capture(repo, 1, 20)
    await capture(repo, 2, 200)
    await capture(repo, 3, 301)
    visits, total = await repo.list_visits(start=START, end=START + timedelta(minutes=10))
    assert total == 2
    assert sorted(v["capture_count"] for v in visits) == [1, 3]


@pytest.mark.asyncio
async def test_favorites_match_complete_visit_and_hidden_captures_cannot_bridge(repo):
    await capture(repo, 0, 0, favorite=True)
    await capture(repo, 1, 40)
    await capture(repo, 2, 80, favorite=True)
    await capture(repo, 3, 130, hidden=1)
    await capture(repo, 4, 180)
    visits, total = await repo.list_visits(start=START, end=START + timedelta(minutes=10), favorites=True)
    assert total == 1
    assert visits[0]["capture_count"] == 3
    captures, count = await repo.visit_captures("visit-test-3", start=START, end=START + timedelta(minutes=10))
    assert count == 0
    assert captures == []


@pytest.mark.asyncio
async def test_manual_uploads_and_unresolved_birds_do_not_claim_one_individual(repo):
    await capture(repo, 0, 0, species="Unknown Bird")
    await capture(repo, 1, 10, species="Unknown Bird")
    for number in [2, 3]:
        event = await capture(repo, number, number * 10)
        await repo.db.execute(
            "UPDATE detections SET frigate_event = ? WHERE frigate_event = ?", (f"manual_visit-test-{number}", event)
        )
    await repo.db.commit()
    try:
        _, total = await repo.list_visits(start=START, end=START + timedelta(minutes=1))
        assert total == 4
    finally:
        await repo.db.execute("DELETE FROM detections WHERE frigate_event LIKE 'manual_visit-test-%'")
        await repo.db.commit()


@pytest.mark.parametrize("end", [None, float("nan"), float("inf"), -1, 99, True, "120"])
def test_invalid_event_bounds_are_not_duration_evidence(end):
    assert valid_event_bounds(100, end) is None


def test_valid_event_bounds_are_utc_and_bounded():
    assert valid_event_bounds(100, 120) == (datetime(1970, 1, 1, 0, 1, 40), datetime(1970, 1, 1, 0, 2))
    assert valid_event_bounds(100, 100 + 86401) is None


@pytest.mark.asyncio
async def test_visit_api_and_expansion_return_complete_visible_membership(repo, monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.config import settings
    from app.main import app
    from app.routers import events

    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    for number in range(13):
        await capture(repo, number, number * 12)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        result = await client.get("/api/visits?start_date=2033-10-03&end_date=2033-10-03&limit=1")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["total"] == 1
        assert body["visits"][0]["capture_count"] == 13
        assert body["visits"][0]["representative"]["frigate_event"] == "visit-test-12"
        expanded = await client.get(
            "/api/visits/visit-test-0/captures?start_date=2033-10-03&end_date=2033-10-03&limit=5&offset=5"
        )
        assert expanded.status_code == 200, expanded.text
        assert expanded.json()["total"] == 13
        assert [row["frigate_event"] for row in expanded.json()["captures"]] == [
            f"visit-test-{n}" for n in range(5, 10)
        ]


@pytest.mark.asyncio
async def test_terminal_bounds_survive_null_and_invalid_updates(repo):
    event = await capture(repo, 0, 0)
    start = START.replace(tzinfo=timezone.utc).timestamp()
    assert await repo.save_event_bounds(event, start, start + 120)
    assert not await repo.save_event_bounds(event, start, None)
    assert not await repo.save_event_bounds(event, start, start - 1)
    assert not await repo.save_event_bounds(event, start + 1, start + 500)
    async with repo.db.execute(
        "SELECT end_time FROM detection_event_bounds WHERE frigate_event = ?", (event,)
    ) as cursor:
        assert (await cursor.fetchone())[0] == (START + timedelta(seconds=120)).isoformat(sep=" ")


@pytest.mark.asyncio
async def test_guest_groups_real_cameras_and_cannot_expand_hidden_or_old_captures(repo, monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.auth import AuthContext, get_auth_context_with_legacy
    from app.config import settings
    from app.main import app
    from app.routers import events, visits

    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "fixed")
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    monkeypatch.setattr(visits, "public_utc_day", lambda: START.date())
    await capture(repo, 0, 0)
    await capture(repo, 1, 10, camera="patio")
    await capture(repo, 2, 20, hidden=1)
    await capture(repo, 3, -86400)
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: AuthContext("guest")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/visits?only_hidden=true&start_date=2033-10-02&end_date=2033-10-03")
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 2
            for visit in response.json()["visits"]:
                assert visit["capture_count"] == 1
                assert visit["representative"]["camera_name"] == "Hidden"
                assert visit["peak_capture"] is None
            for event in ["visit-test-2", "visit-test-3"]:
                response = await client.get(f"/api/visits/{event}/captures?only_hidden=true&start_date=2033-10-02")
                assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_auth_context_with_legacy, None)


async def birds(repo, event, species):
    for index, name in enumerate(species):
        await repo.db.execute(
            """INSERT INTO bird_observations (frigate_event, bird_index, candidate_id, clip_variant,
            frame_index, crop_box_json, species, classifier_score, manual_species, is_hidden)
            VALUES (?, ?, 'crop', 'event', 0, '[0,0,10,10]', ?, .9, 0, 0)""",
            (event, index, name),
        )
    await repo.db.commit()


@pytest.mark.asyncio
async def test_multiple_species_filter_matches_full_visit_and_named_species_only(repo):
    first = await capture(repo, 0, 0)
    multiple = await capture(repo, 1, 10)
    unknown = await capture(repo, 2, 100)
    await birds(repo, first, ["Turdus merula", "Turdus merula"])
    await birds(repo, multiple, ["Turdus merula", "Erithacus rubecula"])
    await birds(repo, unknown, ["Turdus merula", "Unknown Bird"])
    headers, total = await repo.list_visits(start=START, end=START + timedelta(minutes=5), multiple_species_only=True)
    assert total == 1
    assert headers[0]["capture_count"] == 2
    assert headers[0]["peak_event"] == multiple
    raw = await repo.get_all(start_date=START, end_date=START + timedelta(minutes=5), multiple_species_only=True)
    assert [event.frigate_event for event in raw] == [multiple]
    assert (
        await repo.get_count(start_date=START, end_date=START + timedelta(minutes=5), multiple_species_only=True) == 1
    )
    await repo.db.execute(
        "UPDATE bird_observations SET is_hidden = 1 WHERE frigate_event = ? AND bird_index = 1", (multiple,)
    )
    await repo.db.commit()
    assert (await repo.list_visits(start=START, end=START + timedelta(minutes=5), multiple_species_only=True))[1] == 0


@pytest.mark.asyncio
async def test_removed_photo_is_reversible_and_keeps_counting_evidence(repo):
    event = await capture(repo, 0, 0)
    await birds(repo, event, ["Turdus merula"])
    await repo.replace_snapshot_candidates(
        event,
        [
            {"candidate_id": "chosen", "frame_index": 0, "selected": True, "ranking_score": 0.9},
            {
                "candidate_id": "bad-photo",
                "frame_index": 1,
                "selected": False,
                "ranking_score": 0.4,
                "content_sha256": "a" * 64,
            },
        ],
    )
    with pytest.raises(ValueError, match="Choose another"):
        await repo.dismiss_snapshot_candidate(event, "chosen", True)
    assert await repo.dismiss_snapshot_candidate(event, "bad-photo", True)
    listed = await repo.list_snapshot_candidates(event)
    assert len(listed) == 2
    assert listed[1]["photo_hidden"]
    async with repo.db.execute("SELECT COUNT(*) FROM bird_observations WHERE frigate_event = ?", (event,)) as cursor:
        assert (await cursor.fetchone())[0] == 1
    assert await repo.dismiss_snapshot_candidate(event, "bad-photo", False)
    assert not (await repo.list_snapshot_candidates(event))[1]["photo_hidden"]
    assert not await repo.dismiss_snapshot_candidate(event, "missing", True)


@pytest.mark.asyncio
async def test_all_visit_statistics_use_same_overlap_and_identity_rules(repo):
    first = await capture(repo, 0, 0, species_id=777)
    start = START.replace(tzinfo=timezone.utc).timestamp()
    await repo.save_event_bounds(first, start, start + 180)
    await capture(repo, 1, 20)
    await capture(repo, 2, 150)
    end = START + timedelta(minutes=10)
    assert len(await repo.get_window_visit_openings(START, end)) == 1
    assert (await repo.get_daily_species_counts(START, end))[0]["visit_count"] == 1
    assert (await repo.get_daily_visit_counts(start_date=START, end_date=end))["2033-10-03"] == 1


@pytest.mark.asyncio
async def test_date_boundary_counts_each_windows_visible_visit_once(repo):
    midnight = datetime(2033, 10, 4)
    seconds = (midnight - START).total_seconds()
    await capture(repo, 0, seconds - 20)
    await capture(repo, 1, seconds + 20)
    for start, end in [(START, midnight - timedelta(microseconds=1)), (midnight, midnight + timedelta(hours=1))]:
        visits, total = await repo.list_visits(start=start, end=end)
        assert total == 1
        assert visits[0]["capture_count"] == 1
        assert len(await repo.get_window_visit_openings(start, end)) == 1


@pytest.mark.asyncio
async def test_dismiss_photo_api_requires_owner_and_preserves_pixels_and_birds_on_undo(repo, monkeypatch):
    import httpx
    from app.auth import create_access_token
    from app.config import settings
    from app.main import app
    from app.services.media_cache import media_cache

    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "session_secret", "visit-regression-secret-with-enough-characters")
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    event = await capture(repo, 0, 0)
    await birds(repo, event, ["Turdus merula", "Erithacus rubecula"])
    await repo.replace_snapshot_candidates(
        event,
        [
            {
                "candidate_id": "chosen",
                "frame_index": 0,
                "selected": True,
                "image_ref": "visit-test-chosen",
                "ranking_score": 0.9,
            },
            {
                "candidate_id": "bad-photo",
                "frame_index": 1,
                "selected": False,
                "image_ref": "visit-test-bad",
                "ranking_score": 0.4,
                "content_sha256": "a" * 64,
            },
        ],
    )
    await media_cache.cache_snapshot("visit-test-bad", b"retained candidate bytes", source="snapshot_candidate")
    await media_cache.cache_snapshot(event, b"current accepted photograph", source="snapshot_candidate")
    async with repo.db.execute(
        "SELECT * FROM bird_observations WHERE frigate_event = ? ORDER BY bird_index", (event,)
    ) as cursor:
        original_birds = await cursor.fetchall()
    path = f"/api/frigate/{event}/snapshot/candidates/bad-photo"
    owner = {"Authorization": "Bearer " + create_access_token("visit-owner")}
    guest = {"Authorization": "Bearer " + create_access_token("visit-guest", "guest")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for headers in ({}, guest):
            denied = await client.patch(path, headers=headers, json={"dismissed": True})
            assert denied.status_code == 403
        monkeypatch.setattr(settings.public_access, "enabled", False)
        assert (await client.patch(path, json={"dismissed": True})).status_code == 401
        assert (await client.patch(path, headers=owner, json={})).status_code == 422
        assert (
            await client.patch(path.replace("bad-photo", "missing"), headers=owner, json={"dismissed": True})
        ).status_code == 404
        assert (
            await client.patch(path.replace("bad-photo", "chosen"), headers=owner, json={"dismissed": True})
        ).status_code == 409
        hidden = await client.patch(path, headers=owner, json={"dismissed": True})
        assert hidden.status_code == 200, hidden.text
        assert next(row for row in hidden.json()["candidates"] if row["candidate_id"] == "bad-photo")["photo_hidden"]
        assert await media_cache.get_snapshot("visit-test-bad") == b"retained candidate bytes"
        restored = await client.patch(path, headers=owner, json={"dismissed": False})
        assert restored.status_code == 200, restored.text
        assert not next(row for row in restored.json()["candidates"] if row["candidate_id"] == "bad-photo")[
            "photo_hidden"
        ]
    assert await media_cache.get_snapshot(event) == b"current accepted photograph"
    assert await media_cache.get_snapshot("visit-test-bad") == b"retained candidate bytes"
    async with repo.db.execute(
        "SELECT * FROM bird_observations WHERE frigate_event = ? ORDER BY bird_index", (event,)
    ) as cursor:
        assert await cursor.fetchall() == original_birds
    stored = await repo.get_by_frigate_event(event)
    assert stored.category_name == "Turdus merula" and not stored.is_hidden


@pytest.mark.asyncio
async def test_guest_multi_species_flag_is_ignored_on_visits_events_and_counts(repo, monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.auth import create_access_token
    from app.config import settings
    from app.main import app
    from app.routers import events, visits

    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "session_secret", "visit-regression-secret-with-enough-characters")
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "fixed")
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    monkeypatch.setattr(events, "public_utc_day", lambda: START.date())
    monkeypatch.setattr(visits, "public_utc_day", lambda: START.date())
    monkeypatch.setattr(events, "batch_check_clips", AsyncMock(return_value={}))
    single = await capture(repo, 0, 0)
    multiple = await capture(repo, 1, 120)
    hidden = await capture(repo, 2, 240, hidden=1)
    await capture(repo, 3, -86400)
    await birds(repo, single, ["Turdus merula"])
    await birds(repo, multiple, ["Turdus merula", "Erithacus rubecula"])
    await birds(repo, hidden, ["Turdus merula", "Erithacus rubecula"])
    guest = {"Authorization": "Bearer " + create_access_token("visit-guest", "guest")}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=guest
    ) as client:
        for route in ("/api/visits", "/api/events", "/api/events/count"):
            common = "start_date=2033-10-02&end_date=2033-10-03&only_hidden=true"
            regular = await client.get(f"{route}?{common}")
            flagged = await client.get(f"{route}?{common}&multiple_species_only=true")
            assert regular.status_code == flagged.status_code == 200, flagged.text
            assert flagged.json() == regular.json()
            assert hidden not in flagged.text and "visit-test-3" not in flagged.text
            assert "Erithacus rubecula" not in flagged.text
        response = (await client.get("/api/visits")).json()
        assert response["total"] == 2
        assert all(
            row["representative"]["camera_name"] == "Hidden" and row["peak_capture"] is None
            for row in response["visits"]
        )


@pytest.mark.asyncio
async def test_existing_terminal_event_saves_duration_without_media_or_reclassification(repo, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from app.services import event_processor as module

    event_id = await capture(repo, 0, 0)
    await repo.db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?", (event_id,))
    await repo.db.commit()
    original = await repo.get_by_frigate_event(event_id)
    processor = module.EventProcessor(MagicMock())
    processor._auto_full_visit_enabled = MagicMock(return_value=False)
    processor._enqueue_notification_flow = AsyncMock()
    monkeypatch.setattr(module.media_cache, "has_snapshot", lambda _: False)
    schedule = AsyncMock()
    monkeypatch.setattr(module.high_quality_snapshot_service, "schedule_replacement_durable", schedule)
    start = START.replace(tzinfo=timezone.utc).timestamp()
    await processor._process_event_payload(
        {
            "type": "end",
            "after": {
                "id": event_id,
                "camera": "birdcam",
                "label": "bird",
                "start_time": start,
                "end_time": start + 180,
                "has_snapshot": False,
                "has_clip": False,
            },
        }
    )
    async with repo.db.execute(
        "SELECT start_time, end_time FROM detection_event_bounds WHERE frigate_event = ?", (event_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row == (START.isoformat(sep=" "), (START + timedelta(seconds=180)).isoformat(sep=" "))
    after = await repo.get_by_frigate_event(event_id)
    assert (after.category_name, after.score, after.manual_tagged) == (original.category_name, original.score, True)
    schedule.assert_not_awaited()
    processor.classifier.classify_async_live.assert_not_called()
    assert processor._recent_outcomes[-1]["outcome"] == "end_event_handled"


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["catalogue", "taxon"])
async def test_ambiguous_scientific_identity_cannot_bridge_distinct_ids(repo, conflict):
    await capture(repo, 0, 0, species_id=777 if conflict == "catalogue" else None)
    await capture(repo, 1, 10, species_id=888 if conflict == "catalogue" else None)
    await capture(repo, 2, 20)
    if conflict == "taxon":
        await repo.db.executemany(
            "UPDATE detections SET taxa_id = ? WHERE frigate_event = ?", [(1, "visit-test-0"), (2, "visit-test-1")]
        )
        await repo.db.commit()
    visits, count = await repo.list_visits(start=START, end=START + timedelta(minutes=1))
    assert count == 3
    assert all(visit["capture_count"] == 1 for visit in visits)


@pytest.mark.parametrize(
    "start,end",
    [
        (None, 120),
        (True, 120),
        ("100", 120),
        (float("nan"), 120),
        (float("inf"), 120),
        (-1, 120),
        (10**30, 10**30),
        (100, 100 + 86400.001),
    ],
)
def test_bounds_reject_invalid_start_and_unrepresentable_timestamps(start, end):
    assert valid_event_bounds(start, end) is None


@pytest.mark.asyncio
async def test_invalid_or_manual_event_bounds_do_not_create_or_orphan_rows(repo):
    event = await capture(repo, 0, 0)
    start = START.replace(tzinfo=timezone.utc).timestamp()
    for invalid_start, invalid_end in [(None, start + 100), (start, float("nan")), (start, start + 86401)]:
        assert not await repo.save_event_bounds(event, invalid_start, invalid_end)
    assert not await repo.save_event_bounds("visit-test-missing", start, start + 100)
    await repo.db.execute(
        "UPDATE detections SET frigate_event = 'manual_visit-test-0' WHERE frigate_event = ?", (event,)
    )
    await repo.db.commit()
    try:
        assert not await repo.save_event_bounds("manual_visit-test-0", start, start + 100)
        async with repo.db.execute(
            "SELECT COUNT(*) FROM detection_event_bounds WHERE frigate_event LIKE '%visit-test-%'"
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0
    finally:
        await repo.db.execute("DELETE FROM detections WHERE frigate_event = 'manual_visit-test-0'")
        await repo.db.commit()


@pytest.mark.asyncio
async def test_multiple_species_filter_collapses_common_and_scientific_aliases(repo):
    from app.repositories.bird_observation_repository import BirdObservationRepository

    event = await capture(repo, 0, 0)
    alias_row = await repo.db.execute(
        "INSERT INTO taxonomy_cache (scientific_name, common_name) VALUES ('Turdus merula', 'Blackbird')"
    )
    try:
        await birds(repo, event, ["Blackbird", "Turdus merula"])
        summary = (await BirdObservationRepository(repo.db).summaries_for_events([event]))[event]
        assert summary["species"] == [{"species": "Turdus merula", "count": 2}]
        assert (await repo.list_visits(start=START, end=START + timedelta(minutes=5), multiple_species_only=True))[
            1
        ] == 0
        assert not await repo.get_all(
            start_date=START, end_date=START + timedelta(minutes=5), multiple_species_only=True
        )
        assert (
            await repo.get_count(start_date=START, end_date=START + timedelta(minutes=5), multiple_species_only=True)
            == 0
        )
    finally:
        await repo.db.execute("DELETE FROM taxonomy_cache WHERE rowid = ?", (alias_row.lastrowid,))
        await repo.db.commit()


@pytest.mark.asyncio
async def test_multiple_species_filter_includes_unknown_crop_with_resolved_parent_identity(repo, monkeypatch):
    from app.config import settings
    from app.repositories.bird_observation_repository import BirdObservationRepository

    monkeypatch.setattr(settings.classification, "threshold", 0.6)
    event = await capture(repo, 0, 0)
    await birds(repo, event, ["Unknown Bird", "Erithacus rubecula"])
    await repo.db.execute(
        "UPDATE bird_observations SET classifier_label='Turdus merula', classifier_score=.2 "
        "WHERE frigate_event=? AND bird_index=0",
        (event,),
    )
    await repo.db.execute(
        "UPDATE bird_observations SET crop_box_json='[30,0,40,10]' WHERE frigate_event=? AND bird_index=1",
        (event,),
    )
    await repo.replace_snapshot_candidates(
        event,
        [
            {
                "candidate_id": "tracked",
                "source_mode": "frigate_hint_crop",
                "clip_variant": "event",
                "frame_index": 0,
                "crop_box": [0, 0, 10, 10],
                "ranking_score": 0.9,
            }
        ],
    )
    await repo.db.commit()
    observations = BirdObservationRepository(repo.db)
    resolved = (await observations.resolved_for_events([event]))[event]
    assert resolved[0]["species"] == "Turdus merula"
    assert resolved[0]["identity_source"] == "visit"
    assert {bird["species"] for bird in resolved} == {"Turdus merula", "Erithacus rubecula"}
    assert (await observations.list_for_event(event))[0]["species"] == "Unknown Bird"
    headers, total = await repo.list_visits(start=START, end=START + timedelta(minutes=5), multiple_species_only=True)
    assert total == 1
    assert headers[0]["visit_id"] == event
    raw = await repo.get_all(start_date=START, end_date=START + timedelta(minutes=5), multiple_species_only=True)
    assert [row.frigate_event for row in raw] == [event]
    assert (
        await repo.get_count(start_date=START, end_date=START + timedelta(minutes=5), multiple_species_only=True) == 1
    )


@pytest.mark.parametrize("start,end", [(10**400, 10**400), (100, 10**400)])
def test_arbitrary_precision_numeric_event_bounds_are_rejected(start, end):
    assert valid_event_bounds(start, end) is None


@pytest.mark.asyncio
async def test_cross_midnight_visit_is_assigned_to_opening_day_in_history(repo):
    midnight = datetime(2033, 10, 4)
    seconds = (midnight - START).total_seconds()
    await capture(repo, 0, seconds - 20)
    await capture(repo, 1, seconds + 20)
    end = midnight + timedelta(minutes=1)
    assert (await repo.list_visits(start=START, end=end))[1] == 1
    assert await repo.get_daily_visit_counts(start_date=START, end_date=end) == {"2033-10-03": 1}


@pytest.mark.asyncio
async def test_visit_page_total_survives_offset_beyond_end_with_identity_filter(repo):
    first = await capture(repo, 0, 0)
    mixed = await capture(repo, 1, 10, favorite=True)
    await capture(repo, 2, 200)
    await birds(repo, mixed, ["Turdus merula", "Erithacus rubecula"])
    end = START + timedelta(minutes=5)
    page, total = await repo.list_visits(start=START, end=end, offset=100)
    assert page == []
    assert total == 2
    page, total = await repo.list_visits(start=START, end=end, offset=100, favorites=True, multiple_species_only=True)
    assert page == []
    assert total == 1
    page, total = await repo.list_visits(start=START, end=end, favorites=True, multiple_species_only=True)
    assert total == 1
    assert page[0]["visit_id"] == first
    assert page[0]["capture_count"] == 2
    assert page[0]["peak_event"] == mixed


@pytest.mark.asyncio
async def test_visit_peak_uses_visible_birds_and_remains_private(repo):
    first = await capture(repo, 0, 0)
    higher_score = await capture(repo, 1, 10)
    await birds(repo, first, ["Turdus merula", "Turdus merula"])
    await birds(repo, higher_score, ["Turdus merula", "Erithacus rubecula", "Cyanistes caeruleus"])
    await repo.db.execute(
        "UPDATE bird_observations SET is_hidden=1 WHERE frigate_event=? AND bird_index>0", (higher_score,)
    )
    await repo.db.commit()
    end = START + timedelta(minutes=1)
    page, total = await repo.list_visits(start=START, end=end)
    assert total == 1
    assert page[0]["peak_event"] == first
    public, public_total = await repo.list_visits(start=START, end=end, public_audio=True)
    assert public_total == total
    assert public[0]["peak_event"] is None


@pytest.mark.asyncio
async def test_visit_end_retains_subsecond_capture_time(repo):
    await capture(repo, 0, 0.937179)
    visits, total = await repo.list_visits(start=START, end=START + timedelta(minutes=1))
    assert total == 1
    assert datetime.fromisoformat(visits[0]["end_time"]) >= START + timedelta(seconds=0.937179)


@pytest.mark.asyncio
async def test_removal_rechecks_selection_at_the_write(repo, monkeypatch):
    from unittest.mock import AsyncMock

    event = await capture(repo, 0, 0)
    await repo.replace_snapshot_candidates(
        event, [{"candidate_id": "race-photo", "source_mode": "model_crop", "selected": False}]
    )
    stale = await repo.list_snapshot_candidates(event)
    await repo.mark_selected_snapshot_candidate(event, "race-photo")
    monkeypatch.setattr(repo, "list_snapshot_candidates", AsyncMock(return_value=stale))
    with pytest.raises(ValueError, match="Choose another photograph"):
        await repo.dismiss_snapshot_candidate(event, "race-photo", True)
    async with repo.db.execute(
        "SELECT COUNT(*) FROM snapshot_candidate_dismissals WHERE frigate_event=?", (event,)
    ) as cursor:
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_camera_filter_does_not_change_identity_or_expanded_membership(repo):
    await capture(repo, 0, 0, camera="feeder", species_id=777)
    await capture(repo, 1, 20, camera="feeder")
    await capture(repo, 2, 25, camera="patio", species_id=888)
    options = {"start": START, "end": START + timedelta(minutes=1)}
    all_visits, _ = await repo.list_visits(**options)
    filtered, _ = await repo.list_visits(**options, camera="feeder")
    expected = [v for v in all_visits if v["visit_id"] != "visit-test-2"]
    assert [(v["visit_id"], v["capture_count"]) for v in filtered] == [
        (v["visit_id"], v["capture_count"]) for v in expected
    ]
    for visit in filtered:
        captures, total = await repo.visit_captures(visit["visit_id"], **options)
        assert total == visit["capture_count"] == len(captures)
        assert all(c.camera_name == "feeder" for c in captures)


@pytest.mark.asyncio
async def test_capture_page_computes_group_membership_once_and_keeps_total(repo):
    first = await capture(repo, 0, 0)
    await capture(repo, 1, 10)
    await capture(repo, 2, 20)
    statements = []
    await repo.db.set_trace_callback(statements.append)
    try:
        page, total = await repo.visit_captures(first, start=START, limit=1, offset=1)
    finally:
        await repo.db.set_trace_callback(None)
    assert total == 3
    assert [item.frigate_event for item in page] == ["visit-test-1"]
    grouping_queries = [query for query in statements if "visit_source AS" in query]
    assert len(grouping_queries) == 1, "A capture page must not scan and group the same history twice"
    page, total = await repo.visit_captures(first, start=START, limit=1, offset=10)
    assert page == []
    assert total == 3
    assert await repo.visit_captures("missing-visit", start=START) == ([], 0)


@pytest.mark.asyncio
async def test_recent_visit_peak_work_is_bounded_by_matching_history(repo):
    first = await capture(repo, 0, 0)
    await birds(repo, first, ["Turdus merula", "Erithacus rubecula"])
    # Older captures are outside the requested window. Adding counted birds to
    # them must not make a recent page aggregate the entire observation history.
    await repo.db.executemany(
        """INSERT INTO detections(detection_time,detection_index,score,display_name,
            category_name,frigate_event,camera_name,scientific_name,is_hidden)
            VALUES ('2030-01-01 00:00:00',0,0.9,'Turdus merula','Turdus merula',?,'birdcam','Turdus merula',0)""",
        [(f"visit-test-old-{index}",) for index in range(1000)],
    )
    await repo.db.commit()

    async def measured_page():
        steps = 0

        def progress():
            nonlocal steps
            steps += 1
            return 0

        await repo.db.set_progress_handler(progress, 100)
        try:
            page, total = await repo.list_visits(start=START, end=START + timedelta(minutes=1))
        finally:
            await repo.db.set_progress_handler(None, 0)
        assert total == 1
        assert page[0]["peak_event"] == first
        return steps

    before = await measured_page()
    await repo.db.executemany(
        """INSERT INTO bird_observations(frigate_event,bird_index,candidate_id,clip_variant,
            frame_index,crop_box_json,detector_confidence,species,classifier_label,classifier_score)
            VALUES (?,?,'old-candidate','full',0,'[0,0,1,1]',0.9,'Turdus merula','Turdus merula',0.9)""",
        [(f"visit-test-old-{index}", bird_index) for index in range(1000) for bird_index in range(2)],
    )
    await repo.db.commit()
    after = await measured_page()
    assert after <= before * 1.5 + 10, f"Unrelated observations grew SQL work from {before} to {after} steps"
