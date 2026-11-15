"""Operational evidence for expensive last-resort RF-DETR CPU use."""

from datetime import datetime, timezone
import os
from typing import Any

RFDETR_FINDER = "bird_crop_detector_accurate_rfdetr_nano"
CPU_PROVIDERS = frozenset({"cpu", "intel_cpu"})
# The container sees these nodes only when the host passed the device through.
_INTEL_DEVICE_NODES = (("intel_npu", "/dev/accel"), ("intel_gpu", "/dev/dri"))


def present_accelerators() -> set[str]:
    """Accelerators this container can reach, whatever the image packages.

    CUDA visibility is decided by its runtime probe, not a device node, so it
    is never ruled out here.
    """
    return {provider for provider, node in _INTEL_DEVICE_NODES if os.path.isdir(node)} | {"cuda"}


def _parsed(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def check_passed_after_execution(execution: dict[str, Any], check: dict[str, Any]) -> bool:
    """A newer passing check outranks the last frame's provider until the next frame runs."""
    if check.get("state") != "succeeded":
        return False
    checked = _parsed(check.get("checked_at"))
    executed = _parsed(execution.get("checked_at"))
    return checked is not None and (executed is None or checked > executed)


def finder_cpu_problem(
    status: dict[str, Any], *, planned_provider: str, available_accelerators: set[str] | frozenset[str] = frozenset()
) -> dict[str, Any]:
    model_id = str(status.get("model_id") or "")
    check = status.get("device_check") or {}
    execution = status.get("last_execution") or {}
    if execution and check_passed_after_execution(execution, check):
        execution = {}
    provider = str(execution.get("provider") or planned_provider)
    selected_cpu = status.get("requested_provider") in CPU_PROVIDERS
    active = (
        model_id == RFDETR_FINDER
        and bool(status.get("healthy"))
        and provider in CPU_PROVIDERS
        and bool(available_accelerators)
        and not selected_cpu
    )
    reason = str(
        execution.get("fallback_reason")
        or ("CPU was selected for this finder." if selected_cpu else "No current passing NPU or GPU evidence.")
    )
    if not execution.get("fallback_reason") and check.get("reason"):
        reason = str(check["reason"])
    if check.get("reason_code") == "no_positive_baseline" and not execution.get("fallback_reason"):
        reason = "The CPU found no admitted birds in the saved photos, so NPU/GPU agreement could not be checked."
    return {
        "active": active,
        "model_id": model_id,
        "provider": provider,
        "reason": reason if active else None,
        "reason_code": str(execution.get("fallback_reason") or check.get("reason_code") or "accelerator_unverified")
        if active
        else None,
        "action": "Check devices for RF-DETR Nano in Settings. Review NPU/GPU driver access and the saved check result."
        if active
        else None,
    }
