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

from unittest.mock import patch

from app.services.classifier_service import ClassifierService


class _Probeless:
    """A classifier whose capability cache is stale and must not refresh inline."""


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
