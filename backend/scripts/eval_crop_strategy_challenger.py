#!/usr/bin/env python3
"""Compare optimized model crops with same-frame Frigate crops end to end.

The manifest must keep full-resolution images private and may provide one
same-frame Frigate box plus owner-confirmed label aliases per case. Automatic
labels are recorded but deliberately excluded from win/tie/loss promotion
evidence. Every representation is classified without another crop pass.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable

from PIL import Image


_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


MODEL_WIN_MARGIN = 0.02
REQUIRED_MANIFEST_VERSION = "3"


def _label_key(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).casefold()


def _prediction_score(prediction: dict[str, Any] | None) -> float:
    if not isinstance(prediction, dict):
        return 0.0
    try:
        score = float(prediction.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return score if math.isfinite(score) else 0.0


def _prediction_is_expected(prediction: dict[str, Any] | None, expected_labels: list[str]) -> bool:
    expected = {_label_key(label) for label in expected_labels if _label_key(label)}
    return bool(expected and _label_key((prediction or {}).get("label")) in expected)


def _percentile(values: list[float], percentile: float) -> float:
    finite: list[float] = []
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            finite.append(parsed)
    finite.sort()
    if not finite:
        return 0.0
    position = (len(finite) - 1) * min(1.0, max(0.0, float(percentile)))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return finite[lower]
    weight = position - lower
    return finite[lower] + ((finite[upper] - finite[lower]) * weight)


def validate_manifest(manifest: Any) -> list[dict[str, Any]]:
    """Fail closed when a panel cannot support an independent comparison."""
    if not isinstance(manifest, dict):
        raise ValueError("Crop challenger manifest must be a JSON object")
    if str(manifest.get("version") or "") != REQUIRED_MANIFEST_VERSION:
        raise ValueError(
            f"Crop challenger requires manifest version {REQUIRED_MANIFEST_VERSION}; rebuild the private panel"
        )
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Crop challenger manifest must contain at least one case")

    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    positive_visits: set[str] = set()
    for index, raw_case in enumerate(raw_cases, 1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"Manifest case {index} must be an object")
        case_id = str(raw_case.get("id") or "").strip()
        if not case_id:
            raise ValueError(f"Manifest case {index} is missing an id")
        if case_id in case_ids:
            raise ValueError(f"Duplicate manifest case id: {case_id}")
        case_ids.add(case_id)
        if not str(raw_case.get("image_path") or "").strip():
            raise ValueError(f"Manifest case {case_id} is missing image_path")

        boxes = raw_case.get("boxes")
        if not isinstance(boxes, list) or len(boxes) > 1:
            raise ValueError(f"Manifest case {case_id} must contain zero or one same-frame Frigate box")
        expected_labels = raw_case.get("expected_labels") or []
        if not isinstance(expected_labels, list):
            raise ValueError(f"Manifest case {case_id} expected_labels must be a list")
        label_source = str(raw_case.get("label_source") or "")
        if expected_labels and label_source != "owner_manual":
            raise ValueError(f"Manifest case {case_id} has promotion labels without owner_manual provenance")
        if not boxes and expected_labels:
            raise ValueError(f"Hard-negative manifest case {case_id} cannot carry species ground truth")
        if boxes:
            visit_id = str(raw_case.get("visit_id") or "").strip()
            if not visit_id:
                raise ValueError(f"Positive manifest case {case_id} is missing visit_id")
            if visit_id in positive_visits:
                raise ValueError(f"Duplicate positive visit in manifest: {visit_id}")
            positive_visits.add(visit_id)
        cases.append(raw_case)
    return cases


def compare_expected_outcomes(
    *,
    frigate_prediction: dict[str, Any] | None,
    model_prediction: dict[str, Any] | None,
    expected_labels: list[str],
    minimum_model_gain: float = MODEL_WIN_MARGIN,
) -> tuple[str, str]:
    """Return a conservative Frigate/model comparison for owner-labelled evidence."""
    if not expected_labels:
        return "unscored", "no_owner_ground_truth"
    frigate_correct = _prediction_is_expected(frigate_prediction, expected_labels)
    model_correct = _prediction_is_expected(model_prediction, expected_labels)
    if model_correct and not frigate_correct:
        return "win", "model_only_correct"
    if frigate_correct and not model_correct:
        return "loss", "frigate_only_correct"
    if not model_correct and not frigate_correct:
        return "tie", "both_incorrect"

    model_score = _prediction_score(model_prediction)
    frigate_score = _prediction_score(frigate_prediction)
    margin = max(0.0, float(minimum_model_gain))
    if model_score + 1e-9 >= frigate_score + margin:
        return "win", "both_correct_model_confidence_gain"
    if frigate_score + 1e-9 >= model_score + margin:
        return "loss", "both_correct_frigate_confidence_gain"
    return "tie", "both_correct_within_margin"


def select_guarded_crop_prediction(
    *,
    frigate_prediction: dict[str, Any] | None,
    model_prediction: dict[str, Any] | None,
    minimum_model_gain: float = MODEL_WIN_MARGIN,
) -> tuple[dict[str, Any] | None, str, str]:
    """Mirror the production guard that prevents a model crop regressing Frigate.

    The model crop may replace a usable Frigate crop only when both crops produce
    the same classifier identity and the model crop clears the configured score
    margin. This comparison deliberately does not use ground truth.
    """
    if frigate_prediction is None:
        if model_prediction is None:
            return None, "none", "no_prediction"
        return model_prediction, "model_crop", "frigate_prediction_missing"
    if model_prediction is None:
        return frigate_prediction, "frigate_hint_crop", "model_prediction_missing"
    if _label_key(model_prediction.get("label")) != _label_key(frigate_prediction.get("label")):
        return frigate_prediction, "frigate_hint_crop", "identity_mismatch"
    if _prediction_score(model_prediction) + 1e-9 >= _prediction_score(frigate_prediction) + max(
        0.0, float(minimum_model_gain)
    ):
        return model_prediction, "model_crop", "same_identity_model_gain"
    return frigate_prediction, "frigate_hint_crop", "insufficient_model_gain"


def summarize_rows(rows: list[dict[str, Any]], *, negative_classifier_threshold: float = 0.4) -> dict[str, Any]:
    positives = [row for row in rows if not bool(row.get("is_negative"))]
    negatives = [row for row in rows if bool(row.get("is_negative"))]
    scored = [row for row in positives if row.get("outcome") in {"win", "tie", "loss"}]
    guarded_scored = [row for row in positives if row.get("guarded_outcome") in {"win", "tie", "loss"}]
    strategies = Counter(str(row.get("model_strategy")) for row in rows if str(row.get("model_strategy") or "").strip())
    guarded_reasons = Counter(
        str(row.get("guarded_selection_reason"))
        for row in positives
        if str(row.get("guarded_selection_reason") or "").strip()
    )
    detector_latencies = [float(row.get("detector_ms") or 0.0) for row in rows]
    negative_threshold = max(0.0, float(negative_classifier_threshold))
    return {
        "positive_cases": len(positives),
        "scored_positive_cases": len(scored),
        "unscored_positive_cases": len(positives) - len(scored),
        "wins": sum(row.get("outcome") == "win" for row in scored),
        "ties": sum(row.get("outcome") == "tie" for row in scored),
        "losses": sum(row.get("outcome") == "loss" for row in scored),
        "negative_cases": len(negatives),
        "negative_model_crop_count": sum(bool(row.get("model_crop_found")) for row in negatives),
        "negative_high_confidence_crop_count": sum(
            bool(row.get("model_crop_found")) and _prediction_score(row.get("model_prediction")) >= negative_threshold
            for row in negatives
        ),
        "negative_classifier_threshold": negative_threshold,
        "guarded_model_promotions": sum(row.get("guarded_selected_source") == "model_crop" for row in positives),
        "guarded_frigate_retentions": sum(
            row.get("guarded_selected_source") == "frigate_hint_crop" for row in positives
        ),
        "guarded_selection_reasons": dict(sorted(guarded_reasons.items())),
        "guarded_scored_positive_cases": len(guarded_scored),
        "guarded_wins": sum(row.get("guarded_outcome") == "win" for row in guarded_scored),
        "guarded_ties": sum(row.get("guarded_outcome") == "tie" for row in guarded_scored),
        "guarded_losses": sum(row.get("guarded_outcome") == "loss" for row in guarded_scored),
        "strategies": dict(sorted(strategies.items())),
        "detector_latency_ms": {
            "p50": round(_percentile(detector_latencies, 0.50), 3),
            "p95": round(_percentile(detector_latencies, 0.95), 3),
            "max": round(max(detector_latencies, default=0.0), 3),
        },
    }


def _resolve_image_path(manifest_path: Path, raw_path: str) -> Path:
    image_path = Path(raw_path)
    if image_path.is_absolute():
        return image_path
    repo_root = manifest_path.parents[3]
    return (repo_root / image_path).resolve()


def _top_prediction(
    classifier: Any,
    image: Image.Image,
    *,
    input_source: str,
    is_cropped: bool,
) -> dict[str, Any] | None:
    predictions = classifier.classify(
        image,
        input_context={
            "is_cropped": is_cropped,
            "input_source": input_source,
            "disable_crop_resolution": True,
            "crop_challenger_eval": True,
        },
    )
    if not predictions or not isinstance(predictions[0], dict):
        return None
    top = predictions[0]
    return {
        "label": str(top.get("label") or ""),
        "score": _prediction_score(top),
        "index": top.get("index"),
    }


def _coerce_box(raw_box: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
        return None
    try:
        left, top, right, bottom = [int(round(float(value))) for value in raw_box]
    except (TypeError, ValueError):
        return None
    width, height = image_size
    left = max(0, min(width, left))
    top = max(0, min(height, top))
    right = max(0, min(width, right))
    bottom = max(0, min(height, bottom))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def evaluate_case(
    case: dict[str, Any],
    *,
    manifest_path: Path,
    classifier: Any,
    crop_service: Any,
    crop_context_expander: Callable[[Image.Image, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    image_path = _resolve_image_path(manifest_path, str(case.get("image_path") or ""))
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    raw_boxes = list(case.get("boxes") or [])
    reference_box = _coerce_box(raw_boxes[0], image.size) if raw_boxes else None
    if raw_boxes and reference_box is None:
        raise ValueError(f"Manifest case {case.get('id') or image_path.name} has an invalid Frigate box")
    is_negative = not raw_boxes

    full_prediction = _top_prediction(classifier, image, input_source="full_frame", is_cropped=False)
    frigate_prediction = None
    if reference_box is not None:
        frigate_prediction = _top_prediction(
            classifier,
            image.crop(reference_box),
            input_source="frigate_hint_crop",
            is_cropped=True,
        )

    detector_started = time.perf_counter()
    if reference_box is not None:
        model_result = crop_service.generate_guided_classification_candidate_crop(
            image,
            search_box=reference_box,
        )
    else:
        model_result = crop_service.generate_classification_candidate_crop(image)
    detector_ms = (time.perf_counter() - detector_started) * 1000.0
    if isinstance(model_result, dict) and isinstance(model_result.get("crop_image"), Image.Image):
        model_result = crop_context_expander(image, model_result)
    model_image = model_result.get("crop_image") if isinstance(model_result, dict) else None
    model_prediction = None
    if isinstance(model_image, Image.Image):
        model_prediction = _top_prediction(
            classifier,
            model_image,
            input_source="model_crop",
            is_cropped=True,
        )

    expected_labels = [str(label) for label in (case.get("expected_labels") or []) if str(label).strip()]
    outcome, outcome_reason = compare_expected_outcomes(
        frigate_prediction=frigate_prediction,
        model_prediction=model_prediction,
        expected_labels=expected_labels,
    )
    guarded_prediction, guarded_selected_source, guarded_selection_reason = select_guarded_crop_prediction(
        frigate_prediction=frigate_prediction,
        model_prediction=model_prediction,
    )
    guarded_outcome, guarded_outcome_reason = compare_expected_outcomes(
        frigate_prediction=frigate_prediction,
        model_prediction=guarded_prediction,
        expected_labels=expected_labels,
    )
    return {
        "case_id": str(case.get("id") or image_path.name),
        "visit_id": case.get("visit_id"),
        "bucket": case.get("bucket"),
        "tags": list(case.get("tags") or []),
        "is_negative": is_negative,
        "label_source": case.get("label_source"),
        "expected_labels": expected_labels,
        "full_prediction": full_prediction,
        "frigate_prediction": frigate_prediction,
        "model_prediction": model_prediction,
        "model_crop_found": isinstance(model_image, Image.Image),
        "model_strategy": model_result.get("strategy") if isinstance(model_result, dict) else None,
        "model_detector_tier": model_result.get("detector_tier") if isinstance(model_result, dict) else None,
        "model_reason": model_result.get("reason") if isinstance(model_result, dict) else None,
        "model_fallback_reason": model_result.get("fallback_reason") if isinstance(model_result, dict) else None,
        "model_confidence": model_result.get("confidence") if isinstance(model_result, dict) else None,
        "model_tile_count": model_result.get("tile_count") if isinstance(model_result, dict) else None,
        "model_box": list(model_result.get("box"))
        if isinstance(model_result, dict) and model_result.get("box") is not None
        else None,
        "detector_ms": round(detector_ms, 3),
        "outcome": "unscored" if is_negative else outcome,
        "outcome_reason": "hard_negative" if is_negative else outcome_reason,
        "guarded_prediction": guarded_prediction,
        "guarded_selected_source": "none" if is_negative else guarded_selected_source,
        "guarded_selection_reason": "hard_negative" if is_negative else guarded_selection_reason,
        "guarded_outcome": "unscored" if is_negative else guarded_outcome,
        "guarded_outcome_reason": "hard_negative" if is_negative else guarded_outcome_reason,
    }


async def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    from app.config import settings
    from app.services.bird_crop_service import bird_crop_service
    from app.services.classifier_service import ClassifierService
    from app.services.high_quality_snapshot_service import (
        HQ_MODEL_CROP_EXTRA_EXPAND_RATIO,
        high_quality_snapshot_service,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = validate_manifest(manifest)
    classifier = ClassifierService()
    runtime: dict[str, Any] = {}
    try:
        rows = [
            evaluate_case(
                case,
                manifest_path=manifest_path,
                classifier=classifier,
                crop_service=bird_crop_service,
                crop_context_expander=high_quality_snapshot_service._expand_model_crop_context,
            )
            for case in cases
        ]
        classifier_status = dict(classifier.get_status() or {})
        crop_status = dict(bird_crop_service.get_status() or {})
        runtime = {
            "image_flavor": classifier_status.get("image_flavor"),
            "classifier_model_id": classifier_status.get("effective_model_id")
            or classifier_status.get("active_model_id"),
            "classifier_backend": classifier_status.get("inference_backend"),
            "classifier_provider": classifier_status.get("active_provider"),
            "classifier_fallback_reason": classifier_status.get("fallback_reason"),
            "crop_model_id": crop_status.get("model_id"),
            "crop_active_providers": crop_status.get("active_providers") or {},
            "crop_provider_fallbacks": crop_status.get("provider_fallbacks") or {},
            "hq_model_crop_extra_expand_ratio": HQ_MODEL_CROP_EXTRA_EXPAND_RATIO,
            "classifier_min_confidence": max(
                0.0,
                float(getattr(settings.classification, "min_confidence", 0.4) or 0.4),
            ),
        }
    finally:
        await classifier.shutdown()

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "decision_contract": (
            "Only owner-labelled cases enter win/tie/loss. A model crop wins when it alone is correct or when both "
            f"are correct and its classifier score improves by at least {MODEL_WIN_MARGIN:.2f}. The guarded result "
            "mirrors production: retain Frigate unless the model crop has the same classifier identity and clears "
            "that score margin. Hard-negative detections remain diagnostic; the high-confidence count uses the "
            "active classifier minimum."
        ),
        "runtime": runtime,
        "summary": summarize_rows(
            rows,
            negative_classifier_threshold=float(runtime.get("classifier_min_confidence") or 0.4),
        ),
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = asyncio.run(run(args.manifest.resolve(), args.output.resolve()))
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
