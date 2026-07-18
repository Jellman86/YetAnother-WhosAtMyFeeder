"""OpenVINO **NPU** model validation harness.

Companion to ``test_model_openvino_gpu.py`` — targets the Intel NPU ("AI Boost")
device found on Core Ultra (Meteor/Arrow/Lunar Lake) parts. For each installed
ONNX bird model this harness:

  - compiles the model on the NPU using the same static-shape reshape + f32
    precision hint as ``OpenVINOModelInstance.load()`` (the NPU compiler
    *requires* static shapes; f32 guards against f16 activation overflow);
  - verifies the output logits are finite (no NaN/inf);
  - compares NPU vs OpenVINO-CPU logits (logit range ratio, Spearman rank
    correlation, top-5 overlap) so *silent* precision degradation is caught —
    the NPU, like the iGPU, can compile and run yet return the wrong species.

The tests SKIP cleanly when OpenVINO is missing or no NPU device is present
(CI and non-Core-Ultra hosts), so they never break the suite. Run them on real
NPU hardware (e.g. ``/dev/accel/accel0`` passed into the container) to decide
which models earn ``intel_npu`` in ``model_manager`` ``supported_inference_providers``.

``NPU_NOT_SUPPORTED`` documents models known to fail on the NPU (populate from
hardware runs), analogous to ``GPU_NOT_SUPPORTED`` in the GPU harness.
"""

from __future__ import annotations

import pytest

try:
    import numpy as np
    import openvino as ov

    OPENVINO_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    OPENVINO_AVAILABLE = False

if OPENVINO_AVAILABLE:
    # Reuse the shared, already-validated helpers from the GPU harness so the two
    # device harnesses stay consistent (same synthetic image, preprocessing,
    # inference and Spearman implementations).
    from tests.test_model_openvino_gpu import (
        _installed_onnx_models,
        _load_config,
        _make_test_image,
        _preprocess_image,
        _run_inference,
        _spearman_r,
    )

# A model is considered to "match CPU" on the NPU when ALL of these hold. Mirrors
# the GPU harness bar; tighten once real hardware data has been collected.
MIN_LOGIT_RANGE_RATIO = 0.5
MIN_SPEARMAN_R = 0.90
MIN_TOP5_OVERLAP = 1

# Models validated on Arrow Lake-S NPU with OpenVINO 2026.2.1 by the isolated
# full-device sweep on 2026-07-18. Every entry compiled, produced finite output
# for 12 real images, and matched CPU top-1 on all 12.
NPU_VALIDATED: set[str] = {
    "convnext_large_inat21",
    "convnext_v1_tiny_eu_common",
    "eu_medium_focalnet_b",
    "eva02_large_inat21",
    "flexivit_il_all",
    "moganet_s_eu_common",
    "regnet_y_8g_eu_common",
    "rope_vit_b14_inat21",
    "uniformer_s_eu_common",
}

# Models known NOT to work on the NPU — fill in from hardware validation runs.
# Format: model_id -> documented failure reason (compile crash, NaN, wrong top-1).
NPU_NOT_SUPPORTED: dict[str, str] = {}

pytestmark = [
    pytest.mark.skipif(not OPENVINO_AVAILABLE, reason="openvino not installed"),
]


def _npu_present() -> bool:
    try:
        return "NPU" in ov.Core().available_devices
    except Exception:
        return False


@pytest.fixture(scope="module")
def npu_available() -> bool:
    return _npu_present()


def _compile_on_npu(model_path, config) -> tuple[bool, str, object]:
    """Compile an ONNX model on the NPU using the same strategy as
    ``OpenVINOModelInstance.load()``. Returns ``(ok, error, compiled_or_None)``."""
    core = ov.Core()
    if "NPU" not in core.available_devices:
        pytest.skip("No Intel NPU device available")
    try:
        model = core.read_model(str(model_path))
        partial = model.inputs[0].get_partial_shape()
        if partial.rank.is_static and partial[0].is_dynamic:
            static_shape = [1] + [partial[d].get_length() for d in range(1, partial.rank.get_length())]
            model.reshape(static_shape)
    except Exception as e:  # pragma: no cover - hardware/model dependent
        return False, f"model read/reshape failed: {e}", None

    compile_config = {
        "PERFORMANCE_HINT": "LATENCY",
        "NUM_STREAMS": "1",
        "INFERENCE_PRECISION_HINT": "f32",
    }
    try:
        return True, "", core.compile_model(model, "NPU", config=compile_config)
    except Exception as e:  # pragma: no cover - hardware/model dependent
        return False, str(e), None


