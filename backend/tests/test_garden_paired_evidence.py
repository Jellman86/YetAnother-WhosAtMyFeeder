"""Paired replay must score the saved box and preserve whole-window privacy."""

import copy
import importlib.util
from pathlib import Path
import sys

import pytest


path = Path(__file__).parents[1] / "scripts" / "assess_garden_detector_evidence.py"
spec = importlib.util.spec_from_file_location("garden_paired_evidence", path)
assessment = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = assessment
spec.loader.exec_module(assessment)


SHA = "a" * 64
OTHER = "b" * 64
BIRD = [0.1, 0.1, 0.15, 0.15]
MAMMAL = [0.6, 0.6, 0.2, 0.2]


def report():
    models = {
        "baseline": {
            "sha256": SHA,
            "provider": "cpu",
            "input_contract": "rgb-f32-nchw-640-letterbox114",
            "labels": ["animal", "person", "vehicle"],
            "groups": {"animal": "animal", "person": "person", "vehicle": "vehicle"},
            "head_contract": "raw-bcn-classwise-nms-0.45",
            "score_floors": {"animal": 0.63, "person": 0.2, "vehicle": 0.4},
        },
        "alternative": {
            "sha256": OTHER,
            "provider": "cpu",
            "input_contract": "rgb-f32-nchw-640-letterbox114",
            "labels": ["bird", "cat", "person"],
            "groups": {"bird": "bird", "cat": "mammal", "person": "person"},
            "head_contract": "raw-bcn-classwise-nms-0.45",
            "score_floors": {"bird": 0.2, "cat": 0.2, "person": 0.2},
        },
    }
    samples = []
    for ordinal in range(3):
        sample = {
            "ordinal": ordinal,
            "frame_index": ordinal * 10,
            "source_sha256": SHA,
            "rgb_sha256": SHA,
            "tensor_sha256": OTHER,
        }
        for key, model in models.items():
            sample[key] = {
                "model_sha256": model["sha256"],
                "source_sha256": SHA,
                "provider": model["provider"],
                "rgb_sha256": SHA,
                "tensor_sha256": OTHER,
                "detections": [],
            }
        sample["annotations"] = {
            "rgb_sha256": SHA,
            "complete": True,
            "boxes": [{"label": "bird", "box_xywh": BIRD}, {"label": "mammal", "box_xywh": MAMMAL}],
        }
        samples.append(sample)
    return {
        "schema_version": 1,
        "models": models,
        "windows": [
            {"id": "window-1", "visit_id": "visit-1", "split": "development", "source_sha256": SHA, "samples": samples}
        ],
    }


def policies(value):
    return assessment.assess(value)["windows"][0]["policies"]


def test_localization_success_does_not_hide_a_wrong_stronger_saved_box():
    value = report()
    value["windows"][0]["samples"][0]["baseline"]["detections"] = [["animal", 0.95, BIRD], ["animal", 0.8, MAMMAL]]
    result = policies(value)["baseline"]
    assert result["outcome"] == "candidate"
    assert result["selected"]["truth"] == "bird"
    assert result["any_mammal_localized"] is True
    assert result["selected"]["score"] == 0.95


def test_person_comparison_can_recover_animal_without_mutating_baseline():
    value = report()
    samples = value["windows"][0]["samples"]
    samples[0]["baseline"]["detections"] = [["person", 0.89, BIRD]]
    samples[1]["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    before = copy.deepcopy(value)
    result = policies(value)
    assert result["baseline"]["outcome"] == "person_rejected"
    assert result["person_comparison"]["selected"]["truth"] == "mammal"
    assert value == before


def test_final_person_sample_revokes_earlier_candidates_in_each_policy():
    value = report()
    samples = value["windows"][0]["samples"]
    samples[0]["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    for key in ("baseline", "alternative"):
        samples[2][key]["detections"] = [["person", 0.85, BIRD]]
    for result in policies(value).values():
        assert result["outcome"] == "person_rejected"
        assert result["selected"] is None


def test_bird_gate_removes_only_matching_bird_and_reranks_mammal():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.95, BIRD], ["animal", 0.8, MAMMAL]]
    sample["alternative"]["detections"] = [["bird", 0.96, BIRD], ["cat", 0.75, MAMMAL]]
    result = policies(value)
    assert result["person_comparison"]["selected"]["truth"] == "bird"
    assert result["bird_gate_experiment"]["selected"]["truth"] == "mammal"
    assert result["bird_gate_experiment"]["suppressed_candidates"] == 1
    assert result["bird_gate_experiment"]["suppressed_truth"] == {"bird": 1}


