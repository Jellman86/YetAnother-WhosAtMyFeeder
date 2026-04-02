import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path("/config/workspace/YA-WAMF/scripts/run_issue33_harness.py")
spec = importlib.util.spec_from_file_location("run_issue33_harness", SCRIPT_PATH)
issue33 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = issue33
assert spec.loader is not None
spec.loader.exec_module(issue33)


def test_build_thresholds_sets_issue33_specific_limits():
    parser = issue33._build_arg_parser()
    args = parser.parse_args(
        [
            "--min-reconnect-delta",
            "2",
            "--max-video-pending",
            "15",
            "--max-video-failure-count-delta",
            "1",
        ]
    )

    thresholds = issue33._build_thresholds(args)

    assert thresholds.min_topic_liveness_reconnects_delta == 2
    assert thresholds.allow_video_circuit_open is False
    assert thresholds.max_video_pending == 15
    assert thresholds.max_video_failure_count_delta == 1


def test_build_thresholds_defaults_to_zero_frigate_growth_requirement():
    parser = issue33._build_arg_parser()
    args = parser.parse_args([])

    thresholds = issue33._build_thresholds(args)

    assert thresholds.min_frigate_messages_delta == 0


def test_should_stop_frigate_publisher_after_configured_delay():
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=29.9, stop_after_seconds=30.0) is False
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=30.0, stop_after_seconds=30.0) is True
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=120.0, stop_after_seconds=0.0) is False


def test_normalize_issue33_evaluation_accepts_induced_stall_when_reconnect_occurs():
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "Frigate topic message growth below threshold (-163 < 1).",
            "Frigate stream stalled while BirdNET remained active (1 incident(s)).",
        ],
        "topic_liveness_reconnects_delta": 1,
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=True,
    )

    assert normalized["passed"] is True
    assert normalized["failure_reasons"] == []


def test_normalize_issue33_evaluation_keeps_failures_without_induced_stall():
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "Frigate stream stalled while BirdNET remained active (1 incident(s)).",
        ],
        "topic_liveness_reconnects_delta": 1,
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=False,
    )

    assert normalized["passed"] is False
    assert normalized["failure_reasons"] == [
        "Frigate stream stalled while BirdNET remained active (1 incident(s)).",
    ]
