"""Evaluation harness for bird crop detector models.

Usage:
    PYTHONPATH=backend /config/workspace/YA-WAMF/backend/venv/bin/python \
        backend/scripts/eval_crop_detector_accuracy.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.services.bird_crop_service import BirdCropService


Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class CropEvalCase:
    case_id: str
    bucket: str
    image_path: Path
    boxes: list[Box]
    source: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DetectionCandidate:
    box: Box
    confidence: float


def _coerce_box(raw: Any) -> Box:
    if isinstance(raw, dict):
        return (int(raw["x1"]), int(raw["y1"]), int(raw["x2"]), int(raw["y2"]))
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    raise ValueError(f"Unsupported box payload: {raw!r}")


def load_manifest(path: Path) -> list[CropEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[CropEvalCase] = []
    for item in payload.get("cases", []):
        cases.append(
            CropEvalCase(
                case_id=str(item["id"]),
                bucket=str(item["bucket"]),
                image_path=Path(str(item["image_path"])),
                boxes=[_coerce_box(box) for box in item.get("boxes", [])],
                source=item.get("source"),
                notes=item.get("notes"),
            )
        )
    return cases


def _resolve_manifest_image_path(manifest_path: Path, raw_path: str) -> Path:
    image_path = Path(raw_path)
    if image_path.is_absolute():
        return image_path
    repo_root = manifest_path.parents[3]
    return (repo_root / image_path).resolve()


def load_manifest_resolved(path: Path) -> list[CropEvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[CropEvalCase] = []
    for item in payload.get("cases", []):
        cases.append(
            CropEvalCase(
                case_id=str(item["id"]),
                bucket=str(item["bucket"]),
                image_path=_resolve_manifest_image_path(path, str(item["image_path"])),
                boxes=[_coerce_box(box) for box in item.get("boxes", [])],
                source=item.get("source"),
                notes=item.get("notes"),
            )
        )
    return cases


def compute_iou(box_a: Box, box_b: Box) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union_area = area_a + area_b - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def evaluate_case(
    case: CropEvalCase,
    candidates: list[DetectionCandidate],
    *,
    iou_thresholds: tuple[float, float] = (0.3, 0.5),
) -> dict[str, Any]:
    best_confidence: float | None = None
    best_iou = 0.0
    useful_crop = False

    for candidate in candidates:
        confidence = float(candidate.confidence)
        candidate_best_iou = max((compute_iou(candidate.box, gt_box) for gt_box in case.boxes), default=0.0)
        if (
            candidate_best_iou > best_iou
            or (candidate_best_iou == best_iou and (best_confidence is None or confidence > best_confidence))
        ):
            best_confidence = confidence
            best_iou = candidate_best_iou
        useful_crop = useful_crop or candidate_best_iou >= iou_thresholds[1]

    return {
        "case_id": case.case_id,
        "bucket": case.bucket,
        "image_path": str(case.image_path),
        "candidate_count": len(candidates),
        "any_detection": bool(candidates),
        "best_confidence": best_confidence,
        "best_iou": best_iou,
        "recall_at_0_3": best_iou >= iou_thresholds[0],
        "recall_at_0_5": best_iou >= iou_thresholds[1],
        "useful_crop": useful_crop,
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        confidences = [float(row["best_confidence"]) for row in rows if row.get("best_confidence") is not None]
        ious = [float(row.get("best_iou") or 0.0) for row in rows]
        return {
            "cases": total,
            "any_detection_recall": (sum(1 for row in rows if row.get("any_detection")) / total) if total else 0.0,
            "recall_at_0_3": (sum(1 for row in rows if row.get("recall_at_0_3")) / total) if total else 0.0,
            "recall_at_0_5": (sum(1 for row in rows if row.get("recall_at_0_5")) / total) if total else 0.0,
            "useful_crop_rate": (sum(1 for row in rows if row.get("useful_crop")) / total) if total else 0.0,
            "mean_best_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
            "mean_best_iou": (sum(ious) / len(ious)) if ious else 0.0,
        }

    buckets = sorted({str(row.get("bucket") or "unknown") for row in results})
    by_bucket = {
        bucket: _summary([row for row in results if str(row.get("bucket") or "unknown") == bucket])
        for bucket in buckets
    }
    return {
        "overall": _summary(results),
        "by_bucket": by_bucket,
    }


def _load_candidates_for_case(service: BirdCropService, case: CropEvalCase, *, tier: str) -> tuple[list[DetectionCandidate], dict[str, Any]]:
    image = Image.open(case.image_path).convert("RGB")
    model = service._ensure_model_for_tier(tier)
    if model is None:
        raise FileNotFoundError(f"Crop detector tier '{tier}' is not installed or could not be loaded")
    raw_candidates = service._infer_candidates(model, image)
    candidates = [
        DetectionCandidate(
            box=tuple(int(round(v)) for v in candidate["box"]),
            confidence=float(candidate["confidence"]),
        )
        for candidate in raw_candidates
        if candidate.get("box") is not None and candidate.get("confidence") is not None
    ]
    selected = service._select_best_valid_candidate(
        image,
        [{"box": candidate.box, "confidence": candidate.confidence} for candidate in candidates],
        detector_tier=tier,
        fallback_reason=None,
    )
    return candidates, selected


def evaluate_cases_for_tier(
    cases: list[CropEvalCase],
    *,
    tier: str,
    confidence_threshold: float = 0.35,
    expand_ratio: float = 0.12,
    min_crop_size: int = 96,
) -> dict[str, Any]:
    service = BirdCropService(
        detector_tier=tier,
        confidence_threshold=confidence_threshold,
        expand_ratio=expand_ratio,
        min_crop_size=min_crop_size,
    )
    raw_results: list[dict[str, Any]] = []
    selected_results: list[dict[str, Any]] = []
    for case in cases:
        candidates, selected = _load_candidates_for_case(service, case, tier=tier)
        raw_eval = evaluate_case(case, candidates)
        selected_eval = evaluate_case(
            case,
            [DetectionCandidate(box=tuple(int(round(v)) for v in selected["box"]), confidence=float(selected["confidence"]))]
            if selected.get("box") is not None and selected.get("confidence") is not None
            else [],
        )
        raw_eval["selected_reason"] = selected.get("reason")
        raw_eval["selected_box"] = selected.get("box")
        raw_eval["selected_confidence"] = selected.get("confidence")
        raw_results.append(raw_eval)
        selected_eval["selected_reason"] = selected.get("reason")
        selected_results.append(selected_eval)
    return {
        "tier": tier,
        "raw_summary": summarize_results(raw_results),
        "selected_summary": summarize_results(selected_results),
        "cases": raw_results,
    }


def _draw_box(draw: ImageDraw.ImageDraw, box: Box, *, color: str, width: int = 3) -> None:
    draw.rectangle(box, outline=color, width=width)


def write_overlays(cases: list[CropEvalCase], results_by_tier: dict[str, dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_index = {
        tier: {case_result["case_id"]: case_result for case_result in payload["cases"]}
        for tier, payload in results_by_tier.items()
    }
    for case in cases:
        image = Image.open(case.image_path).convert("RGB")
        draw = ImageDraw.Draw(image)
        for box in case.boxes:
            _draw_box(draw, box, color="lime", width=4)
        for tier, tier_results in results_index.items():
            result = tier_results.get(case.case_id) or {}
            selected_box = result.get("selected_box")
            if selected_box is not None:
                _draw_box(draw, tuple(int(round(v)) for v in selected_box), color="red" if tier == "fast" else "blue", width=3)
        image.save(output_dir / f"{case.case_id}.jpg", quality=90)


def _print_summary(results_by_tier: dict[str, dict[str, Any]]) -> None:
    for tier, payload in results_by_tier.items():
        raw = payload["raw_summary"]["overall"]
        selected = payload["selected_summary"]["overall"]
        print(f"\n[{tier}]")
        print(
            "raw:",
            f"cases={raw['cases']}",
            f"any={raw['any_detection_recall']:.3f}",
            f"iou@0.3={raw['recall_at_0_3']:.3f}",
            f"iou@0.5={raw['recall_at_0_5']:.3f}",
            f"useful={raw['useful_crop_rate']:.3f}",
            f"mean_iou={raw['mean_best_iou']:.3f}",
        )
        print(
            "selected:",
            f"cases={selected['cases']}",
            f"any={selected['any_detection_recall']:.3f}",
            f"iou@0.3={selected['recall_at_0_3']:.3f}",
            f"iou@0.5={selected['recall_at_0_5']:.3f}",
            f"useful={selected['useful_crop_rate']:.3f}",
            f"mean_iou={selected['mean_best_iou']:.3f}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate crop detector tiers against a labeled manifest.")
    default_manifest = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "crop_detector_manifest.json"
    parser.add_argument("--manifest", default=str(default_manifest), help="Path to crop_detector_manifest.json")
    parser.add_argument("--tiers", nargs="+", default=["fast", "accurate"], choices=["fast", "accurate"], help="Detector tiers to evaluate")
    parser.add_argument("--confidence-threshold", type=float, default=0.35)
    parser.add_argument("--expand-ratio", type=float, default=0.12)
    parser.add_argument("--min-crop-size", type=int, default=96)
    parser.add_argument("--output-json", type=str, default="", help="Optional path to write JSON results")
    parser.add_argument("--overlay-dir", type=str, default="", help="Optional directory to write overlay images")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    cases = load_manifest_resolved(manifest_path)
    results_by_tier = {
        tier: evaluate_cases_for_tier(
            cases,
            tier=tier,
            confidence_threshold=args.confidence_threshold,
            expand_ratio=args.expand_ratio,
            min_crop_size=args.min_crop_size,
        )
        for tier in args.tiers
    }
    _print_summary(results_by_tier)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(results_by_tier, indent=2), encoding="utf-8")
    if args.overlay_dir:
        write_overlays(cases, results_by_tier, Path(args.overlay_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
