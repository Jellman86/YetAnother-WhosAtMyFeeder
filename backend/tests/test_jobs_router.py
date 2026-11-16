import pytest

from app.routers.jobs import get_jobs_snapshot
from app.services.jobs_snapshot import JobSnapshotItem, build_lanes


def test_build_lanes_keeps_distinct_video_and_media_work(monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs_snapshot.auto_video_classifier.get_status",
        lambda: {
            "pending_capacity": 1000,
            "max_concurrent_configured": 3,
            "max_concurrent_effective": 1,
            "circuit_open": False,
            "maintenance_circuit_open": False,
            "throttled_for_live_pressure": True,
        },
    )
    monkeypatch.setattr(
        "app.services.jobs_snapshot.high_quality_snapshot_service.get_status",
        lambda: {"deferred": 1},
    )
    monkeypatch.setattr(
        "app.services.jobs_snapshot.full_visit_clip_service.get_status",
        lambda: {"queue_capacity": 128, "queued": 0, "workers": 2, "queue_full_rejections": 0},
    )
    items = [
        JobSnapshotItem(
            id="video:1",
            event_id="1",
            kind="video_analysis",
            source="maintenance",
            status="queued",
            phase="waiting",
        ),
        JobSnapshotItem(
            id="high_quality_snapshot:1",
            event_id="1",
            kind="high_quality_snapshot",
            source="automatic",
            status="running",
            phase="selecting_best_frame",
        ),
    ]

    lanes = {lane.kind: lane for lane in build_lanes(items)}

    assert lanes["video_analysis"].queued == 1
    assert lanes["video_analysis"].blocker == "waiting_for_live_detections"
    assert lanes["video_analysis"].capacity == 1000
    assert lanes["video_analysis"].max_concurrent_configured == 3
    assert lanes["video_analysis"].max_concurrent_effective == 1
    assert lanes["high_quality_snapshot"].running == 1
    assert lanes["high_quality_snapshot"].blocker == "waiting_for_capacity"


@pytest.mark.asyncio
async def test_jobs_snapshot_applies_item_limit_after_lane_totals(monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs_snapshot.auto_video_classifier.get_jobs_snapshot",
        lambda: [
            {
                "id": "video:1",
                "event_id": "1",
                "kind": "video_analysis",
                "source": "maintenance",
                "status": "queued",
                "phase": "waiting",
            },
            {
                "id": "video:2",
                "event_id": "2",
                "kind": "video_analysis",
                "source": "maintenance",
                "status": "queued",
                "phase": "waiting",
            },
        ],
    )
    monkeypatch.setattr(
        "app.services.jobs_snapshot.auto_video_classifier.get_status",
        lambda: {
            "pending_capacity": 1000,
            "max_concurrent_configured": 2,
            "max_concurrent_effective": 2,
        },
    )
    monkeypatch.setattr("app.services.jobs_snapshot.high_quality_snapshot_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.services.jobs_snapshot.high_quality_snapshot_service.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot.full_visit_clip_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.services.jobs_snapshot.full_visit_clip_service.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot._backfill_job_snapshots", lambda: [])

    response = await get_jobs_snapshot(include_routine=True, limit=1, _auth=object())

    assert len(response.items) == 1
    assert response.lanes[0].queued == 2


@pytest.mark.asyncio
async def test_jobs_snapshot_limit_keeps_newest_completed_work(monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs_snapshot.auto_video_classifier.get_jobs_snapshot",
        lambda: [
            {
                "id": "video:older",
                "event_id": "older",
                "kind": "video_analysis",
                "source": "maintenance",
                "status": "completed",
                "phase": "completed",
                "finished_at": "2026-07-22T10:00:00+00:00",
            },
            {
                "id": "video:newer",
                "event_id": "newer",
                "kind": "video_analysis",
                "source": "maintenance",
                "status": "completed",
                "phase": "completed",
                "finished_at": "2026-07-22T11:00:00+00:00",
            },
        ],
    )
    monkeypatch.setattr("app.services.jobs_snapshot.auto_video_classifier.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot.high_quality_snapshot_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.services.jobs_snapshot.high_quality_snapshot_service.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot.full_visit_clip_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.services.jobs_snapshot.full_visit_clip_service.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot._backfill_job_snapshots", lambda: [])

    response = await get_jobs_snapshot(include_routine=True, limit=1, _auth=object())

    assert [item.id for item in response.items] == ["video:newer"]


