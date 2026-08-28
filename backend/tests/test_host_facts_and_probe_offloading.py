"""Two faults found while diagnosing #300.

#313: a status request re-detected hardware capabilities inline, and detection
spawns child processes that import an inference runtime. Every other request
waited behind it, including ones that touch nothing. A reporter's capture showed
`/api/version`, a fixed string, taking 22.5 seconds to first byte.

The second is the reason that took so long to find: the diagnostics bundle
records neither the host's processor count nor its memory, so a performance
report cannot be sized. Two bundles and a HAR could not answer "is this machine
big enough".
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import classifier_service
from app.services.classifier_service import ClassifierService


def test_status_does_not_detect_capabilities_inline():
    """A status read returns what is known. It does not go and find out.

    Detection spawns subprocesses with five second timeouts, so doing it on the
    event loop stalls every concurrent request (CLAUDE.md section 4).
    """
    service = ClassifierService.__new__(ClassifierService)
    service._accel_caps = {"openvino_available": True}
    service._accel_caps_last_refreshed_monotonic = None  # never refreshed: maximally stale
    service._accel_caps_ttl_seconds = 60.0

    with patch("app.services.classifier_service._detect_acceleration_capabilities") as detect:
        caps = service._accel_caps_for_read()

    detect.assert_not_called()
    assert caps == {"openvino_available": True}


def test_a_never_taken_reading_says_so_rather_than_guessing():
    """Section 5: state an unknown as unknown, do not round it up to healthy."""
    service = ClassifierService.__new__(ClassifierService)
    service._accel_caps = {}
    service._accel_caps_last_refreshed_monotonic = None
    service._accel_caps_ttl_seconds = 60.0

    assert service._accel_caps_age_seconds() is None


def test_health_reports_the_host_it_is_running_on():
    """Sizing a performance report needs the machine, and the bundle had neither."""
    from app.services.host_facts import collect_host_facts

    facts = collect_host_facts()

    assert "cpu_count" in facts
    assert "memory_total_bytes" in facts
    assert "cpu_quota" in facts, "a container CPU limit changes what the numbers mean"


def test_host_facts_never_raise_on_an_unusual_platform():
    """Diagnostics must not fail to generate because a /proc file is missing."""
    from app.services import host_facts

    with patch.object(host_facts, "_read_cgroup_cpu_quota", side_effect=OSError("no cgroup")):
        facts = host_facts.collect_host_facts()

    assert facts["cpu_quota"] is None
    assert facts["cpu_count"] is not None


def test_a_cgroup_v1_cpu_limit_is_read(tmp_path):
    """Unraid and older Docker mount cgroup v1; a --cpus limit lives there.

    Reading only the v2 path reported a two core container on a sixteen core
    v1 host as unconstrained — the exact misdiagnosis this module exists to
    prevent.
    """
    from app.services import host_facts

    quota = tmp_path / "cpu.cfs_quota_us"
    period = tmp_path / "cpu.cfs_period_us"
    quota.write_text("200000\n")
    period.write_text("100000\n")

    with (
        patch.object(host_facts, "CGROUP_V2_CPU_MAX", str(tmp_path / "missing")),
        patch.object(host_facts, "CGROUP_V1_CPU_QUOTA", str(quota)),
        patch.object(host_facts, "CGROUP_V1_CPU_PERIOD", str(period)),
    ):
        assert host_facts._read_cgroup_cpu_quota() == 2.0

    quota.write_text("-1\n")
    with (
        patch.object(host_facts, "CGROUP_V2_CPU_MAX", str(tmp_path / "missing")),
        patch.object(host_facts, "CGROUP_V1_CPU_QUOTA", str(quota)),
        patch.object(host_facts, "CGROUP_V1_CPU_PERIOD", str(period)),
    ):
        assert host_facts._read_cgroup_cpu_quota() is None  # explicitly unlimited


def test_a_cgroup_v1_memory_limit_is_read(tmp_path):
    from app.services import host_facts

    limit = tmp_path / "memory.limit_in_bytes"
    limit.write_text("2147483648\n")

    with (
        patch.object(host_facts, "CGROUP_V2_MEMORY_MAX", str(tmp_path / "missing")),
        patch.object(host_facts, "CGROUP_V1_MEMORY_LIMIT", str(limit)),
    ):
        assert host_facts._read_cgroup_memory_limit() == 2147483648

    # v1 reports "no limit" as a near-2^63 sentinel, not the word "max".
    limit.write_text("9223372036854771712\n")
    with (
        patch.object(host_facts, "CGROUP_V2_MEMORY_MAX", str(tmp_path / "missing")),
        patch.object(host_facts, "CGROUP_V1_MEMORY_LIMIT", str(limit)),
    ):
        assert host_facts._read_cgroup_memory_limit() is None


def test_an_unreadable_cpu_quota_is_not_rounded_up_to_the_whole_machine(tmp_path):
    """No cgroup file at all means the limit is unknown, not absent.

    Claiming the full core count as effective when the quota could not be read
    is the guess the module docstring forbids: a constrained container on an
    exotic platform would be sized as the whole machine.
    """
    from app.services import host_facts

    with patch.object(host_facts, "_read_cgroup_cpu_quota", side_effect=OSError("no cgroup at all")):
        facts = host_facts.collect_host_facts()

    assert facts["cpu_quota"] is None
    assert facts["effective_cpus"] is None, "an unknown limit must stay unknown"


def test_an_explicitly_unlimited_quota_makes_the_machine_the_limit():
    from app.services import host_facts

    with patch.object(host_facts, "_read_cgroup_cpu_quota", return_value=None):
        facts = host_facts.collect_host_facts()

    assert facts["cpu_quota"] is None
    assert facts["effective_cpus"] == float(facts["cpu_count"])


def test_scheduler_wakes_more_often_than_the_reading_expires():
    """A wake interval equal to the TTL re-probes on every tick, forever.

    Detection spawns child processes that import an inference runtime, for
    facts that cannot change without a container restart. The scheduler must
    wake to check well within the reading's lifetime, so most wakes are a
    monotonic comparison and a probe runs only when the reading has expired.
    """
    from app.main import ACCEL_CAPS_REFRESH_SECONDS
    from app.services.classifier_service import CLASSIFIER_ACCEL_PROBE_TTL_SECONDS

    assert ACCEL_CAPS_REFRESH_SECONDS < CLASSIFIER_ACCEL_PROBE_TTL_SECONDS


def test_a_reading_is_stamped_when_detection_finishes_not_when_it_starts():
    """A reading stamped at probe start is born as old as the probe was slow.

    The probes carry five second timeouts apiece, so start-stamping makes a
    fresh reading look seconds old and trips the staleness rule early.
    """
    service = ClassifierService.__new__(ClassifierService)
    service._accel_caps = {}
    service._accel_caps_last_refreshed_monotonic = None
    service._accel_caps_ttl_seconds = 60.0

    clock = {"now": 1000.0}

    def probe_taking_ten_seconds() -> dict:
        clock["now"] += 10.0
        return {}

    with (
        patch(
            "app.services.classifier_service._detect_acceleration_capabilities",
            side_effect=probe_taking_ten_seconds,
        ),
        patch.object(classifier_service.time, "monotonic", side_effect=lambda: clock["now"]),
    ):
        service._refresh_accel_caps(force=True)
        age = service._accel_caps_age_seconds()

    assert age is not None and age < 5.0


def test_a_reading_refreshed_on_schedule_is_never_reported_stale():
    """The scheduler refreshes an expired reading at its next wake.

    A reading one wake interval past its TTL is on schedule; reporting it
    stale makes a healthy install flap and sends a reader chasing a
    hardware-detection fault that does not exist. Stale must mean the
    scheduler has actually missed.
    """
    service = ClassifierService.__new__(ClassifierService)
    service._accel_caps = {}
    service._accel_caps_ttl_seconds = 900.0

    with patch.object(classifier_service.time, "monotonic", return_value=1950.0):
        service._accel_caps_last_refreshed_monotonic = 1000.0  # expired, awaiting the next wake
        on_schedule = service.accel_caps_are_stale()
        service._accel_caps_last_refreshed_monotonic = 800.0  # several wakes have come and gone
        missed = service.accel_caps_are_stale()

    assert not on_schedule
    assert missed


def test_reload_does_not_run_model_init_on_the_event_loop():
    """A model reload loads the model in a worker thread, not on the loop.

    Saving settings with a changed provider triggers a reload from a request
    handler's background task, which runs on the event loop. Model init also
    re-detects hardware, which spawns subprocesses — the #313 stall, moved from
    the status read to the settings write, unless it leaves the loop.
    """
    service = ClassifierService.__new__(ClassifierService)
    service._models_lock = threading.Lock()
    service._models = {}
    service._worker_process_mode = False
    service._image_execution_mode = "in_process"
    service._classifier_supervisor = None
    service._video_supervisor = None

    init_threads: list[int] = []
    service._init_bird_model = lambda: init_threads.append(threading.get_ident())  # type: ignore[method-assign]

    async def reload_and_report_loop_thread() -> int:
        await service.reload_bird_model()
        return threading.get_ident()

    loop_thread = asyncio.run(reload_and_report_loop_thread())

    assert init_threads, "the reload never initialised the model"
    assert init_threads[0] != loop_thread


def test_the_probe_scheduler_never_builds_the_classifier():
    """A missing singleton is skipped, not constructed on the event loop.

    Constructing ClassifierService detects hardware and loads the model
    synchronously. If a failed reload leaves the singleton absent, the probe
    scheduler must wait for whoever owns construction, not rebuild it inline
    and stall every request.
    """
    with (
        patch.object(classifier_service, "_classifier_instance", None),
        patch.object(ClassifierService, "__init__", side_effect=AssertionError("constructed on the event loop")),
    ):
        asyncio.run(classifier_service.refresh_accel_caps_if_running())


def test_the_probe_scheduler_refreshes_a_running_classifier():
    service = MagicMock(refresh_accel_caps_off_request_path=AsyncMock())

    with patch.object(classifier_service, "_classifier_instance", service):
        asyncio.run(classifier_service.refresh_accel_caps_if_running())

    service.refresh_accel_caps_off_request_path.assert_awaited_once()


def test_settings_triggered_reload_builds_the_classifier_off_the_loop():
    """Rebuilding the classifier singleton must not happen on the event loop.

    Constructing ClassifierService detects hardware and loads the model
    synchronously, so the settings-save path has to do the construction in a
    worker thread.
    """
    built_threads: list[int] = []

    def record_build() -> MagicMock:
        built_threads.append(threading.get_ident())
        return MagicMock(reload_bird_model=AsyncMock())

    async def reload_and_report_loop_thread() -> int:
        with patch.object(classifier_service, "get_classifier", side_effect=record_build):
            await classifier_service.reload_classifier_out_of_band(full_restart=False)
        return threading.get_ident()

    loop_thread = asyncio.run(reload_and_report_loop_thread())

    assert built_threads, "the reload never touched the classifier singleton"
    assert built_threads[0] != loop_thread
