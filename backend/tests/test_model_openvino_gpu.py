"""OpenVINO GPU support validation for installed models.

Verifies that models claiming `intel_gpu` in `supported_inference_providers`
actually compile and produce finite output on OpenVINO GPU, and that models
NOT claiming it either fail gracefully or are excluded by design.

These tests require an Intel GPU and OpenVINO to be available. They are
automatically skipped when GPU hardware is not present.

Run:
    pytest tests/test_model_openvino_gpu.py -v
    pytest tests/test_model_openvino_gpu.py -v -k convnext_large_inat21
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

try:
    import openvino as ov
    OPENVINO_AVAILABLE = True
except ImportError:
    OPENVINO_AVAILABLE = False

# ---------------------------------------------------------------------------
# GPU support matrix (ground truth from manual validation on this hardware)
# Keep this in sync with model_manager.py supported_inference_providers.
# ---------------------------------------------------------------------------

#: Models confirmed to compile AND produce correct (non-degenerate) output in full
#: end-to-end inference on Intel GPU with OpenVINO f32.
#:
#: NOTE: All models tested on this hardware (Intel integrated GPU, OpenVINO 2024.6)
#: have shown either:
#:   - NaN/Inf output (caught by the GPU startup self-test → fallback to CPU)
#:   - Near-uniform/degenerate output on real images (passes NaN check but
#:     produces garbage confidences ~0.0001 per class, effectively uniform over 10K classes)
#:   - OpenCL execution crashes (clWaitForEvents -14)
#:
#: Until a model is validated via full API pipeline benchmark (not just isolated
#: inference), it should NOT be added here.  See docs/features/model-accuracy.md
#: for the benchmark results used to determine this.
GPU_VALIDATED: set[str] = set()

#: Models where Intel GPU is NOT supported, with the failure reason.
#: These have all been tested on Intel integrated GPU with OpenVINO 2024.6.
GPU_NOT_SUPPORTED: dict[str, str] = {
    "convnext_large_inat21":      "Degenerate output — compiles without NaN but produces near-uniform (~0.0001) confidences on real images in full pipeline; effectively unusable",
    "rope_vit_b14_inat21":        "NaN output — RoPE attention ops produce non-finite values in f32 on Intel GPU (caught by startup self-test)",
    "hieradet_small_inat21":      "NaN output — ViT attention produces non-finite values in f32 on Intel GPU (caught by startup self-test)",
    "hieradet_dino_small_inat21": "Compile error — HieraDeT architecture fails to load on OpenVINO GPU plugin",
    "flexivit_il_all":            "NaN output — FlexiViT DINOv2 attention produces non-finite values in f32 on Intel GPU (caught by startup self-test)",
    "eva02_large_inat21":         "Runtime crash — clWaitForEvents error code -14 during OpenCL inference",
    "eu_medium_focalnet_b":       "Degenerate output — compiles and passes isolated NaN test but falls back to CPU in full pipeline due to degraded GPU state",
    "mobilenet_v2_birds":         "TFLite model — not loaded via OpenVINO",
    "bird_crop_detector":         "Crop detector — CPU-only by design",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _models_dir() -> Path:
    if os.path.exists("/data/models"):
        return Path("/data/models")
    return Path(__file__).resolve().parent.parent / "data" / "models"


def _load_config(model_dir: Path) -> dict[str, Any]:
    config_path = model_dir / "model_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    # Legacy fallback
    known: dict[str, int] = {"convnext_large_inat21": 384, "eva02_large_inat21": 336}
    return {"input_size": known.get(model_dir.name, 224)}


def _installed_onnx_models() -> list[tuple[str, Path]]:
    base = _models_dir()
    if not base.exists():
        return []
    return [
        (d.name, d)
        for d in sorted(base.iterdir())
        if d.is_dir() and (d / "model.onnx").exists()
    ]


def _compile_on_gpu(model_path: Path, config: dict[str, Any]) -> tuple[bool, str, bool]:
    """Attempt to compile and run inference on OpenVINO GPU.

    Returns:
        (compile_ok, error_message, has_nan)
    """
    core = ov.Core()
    if "GPU" not in core.available_devices:
        pytest.skip("No Intel GPU device available")

    input_size = config.get("input_size", 224)

    try:
        model = core.read_model(str(model_path))
        # Reshape dynamic batch to static=1 (mirrors classifier_service.py)
        partial = model.inputs[0].get_partial_shape()
        if partial.rank.is_static and partial[0].is_dynamic:
            static_shape = [1] + [partial[d].get_length() for d in range(1, partial.rank.get_length())]
            model.reshape(static_shape)
    except Exception as e:
        return False, f"model read/reshape failed: {e}", False

    try:
        compiled = core.compile_model(
            model,
            "GPU",
            {
                "INFERENCE_PRECISION_HINT": "f32",
                "PERFORMANCE_HINT": "LATENCY",
                "NUM_STREAMS": "1",
            },
        )
    except Exception as e:
        return False, str(e), False

    try:
        infer = compiled.create_infer_request()
        rng = np.random.default_rng(42)
        actual_shape = compiled.inputs[0].shape
        x = np.clip(rng.standard_normal(tuple(actual_shape)), -3, 3).astype(np.float32)
        infer.infer({0: x})
        out = infer.get_output_tensor(0).data
        has_nan = bool(np.any(~np.isfinite(out)))
        return True, "", has_nan
    except Exception as e:
        return True, str(e), False  # compiled OK, inference crashed


# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.skipif(not OPENVINO_AVAILABLE, reason="openvino not installed"),
]


@pytest.fixture(scope="module")
def gpu_available() -> bool:
    if not OPENVINO_AVAILABLE:
        return False
    try:
        core = ov.Core()
        return "GPU" in core.available_devices
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tests: validated GPU models must compile cleanly and produce finite output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", sorted(GPU_VALIDATED))
def test_gpu_validated_model_compiles_and_produces_finite_output(
    model_id: str, gpu_available: bool
) -> None:
    """Models in GPU_VALIDATED must compile on OpenVINO GPU and output finite logits."""
    if not gpu_available:
        pytest.skip("No Intel GPU available")

    models = dict(_installed_onnx_models())
    if model_id not in models:
        pytest.skip(f"{model_id} not installed — download it first via the Model Manager")

    model_dir = models[model_id]
    config = _load_config(model_dir)
    compile_ok, error, has_nan = _compile_on_gpu(model_dir / "model.onnx", config)

    assert compile_ok, f"{model_id}: GPU compile failed: {error}"
    assert not has_nan, (
        f"{model_id}: GPU inference produced NaN/Inf output — "
        "model should be removed from GPU_VALIDATED"
    )


# ---------------------------------------------------------------------------
# Tests: unsupported models must NOT be in GPU_VALIDATED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", sorted(GPU_NOT_SUPPORTED))
def test_gpu_unsupported_model_is_not_in_validated_set(model_id: str) -> None:
    """Models in GPU_NOT_SUPPORTED must not also appear in GPU_VALIDATED."""
    assert model_id not in GPU_VALIDATED, (
        f"{model_id} is listed in both GPU_VALIDATED and GPU_NOT_SUPPORTED — "
        "resolve the contradiction"
    )


# ---------------------------------------------------------------------------
# Tests: registry supported_inference_providers matches our validation sets
# ---------------------------------------------------------------------------

def test_registry_intel_gpu_matches_validation_matrix() -> None:
    """Every model in the registry that lists intel_gpu must be in GPU_VALIDATED."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.services.model_manager import REMOTE_REGISTRY

    mismatches: list[str] = []
    for entry in REMOTE_REGISTRY:
        model_id = entry.get("id", "")
        providers = entry.get("supported_inference_providers") or []
        claims_gpu = "intel_gpu" in providers

        if claims_gpu and model_id not in GPU_VALIDATED:
            mismatches.append(
                f"{model_id}: claims intel_gpu but is not in GPU_VALIDATED"
            )
        if not claims_gpu and model_id in GPU_VALIDATED:
            mismatches.append(
                f"{model_id}: is in GPU_VALIDATED but does not list intel_gpu"
            )

    assert not mismatches, (
        "Registry and GPU validation matrix are out of sync:\n"
        + "\n".join(f"  - {m}" for m in mismatches)
    )


