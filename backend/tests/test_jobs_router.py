import pytest

from app.routers.jobs import JobSnapshotItem, _build_lanes, get_jobs_snapshot


def test_build_lanes_keeps_distinct_video_and_media_work(monkeypatch):
    monkeypatch.setattr(
        "app.routers.jobs.auto_video_classifier.get_status",
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
        "app.routers.jobs.high_quality_snapshot_service.get_status",
        lambda: {"deferred": 1},
    )
    monkeypatch.setattr(
        "app.routers.jobs.full_visit_clip_service.get_status",
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

    lanes = {lane.kind: lane for lane in _build_lanes(items)}

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
        "app.routers.jobs.auto_video_classifier.get_jobs_snapshot",
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
        "app.routers.jobs.auto_video_classifier.get_status",
        lambda: {
            "pending_capacity": 1000,
            "max_concurrent_configured": 2,
            "max_concurrent_effective": 2,
        },
    )
    monkeypatch.setattr("app.routers.jobs.high_quality_snapshot_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.routers.jobs.high_quality_snapshot_service.get_status", lambda: {})
    monkeypatch.setattr("app.routers.jobs.full_visit_clip_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.routers.jobs.full_visit_clip_service.get_status", lambda: {})
    monkeypatch.setattr("app.routers.jobs._backfill_job_snapshots", lambda: [])

    response = await get_jobs_snapshot(include_routine=True, limit=1, _auth=object())

    assert len(response.items) == 1
    assert response.lanes[0].queued == 2


@pytest.mark.asyncio
async def test_jobs_snapshot_limit_keeps_newest_completed_work(monkeypatch):
    monkeypatch.setattr(
        "app.routers.jobs.auto_video_classifier.get_jobs_snapshot",
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
    monkeypatch.setattr("app.routers.jobs.auto_video_classifier.get_status", lambda: {})
    monkeypatch.setattr("app.routers.jobs.high_quality_snapshot_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.routers.jobs.high_quality_snapshot_service.get_status", lambda: {})
    monkeypatch.setattr("app.routers.jobs.full_visit_clip_service.get_jobs_snapshot", lambda: [])
    monkeypatch.setattr("app.routers.jobs.full_visit_clip_service.get_status", lambda: {})
    monkeypatch.setattr("app.routers.jobs._backfill_job_snapshots", lambda: [])

    response = await get_jobs_snapshot(include_routine=True, limit=1, _auth=object())

    assert [item.id for item in response.items] == ["video:newer"]
