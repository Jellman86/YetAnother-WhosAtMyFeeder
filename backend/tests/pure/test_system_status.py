"""The status every owner screen reads: what each verdict says for a given state, and when it is pushed."""

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from pathlib import Path

from app.models.analysis_status import AnalysisStatusResponse
from app.models.jobs import JobLaneSnapshot, JobSnapshotItem, JobsSnapshotResponse
from app.models.service_connections import FrigateApiStatus, MqttConnectionStatus, ServiceConnectionsResponse
from app.models.system_status import CameraHealth, CameraHealthReading, TelemetrySummary
from app.services.system_status import (
    SystemStatusInputs,
    SystemStatusService,
    derive_system_status,
    material_key,
    should_publish,
    summarise_jobs,
)

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
READINESS_CASES = json.loads((Path(__file__).parent.parent / "fixtures" / "model_readiness_cases.json").read_text())[
    "cases"
]


def connections(mqtt: str = "connected", frigate: str = "reachable") -> ServiceConnectionsResponse:
    return ServiceConnectionsResponse(
        mqtt=MqttConnectionStatus(state=mqtt, server="mqtt", port=1883),
        frigate=FrigateApiStatus(state=frigate, url="http://frigate:5000"),
        generated_at="2026-11-16T09:00:00Z",
    )


def no_jobs() -> JobsSnapshotResponse:
    return JobsSnapshotResponse(captured_at="2026-11-16T09:00:00Z", items=[], lanes=[])


def healthy(**overrides) -> SystemStatusInputs:
    base = SystemStatusInputs(
        startup_instance_id="instance-1",
        connections=connections(),
        jobs=no_jobs(),
        analysis=AnalysisStatusResponse(pending=0, active=0, circuit_open=False),
        mqtt_health={"pressure_level": "normal", "topic_message_counts": {"frigate": 4, "birdnet": 2}},
        classifier_health={
            "status": "ok",
            "live_image": {"status": "ok"},
            "bird_finder": {"active": False, "model_id": "yolox"},
            "models": {"bird": {"loaded": True}},
        },
        classifier_status={"active_model_id": "small", "selected_provider": "auto", "active_provider": "cpu"},
        media_storage_available=True,
        notification_channels_enabled=1,
        birdnet_enabled=True,
        event_pipeline={"status": "ok"},
    )
    return replace(base, **overrides)


def verdicts(inputs: SystemStatusInputs) -> dict[str, tuple[str, str]]:
    snapshot = derive_system_status(inputs, revision=1, now=NOW)
    return {verdict.key: (verdict.state, verdict.cause) for verdict in snapshot.subsystems}


def overall(inputs: SystemStatusInputs) -> tuple[str, str, str | None]:
    verdict = derive_system_status(inputs, revision=1, now=NOW).overall
    return verdict.state, verdict.cause, verdict.subsystem


def test_a_healthy_install_is_ok_with_every_subsystem_named():
    assert overall(healthy()) == ("ok", "ok", None)
    assert verdicts(healthy()) == {
        "mqtt": ("ok", "connected"),
        "frigate": ("ok", "reachable"),
        "classifier": ("ok", "ready"),
        "finder": ("ok", "ready"),
        "audio": ("ok", "hearing"),
        "storage": ("ok", "writable"),
        "notifications": ("ok", "ready"),
    }


def test_a_broker_that_is_down_is_the_first_thing_to_fix_and_audio_is_unmeasured():
    inputs = healthy(connections=connections(mqtt="disconnected", frigate="unreachable"))
    assert overall(inputs) == ("degraded", "disconnected", "mqtt")
    assert verdicts(inputs)["audio"] == ("unknown", "broker_down")
    assert verdicts(inputs)["frigate"] == ("error", "unreachable")


def test_frigate_unreachable_outranks_unwritable_storage():
    inputs = healthy(connections=connections(frigate="unreachable"), media_storage_available=False)
    assert overall(inputs) == ("degraded", "unreachable", "frigate")
    assert verdicts(inputs)["storage"] == ("error", "not_writable")


