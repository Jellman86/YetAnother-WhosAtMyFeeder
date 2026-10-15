from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
from PIL import Image

from scripts.eval_crop_detector_accuracy import (
    CropEvalCase,
    DetectionCandidate,
    compute_iou,
    evaluate_case,
    load_manifest,
    load_manifest_resolved,
    summarize_results,
    _load_candidates_for_case,
)


@pytest.mark.parametrize("problem", ["unverified", "changed_image", "missing_checksum"])
@pytest.mark.parametrize("loader", [load_manifest, load_manifest_resolved])
def test_accuracy_rejects_unbound_annotations_before_loading_a_detector(tmp_path, problem, loader):
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (100, 100)).save(image_path)
    checksum = hashlib.sha256(image_path.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "source-bound",
                        "bucket": "feeder_real",
                        "image_path": str(image_path),
                        "boxes": [[10, 10, 90, 90]],
                        "image_sha256": None if problem == "missing_checksum" else checksum,
                        "annotation_verified": problem != "unverified",
                    }
                ]
            }
        )
    )
    case = loader(manifest)[0]
    if problem == "changed_image":
        Image.new("RGB", (100, 100), "white").save(image_path)

    class NoInference:
        def _ensure_model_for_tier(self, _tier):
            pytest.fail("An invalid panel must not start native inference")

    with pytest.raises(ValueError, match="annotation|checksum"):
        _load_candidates_for_case(NoInference(), case, tier="accurate")


@pytest.mark.parametrize("boxes", [[], [(10, 10, 90, 90)]])
def test_verified_panel_decodes_the_verified_bytes_even_if_the_file_is_replaced(tmp_path, boxes):
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (100, 100)).save(image_path)
    case = CropEvalCase(
        case_id="verified",
        bucket="test",
        image_path=image_path,
        boxes=boxes,
        image_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
        annotation_verified=True,
    )

    class Detector:
        def _ensure_model_for_tier(self, _tier):
            Image.new("RGB", (100, 100), "white").save(image_path)
            return object()

        def _infer_candidates(self, _model, image):
            assert image.getpixel((0, 0)) == (0, 0, 0)
            return []

        def _select_best_valid_candidate(self, _image, _candidates, **_kwargs):
            return {"reason": "no_candidate"}

    assert _load_candidates_for_case(Detector(), case, tier="accurate") == ([], {"reason": "no_candidate"})


def test_accuracy_rejects_boxes_outside_the_verified_image(tmp_path):
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (100, 100)).save(image_path)
    case = CropEvalCase(
        case_id="wrong-coordinate-system",
        bucket="test",
        image_path=image_path,
        boxes=[(10, 10, 110, 110)],
        image_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
        annotation_verified=True,
    )
    with pytest.raises(ValueError, match="annotations are outside"):
        _load_candidates_for_case(object(), case, tier="accurate")


def test_committed_diagnostic_boxes_are_bound_to_the_reviewed_fixture_images():
    cases = load_manifest_resolved(Path(__file__).parent / "fixtures/crop_detector_manifest.json")

    class NoCandidates:
        def _ensure_model_for_tier(self, _tier):
            return object()

        def _infer_candidates(self, _model, _image):
            return []

        def _select_best_valid_candidate(self, _image, _candidates, **_kwargs):
            return {"reason": "no_candidate"}

    assert len(cases) == 8
    for case in cases:
        assert _load_candidates_for_case(NoCandidates(), case, tier="accurate")[0] == []


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


def test_negative_case_reports_false_positive_without_reducing_positive_recall() -> None:
    negative = CropEvalCase(
        case_id="empty_feeder_01",
        bucket="hard_negative",
        image_path=Path("/tmp/empty_feeder.jpg"),
        boxes=[],
        visit_id="empty-visit",
        tags=("foliage", "empty"),
    )

    result = evaluate_case(
        negative,
        [DetectionCandidate(box=(10, 10, 80, 80), confidence=0.7)],
    )
    summary = summarize_results(
        [
            result,
            {
                "case_id": "bird-visit",
                "visit_id": "bird-visit",
                "bucket": "feeder_real",
                "is_negative": False,
                "any_detection": True,
                "best_confidence": 0.8,
                "best_iou": 0.7,
                "recall_at_0_3": True,
                "recall_at_0_5": True,
                "useful_crop": True,
                "tags": ["distant"],
            },
        ]
    )

    assert result["is_negative"] is True
    assert result["false_positive"] is True
    assert summary["overall"]["positive_cases"] == 1
    assert summary["overall"]["negative_cases"] == 1
    assert summary["overall"]["recall_at_0_5"] == 1.0
    assert summary["overall"]["false_positive_rate"] == 1.0
    assert summary["by_tag"]["foliage"]["false_positive_rate"] == 1.0


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
