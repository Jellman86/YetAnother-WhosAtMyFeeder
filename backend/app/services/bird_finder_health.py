"""Operational evidence for expensive last-resort RF-DETR CPU use."""

from typing import Any

RFDETR_FINDER = "bird_crop_detector_accurate_rfdetr_nano"


def finder_cpu_problem(
    status: dict[str, Any], *, planned_provider: str, available_accelerators: set[str] | frozenset[str] = frozenset()
) -> dict[str, Any]:
    model_id = str(status.get("model_id") or "")
    execution = status.get("last_execution") or {}
    provider = str(execution.get("provider") or planned_provider)
    active = (
        model_id == RFDETR_FINDER
        and bool(status.get("healthy"))
        and provider in {"cpu", "intel_cpu"}
        and bool(available_accelerators)
        and status.get("requested_provider") != "cpu"
    )
    selected_cpu = status.get("requested_provider") in {"cpu", "intel_cpu"}
    reason = str(
        execution.get("fallback_reason")
        or ("CPU was selected for this finder." if selected_cpu else "No current passing NPU or GPU evidence.")
    )
    check = status.get("device_check") or {}
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
