"""Benchmark an external crop-detector candidate without enabling it at runtime.

This probe deliberately sits outside the model registry.  It is intended for
reproducible candidate evaluation on labelled positive and negative images;
passing it is not sufficient to promote or distribute a model.

The adapter implements the shared official D-FINE-N/DEIMv2-N ONNX deployment
contract: RGB input, aspect-preserving 640px letterbox, 0..1 NCHW floats, and
the ``labels``, ``boxes`` and ``scores`` post-processing outputs embedded in
the exported graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image


Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    bucket: str
    image_path: Path
    boxes: tuple[Box, ...]
    visit_id: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class PreparedInput:
    feeds: dict[str, np.ndarray]
    ratio: float
    pad_x: int
    pad_y: int
    original_size: tuple[int, int]


@dataclass(frozen=True)
class Candidate:
    box: Box
    confidence: float


class InferenceBackend(Protocol):
    def run(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    fraction = index - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _coerce_box(raw: Any) -> Box:
    if isinstance(raw, dict):
        values = (raw["x1"], raw["y1"], raw["x2"], raw["y2"])
    elif isinstance(raw, (list, tuple)) and len(raw) == 4:
        values = raw
    else:
        raise ValueError(f"Unsupported box payload: {raw!r}")
    box = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in box):
        raise ValueError(f"Non-finite box payload: {raw!r}")
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError(f"Invalid box geometry: {raw!r}")
    return box


def _resolve_image_path(manifest_path: Path, raw_path: str) -> Path:
    image_path = Path(raw_path)
    if image_path.is_absolute():
        return image_path

    candidates = [manifest_path.parent / image_path, Path.cwd() / image_path]
    candidates.extend(parent / image_path for parent in manifest_path.parents)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return (Path.cwd() / image_path).resolve()


def load_manifest(manifest_path: Path) -> list[EvalCase]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Manifest must contain a non-empty cases list")

    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for raw_case in raw_cases:
        case_id = str(raw_case["id"]).strip()
        if not case_id or case_id in seen_ids:
            raise ValueError(f"Manifest case ids must be non-empty and unique: {case_id!r}")
        seen_ids.add(case_id)
        image_path = _resolve_image_path(manifest_path, str(raw_case["image_path"]))
        if not image_path.is_file():
            raise FileNotFoundError(f"Image for case {case_id!r} does not exist: {image_path}")
        cases.append(
            EvalCase(
                case_id=case_id,
                bucket=str(raw_case.get("bucket") or "unknown"),
                image_path=image_path,
                boxes=tuple(_coerce_box(box) for box in (raw_case.get("boxes") or [])),
                visit_id=str(raw_case.get("visit_id") or case_id),
                tags=tuple(str(tag) for tag in (raw_case.get("tags") or []) if str(tag).strip()),
            )
        )
    return cases


class DetrDeployAdapter:
    """Strict adapter for the official D-FINE/DEIMv2 deploy-mode export."""

    def __init__(self, *, input_size: int = 640, bird_label: int = 14) -> None:
        if input_size <= 0:
            raise ValueError("input_size must be positive")
        self.input_size = input_size
        self.bird_label = bird_label

    def prepare(self, image: Image.Image) -> PreparedInput:
        image = image.convert("RGB")
        original_width, original_height = image.size
        ratio = min(self.input_size / original_width, self.input_size / original_height)
        resized_width = max(1, int(original_width * ratio))
        resized_height = max(1, int(original_height * ratio))
        resized = image.resize((resized_width, resized_height), Image.Resampling.BILINEAR)
        pad_x = (self.input_size - resized_width) // 2
        pad_y = (self.input_size - resized_height) // 2
        letterboxed = Image.new("RGB", (self.input_size, self.input_size))
        letterboxed.paste(resized, (pad_x, pad_y))

        pixels = np.asarray(letterboxed, dtype=np.float32) / np.float32(255.0)
        images = np.ascontiguousarray(np.transpose(pixels, (2, 0, 1))[None, ...])
        sizes = np.asarray([[self.input_size, self.input_size]], dtype=np.int64)
        return PreparedInput(
            feeds={"images": images, "orig_target_sizes": sizes},
            ratio=ratio,
            pad_x=pad_x,
            pad_y=pad_y,
            original_size=(original_width, original_height),
        )

    def parse(self, outputs: dict[str, np.ndarray], prepared: PreparedInput) -> list[Candidate]:
        missing = {"labels", "boxes", "scores"} - outputs.keys()
        if missing:
            raise ValueError(f"DETR-family outputs are missing: {sorted(missing)}")
        labels = np.asarray(outputs["labels"])
        boxes = np.asarray(outputs["boxes"])
        scores = np.asarray(outputs["scores"])
        if labels.ndim != 2 or boxes.ndim != 3 or scores.ndim != 2:
            raise ValueError(
                f"Unexpected output ranks: labels={labels.shape}, boxes={boxes.shape}, scores={scores.shape}"
            )
        if labels.shape != scores.shape or boxes.shape[:2] != labels.shape or boxes.shape[2] != 4:
            raise ValueError(
                f"Inconsistent output shapes: labels={labels.shape}, boxes={boxes.shape}, scores={scores.shape}"
            )
        if not np.isfinite(boxes).all() or not np.isfinite(scores).all():
            raise ValueError("Candidate produced non-finite boxes or scores")

        width, height = prepared.original_size
        candidates: list[Candidate] = []
        for label, raw_box, score in zip(labels[0], boxes[0], scores[0], strict=True):
            if int(label) != self.bird_label:
                continue
            x1 = float(np.clip((raw_box[0] - prepared.pad_x) / prepared.ratio, 0, width))
            y1 = float(np.clip((raw_box[1] - prepared.pad_y) / prepared.ratio, 0, height))
            x2 = float(np.clip((raw_box[2] - prepared.pad_x) / prepared.ratio, 0, width))
            y2 = float(np.clip((raw_box[3] - prepared.pad_y) / prepared.ratio, 0, height))
            confidence = float(score)
            if x2 <= x1 or y2 <= y1 or not math.isfinite(confidence):
                continue
            candidates.append(Candidate(box=(x1, y1, x2, y2), confidence=confidence))
        candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
        return candidates


class OnnxRuntimeBackend:
    def __init__(self, model_path: Path, *, providers: list[str]) -> None:
        import onnxruntime as ort

        available = set(ort.get_available_providers())
        missing = set(providers) - available
        if missing:
            raise RuntimeError(
                f"Requested ONNX Runtime providers are unavailable: {sorted(missing)}; available={sorted(available)}"
            )
        self._session = ort.InferenceSession(str(model_path), providers=providers)
        actual = self._session.get_providers()
        if not actual or actual[0] != providers[0]:
            raise RuntimeError(
                f"ONNX Runtime did not select the requested provider: requested={providers}, actual={actual}"
            )

    def run(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        names = [output.name for output in self._session.get_outputs()]
        values = self._session.run(names, feeds)
        return dict(zip(names, values, strict=True))


class OpenVinoBackend:
    def __init__(self, model_path: Path, *, device: str) -> None:
        import openvino as ov

        self._core = ov.Core()
        available = {value.split(".", 1)[0].upper() for value in self._core.available_devices}
        if device.upper() not in available:
            raise RuntimeError(f"Requested OpenVINO device {device!r} is unavailable; available={sorted(available)}")
        model = self._core.read_model(str(model_path))
        # The official exporter uses a dynamic batch axis.  Intel NPU rejects
        # that unbounded dimension even though this application only ever
        # performs single-image inference, so make the actual contract
        # explicit before compiling on every OpenVINO device.  Using the same
        # static graph everywhere also makes provider comparisons meaningful.
        input_names = {input_port.get_any_name() for input_port in model.inputs}
        if input_names != {"images", "orig_target_sizes"}:
            raise ValueError(f"Unexpected OpenVINO candidate inputs: {sorted(input_names)}")
        model.reshape({"images": [1, 3, 640, 640], "orig_target_sizes": [1, 2]})
        self._compiled = self._core.compile_model(model, device.upper())
        self._request = self._compiled.create_infer_request()
        self._output_names: list[str] = []
        for output in self._compiled.outputs:
            names = output.get_names()
            self._output_names.append(sorted(names)[0] if names else output.get_any_name())
        if set(self._output_names) != {"labels", "boxes", "scores"}:
            raise ValueError(f"Unexpected OpenVINO candidate outputs: {self._output_names}")

    def run(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        self._request.infer(feeds)
        return {name: np.array(self._request.get_tensor(name).data, copy=True) for name in self._output_names}


def build_backend(model_path: Path, provider: str) -> InferenceBackend:
    if provider == "cpu":
        return OnnxRuntimeBackend(model_path, providers=["CPUExecutionProvider"])
    if provider == "cuda":
        return OnnxRuntimeBackend(model_path, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    devices = {
        "intel_cpu": "CPU",
        "intel_gpu": "GPU",
        "intel_npu": "NPU",
    }
    try:
        device = devices[provider]
    except KeyError as error:
        raise ValueError(f"Unknown provider: {provider}") from error
    return OpenVinoBackend(model_path, device=device)


def compute_iou(box_a: Box, box_b: Box) -> float:
    intersection_width = max(0.0, min(box_a[2], box_b[2]) - max(box_a[0], box_b[0]))
    intersection_height = max(0.0, min(box_a[3], box_b[3]) - max(box_a[1], box_b[1]))
    intersection = intersection_width * intersection_height
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _summarize_threshold(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    positives = [row for row in rows if row["ground_truth_boxes"]]
    negatives = [row for row in rows if not row["ground_truth_boxes"]]
    positive_metrics: list[dict[str, Any]] = []
    false_positives = 0
    for row in rows:
        candidates = [candidate for candidate in row["candidates"] if candidate["confidence"] >= threshold]
        if not row["ground_truth_boxes"]:
            false_positives += bool(candidates)
            continue
        selected_iou = (
            max(
                (
                    compute_iou(tuple(candidates[0]["box"]), tuple(reference_box))
                    for reference_box in row["ground_truth_boxes"]
                ),
                default=0.0,
            )
            if candidates
            else 0.0
        )
        any_candidate_iou = max(
            (
                compute_iou(tuple(candidate["box"]), tuple(reference_box))
                for candidate in candidates
                for reference_box in row["ground_truth_boxes"]
            ),
            default=0.0,
        )
        positive_metrics.append(
            {
                "detected": bool(candidates),
                "selected_iou": selected_iou,
                "any_candidate_iou": any_candidate_iou,
            }
        )

    positive_total = len(positives)
    negative_total = len(negatives)
    return {
        "threshold": threshold,
        "positive_cases": positive_total,
        "negative_cases": negative_total,
        "detected_positive_count": sum(metric["detected"] for metric in positive_metrics),
        "any_detection_recall": (
            sum(metric["detected"] for metric in positive_metrics) / positive_total if positive_total else 0.0
        ),
        "iou_0_3_count": sum(metric["selected_iou"] >= 0.3 for metric in positive_metrics),
        "recall_at_0_3": (
            sum(metric["selected_iou"] >= 0.3 for metric in positive_metrics) / positive_total
            if positive_total
            else 0.0
        ),
        "iou_0_5_count": sum(metric["selected_iou"] >= 0.5 for metric in positive_metrics),
        "recall_at_0_5": (
            sum(metric["selected_iou"] >= 0.5 for metric in positive_metrics) / positive_total
            if positive_total
            else 0.0
        ),
        "mean_best_iou": (
            statistics.fmean(metric["selected_iou"] for metric in positive_metrics) if positive_metrics else 0.0
        ),
        "any_candidate_iou_0_3_count": sum(metric["any_candidate_iou"] >= 0.3 for metric in positive_metrics),
        "any_candidate_recall_at_0_3": (
            sum(metric["any_candidate_iou"] >= 0.3 for metric in positive_metrics) / positive_total
            if positive_total
            else 0.0
        ),
        "any_candidate_iou_0_5_count": sum(metric["any_candidate_iou"] >= 0.5 for metric in positive_metrics),
        "any_candidate_recall_at_0_5": (
            sum(metric["any_candidate_iou"] >= 0.5 for metric in positive_metrics) / positive_total
            if positive_total
            else 0.0
        ),
        "false_positive_count": false_positives,
        "false_positive_rate": false_positives / negative_total if negative_total else 0.0,
    }


def benchmark(
    *,
    candidate: str,
    model_path: Path,
    manifest_path: Path,
    provider: str,
    thresholds: list[float],
    warmup_runs: int,
    repetitions: int,
) -> dict[str, Any]:
    cases = load_manifest(manifest_path)
    adapter = DetrDeployAdapter()
    compile_started = time.perf_counter()
    backend = build_backend(model_path, provider)
    compile_ms = (time.perf_counter() - compile_started) * 1000.0

    with Image.open(cases[0].image_path) as first_image:
        first_prepared = adapter.prepare(first_image)
    for _ in range(warmup_runs):
        adapter.parse(backend.run(first_prepared.feeds), first_prepared)

    minimum_threshold = min(thresholds)
    rows: list[dict[str, Any]] = []
    inference_latencies: list[float] = []
    preprocessing_latencies: list[float] = []
    for case in cases:
        prepare_started = time.perf_counter()
        with Image.open(case.image_path) as raw_image:
            prepared = adapter.prepare(raw_image)
        preprocessing_latencies.append((time.perf_counter() - prepare_started) * 1000.0)

        outputs: dict[str, np.ndarray] | None = None
        sample_latencies: list[float] = []
        for _ in range(repetitions):
            infer_started = time.perf_counter()
            outputs = backend.run(prepared.feeds)
            sample_latencies.append((time.perf_counter() - infer_started) * 1000.0)
        if outputs is None:
            raise RuntimeError("No inference output was produced")
        inference_latencies.append(statistics.median(sample_latencies))
        candidates = [
            candidate for candidate in adapter.parse(outputs, prepared) if candidate.confidence >= minimum_threshold
        ]
        rows.append(
            {
                "case_id": case.case_id,
                "visit_id": case.visit_id,
                "bucket": case.bucket,
                "tags": list(case.tags),
                "image_path": str(case.image_path),
                "ground_truth_boxes": [list(box) for box in case.boxes],
                "candidates": [
                    {"box": [round(value, 4) for value in candidate.box], "confidence": candidate.confidence}
                    for candidate in candidates
                ],
            }
        )

    return {
        "schema_version": 1,
        "candidate": candidate,
        "candidate_status": "benchmark_only_not_runtime_approved",
        "model": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "input_contract": "RGB; aspect-preserving centered black 640x640 letterbox; float32 NCHW 0..1",
            "bird_label": 14,
        },
        "provider": provider,
        "manifest": str(manifest_path),
        "case_count": len(cases),
        "positive_case_count": sum(bool(case.boxes) for case in cases),
        "negative_case_count": sum(not case.boxes for case in cases),
        "visit_count": len({case.visit_id for case in cases}),
        "compile_ms": compile_ms,
        "latency_ms": {
            "inference_median": statistics.median(inference_latencies),
            "inference_p95": _percentile(inference_latencies, 0.95),
            "preprocess_median": statistics.median(preprocessing_latencies),
            "preprocess_p95": _percentile(preprocessing_latencies, 0.95),
            "warmup_runs": warmup_runs,
            "repetitions_per_case": repetitions,
        },
        "thresholds": [_summarize_threshold(rows, threshold) for threshold in thresholds],
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark an external crop-detector candidate")
    parser.add_argument(
        "--candidate",
        choices=["dfine_n_coco", "deimv2_n_coco"],
        default="dfine_n_coco",
    )
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--provider",
        choices=["cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"],
        required=True,
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[0.4, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.001],
    )
    parser.add_argument("--warmup-runs", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    if not args.model.is_file():
        parser.error(f"Model does not exist: {args.model}")
    if not args.manifest.is_file():
        parser.error(f"Manifest does not exist: {args.manifest}")
    if args.warmup_runs < 0 or args.repetitions < 1:
        parser.error("warmup-runs must be non-negative and repetitions must be positive")
    thresholds = sorted({float(value) for value in args.thresholds}, reverse=True)
    if not thresholds or any(value < 0.0 or value > 1.0 for value in thresholds):
        parser.error("thresholds must be between 0 and 1")

    result = benchmark(
        candidate=args.candidate,
        model_path=args.model.resolve(),
        manifest_path=args.manifest.resolve(),
        provider=args.provider,
        thresholds=thresholds,
        warmup_runs=args.warmup_runs,
        repetitions=args.repetitions,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "candidate": result["candidate"],
                "provider": result["provider"],
                "cases": result["case_count"],
                "compile_ms": round(result["compile_ms"], 1),
                "inference_median_ms": round(result["latency_ms"]["inference_median"], 1),
                "thresholds": result["thresholds"],
                "output_json": str(args.output_json),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