# ---------------------------------------------------------------------------
# Tests: unsupported models produce expected failure (live GPU, informational)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_id,reason", sorted(GPU_NOT_SUPPORTED.items()))
def test_gpu_unsupported_model_fails_or_produces_nan(
    model_id: str, reason: str, gpu_available: bool
) -> None:
    """Unsupported models should either fail to compile or produce NaN — documents why."""
    if not gpu_available:
        pytest.skip("No Intel GPU available")

    models = dict(_installed_onnx_models())
    if model_id not in models:
        pytest.skip(f"{model_id} not installed")

    # Skip TFLite and non-ONNX models
    model_dir = models[model_id]
    if not (model_dir / "model.onnx").exists():
        pytest.skip(f"{model_id} has no model.onnx — not an ONNX model")

    config = _load_config(model_dir)
    compile_ok, error, has_nan = _compile_on_gpu(model_dir / "model.onnx", config)

    # This test is informational — it documents that the model correctly fails.
    # It does NOT assert failure, because the failure mode may vary by GPU driver.
    # What matters is it's not in GPU_VALIDATED.
    if compile_ok and not has_nan:
        pytest.fail(
            f"{model_id}: unexpectedly passed on GPU — "
            f"move it to GPU_VALIDATED and update model_manager.py.\n"
            f"Expected failure reason was: {reason}"
        )
    # compile failed OR has_nan — expected, test passes
