"""Per-camera health read from Frigate's stats feed, without trusting its JSON shape."""

import math
import re
from datetime import datetime, timezone
from typing import Literal

from app.models.system_status import CameraHealth, CameraHealthReading

CAMERA_STATS_TIMEOUT_SECONDS = 10.0
CAMERA_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")


def validate_camera_name(camera: str) -> bool:
    return bool(CAMERA_NAME_PATTERN.match(camera)) and len(camera) <= 64


def finite_camera_metric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        metric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return metric if math.isfinite(metric) and metric >= 0 else None


def parse_camera_stats(payload: object) -> list[CameraHealth]:
    raw_cameras = payload.get("cameras") if isinstance(payload, dict) else None
    cameras: list[CameraHealth] = []
    if not isinstance(raw_cameras, dict):
        return cameras
    for camera, raw_metrics in raw_cameras.items():
        if not isinstance(camera, str) or not validate_camera_name(camera):
            continue
        metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
        camera_fps = finite_camera_metric(metrics.get("camera_fps"))
        status: Literal["online", "offline", "unknown"]
        if camera_fps is None:
            status = "unknown"
        elif camera_fps > 0:
            status = "online"
        else:
            status = "offline"
        cameras.append(
            CameraHealth(
                camera=camera,
                status=status,
                camera_fps=camera_fps,
                process_fps=finite_camera_metric(metrics.get("process_fps")),
                detection_fps=finite_camera_metric(metrics.get("detection_fps")),
            )
        )
    return cameras


async def read_camera_health() -> CameraHealthReading:
    """Ask Frigate once. Raises what the client raises; the caller decides what a failure means."""
    from app.services.frigate_client import frigate_client

    resp = await frigate_client.get("api/stats", timeout=CAMERA_STATS_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return CameraHealthReading(
        cameras=parse_camera_stats(resp.json()),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
