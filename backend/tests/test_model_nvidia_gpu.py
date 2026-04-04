"""NVIDIA GPU diagnostic probe for YA-WAMF models.

This module probes each installed ONNX model through ONNX Runtime's
CUDAExecutionProvider and TensorrtExecutionProvider, comparing results
to CPU reference inference.  It is intended for contributors with NVIDIA
GPUs who want to help establish GPU support status for models that fail
on Intel iGPU.

All tests in this file are DIAGNOSTIC ONLY — they never fail.  Run with
-s to see the full output table, which is designed to be pasted into a
GitHub issue.

QUICK START
-----------
Ensure your Docker container has GPU access (--gpus all or deploy.resources
in compose), then run inside the container:

    docker exec yawamf-backend python -m pytest \\
        tests/test_model_nvidia_gpu.py -v -s

Or to target a specific probe:

    # Full per-model survey across all strategies:
    docker exec yawamf-backend python -m pytest \\
        tests/test_model_nvidia_gpu.py::test_nvidia_gpu_full_probe -v -s

    # ConvNeXt-only focused probe:
    docker exec yawamf-backend python -m pytest \\
        tests/test_model_nvidia_gpu.py::test_convnext_nvidia_probe -v -s

SHARING RESULTS
---------------
If you run these probes, please paste the printed table into the relevant
GitHub issue or discussion.  The most useful data to include is:

  - Output of: nvidia-smi --query-gpu=name,driver_version,memory.total \\
                            --format=csv,noheader
  - Output of: python -c "import onnxruntime; print(onnxruntime.__version__)"
  - The full probe table (run with -s)

HOW TO EXPOSE GPU TO DOCKER
----------------------------
docker-compose.yml (NVIDIA Container Toolkit required):

    services:
      yawamf-backend:
        deploy:
          resources:
            reservations:
              devices:
                - driver: nvidia
                  count: all
                  capabilities: [gpu]

Or for a one-off run:

    docker run --gpus all ghcr.io/jellman86/wamf-backend:dev \\
        python -m pytest tests/test_model_nvidia_gpu.py -v -s
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# ORT import guard
# ---------------------------------------------------------------------------

try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
except ImportError:
    ORT_AVAILABLE = False

pytestmark = [
    pytest.mark.skipif(not ORT_AVAILABLE, reason="onnxruntime not installed"),
]


# ---------------------------------------------------------------------------
# Helpers — mirrored from test_model_openvino_gpu.py for standalone use
# ---------------------------------------------------------------------------

def _models_dir() -> Path:
    if os.path.exists("/data/models"):
        return Path("/data/models")
    return Path(__file__).resolve().parent.parent / "data" / "models"


def _load_config(model_dir: Path) -> dict[str, Any]:
    config_path = model_dir / "model_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
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


def _make_test_image(size: int) -> Image.Image:
    """Deterministic synthetic test image (same as OpenVINO probe)."""
    rng = np.random.default_rng(12345)
    h = w = size
    img = np.zeros((h, w, 3), dtype=np.float32)
    for freq in [2, 4, 8, 16]:
        phase = rng.uniform(0, 2 * np.pi, (3,))
        xs = np.linspace(0, freq * np.pi, w)
        ys = np.linspace(0, freq * np.pi, h)
        xx, yy = np.meshgrid(xs, ys)
        for c in range(3):
            img[:, :, c] += np.cos(xx + phase[c]) * np.sin(yy + phase[c]) / freq
    for c in range(3):
        cmin, cmax = img[:, :, c].min(), img[:, :, c].max()
        if cmax > cmin:
            img[:, :, c] = (img[:, :, c] - cmin) / (cmax - cmin)
    img = (img * 215 + 20).clip(0, 255).astype(np.uint8)
    return Image.fromarray(img, mode="RGB")


def _preprocess_image(image: Image.Image, *, config: dict[str, Any]) -> np.ndarray:
    """Reproduce the classifier_service preprocessing pipeline."""
    input_size = int(config.get("input_size", 224))
    preproc = config.get("preprocessing") or {}
    resize_mode = str(preproc.get("resize_mode") or "center_crop").lower()
    interpolation_name = str(preproc.get("interpolation") or "bicubic").lower()
    crop_pct = float(preproc.get("crop_pct") or 1.0)
    mean = np.array(preproc.get("mean") or [0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array(preproc.get("std") or [0.229, 0.224, 0.225], dtype=np.float32)

    interp_map = {
        "nearest": Image.Resampling.NEAREST,
        "bilinear": Image.Resampling.BILINEAR,
        "bicubic": Image.Resampling.BICUBIC,
        "lanczos": Image.Resampling.LANCZOS,
    }
    interp = interp_map.get(interpolation_name, Image.Resampling.BICUBIC)
    img = image.convert("RGB")

    if resize_mode == "direct_resize":
        img = img.resize((input_size, input_size), interp)
    elif resize_mode == "center_crop":
        scale_size = max(input_size, int(round(input_size / crop_pct)))
        w, h = img.size
        if w <= h:
            new_w, new_h = scale_size, max(1, int(round(h * scale_size / w)))
        else:
            new_h, new_w = scale_size, max(1, int(round(w * scale_size / h)))
        img = img.resize((new_w, new_h), interp)
        left = max(0, (new_w - input_size) // 2)
        top = max(0, (new_h - input_size) // 2)
        img = img.crop((left, top, left + input_size, top + input_size))
    else:  # letterbox
        w, h = img.size
        scale = min(input_size / w, input_size / h)
        new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        img = img.resize((new_w, new_h), interp)
        canvas = Image.new("RGB", (input_size, input_size), (128, 128, 128))
        canvas.paste(img, ((input_size - new_w) // 2, (input_size - new_h) // 2))
        img = canvas

    arr = np.array(img).astype(np.float32) / 255.0
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)
    return arr[np.newaxis, ...].astype(np.float32)


def _spearman_r(a: np.ndarray, b: np.ndarray) -> float:
    n = len(a)
    if n < 2:
        return float("nan")
    rank_a = np.argsort(np.argsort(a)).astype(float)
    rank_b = np.argsort(np.argsort(b)).astype(float)
    d = rank_a - rank_b
    return float(1.0 - 6.0 * np.sum(d ** 2) / (n * (n ** 2 - 1)))


def _ort_run(session: Any, tensor: np.ndarray) -> np.ndarray:
    """Run ORT inference and return flat logit array."""
    input_name = session.get_inputs()[0].name
    out = session.run(None, {input_name: tensor})[0]
    return np.asarray(out, dtype=np.float32).reshape(-1)


def _ort_session(
    model_path: str,
    providers: list,
    provider_options: dict | None = None,
) -> tuple[bool, str, Any]:
    """Create an ORT InferenceSession, returning (ok, error, session)."""
    try:
        opts = ort.SessionOptions()
        opts.log_severity_level = 3  # suppress verbose TRT logs

        if provider_options:
            prov_list = [
                (p, provider_options.get(p, {})) for p in providers
            ]
        else:
            prov_list = providers

        sess = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=prov_list,
        )
        return True, "", sess
    except Exception as e:
        return False, str(e), None


# ---------------------------------------------------------------------------
# NVIDIA detection helpers
# ---------------------------------------------------------------------------

def _nvidia_gpu_info() -> str:
    """Return a one-line GPU description from nvidia-smi, or empty string."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[0].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def _cuda_available() -> bool:
    """Return True if CUDAExecutionProvider can actually run inference."""
    if not ORT_AVAILABLE:
        return False
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return False
    # Probe with a tiny 1×1 ONNX identity model built from scratch
    try:
        from onnx import helper, TensorProto
        x = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])
        y = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 1])
        node = helper.make_node("Identity", inputs=["x"], outputs=["y"])
        graph = helper.make_graph([node], "probe", [x], [y])
        model_proto = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 11)])
        with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as f:
            f.write(model_proto.SerializeToString())
            tmp = f.name
        try:
            ok, _, sess = _ort_session(tmp, ["CUDAExecutionProvider", "CPUExecutionProvider"])
            if ok and sess:
                sess.run(None, {"x": np.ones((1, 1), dtype=np.float32)})
                return True
        finally:
            os.unlink(tmp)
    except Exception:
        pass
    return False


