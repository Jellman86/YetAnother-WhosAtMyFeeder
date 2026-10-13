"""Recording scans discard all proposals on a later person sample."""

import hashlib
from unittest.mock import Mock

import numpy as np
import pytest

from app.services import garden_motion_worker as worker


@pytest.fixture
def scan(monkeypatch, tmp_path):
    clip, model, photo = [tmp_path / name for name in ("clip.mp4", "model.onnx", "photo.jpg")]
    clip.write_bytes(b"clip")
    model.write_bytes(b"model")
    reader = Mock()
    props = {
        worker.cv2.CAP_PROP_FRAME_WIDTH: 100,
        worker.cv2.CAP_PROP_FRAME_HEIGHT: 100,
        worker.cv2.CAP_PROP_FPS: 10,
        worker.cv2.CAP_PROP_FRAME_COUNT: 100,
        worker.cv2.CAP_PROP_POS_FRAMES: 11,
    }
    reader.get.side_effect = lambda key: props[key]
    reader.read.return_value = (True, np.full((100, 100, 3), [10, 20, 30], dtype=np.uint8))
    monkeypatch.setattr(worker.cv2, "VideoCapture", lambda *args: reader)
    runtime = Mock(actual=["CPUExecutionProvider"])
    runtime.infer.return_value = np.zeros((1, 7, 1), dtype=np.float32)
    monkeypatch.setattr(worker, "Runtime", lambda *args: runtime)
    payload = dict(
        model=str(model),
        clip=str(clip),
        photo=str(photo),
        duration=10,
        clip_sha256=hashlib.sha256(b"clip").hexdigest(),
        model_sha256=hashlib.sha256(b"model").hexdigest(),
        names=["animal", "person", "vehicle"],
    )
    return payload, reader, runtime, photo, props


def test_person_in_last_sample_discards_earlier_animal_without_writing_photo(scan, monkeypatch):
    payload, reader, runtime, photo, _ = scan
    decode = Mock(side_effect=[[("animal", 0.9, (0.1, 0.1, 0.5, 0.5))], [], [("person", 0.3, (0.1, 0.1, 0.5, 0.5))]])
    monkeypatch.setattr(worker, "decode_candidates", decode)
    assert worker.scan_clip(payload) == {"outcome": "person_rejected"}
    assert runtime.infer.call_count == 3
    assert not photo.exists()
    reader.release.assert_called_once()


def test_candidate_binds_sample_rgb_tensor_and_stored_jpeg(scan, monkeypatch):
    payload, reader, runtime, photo, _ = scan
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    result = worker.scan_clip(payload)
    assert result["outcome"] == "candidate"
    assert result["devices"] == ["CPUExecutionProvider"]
    assert result["frame_index"] == 10 and result["frame_offset"] == 1
    assert result["image_sha256"] == hashlib.sha256(photo.read_bytes()).hexdigest()
    rgb = np.full((100, 100, 3), [30, 20, 10], dtype=np.uint8)
    tensor, _ = worker.detector_input(rgb)
    assert result["sampled_frame_sha256"] == hashlib.sha256(rgb.tobytes()).hexdigest()
    assert result["detector_input_sha256"] == hashlib.sha256(tensor.tobytes()).hexdigest()
    reader.release.assert_called_once()


def test_frigate_keyframe_padding_is_allowed_without_sampling_past_requested_window(scan, monkeypatch):
    payload, reader, _, _, props = scan
    props[worker.cv2.CAP_PROP_FRAME_COUNT] = 123
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    assert worker.scan_clip(payload)["outcome"] == "candidate"
    assert [call.args[1] for call in reader.set.call_args_list] == [1000.0, 5000.0, 9000.0]


@pytest.mark.parametrize("count", [0, 0.5, float("nan"), 10000])
def test_invalid_or_too_short_recording_fails_before_inference(scan, count):
    payload, reader, runtime, photo, props = scan
    props[worker.cv2.CAP_PROP_FRAME_COUNT] = count
    with pytest.raises(ValueError):
        worker.scan_clip(payload)
    runtime.infer.assert_not_called()
    reader.release.assert_called_once()
    assert not photo.exists()