def test_an_offline_camera_degrades_frigate():
    cameras = CameraHealthReading(
        cameras=[CameraHealth(camera="feeder", status="offline", camera_fps=0.0)], checked_at="2026-11-16T09:00:00Z"
    )
    inputs = healthy(cameras=cameras)
    assert verdicts(inputs)["frigate"] == ("degraded", "cameras_offline")
    assert overall(inputs) == ("degraded", "cameras_offline", "frigate")


def test_a_finder_on_the_cpu_is_the_finders_verdict_not_the_classifiers():
    inputs = healthy(
        classifier_health={
            "status": "degraded",
            "live_image": {"status": "ok"},
            "bird_finder": {"active": True, "model_id": "rfdetr"},
            "models": {"bird": {"loaded": True}},
        }
    )
    assert verdicts(inputs)["classifier"] == ("ok", "ready")
    assert verdicts(inputs)["finder"] == ("degraded", "cpu_fallback")
    assert overall(inputs) == ("degraded", "cpu_fallback", "finder")


def test_a_model_that_did_not_load_is_named():
    inputs = healthy(classifier_health={"status": "error", "models": {"bird": {"loaded": False, "error": "x"}}})
    assert verdicts(inputs)["classifier"] == ("error", "model_not_loaded")


def test_a_chosen_model_not_on_this_install_is_an_error_the_status_line_also_states():
    # The worker loads the model on its first visit, so runtime health alone still reads "ok".
    inputs = healthy(classifier_status={"active_model_id": "small", "active_model_installed": False})
    assert verdicts(inputs)["classifier"] == ("error", "model_missing")
    assert overall(inputs) == ("degraded", "model_missing", "classifier")


def test_the_classifier_verdict_and_the_models_readiness_agree_on_every_shared_case():
    # The same reports the SPA's status line and the setup review read: a model the readiness rule
    # calls missing is never a working classifier chip, and nothing else is called missing.
    for case in READINESS_CASES:
        inputs = healthy(classifier_status=case["status"] or {})
        state, cause = verdicts(inputs)["classifier"]
        if case["readiness"] == "missing":
            assert (state, cause) == ("error", "model_missing"), case["name"]
        else:
            assert cause != "model_missing", case["name"]


def test_a_chosen_finder_not_downloaded_needs_a_look_rather_than_reading_as_ready():
    inputs = healthy(
        classifier_status={"active_model_id": "small", "crop_detector": {"model_id": "yolox", "installed": False}}
    )
    assert verdicts(inputs)["finder"] == ("degraded", "not_downloaded")
    downloaded = healthy(
        classifier_status={"active_model_id": "small", "crop_detector": {"model_id": "yolox", "installed": True}}
    )
    assert verdicts(downloaded)["finder"] == ("ok", "ready")


def test_a_finder_not_downloaded_behind_an_installed_fallback_is_still_not_downloaded():
    # The spec describes the fallback it would run (installed), and names the chosen finder apart.
    fallback = {
        "model_id": "bird_crop_detector_accurate_yolox_tiny",
        "chosen_model_id": "bird_crop_detector_accurate_rfdetr_nano",
        "installed": True,
        "chosen_installed": False,
        "reason": "fallback_default_accurate",
    }
    inputs = healthy(classifier_status={"active_model_id": "small", "crop_detector": fallback})
    assert verdicts(inputs)["finder"] == ("degraded", "not_downloaded")


def test_a_finder_never_downloaded_leaves_the_install_ok():
    # Optional and never bundled: its chip and panel say so, but the install is not degraded and no
    # notification stands for it.
    inputs = healthy(
        classifier_status={"active_model_id": "small", "crop_detector": {"model_id": "yolox", "installed": False}}
    )
    assert overall(inputs) == ("ok", "ok", None)


def test_a_missing_model_is_an_error_even_before_the_runtime_has_reported():
    # Whether the model's files are here is measured from the install, not from the runtime, so
    # no runtime reading yet does not make it unmeasured.
    inputs = healthy(
        classifier_health={}, classifier_status={"active_model_id": "small", "active_model_installed": False}
    )
    assert verdicts(inputs)["classifier"] == ("error", "model_missing")
    assert overall(inputs) == ("degraded", "model_missing", "classifier")


