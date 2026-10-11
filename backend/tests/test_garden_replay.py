import importlib.util
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

from app.services.garden_visitors import GardenPolicy


path = Path(__file__).parents[1] / "scripts" / "replay_garden_visitors.py"
spec = importlib.util.spec_from_file_location("garden_replay", path)
replay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = replay
spec.loader.exec_module(replay)


def test_speciesnet_input_is_rgb_nhwc_float_after_uint8_roundtrip():
    image = Image.new("RGB", (8, 8), (255, 0, 128))
    value = replay.preprocess(image, "4.0.3a", (0, 0, 1, 1))
    assert value.shape == (1, 480, 480, 3)
    assert value.dtype == np.float32
    np.testing.assert_allclose(value[0, 0, 0], [1, 0, 128 / 255])


def test_crop_uses_normalized_xywh_and_rejects_invalid_geometry():
    pixels = np.zeros((20, 20, 3), dtype=np.uint8)
    pixels[10:, :10, 1] = 255
    value = replay.preprocess(Image.fromarray(pixels), "4.0.3a", (0, 0.5, 0.5, 0.5))
    np.testing.assert_allclose(value[0, 200, 200], [0, 1, 0])
    for box in ((0, 0, 0, 1), (-0.1, 0, 1, 1), (0, 0, 2, 1), (0, 0, float("nan"), 1)):
        with pytest.raises(ValueError):
            replay.preprocess(Image.fromarray(pixels), "4.0.3a", box)


def test_whole_image_variant_removes_upstream_thirty_percent_up_to_four_hundred_pixels():
    pixels = np.zeros((1000, 10, 3), dtype=np.uint8)
    pixels[:150, :, 0] = 255
    pixels[850:, :, 0] = 255
    value = replay.preprocess(Image.fromarray(pixels), "4.0.3b", None)
    assert value.max() == 0


def test_media_paths_cannot_escape_input_folder(tmp_path):
    with pytest.raises(ValueError, match="input folder"):
        replay.media_path(tmp_path, "../secret.jpg")
    outside = tmp_path.parent / "outside.jpg"
    outside.touch()
    (tmp_path / "link.jpg").symlink_to(outside)
    with pytest.raises(ValueError, match="input folder"):
        replay.media_path(tmp_path, "link.jpg")


def test_manifest_replay_is_idempotent_and_conflicting_identity_fails_closed():
    event = {"id": "event-1", "camera": "patio", "label": "cat", "path": "cat.jpg"}
    assert replay.unique_inputs([event, event]) == [event]
    with pytest.raises(ValueError, match="Conflicting"):
        replay.unique_inputs([event, event | {"camera": "other"}])


def test_report_file_is_private_and_cannot_overwrite_existing_file(tmp_path):
    destination = tmp_path / "report.json"
    replay.write_report(destination, {"garden_visits": []})
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        replay.write_report(destination, {})


def test_decoder_uses_raw_three_class_head_and_class_aware_suppression():
    output = np.zeros((1, 7, 3), dtype=np.float32)
    output[0, :4, :] = np.array([[320, 320, 320], [320, 320, 320], [100, 100, 100], [100, 100, 100]])
    output[0, 4, :2] = [0.9, 0.8]
    output[0, 5, 2] = 0.95
    found = replay.decode_detector(output, 640)
    assert [item[0] for item in found] == ["person", "animal"]
    assert found[1][2] == pytest.approx((270 / 640, 270 / 640, 100 / 640, 100 / 640))


def test_video_samples_are_bounded_and_spread_over_recording():
    assert replay.sample_positions(10, 3) == [0, 4.95, 9.9]
    with pytest.raises(ValueError):
        replay.sample_positions(float("nan"), 3)
    with pytest.raises(ValueError):
        replay.sample_positions(10, 1000)


def test_openvino_device_property_accepts_single_npu_string_without_splitting_letters():
    assert replay.execution_devices("NPU") == ["NPU"]
    assert replay.execution_devices(["GPU.0"]) == ["GPU.0"]


class FakeClassifier:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def infer(self, value):
        self.calls += 1
        return np.array([next(self.values)], dtype=np.float32)


def bundle():
    fox = {"id": "fox", "name": "red fox", "ranks": ["mammalia", "carnivora", "canidae", "vulpes", "vulpes"]}
    human = {"id": "human", "name": "human", "ranks": ["mammalia", "primates", "hominidae", "homo", "sapiens"]}
    return {"outputs": [fox, human], "taxonomy": [fox, human], "geofence": {}}


def run(records, tmp_path, classifier):
    policy = GardenPolicy(enabled=True, cameras=frozenset({"patio"}), labels=frozenset({"animal"}))
    return replay.replay(
        records,
        tmp_path,
        policy,
        "GBR",
        bundle(),
        classifier,
        None,
        variant="4.0.3a",
        detector_size=640,
        video_frames=3,
    )


def test_bird_person_and_other_camera_do_not_read_media_or_call_classifier(tmp_path):
    classifier = FakeClassifier([])
    records = [
        {"id": "bird", "camera": "patio", "label": "bird", "path": "missing.jpg"},
        {"id": "person", "camera": "patio", "label": "person", "path": "missing.jpg"},
        {"id": "other", "camera": "feeder", "label": "animal", "path": "missing.jpg"},
    ]
    report = run(records, tmp_path, classifier)
    assert classifier.calls == 0
    assert report["observations"] == []
    assert report["production_writes"] == 0


def test_later_human_frame_revokes_earlier_animal_and_redacts_source_identity(tmp_path, monkeypatch):
    (tmp_path / "clip.mp4").touch()
    monkeypatch.setattr(
        replay, "frames", lambda *_: iter([(0, Image.new("RGB", (10, 10))), (1, Image.new("RGB", (10, 10)))])
    )
    classifier = FakeClassifier([[10, -10], [-10, 10]])
    records = [{"id": "private-human-event", "camera": "patio", "label": "animal", "path": "clip.mp4"}]
    report = run(records, tmp_path, classifier)
    assert classifier.calls == 2
    assert report["observations"] == []
    assert report["outcomes"]["human_rejected"] == 1
    assert report["outcomes"]["garden"] == 0
    assert "private-human-event" not in str(report)


def test_duplicate_event_is_classified_once_and_saved_only_to_prototype_report(tmp_path):
    Image.new("RGB", (10, 10)).save(tmp_path / "fox.png")
    event = {"id": "fox", "camera": "patio", "label": "animal", "path": "fox.png"}
    classifier = FakeClassifier([[10, -10]])
    report = run([event, event], tmp_path, classifier)
    assert classifier.calls == 1
    assert len(report["observations"]) == 1
    assert report["observations"][0]["taxon"]["id"] == "fox"
    assert report["observations"][0]["needs_review"]
    assert report["observations"][0]["supporting_frames"] == 1
    assert "single_frame_only" in report["observations"][0]["review_reasons"]
    assert report["production_writes"] == 0
