"""Pure provider policy: explicit inputs in, an immutable plan out.

No settings, files, devices or classifier instance are involved, so every case here
is the decision alone.
"""

import dataclasses

import pytest

from app.services.inference.provider_policy import (
    InferenceSelection,
    apply_host_validated_providers,
    is_gpu_provider_name,
    normalize_inference_provider,
    provider_supported_for_spec,
    reconcile_ort_active_provider,
    resolve_inference_selection,
    runtime_fallback_targets_for,
    unique_provider_names,
)

ALL_DEVICES = {
    "ort_available": True,
    "cuda_available": True,
    "openvino_available": True,
    "intel_cpu_available": True,
    "intel_gpu_available": True,
    "intel_npu_available": True,
}
CPU_ONLY = {"ort_available": True}


def test_a_selection_is_an_immutable_plan():
    selection = resolve_inference_selection("cpu", CPU_ONLY)

    assert selection == InferenceSelection(
        requested_provider="cpu",
        active_provider="cpu",
        backend="onnxruntime",
        ort_providers=("CPUExecutionProvider",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        selection.backend = "openvino"  # type: ignore[misc]


def test_auto_follows_the_measured_host_order_before_the_default_order():
    selection = resolve_inference_selection("auto", ALL_DEVICES, preferred_providers=["cuda", "intel_gpu"])

    assert (selection.backend, selection.active_provider) == ("onnxruntime", "cuda")
    assert selection.ort_providers == ("CUDAExecutionProvider", "CPUExecutionProvider")
    assert selection.fallback_reason is None


def test_auto_without_evidence_prefers_accelerators_the_model_allows():
    selection = resolve_inference_selection("auto", ALL_DEVICES, supported_providers=["intel_cpu", "cpu"])

    assert (selection.backend, selection.openvino_device) == ("openvino", "CPU")


def test_an_unavailable_request_falls_back_and_says_why():
    selection = resolve_inference_selection("intel_npu", {**CPU_ONLY, "openvino_available": True})

    assert selection.active_provider == "cpu"
    assert selection.requested_provider == "intel_npu"
    assert selection.fallback_reason == "Intel NPU requested but OpenVINO NPU is not available"


def test_a_model_restriction_is_named_in_the_fallback_reason():
    selection = resolve_inference_selection("intel_gpu", ALL_DEVICES, supported_providers=["cpu"])

    assert selection.active_provider == "cpu"
    assert (selection.fallback_reason or "").startswith("Active model artifact does not support Intel GPU")


def test_a_failed_cuda_probe_is_reported_rather_than_claimed():
    caps = {**CPU_ONLY, "cuda_provider_installed": True, "cuda_probe_error": "libcublasLt.so.12 missing"}

    selection = resolve_inference_selection("cuda", caps)

    assert selection.active_provider == "cpu"
    assert "failed runtime probe: libcublasLt.so.12 missing" in (selection.fallback_reason or "")


def test_no_onnx_capable_runtime_is_unavailable_not_cpu():
    selection = resolve_inference_selection("auto", {})

    assert (selection.backend, selection.active_provider) == ("unavailable", "unavailable")
    assert selection.ort_providers == ()


def test_gpu_recovery_steps_down_through_cpu_runtimes_to_tflite():
    targets = runtime_fallback_targets_for(active_backend="openvino", active_provider="intel_gpu", caps=ALL_DEVICES)

    assert targets == [("openvino", "intel_cpu"), ("onnxruntime", "cpu"), ("tflite", "tflite")]


def test_tflite_has_nothing_further_to_fall_back_to():
    assert runtime_fallback_targets_for(active_backend="tflite", active_provider="tflite", caps=ALL_DEVICES) == []


def test_host_evidence_narrows_the_contract_and_may_widen_to_reviewed_candidates_only():
    spec = {
        "supported_inference_providers": ["cpu", "intel_gpu"],
        "candidate_inference_providers": ["cpu", "intel_gpu", "intel_npu"],
    }

    resolved = apply_host_validated_providers(
        spec, validated_providers=["intel_npu", "cuda", "cpu"], preference_order=["cpu", "intel_npu"]
    )

    assert resolved["supported_inference_providers"] == ["cpu", "intel_npu"]
    assert resolved["host_added_inference_providers"] == ["intel_npu"]
    assert resolved["host_validated_inference_providers"] == ["intel_npu", "cpu"]
    assert resolved["host_validation_applied"] is True
    assert spec["supported_inference_providers"] == ["cpu", "intel_gpu"]


def test_without_host_evidence_the_safe_baseline_stays_selectable():
    resolved = apply_host_validated_providers(
        {"supported_inference_providers": ["cpu", "intel_cpu"]}, validated_providers=[], preference_order=["cpu"]
    )

    assert resolved["supported_inference_providers"] == ["cpu", "intel_cpu"]
    assert resolved["host_validation_applied"] is False


def test_a_cuda_session_that_started_on_cpu_is_reported_honestly():
    active, reason = reconcile_ort_active_provider("cuda", ["CPUExecutionProvider"])

    assert active == "cpu"
    assert "without CUDAExecutionProvider" in (reason or "")
    assert reconcile_ort_active_provider("cuda", ["CUDAExecutionProvider"]) == ("cuda", None)


@pytest.mark.parametrize(
    ("value", "expected"), [(None, "auto"), (" Intel_GPU ", "intel_gpu"), ("tpu", "auto"), ("cpu", "cpu")]
)
def test_provider_names_normalise_to_the_supported_set(value, expected):
    assert normalize_inference_provider(value) == expected


def test_provider_lists_drop_auto_unknown_and_duplicates_in_order():
    assert unique_provider_names(["auto", "CUDA", "tpu", "cpu", "cuda"]) == ["cuda", "cpu"]


def test_a_model_without_an_allow_list_supports_every_provider():
    assert provider_supported_for_spec({}, "intel_npu") is True
    assert provider_supported_for_spec({"supported_inference_providers": ["cpu"]}, "intel_npu") is False


@pytest.mark.parametrize(("name", "is_gpu"), [("GPU", True), ("gpu.1", True), ("intel_gpu", True), ("NPU", False)])
def test_gpu_provider_names_are_recognised(name, is_gpu):
    assert is_gpu_provider_name(name) is is_gpu
