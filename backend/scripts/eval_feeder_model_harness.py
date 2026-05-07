"""Evaluate YA-WAMF bird models against labeled feeder snapshots.

This harness differs from eval_model_accuracy.py intentionally: it runs images
through ClassifierService so preprocessing, crop selection, source context, and
model-manager choices match the application path more closely.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

from PIL import Image

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@dataclass(frozen=True)
class FeederEvalCase:
    case_id: str
    image_path: Path
    expected_common_name: str = ""
    expected_scientific_name: str = ""
    taxa_id: int | None = None
    camera_name: str = ""
    source_kind: str = ""
    tags: list[str] | None = None
    notes: str = ""


@dataclass
class FeederEvalResult:
    case_id: str
    model_id: str
    crop_mode: str
    image_path: str
    expected_label: str
    top1_label: str
    top1_score: float
    top3_labels: list[str]
    top1_correct: bool
    top3_correct: bool
    unknown_top1: bool
    high_confidence_unknown: bool
    failure_kind: str
    inference_ms: float
    crop_diagnostics: dict[str, Any]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_label(value: str) -> str:
    normalized = _clean(value).lower()
    for char in ("_", "-", ".", ",", "(", ")", "[", "]"):
        normalized = normalized.replace(char, " ")
    return " ".join(normalized.split())


def _split_tags(value: str) -> list[str]:
    return [tag.strip() for tag in _clean(value).split(",") if tag.strip()]


def _optional_int(value: Any) -> int | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _is_unknown_label(value: str) -> bool:
    normalized = _normalize_label(value)
    return normalized in {"unknown", "unknown bird"} or normalized.startswith("unknown ")


def _expected_labels(case: FeederEvalCase) -> list[str]:
    labels = [
        case.expected_common_name,
        case.expected_scientific_name,
    ]
    return [_normalize_label(label) for label in labels if _normalize_label(label)]


def _label_matches_prediction(expected_labels: Iterable[str], predicted_label: str) -> bool:
    predicted = _normalize_label(predicted_label)
    if not predicted:
        return False
    for expected in expected_labels:
        if predicted == expected:
            return True
    return False


def load_manifest(path: Path | str) -> list[FeederEvalCase]:
    manifest_path = Path(path).resolve()
    cases: list[FeederEvalCase] = []
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=1):
            raw_image_path = _clean(row.get("image_path"))
            if not raw_image_path:
                raise ValueError(f"manifest row {index} is missing image_path")
            image_path = Path(raw_image_path)
            if not image_path.is_absolute():
                image_path = manifest_path.parent / image_path
            expected_common_name = _clean(row.get("expected_common_name"))
            expected_scientific_name = _clean(row.get("expected_scientific_name"))
            taxa_id = _optional_int(row.get("taxa_id"))
            if not expected_common_name and not expected_scientific_name and taxa_id is None:
                raise ValueError(
                    f"manifest row {index} needs expected_common_name, expected_scientific_name, or taxa_id"
                )
            cases.append(
                FeederEvalCase(
                    case_id=_clean(row.get("case_id")) or str(index),
                    image_path=image_path,
                    expected_common_name=expected_common_name,
                    expected_scientific_name=expected_scientific_name,
                    taxa_id=taxa_id,
                    camera_name=_clean(row.get("camera_name")),
                    source_kind=_clean(row.get("source_kind")),
                    tags=_split_tags(row.get("tags", "")),
                    notes=_clean(row.get("notes")),
                )
            )
    return cases


def score_predictions(
    case: FeederEvalCase,
    predictions: list[dict[str, Any]],
    *,
    high_confidence_unknown_threshold: float,
    model_id: str = "",
    crop_mode: str = "",
    inference_ms: float = 0.0,
    crop_diagnostics: dict[str, Any] | None = None,
) -> FeederEvalResult:
    top_predictions = list(predictions or [])
    top1 = top_predictions[0] if top_predictions else {}
    top1_label = _clean(top1.get("label"))
    try:
        top1_score = float(top1.get("score") or 0.0)
    except (TypeError, ValueError):
        top1_score = 0.0

    top3_labels = [_clean(item.get("label")) for item in top_predictions[:3]]
    expected_labels = _expected_labels(case)
    top1_correct = _label_matches_prediction(expected_labels, top1_label)
    top3_correct = any(_label_matches_prediction(expected_labels, label) for label in top3_labels)
    unknown_top1 = _is_unknown_label(top1_label)
    high_confidence_unknown = bool(
        unknown_top1 and top1_score >= float(high_confidence_unknown_threshold)
    )

    failure_kind = ""
    if not top1_correct:
        if high_confidence_unknown:
            failure_kind = "high_confidence_unknown"
        elif unknown_top1:
            failure_kind = "unknown_top1"
        elif not top_predictions:
            failure_kind = "no_prediction"
        else:
            failure_kind = "wrong_species"

    expected_label = case.expected_common_name or case.expected_scientific_name or str(case.taxa_id or "")
    return FeederEvalResult(
        case_id=case.case_id,
        model_id=model_id,
        crop_mode=crop_mode,
        image_path=str(case.image_path),
        expected_label=expected_label,
        top1_label=top1_label,
        top1_score=round(top1_score, 6),
        top3_labels=top3_labels,
        top1_correct=top1_correct,
        top3_correct=top3_correct,
        unknown_top1=unknown_top1,
        high_confidence_unknown=high_confidence_unknown,
        failure_kind=failure_kind,
        inference_ms=round(float(inference_ms), 3),
        crop_diagnostics=dict(crop_diagnostics or {}),
    )


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def aggregate_results(rows: list[FeederEvalResult]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(rows),
        "models": {},
    }
    grouped: dict[tuple[str, str], list[FeederEvalResult]] = {}
    for row in rows:
        grouped.setdefault((row.model_id, row.crop_mode), []).append(row)

    for (model_id, crop_mode), model_rows in sorted(grouped.items()):
        model_bucket = summary["models"].setdefault(model_id, {"crop_modes": {}})
        total = len(model_rows)
        inference_ms = [row.inference_ms for row in model_rows]
        failures: dict[str, int] = {}
        per_species: dict[str, dict[str, int]] = {}
        for row in model_rows:
            if row.failure_kind:
                failures[row.failure_kind] = failures.get(row.failure_kind, 0) + 1
            species = per_species.setdefault(row.expected_label, {"total": 0, "top1_correct": 0, "top3_correct": 0})
            species["total"] += 1
            species["top1_correct"] += int(row.top1_correct)
            species["top3_correct"] += int(row.top3_correct)

        model_bucket["crop_modes"][crop_mode] = {
            "total": total,
            "top1_correct": sum(1 for row in model_rows if row.top1_correct),
            "top3_correct": sum(1 for row in model_rows if row.top3_correct),
            "top1_accuracy": _percent(sum(1 for row in model_rows if row.top1_correct), total),
            "top3_accuracy": _percent(sum(1 for row in model_rows if row.top3_correct), total),
            "unknown_top1_count": sum(1 for row in model_rows if row.unknown_top1),
            "unknown_top1_rate": _percent(sum(1 for row in model_rows if row.unknown_top1), total),
            "high_confidence_unknown_count": sum(1 for row in model_rows if row.high_confidence_unknown),
            "high_confidence_unknown_rate": _percent(
                sum(1 for row in model_rows if row.high_confidence_unknown),
                total,
            ),
            "median_inference_ms": round(sorted(inference_ms)[len(inference_ms) // 2], 3) if inference_ms else 0.0,
            "failure_kinds": dict(sorted(failures.items())),
            "per_species": {
                species: {
                    **counts,
                    "top1_accuracy": _percent(counts["top1_correct"], counts["total"]),
                    "top3_accuracy": _percent(counts["top3_correct"], counts["total"]),
                }
                for species, counts in sorted(per_species.items())
            },
        }
    return summary


def _case_input_context(case: FeederEvalCase) -> dict[str, Any]:
    return {
        "is_cropped": False,
        "event_id": case.case_id,
        "camera_name": case.camera_name,
        "source_kind": case.source_kind,
        "feeder_eval": True,
    }


def evaluate_case(
    case: FeederEvalCase,
    *,
    classifier: Any,
    model_id: str,
    crop_mode: str,
    high_confidence_unknown_threshold: float,
) -> FeederEvalResult:
    image = Image.open(case.image_path).convert("RGB")
    input_context = _case_input_context(case)
    crop_diagnostics: dict[str, Any] = {}
    eval_image = image
    resolver = getattr(classifier, "_resolve_bird_classification_image", None)
    if callable(resolver):
        eval_image, crop_diagnostics = resolver(image, input_context=input_context)
        input_context = {**input_context, "is_cropped": True}

    started = time.perf_counter()
    predictions = classifier.classify(
        eval_image,
        camera_name=case.camera_name or None,
        model_id=model_id,
        input_context=input_context,
    )
    inference_ms = (time.perf_counter() - started) * 1000.0
    return score_predictions(
        case,
        predictions,
        high_confidence_unknown_threshold=high_confidence_unknown_threshold,
        model_id=model_id,
        crop_mode=crop_mode,
        inference_ms=inference_ms,
        crop_diagnostics=crop_diagnostics,
    )


@asynccontextmanager
async def temporary_model_settings(
    *,
    model_manager: Any,
    settings: Any,
    model_id: str,
    crop_mode: str,
    source_mode: str,
) -> AsyncIterator[None]:
    original_active_model_id = getattr(model_manager, "active_model_id", None)
    classification = settings.classification
    original_crop_model_overrides = dict(getattr(classification, "crop_model_overrides", {}) or {})
    original_crop_source_overrides = dict(getattr(classification, "crop_source_overrides", {}) or {})

    if model_id and model_id != original_active_model_id:
        activated = await model_manager.activate_model(model_id)
        if not activated:
            raise RuntimeError(f"model is not installed or cannot be activated: {model_id}")

    crop_model_overrides = dict(original_crop_model_overrides)
    crop_source_overrides = dict(original_crop_source_overrides)
    if crop_mode != "default":
        crop_model_overrides[model_id] = crop_mode
    if source_mode != "default":
        crop_source_overrides[model_id] = source_mode
    classification.crop_model_overrides = crop_model_overrides
    classification.crop_source_overrides = crop_source_overrides

    try:
        yield
    finally:
        classification.crop_model_overrides = original_crop_model_overrides
        classification.crop_source_overrides = original_crop_source_overrides
        if original_active_model_id and getattr(model_manager, "active_model_id", None) != original_active_model_id:
            await model_manager.activate_model(original_active_model_id)


def _write_outputs(rows: list[FeederEvalResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = aggregate_results(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    result_rows = []
    for row in rows:
        payload = asdict(row)
        payload["top3_labels"] = "|".join(row.top3_labels)
        payload["crop_diagnostics"] = json.dumps(row.crop_diagnostics, sort_keys=True)
        result_rows.append(payload)

    fieldnames = (
        list(result_rows[0].keys())
        if result_rows
        else list(FeederEvalResult.__dataclass_fields__.keys())
    )
    with (output_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result_rows)

    failures = [row for row in result_rows if row.get("failure_kind")]
    if failures:
        with (output_dir / "failures.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(failures)


async def run_harness(
    *,
    manifest_path: Path,
    output_dir: Path,
    model_ids: list[str],
    crop_modes: list[str],
    source_mode: str,
    high_confidence_unknown_threshold: float,
) -> dict[str, Any]:
    from app.config import settings
    from app.services.classifier_service import ClassifierService
    from app.services.model_manager import model_manager

    cases = load_manifest(manifest_path)
    rows: list[FeederEvalResult] = []
    for model_id in model_ids:
        for crop_mode in crop_modes:
            async with temporary_model_settings(
                model_manager=model_manager,
                settings=settings,
                model_id=model_id,
                crop_mode=crop_mode,
                source_mode=source_mode,
            ):
                classifier = ClassifierService()
                try:
                    for case in cases:
                        rows.append(
                            evaluate_case(
                                case,
                                classifier=classifier,
                                model_id=model_id,
                                crop_mode=crop_mode,
                                high_confidence_unknown_threshold=high_confidence_unknown_threshold,
                            )
                        )
                finally:
                    await classifier.shutdown()

    _write_outputs(rows, output_dir)
    return aggregate_results(rows)


def _split_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate YA-WAMF models on labeled feeder snapshots.")
    parser.add_argument("--manifest", required=True, help="CSV manifest of labeled feeder images")
    parser.add_argument("--output-dir", required=True, help="Directory for summary.json/results.csv/failures.csv")
    parser.add_argument("--models", required=True, help="Comma-separated installed model IDs to evaluate")
    parser.add_argument(
        "--crop-modes",
        default="default",
        help="Comma-separated crop overrides: default,on,off",
    )
    parser.add_argument(
        "--source-mode",
        default="default",
        help="Optional crop source override, for example default,standard,high_quality",
    )
    parser.add_argument(
        "--high-confidence-unknown-threshold",
        type=float,
        default=0.90,
        help="Top-1 Unknown score at or above this value is counted as high-confidence unknown",
    )
    args = parser.parse_args()

    summary = asyncio.run(
        run_harness(
            manifest_path=Path(args.manifest),
            output_dir=Path(args.output_dir),
            model_ids=_split_csv_arg(args.models),
            crop_modes=_split_csv_arg(args.crop_modes),
            source_mode=args.source_mode,
            high_confidence_unknown_threshold=args.high_confidence_unknown_threshold,
        )
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