@pytest.mark.parametrize("detections", [[], [["bird", 0.79, BIRD]], [["bird", 0.95, BIRD], ["cat", 0.3, BIRD]]])
def test_missing_weak_or_ambiguous_bird_evidence_retains_candidate(detections):
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, BIRD]]
    sample["alternative"]["detections"] = detections
    assert policies(value)["bird_gate_experiment"]["outcome"] == "candidate"


def test_bird_gate_counts_a_lost_mammal_instead_of_calling_it_noise_reduction():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["alternative"]["detections"] = [["bird", 0.95, MAMMAL]]
    result = policies(value)["bird_gate_experiment"]
    assert result["outcome"] == "no_candidate"
    assert result["lost_mammal_candidate"] is True
    assert result["suppressed_truth"] == {"mammal": 1}


def test_losing_one_mammal_is_reported_even_when_another_mammal_remains():
    value = report()
    first, second, _ = value["windows"][0]["samples"]
    first["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    first["alternative"]["detections"] = [["bird", 0.95, MAMMAL]]
    second["baseline"]["detections"] = [["animal", 0.8, MAMMAL]]
    result = policies(value)["bird_gate_experiment"]
    assert result["outcome"] == "candidate"
    assert result["lost_mammal_candidate"] is True
    assert result["lost_all_localized_mammals"] is False
    assert result["suppressed_truth"] == {"mammal": 1}


def test_bad_localization_overlapping_a_known_animal_is_not_called_background():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, [0.5, 0.5, 0.4, 0.4]]]
    assert policies(value)["baseline"]["selected"]["truth"] == "ambiguous"


def test_command_writes_private_new_report_with_input_checksum(tmp_path, monkeypatch):
    import hashlib
    import json

    evidence, output = tmp_path / "evidence.json", tmp_path / "report.json"
    encoded = json.dumps(report()).encode()
    evidence.write_bytes(encoded)
    monkeypatch.setattr(sys, "argv", ["assess", "--evidence", str(evidence), "--output", str(output)])
    assessment.main()
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["evidence_sha256"] == hashlib.sha256(encoded).hexdigest()
    with pytest.raises(FileExistsError):
        assessment.main()


@pytest.mark.parametrize("annotations", [None, {"rgb_sha256": SHA, "complete": False, "boxes": []}])
def test_missing_or_nonexhaustive_annotations_are_unknown_not_background(annotations):
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["annotations"] = annotations
    assert policies(value)["baseline"]["selected"]["truth"] == "unknown"


def test_exhaustively_reviewed_empty_scene_can_score_background():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["annotations"]["boxes"] = []
    assert policies(value)["baseline"]["selected"]["truth"] == "background"


def test_known_person_not_detected_is_explicit_privacy_failure():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["annotations"]["boxes"].append({"label": "person", "box_xywh": BIRD})
    assert policies(value)["person_comparison"]["known_person_admitted"] is True


def test_equal_scores_keep_first_sample_and_candidate_like_current_worker():
    value = report()
    for sample in value["windows"][0]["samples"]:
        sample["baseline"]["detections"] = [["animal", 0.9, BIRD], ["animal", 0.9, MAMMAL]]
    selected = policies(value)["baseline"]["selected"]
    assert selected["sample_ordinal"] == 0
    assert selected["box_xywh"] == BIRD


