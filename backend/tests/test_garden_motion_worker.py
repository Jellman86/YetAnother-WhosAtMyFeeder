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
    still = np.full((100, 100, 3), [10, 20, 30], dtype=np.uint8)
    reader.frames = [still]
    for shade in (120, 230):
        moved = still.copy()
        moved[10:60, 10:60] = shade
        reader.frames.append(moved)
    reader.read.side_effect = lambda: (True, reader.frames[(reader.read.call_count - 1) % len(reader.frames)])
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


def test_a_proposal_that_never_moves_is_rejected_without_a_photo(scan, monkeypatch):
    payload, reader, _, photo, _ = scan
    reader.frames = [np.full((100, 100, 3), [10, 20, 30], dtype=np.uint8)]
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    result = worker.scan_clip(payload)
    assert result == {"outcome": "still_rejected", "detector_score": 0.9, "motion_ratio": 0.0}
    assert not photo.exists()
    reader.release.assert_called_once()


def test_a_moving_proposal_reports_its_motion_ratio(scan, monkeypatch):
    payload, *_ = scan
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    result = worker.scan_clip(payload)
    assert result["outcome"] == "candidate"
    assert result["motion_ratio"] >= worker.STILL_PROPOSAL_MOTION_RATIO


def temporal_reader(scan, animal_frames):
    """One marked animal interval in a real frame-indexed recording layout."""
    _, reader, _, _, props = scan
    index = 0

    def seek(key, value):
        nonlocal index
        assert key == worker.cv2.CAP_PROP_POS_MSEC
        index = round(value / 1000 * props[worker.cv2.CAP_PROP_FPS])
        return True

    def read():
        props[worker.cv2.CAP_PROP_POS_FRAMES] = index + 1
        frame = np.full((100, 100, 3), 20, dtype=np.uint8)
        if index in animal_frames:
            frame[10:60, 10:60] = 220
        return True, frame

    reader.set.side_effect = seek
    reader.read.side_effect = read
    return lambda: index


def test_offline_nine_sample_comparison_recovers_a_brief_candidate_between_live_samples(scan, monkeypatch):
    payload, reader, runtime, photo, _ = scan
    index = temporal_reader(scan, {20})
    monkeypatch.setattr(
        worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))] if index() == 20 else []
    )
    assert worker.scan_clip(payload)["outcome"] == "no_candidate"
    assert not photo.exists()
    runtime.infer.reset_mock()
    result = worker.scan_clip(payload, samples_per_window=9)
    assert result["outcome"] == "candidate"
    assert result["frame_index"] == 20 and result["frame_offset"] == 2
    assert result["sampling"] == {"requested": 9, "decoded": 9, "inferred": 9}
    assert runtime.infer.call_count == 9
    reader.release.assert_called()


def test_person_only_in_an_added_sample_vetoes_the_complete_offline_window(scan, monkeypatch):
    payload, _, _, photo, _ = scan
    index = temporal_reader(scan, {10})

    def candidates(*args):
        if index() == 10:
            return [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))]
        return [("person", 0.3, (0.1, 0.1, 0.5, 0.5))] if index() == 79 else []

    monkeypatch.setattr(worker, "decode_candidates", candidates)
    assert worker.scan_clip(payload)["outcome"] == "candidate"
    photo.unlink()
    result = worker.scan_clip(payload, samples_per_window=9)
    assert result["outcome"] == "person_rejected"
    assert not photo.exists()
    assert set(result) == {"outcome", "sampling"}


def test_offline_sampling_deduplicates_inference_without_turning_one_still_frame_into_a_visitor(scan, monkeypatch):
    payload, _, runtime, photo, props = scan
    props[worker.cv2.CAP_PROP_FRAME_COUNT] = 1
    temporal_reader(scan, set())
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    result = worker.scan_clip(payload, samples_per_window=9)
    assert result["outcome"] == "still_rejected"
    assert result["sampling"] == {"requested": 9, "decoded": 9, "inferred": 1}
    runtime.infer.assert_called_once()
    assert not photo.exists()


def test_live_payload_cannot_enable_the_offline_sampling_policy(scan, monkeypatch):
    payload, _, runtime, _, _ = scan
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [])
    result = worker.scan_clip(payload | {"samples_per_window": 9})
    assert result == {"outcome": "no_candidate"}
    assert runtime.infer.call_count == 3


def test_offline_samples_remain_inside_the_requested_window_despite_keyframe_padding(scan, monkeypatch):
    payload, reader, runtime, _, props = scan
    props[worker.cv2.CAP_PROP_FRAME_COUNT] = 123
    temporal_reader(scan, set())
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [])
    result = worker.scan_clip(payload, samples_per_window=9)
    assert result["outcome"] == "no_candidate"
    assert [call.args[1] for call in reader.set.call_args_list] == [i * 1000 for i in range(1, 10)]
    assert runtime.infer.call_count == 9
    reader.release.assert_called_once()


def test_failed_added_sample_discards_an_earlier_candidate_and_releases_the_reader(scan, monkeypatch):
    payload, reader, _, photo, _ = scan
    temporal_reader(scan, {10})
    read = reader.read.side_effect

    def fail_late():
        return (False, None) if reader.read.call_count == 4 else read()

    reader.read.side_effect = fail_late
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    with pytest.raises(ValueError, match="could not decode"):
        worker.scan_clip(payload, samples_per_window=9)
    assert not photo.exists()
    reader.release.assert_called_once()


@pytest.mark.parametrize("count", [True, 0, 4, 10, 9.0, "9"])
def test_only_bounded_offline_sampling_policies_are_accepted_before_native_loading(scan, count):
    payload, reader, runtime, _, _ = scan
    with pytest.raises(ValueError, match="sampling"):
        worker.scan_clip(payload, samples_per_window=count)
    runtime.infer.assert_not_called()
    reader.read.assert_not_called()