def test_a_backfill_is_named_the_way_the_browser_names_it(monkeypatch):
    """The stream-driven row and the snapshot row must be one job, not two."""
    from app.routers.backfill import BackfillJobStatus
    from app.services.jobs_snapshot import _backfill_job_snapshots

    weather = BackfillJobStatus(
        id="da620f73",
        kind="weather",
        status="completed",
        started_at="2026-09-10T07:10:38+00:00",
        finished_at="2026-09-10T07:10:39+00:00",
        processed=94,
        total=94,
        message="Updated 94 detection(s)",
    )
    detections = BackfillJobStatus(id="b2", kind="detections", status="running", started_at="2026-09-10T07:10:38+00:00")
    monkeypatch.setattr("app.routers.backfill._JOB_STORE", {weather.id: weather, detections.id: detections})

    by_id = {item["id"]: item for item in _backfill_job_snapshots()}

    assert set(by_id) == {"backfill:weather:da620f73", "backfill:detections:b2"}
    assert by_id["backfill:weather:da620f73"]["kind"] == "weather_backfill"
    assert by_id["backfill:weather:da620f73"]["phase"] == "Updated 94 detection(s)"
    assert by_id["backfill:detections:b2"]["kind"] == "backfill"
    assert by_id["backfill:detections:b2"]["phase"] == "processing"


def _only_these_jobs(monkeypatch, *, memory=(), saved=(), backfill=()):
    for name in ("auto_video_classifier", "full_visit_clip_service", "archive_service"):
        monkeypatch.setattr(f"app.services.jobs_snapshot.{name}.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.services.jobs_snapshot.auto_video_classifier.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot.full_visit_clip_service.get_status", lambda: {})
    monkeypatch.setattr("app.services.jobs_snapshot.high_quality_snapshot_service.get_status", lambda: {})
    monkeypatch.setattr(
        "app.services.jobs_snapshot.high_quality_snapshot_service.get_jobs_snapshot", lambda: list(memory)
    )
    monkeypatch.setattr("app.services.jobs_snapshot._backfill_job_snapshots", lambda: list(backfill))
    return list(saved)


@pytest.mark.asyncio
async def test_a_failed_job_never_carries_a_secret_or_a_credential_url(monkeypatch):
    from app.config import settings
    from app.services.jobs_snapshot import build_jobs_snapshot

    monkeypatch.setattr(settings.frigate, "mqtt_password", "fixture-broker-pass-5521")
    message = (
        "Backfill failed: GET http://owner:fixture-url-pass-5521@frigate:5000/api/events?token=abc123 "
        "refused; broker password fixture-broker-pass-5521; api_key=sk-fixture-5521"
    )
    saved = _only_these_jobs(
        monkeypatch,
        backfill=[
            {
                "id": "backfill:detections:1",
                "kind": "backfill",
                "source": "owner",
                "status": "failed",
                "phase": message,
                "error": message,
            }
        ],
    )

    snapshot = await build_jobs_snapshot(saved_high_quality_jobs=saved)

    serialised = snapshot.model_dump_json()
    for secret in ("fixture-url-pass-5521", "fixture-broker-pass-5521", "abc123", "sk-fixture-5521", "owner:"):
        assert secret not in serialised
    assert "Backfill failed" in snapshot.items[0].error
    assert "frigate:5000" in snapshot.items[0].phase


@pytest.mark.asyncio
async def test_a_photograph_job_held_in_memory_is_not_counted_again_from_the_saved_rows(monkeypatch):
    from app.services.jobs_snapshot import build_jobs_snapshot

    running = {
        "id": "high_quality_snapshot:evt-1",
        "event_id": "evt-1",
        "kind": "high_quality_snapshot",
        "source": "automatic",
        "status": "running",
        "phase": "selecting_best_frame",
    }
    saved = _only_these_jobs(
        monkeypatch,
        memory=[running],
        saved=[
            {**running, "status": "queued", "phase": "waiting"},
            {
                **running,
                "id": "high_quality_snapshot:evt-2",
                "event_id": "evt-2",
                "status": "queued",
                "phase": "waiting",
            },
        ],
    )

    snapshot = await build_jobs_snapshot(saved_high_quality_jobs=saved)

    by_id = {item.id: item for item in snapshot.items}
    assert len(snapshot.items) == 2
    assert by_id["high_quality_snapshot:evt-1"].status == "running"
    lane = next(lane for lane in snapshot.lanes if lane.kind == "high_quality_snapshot")
    assert (lane.running, lane.queued) == (1, 1)
