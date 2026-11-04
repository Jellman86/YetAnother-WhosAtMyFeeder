from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from PIL import Image

from scripts.eval_bird_count_qualification import main, qualify_counting


def freeze(manifest, predictions):
    frozen = json.dumps(manifest, sort_keys=True).encode()
    predictions["manifest_sha256"] = hashlib.sha256(frozen).hexdigest()
    return frozen


def panel():
    manifest = {
        "protocol": {"minimum_multibird_visits": 1, "minimum_negative_visits": 1},
        "cases": [
            {
                "id": "two",
                "visit_id": "visit-two",
                "tags": ["holdout"],
                "boxes": [[10, 10, 50, 50], [70, 10, 110, 50]],
                "image_sha256": "a" * 64,
                "annotation_verified": True,
                "annotation_scope": "exhaustive",
            },
            {
                "id": "empty",
                "visit_id": "visit-empty",
                "tags": ["holdout"],
                "boxes": [],
                "image_sha256": "b" * 64,
                "annotation_verified": True,
                "annotation_scope": "exhaustive",
            },
        ],
    }
    frozen = json.dumps(manifest, sort_keys=True).encode()
    rows = [
        {"case_id": case["id"], "image_sha256": case["image_sha256"], "boxes": case["boxes"], "status": "completed"}
        for case in manifest["cases"]
    ]
    predictions = {
        "manifest_sha256": hashlib.sha256(frozen).hexdigest(),
        "evaluation_role": "retained_bird_observations",
        "baseline": deepcopy(rows),
        "candidate": deepcopy(rows),
    }
    return manifest, frozen, predictions


def test_object_perfect_independent_holdout_passes_only_the_declared_corpus():
    manifest, frozen, predictions = panel()
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is True
    assert result["candidate"]["matched_birds"] == 2
    assert result["candidate"]["false_birds"] == 0
    assert result["primary_multibird_visits"] == 1


def test_equal_counts_cannot_hide_a_missed_bird_and_a_fixture():
    manifest, frozen, predictions = panel()
    predictions["candidate"][0]["boxes"] = [[10, 10, 50, 50], [150, 150, 190, 190]]
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is False
    assert result["candidate"]["matched_birds"] == 1
    assert result["candidate"]["missed_birds"] == 1
    assert result["candidate"]["false_birds"] == 1
    assert result["candidate"]["exact_count_frames"] == 2
    assert result["candidate"]["exact_object_frames"] == 1


def test_a_duplicate_part_box_is_an_extra_even_when_its_species_is_right():
    manifest, frozen, predictions = panel()
    predictions["candidate"][0]["boxes"] += [[12, 12, 48, 48]]
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is False
    assert result["candidate"]["false_birds"] == 1


@pytest.mark.parametrize("problem", ["checksum", "count_only", "partial", "missing", "duplicate", "raw", "failed"])
def test_incomplete_or_unbound_evidence_cannot_qualify(problem):
    manifest, frozen, predictions = panel()
    if problem == "checksum":
        predictions["manifest_sha256"] = "c" * 64
    elif problem == "count_only":
        del manifest["cases"][0]["boxes"]
    elif problem == "partial":
        manifest["cases"][0]["annotation_scope"] = "target_only"
    elif problem == "missing":
        predictions["candidate"].pop()
    elif problem == "duplicate":
        predictions["candidate"].append(deepcopy(predictions["candidate"][0]))
    elif problem == "raw":
        predictions["evaluation_role"] = "raw_detector_boxes"
    else:
        predictions["candidate"][0]["status"] = "failed"
    if problem in {"count_only", "partial"}:
        frozen = freeze(manifest, predictions)
    assert qualify_counting(manifest, frozen, predictions)["qualified"] is False


@pytest.mark.parametrize("shared", ["visit_id", "image_sha256"])
def test_development_and_holdout_must_not_share_visits_or_images(shared):
    manifest, frozen, predictions = panel()
    development = {**deepcopy(manifest["cases"][0]), "id": "development", "tags": ["development"]}
    development["visit_id"] = "different-visit"
    development["image_sha256"] = "d" * 64
    development[shared] = manifest["cases"][0][shared]
    manifest["cases"].append(development)
    frozen = freeze(manifest, predictions)
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is False
    assert any("leakage" in reason for reason in result["failures"])