@pytest.mark.parametrize(
    "defect",
    [
        "sample",
        "duplicate",
        "model",
        "source",
        "sample_source",
        "provider",
        "rgb",
        "tensor",
        "annotation",
        "box",
        "nonfinite",
        "output",
    ],
)
def test_incomplete_or_mismatched_evidence_is_refused(defect):
    value = report()
    samples = value["windows"][0]["samples"]
    if defect == "sample":
        samples.pop()
    elif defect == "duplicate":
        samples[1]["ordinal"] = 0
    elif defect == "output":
        del samples[0]["alternative"]
    elif defect in {"model", "rgb", "tensor", "source"}:
        samples[0]["alternative"][
            {"model": "model_sha256", "rgb": "rgb_sha256", "tensor": "tensor_sha256", "source": "source_sha256"}[defect]
        ] = "c" * 64
    elif defect == "sample_source":
        samples[0]["source_sha256"] = OTHER
    elif defect == "provider":
        samples[0]["alternative"]["provider"] = "cuda"
    elif defect == "annotation":
        samples[0]["annotations"]["rgb_sha256"] = OTHER
    elif defect == "box":
        samples[0]["baseline"]["detections"] = [["animal", 0.9, [0.9, 0.1, 0.5, 0.2]]]
    elif defect == "nonfinite":
        samples[0]["baseline"]["detections"] = [["animal", float("nan"), MAMMAL]]
    with pytest.raises(ValueError):
        assessment.assess(value)


def test_summary_counts_visits_windows_samples_and_annotation_coverage_separately():
    value = report()
    second = copy.deepcopy(value["windows"][0])
    second["id"] = "window-2"
    for frame in second["samples"]:
        frame["frame_index"] += 100
    second["samples"][0]["annotations"] = None
    value["windows"].append(second)
    summary = assessment.assess(value)["summary"]
    assert summary == {"windows": 2, "samples": 6, "visit_groups": 1, "fully_annotated_samples": 5}


def test_same_visit_cannot_be_counted_as_both_development_and_holdout():
    value = report()
    second = copy.deepcopy(value["windows"][0])
    second.update(id="window-2", split="holdout")
    value["windows"].append(second)
    with pytest.raises(ValueError, match="visit|split"):
        assessment.assess(value)


def test_overlapping_reviewed_species_groups_are_ambiguous():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["annotations"]["boxes"].append({"label": "bird", "box_xywh": MAMMAL})
    assert policies(value)["baseline"]["selected"]["truth"] == "ambiguous"


def test_person_outside_animal_crop_still_rejects_bird_gate_policy():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["alternative"]["detections"] = [["person", 0.4, BIRD]]
    assert policies(value)["bird_gate_experiment"]["outcome"] == "person_rejected"


def test_renaming_a_duplicate_physical_window_does_not_create_an_independent_visit():
    value = report()
    second = copy.deepcopy(value["windows"][0])
    second.update(id="window-2", visit_id="renamed-visit", split="holdout")
    value["windows"].append(second)
    with pytest.raises(ValueError, match="duplicate|physical|split"):
        assessment.assess(value)


def test_identical_rgb_cannot_be_reused_as_independent_holdout():
    value = report()
    second = copy.deepcopy(value["windows"][0])
    second.update(id="window-2", visit_id="another-visit", source_sha256=OTHER, split="holdout")
    for frame in second["samples"]:
        frame["source_sha256"] = OTHER
        for key in ("baseline", "alternative"):
            frame[key]["source_sha256"] = OTHER
    value["windows"].append(second)
    with pytest.raises(ValueError, match="RGB|split"):
        assessment.assess(value)


def test_nested_credible_mammal_abstains_from_bird_suppression():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["baseline"]["detections"] = [["animal", 0.9, MAMMAL]]
    sample["alternative"]["detections"] = [["bird", 0.95, MAMMAL], ["cat", 0.4, [0.65, 0.65, 0.05, 0.05]]]
    assert policies(value)["bird_gate_experiment"]["outcome"] == "candidate"


