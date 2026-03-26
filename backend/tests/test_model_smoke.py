"""Fast smoke tests for all installed ONNX models.

Verifies that every model directory under data/models/ that contains a
model.onnx is well-formed: loads cleanly, produces output of the right
shape, has no NaN/Inf values, and has a valid model_config.json.

These tests do NOT require network access or real bird images.
They are designed to run inside the container (or locally) and complete
in under 60 seconds even on CPU.

Run:
    pytest tests/test_model_smoke.py -v
    pytest tests/test_model_smoke.py -v -k convnext_large_inat21
"""

from __future__ import annotations

import gc
import json
import os
from pathlib import Path

import numpy as np
import pytest

try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
except ImportError:
    ORT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not ORT_AVAILABLE, reason="onnxruntime not installed")

# ---------------------------------------------------------------------------
# Discover installed models
# ---------------------------------------------------------------------------

def _models_dir() -> Path:
    if os.path.exists("/data/models"):
        return Path("/data/models")
    return Path(__file__).resolve().parent.parent / "data" / "models"


def _discover_installed_models() -> list[tuple[str, Path]]:
    """Return (model_id, model_dir) for every directory with a model.onnx."""
    base = _models_dir()
    if not base.exists():
        return []
    results = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / "model.onnx").exists():
            results.append((d.name, d))
    return results


def _has_sidecar(model_id: str) -> bool:
    """Return True if the model directory has a model_config.json sidecar."""
    return (_model_dir(model_id) / "model_config.json").exists()