def test_parts_switched_off_are_off_and_do_not_degrade():
    inputs = healthy(birdnet_enabled=False, notification_channels_enabled=0)
    assert verdicts(inputs)["audio"] == ("off", "disabled")
    assert verdicts(inputs)["notifications"] == ("off", "none_enabled")
    assert overall(inputs) == ("ok", "ok", None)


def test_silence_since_start_is_unmeasured_not_a_fault():
    inputs = healthy(mqtt_health={"topic_message_counts": {"birdnet": 0}})
    assert verdicts(inputs)["audio"] == ("unknown", "nothing_heard")
    assert overall(inputs)[0] == "ok"


def test_dropped_notifications_degrade():
    assert verdicts(healthy(notification_dropped_jobs=3))["notifications"] == ("degraded", "dropped")


def test_a_connection_never_measured_is_not_counted_as_fine():
    assert overall(healthy(connections=connections(frigate="unchecked"))) == ("unknown", "unchecked", "frigate")
    assert overall(healthy(connections=connections(mqtt="connecting"))) == ("unknown", "connecting", "mqtt")


@pytest.mark.parametrize(
    "overrides,cause",
    [
        ({"event_pipeline": {"status": "degraded", "critical_failure_active": True}}, "pipeline_critical"),
        ({"event_pipeline": {"status": "degraded"}}, "pipeline_degraded"),
        ({"db_pool_degraded": True}, "database_slow"),
        ({"startup_warning_count": 2}, "startup_warnings"),
        ({"mqtt_health": {"pressure_level": "high", "topic_message_counts": {"birdnet": 1}}}, "pressure_high"),
        ({"mqtt_health": {"backlog_wait_active": True, "topic_message_counts": {"birdnet": 1}}}, "backlog"),
    ],
)
def test_the_rest_of_the_health_judgement_degrades_with_a_cause(overrides, cause):
    assert overall(healthy(**overrides))[:2] == ("degraded", cause)


def job(
    id_: str, kind: str, status: str, current: int = 0, total: int = 0, unit: str = "items", visibility="prominent"
):
    return JobSnapshotItem(
        id=id_,
        kind=kind,
        source="owner",
        status=status,
        phase="processing",
        current=current,
        total=total,
        unit=unit,
        visibility=visibility,
    )


def lane(kind: str, running: int = 0, queued: int = 0) -> JobLaneSnapshot:
    return JobLaneSnapshot(kind=kind, running=running, queued=queued)


def test_jobs_are_one_count_of_prominent_work_and_routine_work_is_left_out():
    jobs = JobsSnapshotResponse(
        captured_at="t",
        items=[
            job("backfill:1", "backfill", "running", 40, 100, "detections"),
            job("video:1", "video_analysis", "queued"),
            job("video:2", "video_analysis", "queued"),
            job("video:3", "video_analysis", "queued"),
            job("hq:1", "high_quality_snapshot", "running", visibility="routine"),
        ],
        lanes=[lane("backfill", running=1), lane("video_analysis", queued=3), lane("high_quality_snapshot", running=1)],
    )
    summary = summarise_jobs(jobs)
    assert (summary.running, summary.queued) == (1, 3)
    assert summary.progress is not None
    assert (summary.progress.current, summary.progress.total, summary.progress.unit) == (40, 100, "detections")


def test_no_progress_is_claimed_for_unlike_work_or_an_unknown_total():
    mixed = JobsSnapshotResponse(
        captured_at="t",
        items=[
            job("a", "backfill", "running", 1, 10, "detections"),
            job("b", "reclassify", "running", 2, 15, "frames"),
        ],
        lanes=[lane("backfill", running=1), lane("reclassify", running=1)],
    )
    assert summarise_jobs(mixed).progress is None
    unknown = JobsSnapshotResponse(
        captured_at="t", items=[job("a", "backfill", "running", 3, 0)], lanes=[lane("backfill", running=1)]
    )
    assert summarise_jobs(unknown).progress is None


def test_no_progress_is_claimed_when_some_running_jobs_are_not_in_the_page():
    jobs = JobsSnapshotResponse(
        captured_at="t", items=[job("a", "backfill", "running", 3, 10)], lanes=[lane("backfill", running=2)]
    )
    summary = summarise_jobs(jobs)
    assert summary.running == 2
    assert summary.progress is None


