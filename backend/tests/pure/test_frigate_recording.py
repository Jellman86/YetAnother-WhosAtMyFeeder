from app.utils.frigate_recording import (
    evaluate_recording_clip_capability,
    get_camera_continuous_retention_days,
)


def _camera(*, record_days: float | None = None, record_enabled: bool = True, record_role: bool = True) -> dict:
    camera: dict = {
        "enabled": True,
        "ffmpeg": {
            "inputs": [
                {
                    "path": "rtsp://camera.example/stream",
                    "roles": ["detect", "record"] if record_role else ["detect"],
                }
            ]
        },
        "record": {"enabled": record_enabled},
    }
    if record_days is not None:
        camera["record"]["continuous"] = {"days": record_days}
    return camera


def test_event_only_retention_is_not_continuous_clip_coverage():
    config = {
        "record": {
            "enabled": True,
            "continuous": {"days": 0},
            "alerts": {"retain": {"days": 30, "mode": "all"}},
            "detections": {"retain": {"days": 7, "mode": "all"}},
        },
        "cameras": {"birdcam": _camera()},
    }

    capability = evaluate_recording_clip_capability(config, ["birdcam"])

    assert capability == {
        "supported": False,
        "reason": "continuous_retention_disabled",
        "recordings_enabled": True,
        "retention_days": None,
        "eligible_cameras": [],
        "ineligible_cameras": {"birdcam": "continuous_retention_disabled"},
    }


def test_camera_continuous_retention_overrides_global_retention():
    config = {
        "record": {"enabled": True, "continuous": {"days": 3}},
        "cameras": {
            "birdcam": _camera(record_days=1),
            "nestcam": _camera(),
        },
    }

    assert get_camera_continuous_retention_days(config, "birdcam") == 1
    assert get_camera_continuous_retention_days(config, "nestcam") == 3


def test_explicit_zero_camera_retention_disables_global_continuous_retention():
    config = {
        "record": {"enabled": True, "continuous": {"days": 3}},
        "cameras": {"birdcam": _camera(record_days=0)},
    }

    capability = evaluate_recording_clip_capability(config, ["birdcam"])

    assert get_camera_continuous_retention_days(config, "birdcam") is None
    assert capability["supported"] is False
    assert capability["reason"] == "continuous_retention_disabled"


def test_all_selected_cameras_need_continuous_coverage():
    config = {
        "record": {"enabled": True, "continuous": {"days": 0}},
        "cameras": {
            "birdcam": _camera(record_days=2),
            "nestcam": _camera(),
        },
    }

    capability = evaluate_recording_clip_capability(config, ["birdcam", "nestcam"])

    assert capability["supported"] is False
    assert capability["reason"] == "partial_camera_coverage"
    assert capability["retention_days"] == 2
    assert capability["eligible_cameras"] == ["birdcam"]
    assert capability["ineligible_cameras"] == {"nestcam": "continuous_retention_disabled"}


def test_retention_reports_the_minimum_guaranteed_across_selected_cameras():
    config = {
        "record": {"enabled": True, "continuous": {"days": 7}},
        "cameras": {
            "birdcam": _camera(record_days=1),
            "nestcam": _camera(record_days=3),
        },
    }

    capability = evaluate_recording_clip_capability(config, ["birdcam", "nestcam"])

    assert capability["supported"] is True
    assert capability["retention_days"] == 1
    assert capability["eligible_cameras"] == ["birdcam", "nestcam"]


def test_record_role_is_required_even_when_recording_is_enabled():
    config = {
        "record": {"enabled": True, "continuous": {"days": 1}},
        "cameras": {"birdcam": _camera(record_role=False)},
    }

    capability = evaluate_recording_clip_capability(config, ["birdcam"])

    assert capability["supported"] is False
    assert capability["reason"] == "record_stream_missing"
    assert capability["ineligible_cameras"] == {"birdcam": "record_stream_missing"}


def test_disabled_and_missing_selected_cameras_are_reported_individually():
    disabled_camera = _camera()
    disabled_camera["enabled"] = False
    config = {
        "record": {"enabled": True, "continuous": {"days": 1}},
        "cameras": {"birdcam": disabled_camera},
    }

    capability = evaluate_recording_clip_capability(config, ["birdcam", "old_camera"])

    assert capability["supported"] is False
    assert capability["reason"] == "camera_configuration_incomplete"
    assert capability["ineligible_cameras"] == {
        "birdcam": "camera_disabled",
        "old_camera": "camera_not_found",
    }