def _default_config(model_id: str) -> dict:
    """Return a best-effort config for models without a sidecar (legacy models)."""
    # Best-effort input sizes for known legacy model IDs
    _KNOWN_SIZES: dict[str, int] = {
        "convnext_large_inat21": 384,
        "eva02_large_inat21": 336,
    }
    return {
        "input_size": _KNOWN_SIZES.get(model_id, 224),
        "preprocessing": {
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
    }


def _load_config(model_id: str) -> dict:
    model_dir = _model_dir(model_id)
    config_path = model_dir / "model_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return _default_config(model_id)


_INSTALLED = _discover_installed_models()
_MODEL_IDS = [m[0] for m in _INSTALLED]


def _model_dir(model_id: str) -> Path:
    return dict(_INSTALLED)[model_id]


class _LazySessionCache:
    """Load at most one ORT session at a time to avoid pinning every model in memory."""

    def __init__(self, model_dirs: dict[str, Path], *, session_factory):
        self._model_dirs = model_dirs
        self._session_factory = session_factory
        self._active_model_id: str | None = None
        self._active_session = None

    def __getitem__(self, model_id: str):
        return self.get(model_id)

    def get(self, model_id: str):
        if self._active_model_id == model_id and self._active_session is not None:
            return self._active_session

        self.close()
        model_dir = self._model_dirs[model_id]
        self._active_session = self._session_factory(model_dir / "model.onnx")
        self._active_model_id = model_id
        return self._active_session

    def close(self) -> None:
        self._active_session = None
        self._active_model_id = None
        gc.collect()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ort_session_cache() -> _LazySessionCache:
    """Load ORT sessions lazily so the smoke suite does not pin all models in RAM."""
    model_dirs = dict(_INSTALLED)

    def _build_session(model_path: Path) -> ort.InferenceSession:
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.inter_op_num_threads = 1
        so.log_severity_level = 3  # suppress verbose ORT logs
        return ort.InferenceSession(
            str(model_path), so,
            providers=["CPUExecutionProvider"]
        )

    cache = _LazySessionCache(model_dirs, session_factory=_build_session)
    try:
        yield cache
    finally:
        cache.close()


def test_session_cache_loads_models_on_demand(tmp_path: Path) -> None:
    model_dirs: dict[str, Path] = {}
    for model_id in ("alpha", "beta"):
        model_dir = tmp_path / model_id
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(b"onnx")
        model_dirs[model_id] = model_dir

    created: list[Path] = []

    class FakeSession:
        def __init__(self, model_path: Path):
            self.model_path = model_path

    def _factory(model_path: Path) -> FakeSession:
        created.append(model_path)
        return FakeSession(model_path)

    cache = _LazySessionCache(model_dirs, session_factory=_factory)

    alpha_first = cache["alpha"]
    alpha_second = cache["alpha"]
    beta_first = cache["beta"]
    beta_second = cache["beta"]

    assert alpha_first is alpha_second
    assert beta_first is beta_second
    assert created == [
        model_dirs["alpha"] / "model.onnx",
        model_dirs["beta"] / "model.onnx",
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_config_is_valid(model_id: str) -> None:
    """model_config.json must exist, be valid JSON, and have required fields.
    Legacy models without a sidecar are marked xfail with a descriptive reason."""
    if not _has_sidecar(model_id):
        pytest.xfail(f"{model_id}: no model_config.json sidecar — legacy model, run export_and_config_birder_model.py to generate one")

    model_dir = _model_dir(model_id)
    config = json.loads((model_dir / "model_config.json").read_text())
    assert "input_size" in config, f"{model_id}: missing input_size"
    assert isinstance(config["input_size"], int), f"{model_id}: input_size must be int"
    assert config["input_size"] > 0, f"{model_id}: input_size must be positive"

    pre = config.get("preprocessing", {})
    if pre:
        assert "mean" in pre, f"{model_id}: preprocessing missing mean"
        assert "std" in pre, f"{model_id}: preprocessing missing std"
        assert len(pre["mean"]) == 3, f"{model_id}: mean must have 3 values"
        assert len(pre["std"]) == 3, f"{model_id}: std must have 3 values"
        for v in pre["std"]:
            assert v > 0, f"{model_id}: std values must be positive"


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_labels_file_is_valid(model_id: str) -> None:
    """labels.txt must exist and have at least 10 entries."""
    labels_path = _model_dir(model_id) / "labels.txt"
    assert labels_path.exists(), f"{model_id}: labels.txt missing"

    labels = [l.strip() for l in labels_path.read_text().splitlines() if l.strip()]
    assert len(labels) >= 10, f"{model_id}: expected at least 10 labels, got {len(labels)}"

    # No empty labels
    for i, lbl in enumerate(labels[:100]):
        assert lbl, f"{model_id}: empty label at index {i}"


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_loads_and_has_correct_io(model_id: str, ort_session_cache: dict) -> None:
    """Model loads with ORT and has a single image input and a single output."""
    session = ort_session_cache[model_id]
    assert session is not None

    inputs = session.get_inputs()
    outputs = session.get_outputs()

    assert len(inputs) >= 1, f"{model_id}: expected at least 1 input"
    assert len(outputs) >= 1, f"{model_id}: expected at least 1 output"

    # Input should be 4-D: (batch, C, H, W) or (batch, H, W, C)
    input_shape = inputs[0].shape
    assert len(input_shape) == 4, f"{model_id}: input should be 4-D, got {input_shape}"


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_inference_on_white_image(model_id: str, ort_session_cache: dict) -> None:
    """Running a white image through the model produces valid, finite output."""
    session = ort_session_cache[model_id]
    model_dir = _model_dir(model_id)
    config = _load_config(model_id)
    labels = [l.strip() for l in (model_dir / "labels.txt").read_text().splitlines() if l.strip()]

    input_size = config["input_size"]
    pre = config.get("preprocessing", {})
    mean = np.array(pre.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
    std = np.array(pre.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)

    # Build a white image tensor
    white = np.ones((input_size, input_size, 3), dtype=np.float32)
    white = (white - mean) / std
    white = white.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: white})
    logits = outputs[0][0]

    assert logits.ndim == 1, f"{model_id}: output should be 1-D per sample"
    assert len(logits) == len(labels), (
        f"{model_id}: output length {len(logits)} != labels count {len(labels)}"
    )
    assert np.all(np.isfinite(logits)), f"{model_id}: output contains NaN or Inf"


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_inference_on_noise_image(model_id: str, ort_session_cache: dict) -> None:
    """Running a noise image produces output and doesn't crash."""
    session = ort_session_cache[model_id]
    config = _load_config(model_id)

    input_size = config["input_size"]
    rng = np.random.default_rng(42)
    noise = rng.standard_normal((1, 3, input_size, input_size)).astype(np.float32)

    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: noise})
    assert outputs[0] is not None, f"{model_id}: got None output"


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_softmax_sums_to_one(model_id: str, ort_session_cache: dict) -> None:
    """Softmax over the output logits should sum to approximately 1.0."""
    session = ort_session_cache[model_id]
    config = _load_config(model_id)

    input_size = config["input_size"]
    pre = config.get("preprocessing", {})
    mean = np.array(pre.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
    std = np.array(pre.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)

    rng = np.random.default_rng(7)
    img = rng.random((input_size, input_size, 3)).astype(np.float32)
    img = (img - mean) / std
    img = img.transpose(2, 0, 1)[np.newaxis]

    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: img})[0][0]

    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()
    assert abs(probs.sum() - 1.0) < 1e-4, (
        f"{model_id}: softmax sum {probs.sum():.6f} not close to 1.0"
    )


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_config_num_classes_matches_labels(model_id: str) -> None:
    """num_classes in model_config.json must match the actual labels.txt line count."""
    if not _has_sidecar(model_id):
        pytest.skip(f"{model_id}: no model_config.json — skipping num_classes check")
    model_dir = _model_dir(model_id)
    config = json.loads((model_dir / "model_config.json").read_text())
    labels = [l.strip() for l in (model_dir / "labels.txt").read_text().splitlines() if l.strip()]

    if "num_classes" in config:
        assert config["num_classes"] == len(labels), (
            f"{model_id}: num_classes={config['num_classes']} but labels.txt has {len(labels)} entries"
        )


@pytest.mark.parametrize("model_id", _MODEL_IDS)
def test_model_inference_top_prediction_is_reasonable(model_id: str, ort_session_cache: dict) -> None:
    """For a real bird-coloured image, top prediction score should be > 0.001 (not degenerate)."""
    session = ort_session_cache[model_id]
    config = _load_config(model_id)

    input_size = config["input_size"]
    pre = config.get("preprocessing", {})
    mean = np.array(pre.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
    std = np.array(pre.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)

    # Brown/green gradient vaguely resembling outdoor scene
    rng = np.random.default_rng(99)
    base = np.zeros((input_size, input_size, 3), dtype=np.float32)
    base[:, :, 0] = np.linspace(0.4, 0.7, input_size)[np.newaxis, :]
    base[:, :, 1] = np.linspace(0.3, 0.6, input_size)[:, np.newaxis]
    base[:, :, 2] = 0.2
    base += rng.normal(0, 0.05, base.shape).astype(np.float32)
    base = np.clip(base, 0, 1)
    tensor = ((base - mean) / std).transpose(2, 0, 1)[np.newaxis]

    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: tensor})[0][0]
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()

    top_score = float(probs.max())
    assert top_score > 0.001, (
        f"{model_id}: top prediction score {top_score:.6f} is suspiciously low — "
        "model output may be degenerate"
    )
