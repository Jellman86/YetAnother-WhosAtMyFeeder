from __future__ import annotations

import json
from pathlib import Path

from scripts.eval_crop_detector_accuracy import (
    CropEvalCase,
    DetectionCandidate,
    compute_iou,
    evaluate_case,
    load_manifest,
    summarize_results,
)


def test_load_manifest_reads_cases_and_boxes(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake")
    manifest_path = tmp_path / "crop_detector_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "clean_cardinal_01",
                        "bucket": "reference_clean",
                        "image_path": str(image_path),
                        "boxes": [{"x1": 10, "y1": 12, "x2": 90, "y2": 88}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_manifest(manifest_path)

    assert cases == [
        CropEvalCase(
            case_id="clean_cardinal_01",
            bucket="reference_clean",
            image_path=image_path,
            boxes=[(10, 12, 90, 88)],
            source=None,
            notes=None,
        )
    ]


def test_compute_iou_returns_expected_overlap() -> None:
    assert compute_iou((10, 10, 50, 50), (30, 30, 70, 70)) == 400 / 2800
    assert compute_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0


def test_evaluate_case_uses_best_candidate_match() -> None:
    case = CropEvalCase(
        case_id="feeder_robin_01",
        bucket="feeder_real",
        image_path=Path("/tmp/feeder_robin_01.jpg"),
        boxes=[(100, 100, 220, 260)],
    )
    candidates = [
        DetectionCandidate(box=(0, 0, 40, 40), confidence=0.99),
        DetectionCandidate(box=(110, 110, 215, 255), confidence=0.62),
        DetectionCandidate(box=(90, 95, 230, 270), confidence=0.55),
    ]

    result = evaluate_case(case, candidates, iou_thresholds=(0.3, 0.5))

    assert result["case_id"] == "feeder_robin_01"
    assert result["bucket"] == "feeder_real"
    assert result["candidate_count"] == 3
    assert result["any_detection"] is True
    assert result["best_confidence"] == 0.62
    assert result["best_iou"] > 0.7
    assert result["recall_at_0_3"] is True
    assert result["recall_at_0_5"] is True
    assert result["useful_crop"] is True


def test_evaluate_case_handles_no_candidates() -> None:
    case = CropEvalCase(
        case_id="clean_bluejay_01",
        bucket="reference_clean",
        image_path=Path("/tmp/clean_bluejay_01.jpg"),
        boxes=[(10, 10, 80, 80)],
    )

    result = evaluate_case(case, [], iou_thresholds=(0.3, 0.5))

    assert result["candidate_count"] == 0
    assert result["any_detection"] is False
    assert result["best_confidence"] is None
    assert result["best_iou"] == 0.0
    assert result["recall_at_0_3"] is False
    assert result["recall_at_0_5"] is False
    assert result["useful_crop"] is False


def test_summarize_results_aggregates_global_and_per_bucket() -> None:
    summary = summarize_results(
        [
            {
                "bucket": "reference_clean",
                "candidate_count": 1,
                "any_detection": True,
                "best_confidence": 0.81,
                "best_iou": 0.71,
                "recall_at_0_3": True,
                "recall_at_0_5": True,
                "useful_crop": True,
            },
            {
                "bucket": "reference_clean",
                "candidate_count": 0,
                "any_detection": False,
                "best_confidence": None,
                "best_iou": 0.0,
                "recall_at_0_3": False,
                "recall_at_0_5": False,
                "useful_crop": False,
            },
            {
                "bucket": "feeder_real",
                "candidate_count": 2,
                "any_detection": True,
                "best_confidence": 0.44,
                "best_iou": 0.35,
                "recall_at_0_3": True,
                "recall_at_0_5": False,
                "useful_crop": False,
            },
        ]
    )

    assert summary["overall"]["cases"] == 3
    assert summary["overall"]["any_detection_recall"] == 2 / 3
    assert summary["overall"]["recall_at_0_3"] == 2 / 3
    assert summary["overall"]["recall_at_0_5"] == 1 / 3
    assert summary["overall"]["useful_crop_rate"] == 1 / 3
    assert summary["by_bucket"]["reference_clean"]["cases"] == 2
    assert summary["by_bucket"]["reference_clean"]["any_detection_recall"] == 0.5
    assert summary["by_bucket"]["feeder_real"]["mean_best_iou"] == 0.35