def test_the_provider_warning_follows_the_dashboards_rule():
    def fallback(status: dict) -> bool:
        return derive_system_status(healthy(classifier_status=status), revision=1, now=NOW).model.provider_fallback

    assert fallback({"enabled": True, "selected_provider": "intel_gpu", "active_provider": "cpu"}) is True
    assert fallback({"enabled": True, "selected_provider": "cpu", "active_provider": "tflite"}) is False
    assert fallback({"enabled": True, "selected_provider": "auto", "active_provider": "cpu"}) is False
    assert fallback({"enabled": True, "fallback_reason": "GPU failed to compile"}) is True
    # A worker-run model reports no `enabled`, so the Dashboard never warned for it; neither does this.
    assert fallback({"selected_provider": "intel_gpu", "active_provider": "cpu"}) is False


def test_the_model_revision_changes_with_the_model_and_not_with_counters():
    def revision(status: dict) -> str:
        return derive_system_status(healthy(classifier_status=status), revision=1, now=NOW).model.revision

    base = {"active_model_id": "small", "active_provider": "cpu", "live_image_in_flight": 0}
    assert revision(base) == revision({**base, "live_image_in_flight": 3})
    assert revision(base) != revision({**base, "active_model_id": "large"})
    assert revision(base) != revision({**base, "active_provider": "intel_gpu"})


def test_the_snapshot_carries_only_the_fields_it_declares():
    secret = "hunter2-private-token"
    inputs = healthy(
        classifier_status={"active_model_id": "small", "api_key": secret, "openvino_import_path": secret},
        mqtt_health={"password": secret, "topic_message_counts": {"birdnet": 1}},
        classifier_health={"status": "ok", "token": secret, "bird_finder": {"model_id": "y", "secret": secret}},
    )
    payload = json.dumps(derive_system_status(inputs, revision=1, now=NOW).model_dump(mode="json"))
    assert secret not in payload


def snapshot_of(inputs: SystemStatusInputs):
    return derive_system_status(inputs, revision=1, now=NOW)


def test_moving_figures_are_not_a_material_change():
    first = snapshot_of(healthy(telemetry=TelemetrySummary(sampled_at=1.0, cpu_percent=10.0)))
    later = derive_system_status(
        healthy(
            telemetry=TelemetrySummary(sampled_at=6.0, cpu_percent=55.0),
            analysis=AnalysisStatusResponse(
                pending=0, active=0, circuit_open=False, oldest_maintenance_pending_age_seconds=12.5
            ),
        ),
        revision=2,
        now=datetime(2026, 11, 16, 9, 1, tzinfo=timezone.utc),
    )
    assert material_key(first) == material_key(later)


def test_a_job_moving_on_or_a_connection_dropping_is_a_material_change():
    base = snapshot_of(healthy())
    moved = snapshot_of(
        healthy(
            jobs=JobsSnapshotResponse(
                captured_at="t", items=[job("a", "backfill", "running", 1, 9)], lanes=[lane("backfill", running=1)]
            )
        )
    )
    dropped = snapshot_of(healthy(connections=connections(mqtt="disconnected")))
    assert material_key(base) != material_key(moved)
    assert material_key(base) != material_key(dropped)


def test_a_change_is_pushed_at_once_and_figures_at_most_every_refresh_interval():
    assert should_publish(previous_key=None, key="a", seconds_since_publish=None, refresh_after_seconds=15)
    assert should_publish(previous_key="a", key="b", seconds_since_publish=0.5, refresh_after_seconds=15)
    assert not should_publish(previous_key="a", key="a", seconds_since_publish=14.9, refresh_after_seconds=15)
    assert should_publish(previous_key="a", key="a", seconds_since_publish=15.0, refresh_after_seconds=15)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_service(inputs_holder: list[SystemStatusInputs], clock: FakeClock, published: list[dict]):
    async def collect() -> SystemStatusInputs:
        return inputs_holder[0]

    async def publish(message: dict) -> None:
        published.append(message)

    return SystemStatusService(
        collect=collect,
        publish=publish,
        has_subscribers=lambda: True,
        clock=clock,
        wall_clock=lambda: NOW,
    )


