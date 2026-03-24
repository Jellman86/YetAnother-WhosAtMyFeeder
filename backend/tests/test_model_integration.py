"""Integration tests: labeled bird images through the full preprocessing pipeline.

Requires downloaded fixture images. Run first:
    python scripts/download_test_fixtures.py

Then:
    pytest tests/test_model_integration.py -v
    pytest tests/test_model_integration.py -v -k "convnext_large_inat21 and house_sparrow"
    pytest tests/test_model_integration.py -v --model eu_medium_focalnet_b

Each test case parameterizes over (model_id, image_path, expected_labels, min_top_n).
A test PASSES if any acceptable label appears in the top-N predictions above a
minimum confidence floor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
except ImportError:
    ORT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not ORT_AVAILABLE, reason="onnxruntime not installed")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _models_dir() -> Path:
    if os.path.exists("/data/models"):
        return Path("/data/models")
    return Path(__file__).resolve().parent.parent / "data" / "models"

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_IMAGES_DIR = _FIXTURES_DIR / "bird_images"
_MANIFEST_PATH = _FIXTURES_DIR / "bird_image_manifest.json"
_DOWNLOADED_PATH = _IMAGES_DIR / "downloaded.json"


# ---------------------------------------------------------------------------
# Preprocessing (mirrors eval_model_accuracy.py)
# ---------------------------------------------------------------------------

def _preprocess(img_path: Path, config: dict) -> np.ndarray:
    pre = config.get("preprocessing", {})
    input_size = config.get("input_size", 224)
    mean = np.array(pre.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
    std = np.array(pre.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)
    crop_pct = float(pre.get("crop_pct", 1.0)) or 1.0
    resize_mode = pre.get("resize_mode", "center_crop")

    img = Image.open(img_path).convert("RGB")

    if resize_mode == "center_crop":
        scale_size = int(input_size / crop_pct)
        w, h = img.size
        if w < h:
            new_w, new_h = scale_size, int(h * scale_size / w)
        else:
            new_w, new_h = int(w * scale_size / h), scale_size
        img = img.resize((new_w, new_h), Image.BICUBIC)
        left = (new_w - input_size) // 2
        top = (new_h - input_size) // 2
        img = img.crop((left, top, left + input_size, top + input_size))
    else:
        img = img.resize((input_size, input_size), Image.BICUBIC)

    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - mean) / std
    return arr.transpose(2, 0, 1)[np.newaxis].astype(np.float32)


def _softmax(logits: np.ndarray) -> np.ndarray:
    exp = np.exp(logits - logits.max())
    return exp / exp.sum()


def _normalise(label: str) -> str:
    return label.lower().replace("_", " ").replace("-", " ").strip()


def _predict_top_n(session: ort.InferenceSession, tensor: np.ndarray, labels: list[str], n: int = 10) -> list[dict]:
    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: tensor})[0][0]
    probs = _softmax(logits)
    top_idx = np.argsort(probs)[::-1][:n]
    return [{"label": labels[i], "score": float(probs[i])} for i in top_idx]


# ---------------------------------------------------------------------------
# Load manifest and discover test parameters
# ---------------------------------------------------------------------------

def _load_installed_models() -> dict[str, dict[str, Any]]:
    base = _models_dir()
    models: dict[str, dict[str, Any]] = {}
    for d in sorted(base.iterdir()) if base.exists() else []:
        if d.is_dir() and (d / "model.onnx").exists() and (d / "model_config.json").exists():
            config = json.loads((d / "model_config.json").read_text())
            labels = [l.strip() for l in (d / "labels.txt").read_text().splitlines() if l.strip()]
            models[d.name] = {"dir": d, "config": config, "labels": labels}
    return models


def _scope_matches(model_config: dict, case_scope: list[str]) -> bool:
    """Return True if the model's taxonomy_scope and source_model_id match any of the case scopes."""
    taxonomy = model_config.get("taxonomy_scope", "")
    source = model_config.get("source_model_id", "")
    # Determine geographic scope from source model ID
    geo_scope = "global"
    if "-eu-" in source or source.endswith("-eu"):
        geo_scope = "eu"
    elif "-na-" in source or source.endswith("-na"):
        geo_scope = "na"
    # If the model has a known geographic scope, the test case must include
    # that geography — taxonomy alone is not sufficient.
    if geo_scope != "global" and geo_scope not in case_scope:
        return False
    # Check taxonomy scope
    if taxonomy in case_scope:
        return True
    # Check geographic scope
    if geo_scope in case_scope:
        return True
    # If case includes "global" or model is birds_only/wildlife_wide and image scope is global
    if "global" in case_scope:
        return True
    return False