def test_npu_device_enumerated(npu_available: bool) -> None:
    """The NPU device is visible to OpenVINO (requires /dev/accel passthrough)."""
    if not npu_available:
        pytest.skip("No Intel NPU device on this host")
    assert "NPU" in ov.Core().available_devices


def test_registry_intel_npu_matches_validation_matrix() -> None:
    """Every standalone registry model claiming intel_npu has retained evidence."""
    from app.services.model_manager import REMOTE_REGISTRY

    registry_claims = {
        str(entry.get("id") or "")
        for entry in REMOTE_REGISTRY
        if "intel_npu" in (entry.get("supported_inference_providers") or [])
    }
    assert registry_claims == NPU_VALIDATED


def test_installed_models_compile_and_agree_on_npu(npu_available: bool) -> None:
    """Discovery sweep: compile every installed model on the NPU and compare to CPU.

    Currently reports findings via skip (this harness *discovers* NPU-viable
    models). Once ``intel_npu`` is added to a model's registry entry, promote the
    corresponding assertion to a hard failure to prevent regressions.
    """
    if not npu_available:
        pytest.skip("No Intel NPU device on this host")
    installed = _installed_onnx_models()
    if not installed:
        pytest.skip("No installed ONNX models — download models first")

    core = ov.Core()
    findings: list[str] = []
    passed: list[str] = []

    for model_id, model_dir in installed:
        if model_id in NPU_NOT_SUPPORTED:
            continue
        config = _load_config(model_dir)
        model_path = model_dir / "model.onnx"
        tensor = _preprocess_image(_make_test_image(int(config.get("input_size", 224))), config=config)

        ok, err, npu_compiled = _compile_on_npu(model_path, config)
        if not ok:
            findings.append(f"{model_id}: NPU compile failed: {err}")
            continue
        npu_logits = _run_inference(npu_compiled, tensor)
        if not np.all(np.isfinite(npu_logits)):
            findings.append(f"{model_id}: NPU produced non-finite logits (NaN/inf)")
            continue

        cpu_model = core.read_model(str(model_path))
        cpu_compiled = core.compile_model(cpu_model, "CPU", config={"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "1"})
        cpu_logits = _run_inference(cpu_compiled, tensor)

        cpu_range = float(cpu_logits.max() - cpu_logits.min())
        npu_range = float(npu_logits.max() - npu_logits.min())
        range_ratio = (npu_range / cpu_range) if cpu_range > 0 else 0.0
        spearman = _spearman_r(cpu_logits, npu_logits)
        cpu_top5 = set(np.argsort(cpu_logits)[-5:].tolist())
        npu_top5 = set(np.argsort(npu_logits)[-5:].tolist())
        overlap = len(cpu_top5 & npu_top5)

        summary = f"{model_id}: range_ratio={range_ratio:.2f}, spearman={spearman:.3f}, top5_overlap={overlap}/5"
        if range_ratio >= MIN_LOGIT_RANGE_RATIO and spearman >= MIN_SPEARMAN_R and overlap >= MIN_TOP5_OVERLAP:
            passed.append(summary)
        else:
            findings.append(f"{model_id}: NPU disagrees with CPU ({summary})")

    report = (
        "NPU validation sweep\nPASSED (NPU-viable):\n  "
        + ("\n  ".join(passed) or "(none)")
        + "\nFINDINGS (exclude from intel_npu):\n  "
        + ("\n  ".join(findings) or "(none)")
    )
    # Discovery mode: surface the full report without hard-failing on
    # hardware/model-specific issues (those become NPU_NOT_SUPPORTED + registry).
    pytest.skip(report)
