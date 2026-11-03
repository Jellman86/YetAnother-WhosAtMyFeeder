"""Pixels and geometry must match the qualified raw Cedar export."""

import numpy as np
import pytest

from app.services.garden_detector_runtime import detector_input, decode_candidates


def test_rgb_letterbox_uses_unit_nchw_and_neutral_padding_without_channel_swap():
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    image[:, :, 0] = 255
    tensor, meta = detector_input(image)
    assert tensor.shape == (1, 3, 640, 640) and tensor.dtype == np.float32
    assert tensor[0, :, 320, 320].tolist() == [1, 0, 0]
    np.testing.assert_allclose(tensor[0, :, 0, 0], [114 / 255] * 3)
    assert meta == (200, 100, 3.2, 0, 160)


def test_raw_head_scores_are_probabilities_and_boxes_are_unpadded_to_source():
    _, meta = detector_input(np.zeros((100, 200, 3), dtype=np.uint8))
    output = np.array([[[320], [320], [320], [160], [0.8], [0.05], [0.01]]], dtype=np.float32)
    candidates = decode_candidates(output, meta, ["animal", "person", "vehicle"])
    assert len(candidates) == 1 and candidates[0][0] == "animal"
    np.testing.assert_allclose(candidates[0][2], [0.25, 0.25, 0.5, 0.5])
    for bad in [output * np.nan, output.copy()]:
        if np.isfinite(bad).all():
            bad[0, 4, 0] = 575.5
        with pytest.raises(ValueError):
            decode_candidates(bad, meta, ["animal", "person", "vehicle"])


def test_person_probability_is_not_hidden_by_the_same_box_animal_argmax():
    output = np.array([[[320], [320], [320], [160], [0.8], [0.3], [0.01]]], dtype=np.float32)
    _, meta = detector_input(np.zeros((100, 200, 3), dtype=np.uint8))
    assert {c[0] for c in decode_candidates(output, meta, ["animal", "person", "vehicle"])} == {"person", "animal"}


def test_many_high_scoring_animals_cannot_push_person_out_of_result_limit():
    output = np.zeros((1, 7, 102), dtype=np.float32)
    for index in range(101):
        output[0, :5, index] = [(index % 16) * 30 + 10, (index // 16) * 30 + 10, 10, 10, 0.9]
    output[0, :4, 101] = [320, 320, 10, 10]
    output[0, 5, 101] = 0.21
    _, meta = detector_input(np.zeros((640, 640, 3), dtype=np.uint8))
    assert any(c[0] == "person" for c in decode_candidates(output, meta, ["animal", "person", "vehicle"]))


def test_wrong_label_order_or_head_shape_is_rejected_before_admission():
    _, meta = detector_input(np.zeros((100, 200, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        decode_candidates(np.zeros((1, 7, 3)), meta, ["person", "animal", "vehicle"])
    with pytest.raises(ValueError):
        decode_candidates(np.zeros((1, 300, 6)), meta, ["animal", "person", "vehicle"])


@pytest.mark.parametrize("threshold,animal", [(0.5, True), (0.6, False), (0.95, False)])
def test_animal_threshold_changes_do_not_weaken_person_privacy_veto(threshold, animal):
    output = np.array([[[320], [320], [320], [160], [0.55], [0.3], [0.01]]], dtype=np.float32)
    _, meta = detector_input(np.zeros((100, 200, 3), dtype=np.uint8))
    names = {c[0] for c in decode_candidates(output, meta, ["animal", "person", "vehicle"], threshold)}
    assert ("animal" in names) is animal
    assert "person" in names


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), 0.49, 0.96, True])
def test_invalid_animal_threshold_is_rejected(threshold):
    _, meta = detector_input(np.zeros((100, 200, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        decode_candidates(np.zeros((1, 7, 1)), meta, ["animal", "person", "vehicle"], threshold)
