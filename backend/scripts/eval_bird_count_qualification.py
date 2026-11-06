"""Qualify retained bird observations against a frozen, object-labelled panel.

This is an offline evidence check, not an inference runner or deployment gate.
It never starts a model, accesses an application database or rewrites history.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image

from app.utils.box_matching import matched_box_count


COHORTS = {"development", "holdout", "stress"}
IOU_THRESHOLD = 0.5


def _box(raw: Any) -> tuple[float, float, float, float] | None:
    if (
        not isinstance(raw, (list, tuple))
        or len(raw) != 4
        or any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in raw)
    ):
        return None
    try:
        value = tuple(float(x) for x in raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(x) for x in value) or value[2] <= value[0] or value[3] <= value[1]:
        return None
    return value if min(value) >= 0 else None


def _checksum(raw: Any) -> bool:
    return isinstance(raw, str) and len(raw) == 64 and all(c in "0123456789abcdef" for c in raw)


def qualify_counting(manifest: dict, frozen_manifest: bytes, predictions: dict) -> dict:
    """Require object matches; equal totals alone cannot qualify a counting policy."""
    failures: list[str] = []
    digest = hashlib.sha256(frozen_manifest).hexdigest()
    try:
        if json.loads(frozen_manifest) != manifest:
            failures.append("manifest differs from frozen bytes")
    except (ValueError, UnicodeDecodeError):
        failures.append("invalid frozen manifest")
    if predictions.get("manifest_sha256") != digest:
        failures.append("predictions are not bound to the frozen manifest")
    if predictions.get("evaluation_role") != "retained_bird_observations":
        failures.append("evidence must contain retained bird observations, not raw detector boxes")

    protocol = manifest.get("protocol") or {}
    minimums = {}
    for key in ("minimum_multibird_visits", "minimum_negative_visits"):
        if type(protocol.get(key)) is not int or protocol[key] < 1:
            failures.append(f"protocol must declare a positive {key}")
            minimums[key] = math.inf
        else:
            minimums[key] = protocol[key]

    cases: dict[str, tuple[dict, str]] = {}
    visits: dict[str, set[str]] = {}
    images: dict[str, set[str]] = {}
    for case in manifest.get("cases", []):
        case_id = str(case.get("id") or "")
        tags = COHORTS.intersection(case.get("tags") or [])
        if not case_id or case_id in cases or len(tags) != 1:
            failures.append(f"invalid or duplicate case/cohort: {case_id}")
            continue
        cohort = next(iter(tags))
        cases[case_id] = (case, cohort)
        visit = case.get("visit_id")
        checksum = case.get("image_sha256")
        if not isinstance(visit, str) or not visit.strip() or not _checksum(checksum):
            failures.append(f"missing visit or image binding: {case_id}")
        else:
            visits.setdefault(visit, set()).add(cohort)
            images.setdefault(checksum, set()).add(cohort)
        if (
            case.get("annotation_verified") is not True
            or case.get("annotation_scope") != "exhaustive"
            or not isinstance(case.get("boxes"), list)
            or any(_box(box) is None for box in case.get("boxes", []))
        ):
            failures.append(f"exhaustive verified object boxes required: {case_id}")
        if cohort == "holdout" and case.get("annotation_amended_after_inference"):
            failures.append(f"amended annotations require a fresh holdout: {case_id}")
    if any(len(cohorts) > 1 for cohorts in visits.values()) or any(len(cohorts) > 1 for cohorts in images.values()):
        failures.append("visit or image leakage across development, holdout or stress cohorts")

    primary = [case for case, cohort in cases.values() if cohort == "holdout"]
    multi = {case.get("visit_id") for case in primary if len(case.get("boxes") or []) >= 2}
    negative = {case.get("visit_id") for case in primary if case.get("boxes") == []}
    if len(multi) < minimums["minimum_multibird_visits"]:
        failures.append("insufficient independent primary multibird visits")
    if len(negative) < minimums["minimum_negative_visits"]:
        failures.append("insufficient independent primary negative visits")
    evaluated = {key: case for key, (case, cohort) in cases.items() if cohort != "development"}
    summaries = {}
    details: dict[str, list[dict]] = {}
    for run in ("baseline", "candidate"):
        rows: dict[str, dict] = {}
        for row in predictions.get(run, []):
            case_id = row.get("case_id")
            if case_id in rows or case_id not in cases:
                failures.append(f"{run}: duplicate or unknown prediction case: {case_id}")
            rows[case_id] = row
        results = []
        for case_id, case in evaluated.items():
            row = rows.get(case_id)
            if (
                row is None
                or row.get("status") != "completed"
                or row.get("image_sha256") != case.get("image_sha256")
                or not isinstance(row.get("boxes"), list)
                or any(_box(box) is None for box in row.get("boxes", []))
            ):
                failures.append(f"{run}: incomplete or unbound result: {case_id}")
                continue
            if not isinstance(case.get("boxes"), list) or any(_box(box) is None for box in case["boxes"]):
                continue
            matched = matched_box_count(case["boxes"], row["boxes"], IOU_THRESHOLD)
            metrics = {
                "matched_targets": matched,
                "missed_targets": len(case["boxes"]) - matched,
                "unmatched_candidates": len(row["boxes"]) - matched,
                "exact_localization": matched == len(case["boxes"]) == len(row["boxes"]),
            }
            results.append(
                {
                    "case_id": case_id,
                    "visit_id": case.get("visit_id"),
                    **metrics,
                    "exact_count": len(case["boxes"]) == len(row["boxes"]),
                }
            )
            if run == "candidate" and not metrics["exact_localization"]:
                failures.append(f"candidate: missed or extra bird: {case_id}")
        summaries[run] = {
            "frames": len(results),
            "matched_birds": sum(row["matched_targets"] for row in results),
            "missed_birds": sum(row["missed_targets"] for row in results),
            "false_birds": sum(row["unmatched_candidates"] for row in results),
            "exact_count_frames": sum(row["exact_count"] for row in results),
            "exact_object_frames": sum(row["exact_localization"] for row in results),
        }
        details[run] = results
    return {
        "qualified": not failures,
        "scope": "Declared annotated counting corpus only; hardware compatibility and deployment remain separate.",
        "manifest_sha256": digest,
        "iou_threshold": IOU_THRESHOLD,
        "primary_multibird_visits": len(multi),
        "primary_negative_visits": len(negative),
        "failures": failures,
        **summaries,
        "cases": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--frozen-manifest-sha256", required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen = args.manifest.read_bytes()
    manifest = json.loads(frozen)
    predictions = json.loads(args.predictions.read_bytes())
    result = qualify_counting(manifest, frozen, predictions)
    if hashlib.sha256(frozen).hexdigest() != args.frozen_manifest_sha256:
        result["failures"].append("manifest does not match the independently recorded frozen checksum")
    for case in manifest.get("cases", []):
        path = Path(case.get("image_path") or "")
        if not path.is_absolute():
            path = args.manifest.parent / path
        try:
            content = path.read_bytes()
            matches = hashlib.sha256(content).hexdigest() == case.get("image_sha256")
            with Image.open(BytesIO(content)) as image:
                image.verify()
                width, height = image.size
            boxes = list(case.get("boxes") or [])
            for run in ("baseline", "candidate"):
                boxes.extend(
                    box
                    for row in predictions.get(run, [])
                    if row.get("case_id") == case.get("id")
                    for box in row.get("boxes", [])
                )
            if any(_box(box) is None or box[2] > width or box[3] > height for box in boxes):
                result["failures"].append(f"object box lies outside the verified image: {case.get('id')}")
        except (OSError, ValueError):
            matches = False
        if not matches:
            result["failures"].append(f"image checksum missing or changed: {case.get('id')}")
    result["qualified"] = not result["failures"]
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