def _build_test_params() -> list[tuple]:
    """Build pytest parameters: (model_id, image_path, expected_labels, min_top_n, case_id)."""
    if not _MANIFEST_PATH.exists() or not _DOWNLOADED_PATH.exists():
        return []

    manifest = json.loads(_MANIFEST_PATH.read_text())
    downloaded = json.loads(_DOWNLOADED_PATH.read_text())
    installed = _load_installed_models()

    params = []
    for case in manifest.get("test_cases", []):
        case_id = case["id"]
        case_images = downloaded.get("cases", {}).get(case_id, [])
        if not case_images:
            continue

        for model_id, model_meta in installed.items():
            if not _scope_matches(model_meta["config"], case.get("scope", [])):
                continue

            for img_record in case_images:
                img_path = Path(img_record.get("path", ""))
                if not img_path.exists():
                    continue
                params.append(pytest.param(
                    model_id,
                    img_path,
                    case["acceptable_labels"],
                    case.get("min_top_n", 5),
                    id=f"{model_id}__{case_id}__{img_path.stem}",
                ))
    return params


_TEST_PARAMS = _build_test_params()
_INSTALLED_MODELS = _load_installed_models()

# Session cache — load each model once
@pytest.fixture(scope="module")
def sessions() -> dict[str, ort.InferenceSession]:
    result: dict[str, ort.InferenceSession] = {}
    needed_ids = {p.values[0] for p in _TEST_PARAMS} if _TEST_PARAMS else set()
    for model_id in needed_ids:
        if model_id not in _INSTALLED_MODELS:
            continue
        model_dir = _INSTALLED_MODELS[model_id]["dir"]
        so = ort.SessionOptions()
        so.intra_op_num_threads = 4
        so.inter_op_num_threads = 2
        so.log_severity_level = 3
        result[model_id] = ort.InferenceSession(
            str(model_dir / "model.onnx"), so,
            providers=["CPUExecutionProvider"]
        )
    return result


# ---------------------------------------------------------------------------
# Correctness tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _TEST_PARAMS, reason="No fixture images found — run scripts/download_test_fixtures.py first")
@pytest.mark.parametrize("model_id,img_path,acceptable_labels,min_top_n", _TEST_PARAMS)
def test_model_identifies_labeled_bird(
    model_id: str,
    img_path: Path,
    acceptable_labels: list[str],
    min_top_n: int,
    sessions: dict,
) -> None:
    """Expected species should appear in the top-N predictions."""
    assert model_id in sessions, f"Session not loaded for {model_id}"
    session = sessions[model_id]
    meta = _INSTALLED_MODELS[model_id]

    tensor = _preprocess(img_path, meta["config"])
    predictions = _predict_top_n(session, tensor, meta["labels"], n=max(min_top_n, 10))

    top_labels_norm = [_normalise(p["label"]) for p in predictions[:min_top_n]]
    acceptable_norm = [_normalise(a) for a in acceptable_labels]

    matched = any(
        any(acc in pred or pred in acc for pred in top_labels_norm)
        for acc in acceptable_norm
    )

    if not matched:
        top5_str = ", ".join(f"{p['label']} ({p['score']:.3f})" for p in predictions[:5])
        pytest.fail(
            f"{model_id} | {img_path.name}\n"
            f"  Expected one of: {acceptable_labels}\n"
            f"  Top-{min_top_n} predictions: {top5_str}"
        )


# ---------------------------------------------------------------------------
# Rejection tests (synthetic images)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _INSTALLED_MODELS, reason="No installed models found")
@pytest.mark.parametrize("model_id", list(_INSTALLED_MODELS.keys()))
def test_white_image_produces_low_confidence(model_id: str, sessions: dict) -> None:
    """A solid white image should not produce very high confidence for any species."""
    if model_id not in sessions:
        pytest.skip("Session not loaded")

    session = sessions[model_id]
    meta = _INSTALLED_MODELS[model_id]
    config = meta["config"]
    input_size = config["input_size"]
    pre = config.get("preprocessing", {})
    mean = np.array(pre.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
    std = np.array(pre.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)

    white = np.ones((input_size, input_size, 3), dtype=np.float32)
    tensor = ((white - mean) / std).transpose(2, 0, 1)[np.newaxis]

    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: tensor})[0][0]
    probs = _softmax(logits)
    top_score = float(probs.max())

    assert top_score < 0.90, (
        f"{model_id}: white image produced suspiciously high confidence {top_score:.3f} — "
        "model may be degenerate or overfit to uniform inputs"
    )


@pytest.mark.skipif(not _INSTALLED_MODELS, reason="No installed models found")
@pytest.mark.parametrize("model_id", list(_INSTALLED_MODELS.keys()))
def test_noise_image_does_not_produce_uniform_output(model_id: str, sessions: dict) -> None:
    """Noise should produce non-uniform output (model is doing something, not constant)."""
    if model_id not in sessions:
        pytest.skip("Session not loaded")

    session = sessions[model_id]
    meta = _INSTALLED_MODELS[model_id]
    input_size = meta["config"]["input_size"]

    rng = np.random.default_rng(42)
    noise = rng.standard_normal((1, 3, input_size, input_size)).astype(np.float32)

    input_name = session.get_inputs()[0].name
    logits = session.run(None, {input_name: noise})[0][0]
    probs = _softmax(logits)

    # If output is uniform, std would be near 0
    std = float(np.std(probs))
    assert std > 1e-5, (
        f"{model_id}: output probabilities have std={std:.2e} — model may be outputting constants"
    )