def _trt_available() -> bool:
    if not ORT_AVAILABLE:
        return False
    return "TensorrtExecutionProvider" in ort.get_available_providers()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cuda_available() -> bool:
    return _cuda_available()


@pytest.fixture(scope="module")
def system_info() -> dict[str, str]:
    gpu_info = _nvidia_gpu_info()
    ort_ver = ort.__version__ if ORT_AVAILABLE else "N/A"
    cuda_ver = "unknown"
    trt_ver = "unknown"
    try:
        r = subprocess.run(
            ["nvcc", "--version"], capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            if "release" in line.lower():
                cuda_ver = line.strip()
                break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        import tensorrt  # type: ignore
        trt_ver = tensorrt.__version__
    except ImportError:
        if _trt_available():
            trt_ver = "bundled with ORT (version unknown)"
    return {
        "gpu": gpu_info or "(nvidia-smi not found — GPU name unavailable)",
        "ort": ort_ver,
        "cuda": cuda_ver,
        "trt": trt_ver,
    }


# ---------------------------------------------------------------------------
# Strategies
#
# Each entry: (label, providers list, provider_options dict)
# Providers are passed in priority order; ORT falls back left-to-right.
# ---------------------------------------------------------------------------

_TRT_CACHE = "/tmp/trt_probe_cache"
_TRT_FP16_CACHE = "/tmp/trt_probe_fp16_cache"

STRATEGIES: list[tuple[str, list[str], dict[str, dict]]] = [
    # ── CUDA ──────────────────────────────────────────────────────────────
    (
        "CUDA/fp32",
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
        {},
    ),
    (
        "CUDA/fp32+exhaustive",
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
        {"CUDAExecutionProvider": {"cudnn_conv_algo_search": "EXHAUSTIVE"}},
    ),
    # ── TensorRT ──────────────────────────────────────────────────────────
    # Note: TRT builds an engine on first run (may take several minutes per
    # model).  Subsequent runs use the cached engine.
    (
        "TRT/fp32",
        ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
        {
            "TensorrtExecutionProvider": {
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": _TRT_CACHE,
                "trt_max_workspace_size": str(1 << 30),
            },
        },
    ),
    (
        "TRT/fp16",
        ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
        {
            "TensorrtExecutionProvider": {
                "trt_fp16_enable": True,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": _TRT_FP16_CACHE,
                "trt_max_workspace_size": str(1 << 30),
            },
        },
    ),
    (
        "TRT/fp16+exhaust",
        ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
        {
            "TensorrtExecutionProvider": {
                "trt_fp16_enable": True,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": _TRT_FP16_CACHE + "_ex",
                "trt_max_workspace_size": str(1 << 30),
            },
            "CUDAExecutionProvider": {"cudnn_conv_algo_search": "EXHAUSTIVE"},
        },
    ),
]


# ---------------------------------------------------------------------------
# Probe result helpers
# ---------------------------------------------------------------------------

def _score_result(
    cpu_out: np.ndarray,
    gpu_out: np.ndarray,
    cpu_range: float,
) -> tuple[float, float, float, int, str]:
    """Return (gpu_range, ratio, spearman, top5_overlap, result_label)."""
    finite = gpu_out[np.isfinite(gpu_out)]
    gpu_range = float(finite.ptp()) if finite.size > 1 else 0.0
    ratio = gpu_range / cpu_range if cpu_range > 0 else 0.0
    has_nan = not np.isfinite(gpu_out).all()

    if has_nan or finite.size == 0:
        return gpu_range, ratio, float("nan"), 0, "NaN / non-finite"

    spearman = _spearman_r(cpu_out, gpu_out)
    top5_cpu = set(np.argsort(cpu_out)[-5:])
    top5_gpu = set(np.argsort(gpu_out)[-5:])
    overlap = len(top5_cpu & top5_gpu)

    if ratio < 0.5:
        result = "low range"
    elif spearman < 0.50:
        result = "diverged (wrong ranking)"
    elif overlap == 0:
        result = "top-5 mismatch"
    else:
        result = "*** PASS ***"

    return gpu_range, ratio, spearman, overlap, result


# ---------------------------------------------------------------------------
# Full probe — all installed models × all strategies
# ---------------------------------------------------------------------------

def test_nvidia_gpu_full_probe(cuda_available: bool, system_info: dict[str, str]) -> None:
    """Run every installed ONNX model through all NVIDIA GPU strategies and
    compare against CPU reference inference.

    This test NEVER fails.  Run with -s to see the output:

        pytest tests/test_model_nvidia_gpu.py::test_nvidia_gpu_full_probe -v -s

    Paste the printed table into a GitHub issue when sharing results.
    The result column interpretation:
        *** PASS ***            — GPU output matches CPU (ratio ≥ 0.5, Spearman ≥ 0.50, top-5 ∩ ≥ 1)
        low range               — GPU logit dynamic range is < 50% of CPU (precision collapse)
        diverged (wrong ranking)— Range ok but predictions in wrong order vs CPU
        top-5 mismatch         — No overlap between GPU and CPU top-5 predictions
        NaN / non-finite        — GPU produced non-finite output
        COMPILE/RUN FAIL        — Session creation or inference threw an exception
    """
    if not cuda_available:
        pytest.skip("No NVIDIA CUDA GPU available (CUDAExecutionProvider probe failed)")

    models = _installed_onnx_models()
    if not models:
        pytest.skip("No installed ONNX models found")

    W = 110
    rows: list[str] = []
    rows.append(f"\n{'='*W}")
    rows.append("NVIDIA GPU Probe — YA-WAMF model compatibility report")
    rows.append(f"  GPU:  {system_info['gpu']}")
    rows.append(f"  ORT:  {system_info['ort']}")
    rows.append(f"  CUDA: {system_info['cuda']}")
    rows.append(f"  TRT:  {system_info['trt']}")
    rows.append(f"{'='*W}")
    rows.append(
        f"{'Model':<35} {'Strategy':<22} {'CPU rng':>8} {'GPU rng':>8} "
        f"{'ratio':>6} {'spear':>7} {'top5∩':>6}  result"
    )
    rows.append(f"{'-'*W}")

    for model_id, model_dir in models:
        model_path = str(model_dir / "model.onnx")
        config = _load_config(model_dir)
        input_size = int(config.get("input_size", 224))
        img = _make_test_image(max(input_size, 640))
        tensor = _preprocess_image(img, config=config)

        # CPU reference
        ok, err, cpu_sess = _ort_session(model_path, ["CPUExecutionProvider"])
        if not ok:
            rows.append(f"{model_id:<35} {'(CPU ref failed)':<22}  {err[:60]}")
            rows.append(f"{'-'*W}")
            continue
        cpu_out = _ort_run(cpu_sess, tensor)
        cpu_range = float(cpu_out[np.isfinite(cpu_out)].ptp()) if np.isfinite(cpu_out).any() else 0.0

        first = True
        for strategy_name, providers, provider_options in STRATEGIES:
            # Skip TRT strategies if TRT EP is not available
            if "TensorrtExecutionProvider" in providers and not _trt_available():
                label = f"{model_id if first else '':<35} {strategy_name:<22}"
                rows.append(f"{label} {'(TRT not available — skipped)':>8}")
                first = False
                continue

            ok, err, sess = _ort_session(model_path, providers, provider_options)
            model_col = model_id if first else ""
            first = False

            if not ok:
                short_err = err[:55].replace("\n", " ")
                rows.append(f"{model_col:<35} {strategy_name:<22}  COMPILE/RUN FAIL  {short_err}")
                continue

            try:
                gpu_out = _ort_run(sess, tensor)
            except Exception as e:
                rows.append(f"{model_col:<35} {strategy_name:<22}  RUN FAIL  {str(e)[:55]}")
                continue

            gpu_range, ratio, spearman, overlap, result = _score_result(cpu_out, gpu_out, cpu_range)
            sp_str = f"{spearman:.3f}" if np.isfinite(spearman) else "  nan"
            rows.append(
                f"{model_col:<35} {strategy_name:<22} {cpu_range:>8.2f} {gpu_range:>8.2f} "
                f"{ratio:>6.2f} {sp_str:>7} {overlap:>6}  {result}"
            )

        rows.append(f"{'-'*W}")

    rows.append(f"{'='*W}")
    rows.append(
        "Please paste this table into the relevant GitHub issue/discussion "
        "along with your GPU, driver, and ORT version."
    )
    print("\n".join(rows))
    # Always pass — diagnostic only


# ---------------------------------------------------------------------------
# ConvNeXt-focused probe
# ---------------------------------------------------------------------------

def test_convnext_nvidia_probe(cuda_available: bool, system_info: dict[str, str]) -> None:
    """Focused probe for ConvNeXt Large on NVIDIA GPU.

    ConvNeXt Large is broken on Intel iGPU (precision degradation, not
    fixable with OV 2025.4).  This test checks whether NVIDIA GPU gives
    correct results and which strategies work best.

    Run with -s to see the table:

        pytest tests/test_model_nvidia_gpu.py::test_convnext_nvidia_probe -v -s
    """
    if not cuda_available:
        pytest.skip("No NVIDIA CUDA GPU available")

    models = dict(_installed_onnx_models())
    if "convnext_large_inat21" not in models:
        pytest.skip("convnext_large_inat21 not installed")

    model_dir = models["convnext_large_inat21"]
    model_path = str(model_dir / "model.onnx")
    config = _load_config(model_dir)
    input_size = int(config.get("input_size", 384))
    img = _make_test_image(max(input_size, 640))
    tensor = _preprocess_image(img, config=config)

    ok, err, cpu_sess = _ort_session(model_path, ["CPUExecutionProvider"])
    if not ok:
        pytest.skip(f"CPU reference failed: {err}")
    cpu_out = _ort_run(cpu_sess, tensor)
    cpu_range = float(cpu_out[np.isfinite(cpu_out)].ptp()) if np.isfinite(cpu_out).any() else 0.0

    W = 115
    rows: list[str] = []
    rows.append(f"\n{'='*W}")
    rows.append("ConvNeXt Large — NVIDIA GPU Precision Probe")
    rows.append(f"  GPU:  {system_info['gpu']}")
    rows.append(f"  ORT:  {system_info['ort']}  |  TRT: {system_info['trt']}")
    rows.append(f"  CPU logit range: {cpu_range:.2f}  (target: ratio ≥ 0.5, Spearman ≥ 0.50, top-5 ∩ ≥ 1)")
    rows.append(f"{'='*W}")
    rows.append(
        f"{'Strategy':<24} {'providers':<45} {'GPU rng':>8} "
        f"{'ratio':>6} {'spear':>7} {'top5∩':>6}  result"
    )
    rows.append(f"{'-'*W}")

    for strategy_name, providers, provider_options in STRATEGIES:
        if "TensorrtExecutionProvider" in providers and not _trt_available():
            rows.append(f"{strategy_name:<24} {'(TRT not available)':45}")
            continue

        ok, err, sess = _ort_session(model_path, providers, provider_options)
        prov_str = "+".join(p.replace("ExecutionProvider", "") for p in providers)

        if not ok:
            short_err = err[:60].replace("\n", " ")
            rows.append(f"{strategy_name:<24} {prov_str:<45}  COMPILE/RUN FAIL  {short_err}")
            continue

        try:
            gpu_out = _ort_run(sess, tensor)
        except Exception as e:
            rows.append(f"{strategy_name:<24} {prov_str:<45}  RUN FAIL  {str(e)[:60]}")
            continue

        gpu_range, ratio, spearman, overlap, result = _score_result(cpu_out, gpu_out, cpu_range)
        sp_str = f"{spearman:.3f}" if np.isfinite(spearman) else "  nan"
        rows.append(
            f"{strategy_name:<24} {prov_str:<45} {gpu_range:>8.2f} "
            f"{ratio:>6.2f} {sp_str:>7} {overlap:>6}  {result}"
        )

    rows.append(f"{'='*W}")
    rows.append(
        "Intel iGPU result for reference: ratio≈0.19, Spearman≈0.52, top-5∩=1 (low range — wrong predictions).\n"
        "If *** PASS *** appears here, ConvNeXt Large can be enabled for NVIDIA GPU users."
    )
    print("\n".join(rows))
    # Always pass — diagnostic only
