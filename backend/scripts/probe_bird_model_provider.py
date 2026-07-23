#!/usr/bin/env python3
"""Probe the active bird model on one concrete inference provider.

This process is intentionally disposable. Provider compilation and inference can
crash inside native GPU/NPU runtimes; keeping each target in its own process means
the API and the live classifier survive a bad driver or model/provider pairing.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.services.classifier_service import ModelInstance, ONNXModelInstance, OpenVINOModelInstance
from app.services.model_manager import model_manager


def _summarize_array(array: np.ndarray, *, name: str) -> dict[str, Any]:
    values = np.asarray(array)
    finite = np.isfinite(values)
    finite_values = values[finite]
    return {
        "name": name,
        "shape": [int(dim) for dim in values.shape],
        "dtype": str(values.dtype),
        "element_count": int(values.size),
        "finite_count": int(finite.sum()),
        "nan_count": int(np.isnan(values).sum()),
        "pos_inf_count": int(np.isposinf(values).sum()),
        "neg_inf_count": int(np.isneginf(values).sum()),
        "finite_min": float(finite_values.min()) if finite_values.size else None,
        "finite_max": float(finite_values.max()) if finite_values.size else None,
    }


def _build_probe_image(input_size: int) -> Image.Image:
    size = max(8, int(input_size))
    x = np.linspace(0, 255, size, dtype=np.uint8)
    y = np.linspace(255, 0, size, dtype=np.uint8)
    rgb = np.stack(
        (
            np.tile(x, (size, 1)),
            np.tile(y[:, None], (1, size)),
            np.full((size, size), 127, dtype=np.uint8),
        ),
        axis=2,
    )
    return Image.fromarray(rgb, mode="RGB")


def _build_model(spec: dict[str, Any], provider: str):
    common = {
        "name": "bird-validation",
        "model_path": str(spec["model_path"]),
        "labels_path": str(spec["labels_path"]),
        "preprocessing": dict(spec.get("preprocessing") or {}),
        "label_grouping": dict(spec.get("label_grouping") or {}),
    }
    runtime = str(spec.get("runtime") or "onnx").strip().lower()
    if runtime in {"tflite", "tensorflow-lite", "tensorflow_lite"}:
        if provider != "cpu":
            raise ValueError("TFLite models can only be validated on the CPU provider")
        return ModelInstance(**common)
    if provider in {"cpu", "cuda"}:
        ort_provider = "CUDAExecutionProvider" if provider == "cuda" else "CPUExecutionProvider"
        return ONNXModelInstance(
            **common,
            input_size=int(spec.get("input_size") or 384),
            ort_providers=[ort_provider],
        )
    openvino_device = {
        "intel_cpu": "CPU",
        "intel_gpu": "GPU",
        "intel_npu": "NPU",
    }.get(provider)
    if not openvino_device:
        raise ValueError(f"Unsupported validation provider: {provider}")
    return OpenVINOModelInstance(
        **common,
        input_size=int(spec.get("input_size") or 384),
        device_name=openvino_device,
        startup_self_test_enabled=False,
    )


def _top_indices(values: np.ndarray) -> list[int]:
    flat = np.asarray(values).reshape(-1)
    if not flat.size or not np.isfinite(flat).any():
        return []
    return [int(index) for index in np.argsort(flat)[-5:][::-1]]


def probe_provider(
    provider: str,
    image_paths: list[str] | None = None,
    *,
    expected_model_id: str | None = None,
) -> dict[str, Any]:
    spec = model_manager.get_active_model_spec()
    report: dict[str, Any] = {
        "provider": provider,
        "model": {
            "model_id": spec.get("model_id"),
            "runtime": spec.get("runtime"),
            "input_size": int(spec.get("input_size") or 224),
            "preprocessing": dict(spec.get("preprocessing") or {}),
        },
    }
    if expected_model_id and str(spec.get("model_id") or "") != expected_model_id:
        report["compile"] = {
            "ok": False,
            "error": f"Active model changed during validation (expected {expected_model_id}, found {spec.get('model_id')})",
        }
        return report
    try:
        model = _build_model(spec, provider)
    except Exception as exc:
        report["compile"] = {"ok": False, "error": str(exc)}
        return report

    try:
        loaded = bool(model.load())
        report["compile"] = {"ok": loaded, "error": getattr(model, "error", None)}
        if not loaded:
            return report

        if provider == "cuda":
            active = list(getattr(getattr(model, "session", None), "get_providers", lambda: [])() or [])
            report["active_runtime_providers"] = active
            if not active or active[0] != "CUDAExecutionProvider":
                report["compile"] = {
                    "ok": False,
                    "error": "CUDAExecutionProvider was requested but is not the primary active provider",
                }
                return report

        paths = [Path(path) for path in (image_paths or []) if Path(path).is_file()]
        images: list[Image.Image] = []
        for path in paths:
            try:
                with Image.open(path) as source:
                    images.append(source.convert("RGB"))
            except Exception:
                continue
        if not images:
            images = [_build_probe_image(int(spec.get("input_size") or 224))]

        # One untimed warm-up absorbs lazy provider initialization. The recorded
        # median represents inference, not process startup or model compilation.
        model.classify_raw(images[0])
        timings: list[float] = []
        per_image_top: list[list[int]] = []
        first_output: np.ndarray | None = None
        measured_outputs: list[np.ndarray] = []
        timed_images = images if paths else images * 3
        for image in timed_images:
            started = time.perf_counter()
            output = np.asarray(model.classify_raw(image)).reshape(-1)
            timings.append((time.perf_counter() - started) * 1000.0)
            if first_output is None:
                first_output = output
            measured_outputs.append(output)
            per_image_top.append(_top_indices(output))

        if first_output is None:
            first_output = np.array([], dtype=np.float32)
        combined_output = np.concatenate(measured_outputs) if measured_outputs else first_output
        report["output_summary"] = _summarize_array(combined_output, name="output_probabilities")
        report["output_top_indices"] = _top_indices(first_output)
        report["per_image_top_indices"] = per_image_top[: len(images)] if paths else [per_image_top[0]]
        report["inference_latency_ms"] = round(float(statistics.median(timings)), 1) if timings else None
        return report
    except Exception as exc:
        report.setdefault("compile", {"ok": True, "error": None})
        report["runtime_error"] = str(exc)
        return report
    finally:
        try:
            model.cleanup()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe the active bird model on one provider")
    parser.add_argument(
        "--provider",
        required=True,
        choices=["cpu", "cuda", "intel_cpu", "intel_gpu", "intel_npu"],
    )
    parser.add_argument("--images", default=None, help="comma-separated real-image paths")
    parser.add_argument("--model-id", default=None, help="fail closed if the active model changed")
    args = parser.parse_args()
    image_paths = [path for path in args.images.split(",") if path] if args.images else None
    print(
        json.dumps(
            probe_provider(args.provider, image_paths, expected_model_id=args.model_id),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