def test_the_service_publishes_changes_and_raises_the_revision_only_for_them():
    async def scenario() -> None:
        clock = FakeClock()
        holder = [healthy()]
        published: list[dict] = []
        service = make_service(holder, clock, published)

        first = await service.refresh_once()
        assert first is not None and first.revision == 1
        assert published[-1]["type"] == "status"

        clock.now = 5.0
        assert await service.refresh_once() is None
        assert len(published) == 1

        holder[0] = healthy(connections=connections(mqtt="disconnected"))
        clock.now = 6.0
        changed = await service.refresh_once()
        assert changed is not None and changed.revision == 2
        assert published[-1]["data"]["overall"]["cause"] == "disconnected"

        clock.now = 21.5
        refreshed = await service.refresh_once()
        assert refreshed is not None and refreshed.revision == 2

    asyncio.run(scenario())


def test_current_reuses_a_recent_reading():
    async def scenario() -> None:
        clock = FakeClock()
        calls = []

        async def collect() -> SystemStatusInputs:
            calls.append(clock.now)
            return healthy()

        async def publish(_message: dict) -> None:
            return None

        service = SystemStatusService(
            collect=collect, publish=publish, has_subscribers=lambda: True, clock=clock, wall_clock=lambda: NOW
        )
        await service.current()
        clock.now = 4.0
        await service.current()
        clock.now = 10.0
        await service.current()
        assert calls == [0.0, 10.0]

    asyncio.run(scenario())


def test_its_own_events_and_heartbeats_do_not_wake_it():
    async def scenario() -> None:
        service = make_service([healthy()], FakeClock(), [])
        service.request_refresh({"type": "status"})
        service.request_refresh({"type": "heartbeat"})
        assert not service._wake.is_set()
        service.request_refresh({"type": "service_connections_changed"})
        assert service._wake.is_set()

    asyncio.run(scenario())


def test_free_text_in_the_snapshot_is_redacted_before_it_is_published():
    secret = "fixture-configured-secret-8812"
    credential_url = "http://owner:fixture-url-pass-8812@frigate:5000/api/stats?token=tok-8812"
    failed = JobSnapshotItem(
        id="backfill:detections:1",
        kind="backfill",
        source="owner",
        status="failed",
        phase=f"Failed against {credential_url}",
        error=f"Refused with {secret}; api_key=key-8812",
    )
    inputs = healthy(
        secrets=(secret,),
        jobs=JobsSnapshotResponse(captured_at="t", items=[failed], lanes=[lane("backfill")]),
        analysis=AnalysisStatusResponse(
            pending=0, active=0, circuit_open=False, maintenance_status_message=f"Paused: {credential_url}"
        ),
        classifier_status={"enabled": True, "fallback_reason": f"GPU failed at {credential_url} with {secret}"},
    )

    payload = json.dumps(derive_system_status(inputs, revision=1, now=NOW).model_dump(mode="json"))

    for leaked in (secret, "fixture-url-pass-8812", "tok-8812", "key-8812", "owner:"):
        assert leaked not in payload
    assert "frigate:5000" in payload


def test_the_health_revision_follows_the_counters_and_the_finder_without_forcing_a_push():
    def snapshot(**overrides):
        return derive_system_status(healthy(**overrides), revision=1, now=NOW)

    base = snapshot(event_pipeline={"status": "ok", "started_events": 10, "completed_events": 9})
    counted = snapshot(event_pipeline={"status": "ok", "started_events": 11, "completed_events": 10})
    finder_on_cpu = snapshot(
        event_pipeline={"status": "ok", "started_events": 10, "completed_events": 9},
        classifier_health={
            "status": "degraded",
            "live_image": {"status": "ok"},
            "bird_finder": {"active": True, "model_id": "rfdetr"},
            "models": {"bird": {"loaded": True}},
        },
    )

    assert base.health_revision != counted.health_revision
    assert base.health_revision != finder_on_cpu.health_revision
    # Counters move with every event; they reach Health with the next figure refresh, not as a push.
    assert material_key(base) == material_key(counted)


