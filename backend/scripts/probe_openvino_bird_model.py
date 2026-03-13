#!/usr/bin/env python3
"""Probe the active bird model on OpenVINO CPU/GPU and summarize outputs."""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np
from PIL import Image

from app.services.classifier_service import OpenVINOModelInstance
from app.services.model_manager import REMOTE_REGISTRY, model_manager


def _json_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 8)


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return str(value)


def summarize_array(array: np.ndarray, *, name: str) -> dict[str, Any]:
    arr = np.asarray(array)
    finite_mask = np.isfinite(arr)
    finite_values = arr[finite_mask]
    return {
        "name": name,
        "shape": [int(dim) for dim in arr.shape],
        "dtype": str(arr.dtype),
        "element_count": int(arr.size),
        "finite_count": int(finite_mask.sum()),
        "nan_count": int(np.isnan(arr).sum()),
        "pos_inf_count": int(np.isposinf(arr).sum()),
        "neg_inf_count": int(np.isneginf(arr).sum()),
        "finite_min": _json_float(float(finite_values.min())) if finite_values.size else None,
        "finite_max": _json_float(float(finite_values.max())) if finite_values.size else None,
        "finite_mean": _json_float(float(finite_values.mean())) if finite_values.size else None,
    }


def compare_probe_outputs(cpu_output: np.ndarray, gpu_output: np.ndarray) -> dict[str, Any]:
    cpu_arr = np.asarray(cpu_output)
    gpu_arr = np.asarray(gpu_output)
    shape_matches = cpu_arr.shape == gpu_arr.shape
    comparison: dict[str, Any] = {
        "shape_matches": shape_matches,
        "cpu_shape": [int(dim) for dim in cpu_arr.shape],
        "gpu_shape": [int(dim) for dim in gpu_arr.shape],
    }
    if shape_matches:
        diff = np.abs(cpu_arr.astype(np.float32) - gpu_arr.astype(np.float32))
        comparison["max_abs_diff"] = _json_float(float(diff.max())) if diff.size else 0.0
        comparison["mean_abs_diff"] = _json_float(float(diff.mean())) if diff.size else 0.0
    else:
        comparison["max_abs_diff"] = None
        comparison["mean_abs_diff"] = None
    return comparison


def resolve_active_bird_model_spec() -> dict[str, Any]:
    model_path, labels_path, input_size = model_manager.get_active_model_paths()
    active_model_id = getattr(model_manager, "active_model_id", "unknown")
    metadata = next((m for m in REMOTE_REGISTRY if m["id"] == active_model_id), None) or {}
    return {
        "model_id": active_model_id,
        "model_path": model_path,
        "labels_path": labels_path,
        "input_size": int(input_size),
        "preprocessing": dict(metadata.get("preprocessing") or {}),
    }


def build_probe_model(spec: dict[str, Any], device: str) -> OpenVINOModelInstance:
    return OpenVINOModelInstance(
        "bird",
        str(spec["model_path"]),
        str(spec["labels_path"]),
        preprocessing=spec.get("preprocessing"),
        input_size=int(spec.get("input_size") or 384),
        device_name=str(device),
    )


def _collect_compile_properties(model: Any) -> dict[str, Any]:
    compiled_model = getattr(model, "compiled_model", None)
    if compiled_model is None:
        return {}
    props: dict[str, Any] = {}
    for name in ("INFERENCE_PRECISION_HINT", "NUM_STREAMS", "PERFORMANCE_HINT", "EXECUTION_DEVICES"):
        try:
            value = compiled_model.get_property(name)
            props[name] = _json_safe_value(value)
        except Exception as exc:
            props[name] = f"ERROR: {exc}"
    return props


def _build_probe_image(input_size: int) -> Image.Image:
    width = max(8, int(input_size))
    height = max(8, int(input_size))
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(255, 0, height, dtype=np.uint8)
    red = np.tile(x, (height, 1))
    green = np.tile(y[:, None], (1, width))
    blue = np.full((height, width), 127, dtype=np.uint8)
    rgb = np.stack((red, green, blue), axis=2)
    return Image.fromarray(rgb, mode="RGB")


def probe_openvino_bird_model(device: str = "GPU") -> dict[str, Any]:
    spec = resolve_active_bird_model_spec()
    model = build_probe_model(spec, device)
    loaded = bool(model.load())
    report: dict[str, Any] = {
        "device": str(device),
        "model": {
            "model_id": spec["model_id"],
            "model_path": spec["model_path"],
            "labels_path": spec["labels_path"],
            "input_size": int(spec["input_size"]),
            "preprocessing": dict(spec.get("preprocessing") or {}),
        },
        "compile": {
            "ok": loaded,
            "error": getattr(model, "error", None),
            "properties": _collect_compile_properties(model) if loaded else {},
        },
    }
    if not loaded:
        return report

    image = _build_probe_image(int(spec["input_size"]))
    input_tensor = np.asarray(model._preprocess(image))
    output = np.asarray(model._infer_logits(image))
    report["input_summary"] = summarize_array(input_tensor, name="input_tensor")
    report["output_summary"] = summarize_array(output, name="output_logits")
    return report


def probe_openvino_bird_model_pair() -> dict[str, Any]:
    cpu_report = probe_openvino_bird_model("CPU")
    gpu_report = probe_openvino_bird_model("GPU")
    pair = {
        "cpu": cpu_report,
        "gpu": gpu_report,
    }
    if "output_summary" not in cpu_report or "output_summary" not in gpu_report:
        return pair

    cpu_model = build_probe_model(resolve_active_bird_model_spec(), "CPU")
    gpu_model = build_probe_model(resolve_active_bird_model_spec(), "GPU")
    if not cpu_model.load() or not gpu_model.load():
        return pair
    image = _build_probe_image(int(resolve_active_bird_model_spec()["input_size"]))
    pair["comparison"] = compare_probe_outputs(cpu_model._infer_logits(image), gpu_model._infer_logits(image))
    return pair


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the active bird model with OpenVINO")
    parser.add_argument("--device", choices=["CPU", "GPU"], default="GPU")
    parser.add_argument("--compare-cpu-gpu", action="store_true")
    args = parser.parse_args()

    if args.compare_cpu_gpu:
        report = probe_openvino_bird_model_pair()
    else:
        report = probe_openvino_bird_model(device=args.device)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
