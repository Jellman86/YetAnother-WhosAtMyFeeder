"""Bounded summaries of tensors and runtime exceptions for status and logs."""

from typing import Any

import numpy as np

from app.services.classifier_worker_protocol import GPU_RUNTIME_FAILURE_CODES


def summarize_numeric_array(values: np.ndarray, *, name: str) -> dict[str, Any]:
    arr = np.asarray(values)
    finite_mask = np.isfinite(arr)
    finite_values = arr[finite_mask]
    invalid_output_kind: str | None = None
    if arr.size == 0:
        invalid_output_kind = "empty"
    elif finite_values.size == 0:
        if np.isnan(arr).any():
            invalid_output_kind = "all_nan"
        elif np.isinf(arr).any():
            invalid_output_kind = "all_inf"
        else:
            invalid_output_kind = "no_finite"
    elif not finite_mask.all():
        invalid_output_kind = "mixed_non_finite"
    summary: dict[str, Any] = {
        "name": str(name),
        "shape": [int(dim) for dim in arr.shape],
        "dtype": str(arr.dtype),
        "element_count": int(arr.size),
        "finite_count": int(finite_mask.sum()),
        "nan_count": int(np.isnan(arr).sum()),
        "pos_inf_count": int(np.isposinf(arr).sum()),
        "neg_inf_count": int(np.isneginf(arr).sum()),
        "invalid_output_kind": invalid_output_kind,
    }
    if finite_values.size:
        summary["finite_min"] = float(finite_values.min())
        summary["finite_max"] = float(finite_values.max())
        summary["finite_mean"] = float(finite_values.mean())
    else:
        summary["finite_min"] = None
        summary["finite_max"] = None
        summary["finite_mean"] = None
    return summary


def gpu_runtime_failure_code(source: object) -> str | None:
    """First device-level OpenCL failure code in an exception, its cause
    chain, or a detail string. Recognition happens on the untruncated text:
    a code buried past a summary limit still retires the worker (#721)."""
    texts: list[str] = []
    if isinstance(source, BaseException):
        seen: set[int] = set()
        current: BaseException | None = source
        while current is not None and len(texts) < 6 and id(current) not in seen:
            seen.add(id(current))
            texts.append(str(current)[:20_000])
            current = current.__cause__ or current.__context__
    else:
        texts.append(str(source)[:20_000])
    joined = " ".join(texts)
    found = [(joined.index(code), code) for code in GPU_RUNTIME_FAILURE_CODES if code in joined]
    return min(found)[1] if found else None


def summarize_runtime_exception(exc: Exception, *, max_len: int = 280) -> str:
    message = f"{type(exc).__name__}: {exc}"
    message = " ".join(message.split())
    code = gpu_runtime_failure_code(exc)
    if code and code not in message:
        message = f"{code}: {message}"
    if len(message) > max_len:
        truncated = f"{message[: max_len - 1]}…"
        if code and code not in truncated:
            truncated = f"{code}: {message}"[: max_len - 1] + "…"
        return truncated
    return message
