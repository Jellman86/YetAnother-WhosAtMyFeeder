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


def test_frigate_keyframe_preroll_is_skipped_so_samples_stay_inside_the_requested_window(scan, monkeypatch):
    payload, reader, _, _, props = scan
    # 12.3 s returned for a 10 s window: Frigate started 2.3 s early, at the previous keyframe.
    props[worker.cv2.CAP_PROP_FRAME_COUNT] = 123
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))])
    assert worker.scan_clip(payload)["outcome"] == "candidate"
    assert [call.args[1] for call in reader.set.call_args_list] == pytest.approx([3290.0, 7250.0, 11210.0])


def test_six_second_keyframe_preroll_from_a_real_camera_is_scanned_and_timed_from_the_window(scan, monkeypatch):
    payload, reader, _, _, props = scan
    # The owner's greenhouse camera returned 16 s for a 10 s window, which the old 5 s
    # allowance rejected with a non-zero exit that looked like a native crash.
    props[worker.cv2.CAP_PROP_FRAME_COUNT] = 160
    index = temporal_reader(scan, {110})
    monkeypatch.setattr(
        worker, "decode_candidates", lambda *args: [("animal", 0.9, (0.1, 0.1, 0.5, 0.5))] if index() == 110 else []
    )
    result = worker.scan_clip(payload)
    assert result["outcome"] == "candidate"
    assert all(call.args[1] >= 6000 for call in reader.set.call_args_list)
    assert result["frame_index"] == 110 and result["frame_offset"] == pytest.approx(5.0)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({worker.cv2.CAP_PROP_FRAME_COUNT: 201}, "duration_limit"),
        ({worker.cv2.CAP_PROP_FRAME_WIDTH: 5000, worker.cv2.CAP_PROP_FRAME_HEIGHT: 4000}, "pixel_limit"),
        ({worker.cv2.CAP_PROP_FPS: 0}, "invalid_metadata"),
        ({worker.cv2.CAP_PROP_POS_FRAMES: 5000}, "frame_unbounded"),
    ],
)
def test_recordings_that_cannot_be_read_report_a_reason_without_inference(scan, change, reason):
    payload, reader, runtime, photo, props = scan
    props.update(change)
    with pytest.raises(worker.UnusableRecording) as raised:
        worker.scan_clip(payload)
    assert raised.value.reason == reason
    assert not photo.exists()
    reader.release.assert_called_once()


def test_worker_reports_an_unreadable_recording_as_a_result_and_names_any_other_failure(monkeypatch, capsys):
    monkeypatch.setattr(worker.sys, "stdin", Mock(buffer=Mock(readline=lambda limit: b"{}")))
    monkeypatch.setattr(worker, "scan_clip", Mock(side_effect=worker.UnusableRecording("decode_failed")))
    worker.main()
    assert capsys.readouterr().out == 'MOTION_RESULT:{"outcome": "unusable_recording", "reason": "decode_failed"}\n'
    monkeypatch.setattr(worker, "scan_clip", Mock(side_effect=KeyError("model")))
    with pytest.raises(KeyError):
        worker.main()
    assert capsys.readouterr().out == "WORKER_ERROR:KeyError\n"


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
    expected = [(2.3 + 9.9 * i / 10) * 1000 for i in range(1, 10)]
    assert [call.args[1] for call in reader.set.call_args_list] == pytest.approx(expected)
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
    with pytest.raises(worker.UnusableRecording, match="decode_failed"):
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


def _real_clip(path, *, seconds: float, fps: int = 10):
    import cv2

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    assert writer.isOpened()
    for index in range(round(seconds * fps)):
        writer.write(np.full((48, 64, 3), index % 255, dtype=np.uint8))
    writer.release()
    return path


@pytest.mark.parametrize(
    ("seconds", "expected"), [(16, "no_candidate"), (25, "duration_limit"), (None, "invalid_metadata")]
)
def test_real_recordings_are_scanned_with_preroll_or_reported_unreadable(tmp_path, monkeypatch, seconds, expected):
    clip = tmp_path / "clip.mp4"
    if seconds is None:
        clip.write_bytes(b"not a recording")
    else:
        _real_clip(clip, seconds=seconds)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    runtime = Mock(actual=["CPUExecutionProvider"])
    runtime.infer.return_value = np.zeros((1, 7, 1), dtype=np.float32)
    monkeypatch.setattr(worker, "Runtime", lambda *args: runtime)
    monkeypatch.setattr(worker, "decode_candidates", lambda *args: [])
    payload = dict(
        model=str(model),
        clip=str(clip),
        photo=str(tmp_path / "photo.jpg"),
        duration=10,
        clip_sha256=hashlib.sha256(clip.read_bytes()).hexdigest(),
        model_sha256=hashlib.sha256(b"model").hexdigest(),
        names=["animal", "person", "vehicle"],
    )
    if expected == "no_candidate":
        assert worker.scan_clip(payload) == {"outcome": "no_candidate"}
        assert runtime.infer.call_count == 3
    else:
        with pytest.raises(worker.UnusableRecording) as raised:
            worker.scan_clip(payload)
        assert raised.value.reason == expected
        runtime.infer.assert_not_called()
