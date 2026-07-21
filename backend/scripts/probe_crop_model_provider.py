#!/usr/bin/env python3
"""Probe one exact crop detector on one provider in a disposable process.

Native accelerator compilers can crash the process. The parent hardware sweep
therefore launches one copy of this module for every model/provider pairing and
compares the returned boxes with an independently executed CPU baseline.
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

from app.services.bird_crop_service import BirdCropService
from app.services.model_manager import model_manager


def _summarize_outputs(outputs: list[np.ndarray]) -> dict[str, Any]:
    element_count = finite_count = nan_count = pos_inf_count = neg_inf_count = 0
    finite_min: float | None = None
    finite_max: float | None = None
    for output in outputs:
        values = np.asarray(output)
        finite = np.isfinite(values)
        finite_values = values[finite]
        element_count += int(values.size)
        finite_count += int(finite.sum())
        nan_count += int(np.isnan(values).sum())
        pos_inf_count += int(np.isposinf(values).sum())
        neg_inf_count += int(np.isneginf(values).sum())
        if finite_values.size:
            current_min = float(finite_values.min())
            current_max = float(finite_values.max())
            finite_min = current_min if finite_min is None else min(finite_min, current_min)
            finite_max = current_max if finite_max is None else max(finite_max, current_max)
    return {
        "name": "detector_outputs",
        "element_count": element_count,
        "finite_count": finite_count,
        "nan_count": nan_count,
        "pos_inf_count": pos_inf_count,
        "neg_inf_count": neg_inf_count,
        "finite_min": finite_min,
        "finite_max": finite_max,
    }


def _synthetic_negatives(size: int) -> list[tuple[str, Image.Image]]:
    """Deterministic hard negatives catch provider-specific false detections."""
    side = max(64, int(size or 416))
    rng = np.random.default_rng(20260721)
    foliage = rng.integers(0, 96, (side, side, 3), dtype=np.uint8)
    foliage[:, :, 1] = np.clip(foliage[:, :, 1].astype(np.int16) + 96, 0, 255).astype(np.uint8)
    x = np.linspace(0, 255, side, dtype=np.uint8)
    gradient = np.stack(
        (np.tile(x, (side, 1)), np.tile(x[:, None], (1, side)), np.full((side, side), 96, dtype=np.uint8)),
        axis=2,
    )
    return [
        ("negative_dark", Image.new("RGB", (side, side), (8, 12, 10))),
        ("negative_foliage", Image.fromarray(foliage, mode="RGB")),
        ("negative_gradient", Image.fromarray(gradient, mode="RGB")),
    ]


def _load_images(image_paths: list[str], *, input_size: int) -> list[tuple[str, Image.Image]]:
    images: list[tuple[str, Image.Image]] = []
    for path_value in image_paths:
        path = Path(path_value)
        if not path.is_file():
            continue
        try:
            with Image.open(path) as source:
                images.append((f"real:{path.name}", source.convert("RGB")))
        except Exception:
            continue
    images.extend(_synthetic_negatives(input_size))
    return images


def _top_detection(candidates: list[dict[str, Any]], image: Image.Image) -> dict[str, Any] | None:
    usable = [candidate for candidate in candidates if candidate.get("box") is not None]
    if not usable:
        return None
    selected = max(usable, key=lambda candidate: float(candidate.get("confidence") or 0.0))
    box = [float(value) for value in selected["box"]]
    width, height = image.size
    return {
        "box": box,
        "normalized_box": [box[0] / width, box[1] / height, box[2] / width, box[3] / height],
        "confidence": float(selected.get("confidence") or 0.0),
    }


def probe_provider(provider: str, model_id: str, image_paths: list[str]) -> dict[str, Any]:
    report: dict[str, Any] = {"provider": provider, "model_id": model_id, "comparison_kind": "crop_box"}
    try:
        spec = model_manager.get_crop_detector_spec_by_model_id(model_id)
    except Exception as exc:
        report["compile"] = {"ok": False, "error": str(exc)}
        return report
    if not spec.get("healthy"):
        report["compile"] = {"ok": False, "error": f"Exact crop detector is not ready: {spec.get('reason')}"}
        return report

    tier = str(spec.get("resolved_tier") or "fast")
    service = BirdCropService(detector_tier=tier, provider_override=provider, strict_provider=True)
    try:
        model = service._load_model_for_tier(tier)
        if not isinstance(model, dict):
            raise RuntimeError("Crop detector did not create a managed inference session")
        if str(model.get("provider") or "") != provider:
            raise RuntimeError(f"Requested {provider}, loaded {model.get('provider') or 'unknown'}")
        report["compile"] = {"ok": True, "error": None}
        report["active_runtime_providers"] = list(getattr(model.get("session"), "get_providers", lambda: [])() or [])
    except Exception as exc:
        report["compile"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return report

    images = _load_images(image_paths, input_size=int((spec.get("metadata") or {}).get("input_size") or 416))
    if not images:
        report["runtime_error"] = "No validation images were available"
        return report

    try:
        service.run_detector_outputs(model, images[0][1])
        timings: list[float] = []
        all_outputs: list[np.ndarray] = []
        detections: list[dict[str, Any]] = []
        for label, image in images:
            started = time.perf_counter()
            outputs, transform = service.run_detector_outputs(model, image)
            timings.append((time.perf_counter() - started) * 1000.0)
            all_outputs.extend(np.asarray(output) for output in outputs)
            candidates = service._parse_detector_outputs(
                outputs,
                transform=transform,
                image_size=image.size,
                output_names=[str(name or "") for name in model.get("output_names") or []],
                detector_tier=tier,
                detector_config=dict(model.get("detector_config") or {}),
            )
            detections.append(
                {
                    "image": label,
                    "kind": "negative" if label.startswith("negative_") else "real",
                    "top_detection": _top_detection(candidates, image),
                    "detection_count": len(candidates),
                }
            )
        report["output_summary"] = _summarize_outputs(all_outputs)
        report["per_image_detections"] = detections
        report["images_evaluated"] = len(detections)
        report["real_images_evaluated"] = sum(1 for row in detections if row["kind"] == "real")
        report["negative_images_evaluated"] = sum(1 for row in detections if row["kind"] == "negative")
        report["inference_latency_ms"] = round(float(statistics.median(timings)), 1) if timings else None
        return report
    except Exception as exc:
        report["runtime_error"] = f"{type(exc).__name__}: {exc}"
        return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--images", default="")
    args = parser.parse_args()
    image_paths = [value for value in str(args.images).split(",") if value]
    print(json.dumps(probe_provider(args.provider, args.model_id, image_paths), separators=(",", ":")))


if __name__ == "__main__":
    main()
