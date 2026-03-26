from __future__ import annotations

from typing import Any


def _parse_positive_days(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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


def _is_record_enabled(record_cfg: object, inherited: bool | None = None) -> bool | None:
    if isinstance(record_cfg, dict) and "enabled" in record_cfg:
        value = record_cfg.get("enabled")
        if isinstance(value, bool):
            return value
    return inherited


def evaluate_recording_clip_capability(
    frigate_config: object,
    selected_cameras: list[str] | None,
) -> dict[str, Any]:
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

    requested_cameras = [camera for camera in (selected_cameras or []) if isinstance(camera, str) and camera.strip()]
    if requested_cameras:
        relevant_cameras = [camera for camera in requested_cameras if camera in cameras_cfg]
    else:
        relevant_cameras = [camera for camera in cameras_cfg.keys() if isinstance(camera, str)]

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
    ineligible_cameras: dict[str, str] = {}
    retention_candidates: list[float] = []
    any_recordings_enabled = False

    for camera in relevant_cameras:
        camera_cfg = cameras_cfg.get(camera)
        camera_record_cfg = camera_cfg.get("record") if isinstance(camera_cfg, dict) else None
        camera_record_enabled = _is_record_enabled(camera_record_cfg, global_record_enabled)

        if camera_record_enabled is not True:
            ineligible_cameras[camera] = "recordings_disabled"
            continue

        any_recordings_enabled = True
        retention_days = get_camera_retention_days(frigate_config, camera)
        if retention_days is None:
            ineligible_cameras[camera] = "retention_unknown"
            continue

        eligible_cameras.append(camera)
        retention_candidates.append(retention_days)

    if eligible_cameras:
        return {
            "supported": True,
            "reason": None,
            "recordings_enabled": True,
            "retention_days": max(retention_candidates),
            "eligible_cameras": eligible_cameras,
            "ineligible_cameras": ineligible_cameras,
        }

    return {
        "supported": False,
        "reason": "retention_unknown" if any_recordings_enabled else "recordings_disabled",
        "recordings_enabled": any_recordings_enabled,
        "retention_days": max(retention_candidates) if retention_candidates else None,
        "eligible_cameras": [],
        "ineligible_cameras": ineligible_cameras,
    }
