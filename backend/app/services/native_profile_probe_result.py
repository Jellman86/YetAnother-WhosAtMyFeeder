"""Allow-listed failure reports shared by the diagnostic child and parent."""

from __future__ import annotations

from typing import Any

from app.services.classifier_worker_protocol import GPU_RUNTIME_FAILURE_CODES, ClassifierWorkerRetirementError

_FAILURE_MESSAGES = {
    "missing_outputs": "At least three representative inference outputs are required. Choose three readable bird photos.",
    "invalid_outputs": "The diagnostic produced missing, nonfinite or uniform output. Review the model/runtime before retrying.",
    "output_dimensions_changed": "The diagnostic output dimensions changed. Review the selected model/runtime before retrying.",
    "indistinguishable_photos": "Different representative photos produced indistinguishable output. Choose distinct bird photos and review the model/runtime.",
    "no_pipeline_result": "The normal classification pipeline returned no result. Review the selected model and representative inputs.",
    "invalid_scores": "The normal classification pipeline produced invalid scores. Review the selected model/runtime before retrying.",
    "profile_changed": "The probe did not keep the exact requested provider and artifact. Review the selected model/provider before retrying.",
    "invalid_photo": "A representative photo could not be decoded within the image limits. Choose readable bird photos.",
    "invalid_clip": "Choose a readable short clip with at least three bounded frames.",
    "video_decode_failed": "The representative video frames could not be decoded. Choose a different short bird clip.",
    "crop_check_failed": "A configured crop detector failed its representative check. Review its model/provider before retrying.",
    "device_failure": "The GPU reported a device-level failure. Review the device/runtime incident before retrying.",
    "unexpected_failure": "The isolated diagnostic could not finish. Review the runtime and representative inputs before retrying.",
}


class ProfileProbeFailure(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(_FAILURE_MESSAGES[reason])


def failure_details(error: Exception) -> dict[str, str]:
    if isinstance(error, ProfileProbeFailure):
        return {"reason": error.reason}
    if isinstance(error, ClassifierWorkerRetirementError):
        details = {"reason": "device_failure"}
        if error.error_code in GPU_RUNTIME_FAILURE_CODES:
            details["device_code"] = error.error_code
        return details
    return {"reason": "unexpected_failure"}


def failure_message(details: Any) -> str | None:
    if not isinstance(details, dict) or set(details) - {"reason", "device_code"}:
        return None
    reason = details.get("reason")
    if not isinstance(reason, str) or reason not in _FAILURE_MESSAGES:
        return None
    code = details.get("device_code")
    if code is not None and (reason != "device_failure" or code not in GPU_RUNTIME_FAILURE_CODES):
        return None
    message = _FAILURE_MESSAGES[reason]
    if code is not None:
        message += f" Device code: {code}."
    return message + " The profile remains blocked."
