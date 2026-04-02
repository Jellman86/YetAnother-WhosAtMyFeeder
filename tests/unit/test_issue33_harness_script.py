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


def test_should_stop_frigate_publisher_after_configured_delay():
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=29.9, stop_after_seconds=30.0) is False
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=30.0, stop_after_seconds=30.0) is True
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=120.0, stop_after_seconds=0.0) is False
