"""The hardware runner's safety contract needs no model downloads or accelerator."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts.run_model_hardware_gate import (
    discover_models,
    run_child,
    validate_report,
    compare_reports,
    gate_passed,
    validate_images,
)


def test_registry_discovery_includes_nested_variants_and_excludes_retired_artifacts(tmp_path):
    for name in ("standalone", "family/eu", "family/na", "retired"):
        folder = tmp_path / name
        folder.mkdir(parents=True)
        (folder / "model.onnx").touch()
    registry = [
        {"id": "standalone", "supported_inference_providers": ["cpu"]},
        {
            "id": "family",
            "region_variants": {
                "eu": {"supported_inference_providers": ["cpu", "intel_npu"]},
                "na": {"supported_inference_providers": ["cpu", "cuda"]},
            },
        },
    ]
    models = discover_models(tmp_path, registry)
    assert set(models) == {"standalone", "family/eu", "family/na"}
    assert models["family/eu"]["supported_inference_providers"] == ["cpu", "intel_npu"]


def good_report():
    return {
        "compile": {"ok": True},
        "output_summary": {
            "element_count": 4,
            "finite_count": 4,
            "finite_min": 0.1,
            "finite_max": 0.9,
        },
        "per_image_top_indices": [[0, 1], [1, 0]],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"runtime_error": "driver error"},
        {"compile": {"ok": False}},
        {"output_summary": {"element_count": 0, "finite_count": 0}},
        {"per_image_top_indices": [[0, 1]]},
        {"per_image_top_indices": [[], []]},
        {"output_summary": {"element_count": 4, "finite_count": 3}},
        {"output_summary": {"element_count": 4, "finite_count": 4, "finite_min": -0.2, "finite_max": 1.2}},
    ],
)
def test_bad_or_incomplete_probe_reports_fail(mutation):
    assert not validate_report(good_report() | mutation, image_count=2, crop=False)


def test_finite_complete_classification_report_passes():
    assert validate_report(good_report(), image_count=2, crop=False)


def test_provider_disagreement_is_not_a_pass():
    baseline = good_report()
    assert compare_reports(baseline, baseline, crop=False)["agrees"]
    assert not compare_reports(baseline, baseline | {"per_image_top_indices": [[1, 0], [1, 0]]}, crop=False)["agrees"]
    assert not compare_reports(baseline, baseline | {"per_image_top_indices": [[0, 5], [1, 5]]}, crop=False)["agrees"]


@pytest.mark.parametrize(
    "program,expected",
    [
        ("import os;os._exit(7)", "crashed"),
        ("import time;time.sleep(30)", "timeout"),
        ("pass", "missing_report"),
    ],
)
def test_each_child_failure_has_a_durable_result(tmp_path, program, expected):
    result = run_child([sys.executable, "-c", program], tmp_path, timeout=0.1 if expected == "timeout" else 2)
    assert result["status"] == expected
    assert json.loads((tmp_path / "result.json").read_text())["status"] == expected


def test_malformed_child_report_is_not_success(tmp_path):
    report = tmp_path / "probe.json"
    report.write_text("not json")
    assert run_child([sys.executable, "-c", "pass"], tmp_path, timeout=1)["status"] == "invalid_report"


def test_missing_executable_is_reported(tmp_path):
    result = run_child([str(Path(tmp_path / "missing-executable"))], tmp_path, timeout=1)
    assert result["status"] == "spawn_failed"


def test_a_requested_accelerator_cannot_pass_without_being_exercised():
    results = [{"provider": "cpu", "status": "passed"}, {"provider": "intel_npu", "status": "not_applicable"}]
    assert not gate_passed(results, ["cpu", "intel_npu"])
    assert not gate_passed([], ["cpu"])
    assert gate_passed(results + [{"provider": "intel_npu", "status": "passed"}], ["cpu", "intel_npu"])


def test_a_native_crash_cannot_be_masked_by_other_passes():
    assert not gate_passed([{"provider": "cpu", "status": "passed"}, {"provider": "cpu", "status": "crashed"}], ["cpu"])


def test_corrupt_real_image_cannot_silently_become_a_synthetic_pass(tmp_path):
    path = tmp_path / "bird.jpg"
    path.write_bytes(b"not a photograph")
    with pytest.raises(OSError):
        validate_images([str(path)])


def test_crop_gate_requires_all_real_images_and_unique_negative_cases():
    report = good_report() | {
        "real_images_evaluated": 2,
        "negative_images_evaluated": 3,
        "per_image_detections": [{"image": str(index), "top_detection": None} for index in range(5)],
    }
    assert validate_report(report, image_count=2, crop=True)
    assert not validate_report(report | {"real_images_evaluated": 1}, image_count=2, crop=True)
    assert not validate_report(report | {"per_image_detections": [{"image": "same"}] * 5}, image_count=2, crop=True)


def test_model_cases_are_grouped_without_moving_other_tests():
    from tests.model_fixture_support import group_model_cases

    def case(filename, model, name):
        return SimpleNamespace(nodeid=f"tests/{filename}::{name}", callspec=SimpleNamespace(params={"model_id": model}))

    beta = case("test_model_smoke.py", "beta", "first")
    alpha = case("test_model_smoke.py", "alpha", "first")
    alpha_second = case("test_model_smoke.py", "alpha", "second")
    other = case("test_other.py", "not-a-model-fixture", "unrelated")
    items = [beta, other, alpha, alpha_second]
    group_model_cases(items)
    assert items == [alpha, other, alpha_second, beta]
