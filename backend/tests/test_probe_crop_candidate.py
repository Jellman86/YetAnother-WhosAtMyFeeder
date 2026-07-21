from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scripts.probe_crop_candidate import (
    DetrDeployAdapter,
    PreparedInput,
    _summarize_threshold,
    compute_iou,
    load_manifest,
)


def test_detr_adapter_reproduces_centered_letterbox_contract() -> None:
    image = Image.new("RGB", (800, 400), (255, 128, 0))

    prepared = DetrDeployAdapter().prepare(image)

    assert prepared.ratio == 0.8
    assert prepared.pad_x == 0
    assert prepared.pad_y == 160
    assert prepared.original_size == (800, 400)
    assert prepared.feeds["images"].shape == (1, 3, 640, 640)
    assert prepared.feeds["images"].dtype == np.float32
    assert prepared.feeds["orig_target_sizes"].tolist() == [[640, 640]]
    assert np.all(prepared.feeds["images"][:, :, :160, :] == 0.0)
    assert prepared.feeds["images"][0, 0, 160, 0] == pytest.approx(1.0)
    assert prepared.feeds["images"][0, 1, 160, 0] == pytest.approx(128 / 255)


def test_detr_adapter_filters_bird_label_and_reverses_letterbox() -> None:
    prepared = PreparedInput(
        feeds={},
        ratio=0.5,
        pad_x=10,
        pad_y=20,
        original_size=(1000, 800),
    )
    outputs = {
        "labels": np.asarray([[14, 0, 14]], dtype=np.int64),
        "boxes": np.asarray(
            [[[60.0, 70.0, 260.0, 220.0], [0.0, 0.0, 10.0, 10.0], [-20.0, -20.0, 700.0, 700.0]]],
            dtype=np.float32,
        ),
        "scores": np.asarray([[0.8, 0.99, 0.2]], dtype=np.float32),
    }

    candidates = DetrDeployAdapter().parse(outputs, prepared)

    assert len(candidates) == 2
    assert candidates[0].confidence == pytest.approx(0.8)
    assert candidates[0].box == pytest.approx((100.0, 100.0, 500.0, 400.0))
    assert candidates[1].box == pytest.approx((0.0, 0.0, 1000.0, 800.0))


def test_detr_adapter_rejects_non_finite_outputs() -> None:
    prepared = PreparedInput(feeds={}, ratio=1.0, pad_x=0, pad_y=0, original_size=(640, 640))
    outputs = {
        "labels": np.asarray([[14]], dtype=np.int64),
        "boxes": np.asarray([[[0.0, 0.0, np.nan, 1.0]]], dtype=np.float32),
        "scores": np.asarray([[0.5]], dtype=np.float32),
    }

    with pytest.raises(ValueError, match="non-finite"):
        DetrDeployAdapter().parse(outputs, prepared)


def test_threshold_summary_separates_recall_from_false_positives() -> None:
    rows = [
        {
            "ground_truth_boxes": [[0, 0, 100, 100]],
            "candidates": [
                {"box": [200, 200, 300, 300], "confidence": 0.9},
                {"box": [10, 10, 90, 90], "confidence": 0.8},
            ],
        },
        {
            "ground_truth_boxes": [[0, 0, 100, 100]],
            "candidates": [{"box": [10, 10, 90, 90], "confidence": 0.9}],
        },
        {
            "ground_truth_boxes": [],
            "candidates": [{"box": [0, 0, 50, 50], "confidence": 0.3}],
        },
        {"ground_truth_boxes": [], "candidates": []},
    ]

    strict = _summarize_threshold(rows, 0.5)
    permissive = _summarize_threshold(rows, 0.2)

    assert strict["detected_positive_count"] == 2
    assert strict["iou_0_3_count"] == 1
    assert strict["iou_0_5_count"] == 1
    assert strict["any_candidate_iou_0_3_count"] == 2
    assert strict["any_candidate_iou_0_5_count"] == 2
    assert strict["false_positive_count"] == 0
    assert permissive["false_positive_count"] == 1
    assert permissive["false_positive_rate"] == 0.5


def test_load_manifest_resolves_repo_relative_paths_and_rejects_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_path = tmp_path / "images" / "bird.jpg"
    image_path.parent.mkdir()
    Image.new("RGB", (10, 10)).save(image_path)
    manifest_path = tmp_path / "fixtures" / "manifest.json"
    manifest_path.parent.mkdir()
    payload = {
        "cases": [
            {
                "id": "case-1",
                "bucket": "clean",
                "image_path": "images/bird.jpg",
                "boxes": [[1, 1, 8, 8]],
            }
        ]
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cases = load_manifest(manifest_path)

    assert cases[0].image_path == image_path
    assert compute_iou(cases[0].boxes[0], cases[0].boxes[0]) == 1.0

    payload["cases"].append(dict(payload["cases"][0]))
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_manifest(manifest_path)