@pytest.mark.parametrize("defect", ["head", "floor", "coverage", "chronology"])
def test_comparison_refuses_insufficient_extraction_contract(defect):
    value = report()
    model = value["models"]["alternative"]
    if defect == "head":
        model["head_contract"] = "end-to-end"
    elif defect == "floor":
        model["score_floors"]["person"] = 0.5
    elif defect == "coverage":
        del model["score_floors"]["cat"]
    else:
        value["windows"][0]["samples"][0]["frame_index"] = 50
    with pytest.raises(ValueError):
        assessment.assess(value)


def test_no_known_person_admission_is_not_a_privacy_pass_without_complete_review():
    value = report()
    value["windows"][0]["samples"][0]["annotations"] = None
    result = policies(value)["baseline"]
    assert result["known_person_admitted"] is False
    assert result["person_annotations_complete"] is False


def test_nested_mixed_truth_cannot_be_counted_as_clean_bird_suppression():
    value = report()
    sample = value["windows"][0]["samples"][0]
    sample["annotations"]["boxes"].append({"label": "mammal", "box_xywh": [0.13, 0.13, 0.04, 0.04]})
    sample["baseline"]["detections"] = [["animal", 0.9, BIRD]]
    sample["alternative"]["detections"] = [["bird", 0.95, BIRD]]
    result = policies(value)["bird_gate_experiment"]
    assert result["suppressed_truth"] == {"ambiguous": 1}


@pytest.mark.parametrize(
    "candidates",
    [
        [[], [], []],
        [[["animal", 0.9, BIRD]], [["animal", 0.9, MAMMAL]], []],
        [[["animal", 0.8, BIRD]], [["animal", 0.95, MAMMAL]], []],
        [[["animal", 0.9, MAMMAL]], [], [["person", 0.3, BIRD]]],
    ],
)
def test_baseline_reducer_agrees_with_actual_worker_under_mocked_inference(candidates, monkeypatch, tmp_path):
    import hashlib
    from unittest.mock import Mock

    import numpy as np
    from app.services import garden_motion_worker as worker

    value = report()
    for frame, decoded in zip(value["windows"][0]["samples"], candidates):
        frame["baseline"]["detections"] = decoded
    expected = policies(value)["baseline"]
    clip, model, photo = [tmp_path / name for name in ("clip.mp4", "model.onnx", "photo.jpg")]
    clip.write_bytes(b"clip")
    model.write_bytes(b"model")
    reader = Mock()
    props = {
        worker.cv2.CAP_PROP_FRAME_WIDTH: 100,
        worker.cv2.CAP_PROP_FRAME_HEIGHT: 100,
        worker.cv2.CAP_PROP_FPS: 10,
        worker.cv2.CAP_PROP_FRAME_COUNT: 100,
    }
    reader.get.side_effect = lambda key: (
        (reader.read.call_count - 1) * 10 + 1 if key == worker.cv2.CAP_PROP_POS_FRAMES else props[key]
    )
    reader.read.return_value = (True, np.zeros((100, 100, 3), dtype=np.uint8))
    monkeypatch.setattr(worker.cv2, "VideoCapture", lambda *args: reader)
    runtime = Mock(actual=["CPUExecutionProvider"])
    runtime.infer.return_value = np.zeros((1, 7, 1), dtype=np.float32)
    monkeypatch.setattr(worker, "Runtime", lambda *args: runtime)
    monkeypatch.setattr(worker, "decode_candidates", Mock(side_effect=candidates))
    actual = worker.scan_clip(
        {
            "clip": str(clip),
            "model": str(model),
            "photo": str(photo),
            "duration": 10,
            "clip_sha256": hashlib.sha256(b"clip").hexdigest(),
            "model_sha256": hashlib.sha256(b"model").hexdigest(),
            "names": ["animal", "person", "vehicle"],
            "animal_confidence": 0.63,
        }
    )
    assert actual["outcome"] == expected["outcome"]
    if expected["selected"]:
        assert actual["frame_index"] == expected["selected"]["frame_index"]
        assert actual["detector_score"] == expected["selected"]["score"]
        assert list(actual["box_xywh"]) == expected["selected"]["box_xywh"]