def test_the_job_count_is_the_lane_total_when_the_list_is_cut_at_a_hundred():
    listed = [job(f"video:{index}", "video_analysis", "queued") for index in range(100)]
    jobs = JobsSnapshotResponse(captured_at="t", items=listed, lanes=[lane("video_analysis", queued=151)])

    summary = summarise_jobs(jobs)

    assert (summary.running, summary.queued) == (0, 151)


def test_a_closed_video_circuit_moves_the_incident_revision_so_its_incident_can_close():
    def snapshot(**analysis):
        return derive_system_status(
            healthy(analysis=AnalysisStatusResponse(pending=0, active=0, **analysis)), revision=1, now=NOW
        )

    tripped = snapshot(circuit_open=True, open_until="2026-11-16T09:10:00Z", failure_count=5)
    recovered = snapshot(circuit_open=False, failure_count=0)
    assert tripped.incident_revision != recovered.incident_revision
    assert tripped.health_revision != recovered.health_revision


def test_the_incident_revision_ignores_counters_that_only_health_shows():
    base = derive_system_status(healthy(event_pipeline={"status": "ok", "started_events": 1}), revision=1, now=NOW)
    counted = derive_system_status(healthy(event_pipeline={"status": "ok", "started_events": 2}), revision=1, now=NOW)
    critical = derive_system_status(
        healthy(event_pipeline={"status": "degraded", "started_events": 2, "critical_failure_active": True}),
        revision=1,
        now=NOW,
    )

    assert base.incident_revision == counted.incident_revision
    assert base.health_revision != counted.health_revision
    assert base.incident_revision != critical.incident_revision


def _set_path(tree: dict, path: str, value) -> dict:
    head, _, rest = path.partition(".")
    node = dict(tree.get(head) or {})
    tree = {**tree, head: _set_path(node, rest, value) if rest else value}
    return tree


def test_every_incident_signal_moves_the_incident_revision():
    from app.services.system_status import INCIDENT_SIGNAL_PATHS

    base_health = {"ml": {"status": "ok", "live_image": {"status": "ok"}, "bird_finder": {"model_id": "y"}}}

    def revision(health: dict) -> str:
        inputs = healthy(incident_health=health)
        return derive_system_status(inputs, revision=1, now=NOW).incident_revision

    base = revision(base_health)
    for path in INCIDENT_SIGNAL_PATHS:
        value = 3 if path.endswith(".queued") else True
        assert revision(_set_path(base_health, path, value)) != base, path


def test_the_incident_signals_are_the_ones_the_incident_workspace_resolves_from():
    import re
    from pathlib import Path

    from app.services.system_status import INCIDENT_SIGNAL_PATHS

    source = (Path(__file__).resolve().parents[3] / "apps/ui/src/lib/stores/incident-signals.ts").read_text()
    block = re.search(r"INCIDENT_SIGNAL_PATHS = \[(.*?)\] as const", source, re.S)
    assert block, "the frontend list is declared as INCIDENT_SIGNAL_PATHS = [...] as const"
    assert tuple(re.findall(r"'([^']+)'", block.group(1))) == INCIDENT_SIGNAL_PATHS


@pytest.mark.parametrize(
    "before,after",
    [
        (
            {"ml": {"worker_pools": {"background": {"circuit_open": True}}}},
            {"ml": {"worker_pools": {"background": {"circuit_open": False}}}},
        ),
        (
            {"ml": {"background_image": {"background_throttled": True, "queued": 4}}},
            {"ml": {"background_image": {"background_throttled": False, "queued": 0}}},
        ),
        (
            {"mqtt": {"frigate_availability": {"status": "offline"}}},
            {"mqtt": {"frigate_availability": {"status": "online"}}},
        ),
    ],
)
def test_a_stateful_recovery_moves_both_revisions(before, after):
    first = derive_system_status(healthy(incident_health=before), revision=1, now=NOW)
    second = derive_system_status(healthy(incident_health=after), revision=1, now=NOW)
    assert first.incident_revision != second.incident_revision
    assert first.health_revision != second.health_revision
