from __future__ import annotations

import math
from typing import Literal, TypedDict


ContinuousRetentionState = Literal["unset", "invalid", "disabled", "enabled"]
RecordingCameraIssue = Literal[
    "camera_disabled",
    "camera_not_found",
    "recordings_disabled",
    "record_stream_missing",
    "continuous_retention_disabled",
    "retention_unknown",
]
RecordingCapabilityReason = Literal[
    "config_unavailable",
    "no_matching_cameras",
    "recordings_disabled",
    "record_stream_missing",
    "continuous_retention_disabled",
    "camera_disabled",
    "camera_not_found",
    "partial_camera_coverage",
    "camera_configuration_incomplete",
    "retention_unknown",
]


class RecordingClipCapability(TypedDict):
    supported: bool
    reason: RecordingCapabilityReason | None
    recordings_enabled: bool
    retention_days: float | None
    eligible_cameras: list[str]
    ineligible_cameras: dict[str, RecordingCameraIssue]


def _parse_positive_days(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _continuous_retention_setting(record_cfg: object) -> tuple[ContinuousRetentionState, float | None]:
    """Return the explicitly configured Frigate continuous-retention state.

    Frigate 0.17 defaults ``record.continuous.days`` to zero. ``unset`` is kept
    distinct here so a camera can inherit the global record policy; once both
    levels are considered, an unset value is therefore treated as disabled.
    """
    if not isinstance(record_cfg, dict):
        return "unset", None

    continuous_cfg = record_cfg.get("continuous")
    if not isinstance(continuous_cfg, dict) or "days" not in continuous_cfg:
        return "unset", None

    value = continuous_cfg.get("days")
    if isinstance(value, bool):
        return "invalid", None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "invalid", None

    if not math.isfinite(parsed) or parsed < 0:
        return "invalid", None
    if parsed == 0:
        return "disabled", None
    return "enabled", parsed


def _collect_retain_days(node: object) -> list[float]:
    """Collect positive day values from retain-like Frigate config blocks."""
    if not isinstance(node, dict):
        return []
    values: list[float] = []

    for key in ("days", "default"):
        parsed = _parse_positive_days(node.get(key))
        if parsed is not None:
            values.append(parsed)

    objects_cfg = node.get("objects")
    if isinstance(objects_cfg, dict):
        for obj_val in objects_cfg.values():
            parsed = _parse_positive_days(obj_val)
            if parsed is not None:
                values.append(parsed)

    return values


def extract_record_retention_days(record_cfg: object) -> float | None:
    """Best-effort extraction of recording/event retention days from Frigate config."""
    if not isinstance(record_cfg, dict):
        return None

    candidates: list[float] = []
    direct_days = _parse_positive_days(record_cfg.get("days"))
    if direct_days is not None:
        candidates.append(direct_days)

    candidates.extend(_collect_retain_days(record_cfg.get("retain")))

    for key in ("detections", "alerts", "events"):
        section = record_cfg.get(key)
        if isinstance(section, dict):
            section_days = _parse_positive_days(section.get("days"))
            if section_days is not None:
                candidates.append(section_days)
            candidates.extend(_collect_retain_days(section.get("retain")))

    export_cfg = record_cfg.get("export")
    if isinstance(export_cfg, dict):
        candidates.extend(_collect_retain_days(export_cfg.get("retain")))

    return max(candidates) if candidates else None


def get_camera_retention_days(frigate_config: object, camera_name: str) -> float | None:
    if not isinstance(frigate_config, dict):
        return None

    candidates: list[float] = []
    global_record = extract_record_retention_days(frigate_config.get("record"))
    if global_record is not None:
        candidates.append(global_record)

    cameras = frigate_config.get("cameras")
    if isinstance(cameras, dict):
        camera_cfg = cameras.get(camera_name)
        if isinstance(camera_cfg, dict):
            camera_record = extract_record_retention_days(camera_cfg.get("record"))
            if camera_record is not None:
                candidates.append(camera_record)

    return max(candidates) if candidates else None


def _get_camera_continuous_retention_setting(
    frigate_config: object, camera_name: str
) -> tuple[ContinuousRetentionState, float | None]:
    if not isinstance(frigate_config, dict):
        return "invalid", None

    global_state, global_days = _continuous_retention_setting(frigate_config.get("record"))
    cameras_cfg = frigate_config.get("cameras")
    if isinstance(cameras_cfg, dict):
        camera_cfg = cameras_cfg.get(camera_name)
        if isinstance(camera_cfg, dict):
            camera_state, camera_days = _continuous_retention_setting(camera_cfg.get("record"))
            if camera_state != "unset":
                return camera_state, camera_days

    if global_state == "unset":
        return "disabled", None
    return global_state, global_days


def get_camera_continuous_retention_days(frigate_config: object, camera_name: str) -> float | None:
    """Return effective positive continuous-recording retention for a camera."""
    state, days = _get_camera_continuous_retention_setting(frigate_config, camera_name)
    return days if state == "enabled" else None


def _is_record_enabled(record_cfg: object, inherited: bool | None = None) -> bool | None:
    if isinstance(record_cfg, dict) and "enabled" in record_cfg:
        value = record_cfg.get("enabled")
        if isinstance(value, bool):
            return value
    return inherited


def _has_record_role(camera_cfg: object) -> bool:
    if not isinstance(camera_cfg, dict):
        return False
    ffmpeg_cfg = camera_cfg.get("ffmpeg")
    if not isinstance(ffmpeg_cfg, dict):
        return False
    inputs = ffmpeg_cfg.get("inputs")
    if not isinstance(inputs, list):
        return False
    for input_cfg in inputs:
        if not isinstance(input_cfg, dict):
            continue
        roles = input_cfg.get("roles")
        if isinstance(roles, list) and "record" in roles:
            return True
    return False


def _selected_camera_names(selected_cameras: list[str] | None) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for camera in selected_cameras or []:
        if not isinstance(camera, str):
            continue
        normalized = camera.strip()
        if not normalized or normalized in seen:
            continue
        names.append(normalized)
        seen.add(normalized)
    return names


def evaluate_recording_clip_capability(
    frigate_config: object,
    selected_cameras: list[str] | None,
) -> RecordingClipCapability:
    if not isinstance(frigate_config, dict):
        return {
            "supported": False,
            "reason": "config_unavailable",
            "recordings_enabled": False,
            "retention_days": None,
            "eligible_cameras": [],
            "ineligible_cameras": {},
        }

    cameras_cfg = frigate_config.get("cameras")
    if not isinstance(cameras_cfg, dict):
        cameras_cfg = {}

    requested_cameras = _selected_camera_names(selected_cameras)
    relevant_cameras = requested_cameras or [camera for camera in cameras_cfg.keys() if isinstance(camera, str)]

    if not relevant_cameras:
        return {
            "supported": False,
            "reason": "no_matching_cameras",
            "recordings_enabled": False,
            "retention_days": None,
            "eligible_cameras": [],
            "ineligible_cameras": {},
        }

    global_record_cfg = frigate_config.get("record")
    global_record_enabled = _is_record_enabled(global_record_cfg, None)

    eligible_cameras: list[str] = []
    ineligible_cameras: dict[str, RecordingCameraIssue] = {}
    retention_candidates: list[float] = []
    any_recordings_enabled = False

    for camera in relevant_cameras:
        camera_cfg = cameras_cfg.get(camera)
        if not isinstance(camera_cfg, dict):
            ineligible_cameras[camera] = "camera_not_found"
            continue
        if camera_cfg.get("enabled") is False:
            ineligible_cameras[camera] = "camera_disabled"
            continue

        camera_record_cfg = camera_cfg.get("record") if isinstance(camera_cfg, dict) else None
        camera_record_enabled = _is_record_enabled(camera_record_cfg, global_record_enabled)

        if camera_record_enabled is not True:
            ineligible_cameras[camera] = "recordings_disabled"
            continue

        any_recordings_enabled = True
        if not _has_record_role(camera_cfg):
            ineligible_cameras[camera] = "record_stream_missing"
            continue

        retention_state, retention_days = _get_camera_continuous_retention_setting(frigate_config, camera)
        if retention_state == "invalid":
            ineligible_cameras[camera] = "retention_unknown"
            continue
        if retention_state != "enabled" or retention_days is None:
            ineligible_cameras[camera] = "continuous_retention_disabled"
            continue

        eligible_cameras.append(camera)
        retention_candidates.append(retention_days)

    if len(eligible_cameras) == len(relevant_cameras):
        return {
            "supported": True,
            "reason": None,
            "recordings_enabled": True,
            "retention_days": min(retention_candidates),
            "eligible_cameras": eligible_cameras,
            "ineligible_cameras": ineligible_cameras,
        }

    if eligible_cameras:
        reason = "partial_camera_coverage"
    else:
        camera_reasons = set(ineligible_cameras.values())
        reason: RecordingCapabilityReason = (
            next(iter(camera_reasons)) if len(camera_reasons) == 1 else "camera_configuration_incomplete"
        )

    return {
        "supported": False,
        "reason": reason,
        "recordings_enabled": any_recordings_enabled,
        "retention_days": min(retention_candidates) if retention_candidates else None,
        "eligible_cameras": eligible_cameras,
        "ineligible_cameras": ineligible_cameras,
    }
