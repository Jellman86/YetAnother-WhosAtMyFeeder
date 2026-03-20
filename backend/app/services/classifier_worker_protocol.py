import json
from typing import Any


_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "ready": ("worker_generation",),
    "heartbeat": ("worker_generation", "busy"),
    "result": ("worker_generation", "request_id", "work_id", "lease_token", "results"),
    "error": ("worker_generation", "request_id", "work_id", "lease_token", "error"),
    "runtime_recovery": ("worker_generation", "request_id", "work_id", "lease_token", "recovery"),
    "progress": ("worker_generation", "request_id", "work_id", "lease_token", "current_frame", "total_frames", "frame_score", "top_label"),
    "classify": ("worker_generation", "request_id", "work_id", "lease_token", "image_b64"),
    "classify_video": ("worker_generation", "request_id", "work_id", "lease_token", "video_path"),
    "shutdown": (),
}


def encode_protocol_message(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def decode_protocol_message(raw: bytes | str) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        payload = json.loads(decoded)
    except Exception as exc:  # pragma: no cover - exercised by malformed payload test
        raise ValueError("invalid protocol message") from exc

    if not isinstance(payload, dict):
        raise ValueError("protocol message must be an object")

    message_type = payload.get("type")
    if not isinstance(message_type, str) or message_type not in _REQUIRED_FIELDS:
        raise ValueError("protocol message type is invalid")

    for field in _REQUIRED_FIELDS[message_type]:
        if field not in payload:
            raise ValueError(f"protocol message missing required field: {field}")

    return payload


def build_ready_event(*, worker_generation: int) -> dict[str, Any]:
    return {
        "type": "ready",
        "worker_generation": int(worker_generation),
    }


def build_heartbeat_event(
    *,
    worker_generation: int,
    request_id: str | None = None,
    busy: bool = False,
) -> dict[str, Any]:
    message = {
        "type": "heartbeat",
        "worker_generation": int(worker_generation),
        "busy": bool(busy),
    }
    if request_id:
        message["request_id"] = str(request_id)
    return message


def build_result_event(
    *,
    worker_generation: int,
    request_id: str,
    work_id: str,
    lease_token: int,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "result",
        "worker_generation": int(worker_generation),
        "request_id": str(request_id),
        "work_id": str(work_id),
        "lease_token": int(lease_token),
        "results": list(results),
    }


def build_error_event(
    *,
    worker_generation: int,
    request_id: str,
    work_id: str,
    lease_token: int,
    error: str,
) -> dict[str, Any]:
    return {
        "type": "error",
        "worker_generation": int(worker_generation),
        "request_id": str(request_id),
        "work_id": str(work_id),
        "lease_token": int(lease_token),
        "error": str(error),
    }


def build_runtime_recovery_event(
    *,
    worker_generation: int,
    request_id: str,
    work_id: str,
    lease_token: int,
    recovery: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "runtime_recovery",
        "worker_generation": int(worker_generation),
        "request_id": str(request_id),
        "work_id": str(work_id),
        "lease_token": int(lease_token),
        "recovery": dict(recovery),
    }


def build_classify_request(
    *,
    worker_generation: int,
    request_id: str,
    work_id: str,
    lease_token: int,
    image_b64: str,
    camera_name: str | None,
    model_id: str | None,
    input_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message = {
        "type": "classify",
        "worker_generation": int(worker_generation),
        "request_id": str(request_id),
        "work_id": str(work_id),
        "lease_token": int(lease_token),
        "image_b64": str(image_b64),
    }
    if camera_name is not None:
        message["camera_name"] = str(camera_name)
    if model_id is not None:
        message["model_id"] = str(model_id)
    if input_context is not None:
        message["input_context"] = dict(input_context)
    return message


def build_classify_video_request(
    *,
    worker_generation: int,
    request_id: str,
    work_id: str,
    lease_token: int,
    video_path: str,
    stride: int = 5,
    max_frames: int | None = None,
) -> dict[str, Any]:
    message = {
        "type": "classify_video",
        "worker_generation": int(worker_generation),
        "request_id": str(request_id),
        "work_id": str(work_id),
        "lease_token": int(lease_token),
        "video_path": str(video_path),
        "stride": int(stride),
    }
    if max_frames is not None:
        message["max_frames"] = int(max_frames)
    return message


def build_progress_event(
    *,
    worker_generation: int,
    request_id: str,
    work_id: str,
    lease_token: int,
    current_frame: int,
    total_frames: int,
    frame_score: float,
    top_label: str,
    frame_thumb: str | None = None,
    frame_index: int | None = None,
    clip_total: int | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    message = {
        "type": "progress",
        "worker_generation": int(worker_generation),
        "request_id": str(request_id),
        "work_id": str(work_id),
        "lease_token": int(lease_token),
        "current_frame": int(current_frame),
        "total_frames": int(total_frames),
        "frame_score": float(frame_score),
        "top_label": str(top_label),
    }
    if frame_thumb is not None:
        message["frame_thumb"] = str(frame_thumb)
    if frame_index is not None:
        message["frame_index"] = int(frame_index)
    if clip_total is not None:
        message["clip_total"] = int(clip_total)
    if model_name is not None:
        message["model_name"] = str(model_name)
    return message


def build_shutdown_request() -> dict[str, Any]:
    return {"type": "shutdown"}