def test_repeat_frames_and_public_stress_photos_do_not_inflate_primary_visit_coverage():
    manifest, frozen, predictions = panel()
    manifest["protocol"]["minimum_multibird_visits"] = 2
    for case_id, tag, visit in [("repeat", "holdout", "visit-two"), ("public", "stress", "public-photo")]:
        case = {**deepcopy(manifest["cases"][0]), "id": case_id, "tags": [tag], "visit_id": visit}
        case["image_sha256"] = hashlib.sha256(case_id.encode()).hexdigest()
        manifest["cases"].append(case)
        for run in ["baseline", "candidate"]:
            predictions[run].append(
                {
                    "case_id": case_id,
                    "image_sha256": case["image_sha256"],
                    "boxes": case["boxes"],
                    "status": "completed",
                }
            )
    frozen = freeze(manifest, predictions)
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is False
    assert result["primary_multibird_visits"] == 1


@pytest.mark.parametrize("value", [None, "1", False, 0, -1])
def test_invalid_protocol_targets_fail_without_qualifying(value):
    manifest, _, predictions = panel()
    manifest["protocol"]["minimum_multibird_visits"] = value
    frozen = freeze(manifest, predictions)
    assert qualify_counting(manifest, frozen, predictions)["qualified"] is False


def test_changed_labels_are_not_an_independent_holdout():
    manifest, _, predictions = panel()
    manifest["cases"][0]["annotation_amended_after_inference"] = True
    frozen = freeze(manifest, predictions)
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is False
    assert any("fresh holdout" in reason for reason in result["failures"])


@pytest.mark.parametrize("box", [[0, 0, 0, 2], [0, 0, float("nan"), 2], [True, 0, 1, 2], ["0", 0, 1, 2]])
def test_invalid_prediction_geometry_cannot_be_treated_as_an_empty_result(box):
    manifest, frozen, predictions = panel()
    predictions["candidate"][0]["boxes"] = [box]
    result = qualify_counting(manifest, frozen, predictions)
    assert result["qualified"] is False
    assert any("incomplete or unbound" in reason for reason in result["failures"])


def test_qualification_import_does_not_initialize_application_state(tmp_path):
    backend = Path(__file__).resolve().parents[2]
    code = (
        "import sys; import scripts.eval_bird_count_qualification; "
        "assert not any(name in sys.modules for name in "
        "['app.config', 'app.database', 'onnxruntime', 'app.services.bird_crop_service'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(backend)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("problem", [None, "changed_image", "invalid_image", "outside_image", "frozen_checksum"])
def test_command_verifies_the_original_media_before_reporting_success(tmp_path, monkeypatch, problem):
    manifest, _, predictions = panel()
    for i, case in enumerate(manifest["cases"]):
        path = tmp_path / f"image-{i}.png"
        Image.new("RGB", (128, 128), "black" if i else "white").save(path)
        case["image_path"] = path.name
        case["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        for run in ("baseline", "candidate"):
            predictions[run][i]["image_sha256"] = case["image_sha256"]
    if problem == "outside_image":
        manifest["cases"][0]["boxes"][1] = [70, 10, 150, 50]
        for run in ("baseline", "candidate"):
            predictions[run][0]["boxes"][1] = [70, 10, 150, 50]
    if problem == "invalid_image":
        path = tmp_path / manifest["cases"][0]["image_path"]
        path.write_bytes(b"not an image")
        manifest["cases"][0]["image_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        for run in ("baseline", "candidate"):
            predictions[run][0]["image_sha256"] = manifest["cases"][0]["image_sha256"]
    frozen = freeze(manifest, predictions)
    if problem == "changed_image":
        Image.new("RGB", (128, 128), "red").save(tmp_path / manifest["cases"][0]["image_path"])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(frozen)
    predictions_path = tmp_path / "predictions.json"
    predictions_path.write_text(json.dumps(predictions))
    report_path = tmp_path / "report.json"
    checksum = "f" * 64 if problem == "frozen_checksum" else hashlib.sha256(frozen).hexdigest()
    monkeypatch.setattr(
        "sys.argv",
        [
            "qualification",
            "--manifest",
            str(manifest_path),
            "--frozen-manifest-sha256",
            checksum,
            "--predictions",
            str(predictions_path),
            "--output",
            str(report_path),
        ],
    )
    assert main() == (0 if problem is None else 1)
    assert json.loads(report_path.read_text())["qualified"] is (problem is None)
