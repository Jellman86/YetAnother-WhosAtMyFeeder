"""Complete-recording replay must preserve pixels, timing and every tail frame."""

import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import numpy as np
import pytest


path = Path(__file__).parents[1] / "scripts" / "replay_garden_motion.py"
spec = importlib.util.spec_from_file_location("garden_motion_replay", path)
replay = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = replay
spec.loader.exec_module(replay)


@pytest.mark.parametrize("count,fps", [(615, 30), (601, 30), (600, 30), (3, 30), (1001, 29.97)])
def test_windows_cover_every_frame_once_including_a_short_tail(count, fps):
    windows = replay.plan_windows(count, fps)
    assert windows[0].start_frame == 0
    assert sum(window.frames for window in windows) == count
    assert all(0.1 <= window.duration <= 10 for window in windows)
    assert all(a.start_frame + a.frames == b.start_frame for a, b in zip(windows, windows[1:]))


@pytest.mark.parametrize("count,fps", [(1, 30), (0, 30), (10, 0), (10, float("nan")), (10, 121), (18001, 30)])
def test_invalid_or_oversized_recordings_are_refused(count, fps):
    with pytest.raises(ValueError):
        replay.plan_windows(count, fps)


def test_remux_command_copies_video_without_scaling_or_reencoding(tmp_path, monkeypatch):
    run = Mock()
    monkeypatch.setattr(replay.subprocess, "run", run)
    replay.remux(Path("/ffmpeg"), tmp_path / "source.mp4", tmp_path / "window.mp4", replay.Window(300, 300, 30))
    command = run.call_args.args[0]
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-ss") + 1] == "10.0"
    assert command[command.index("-t") + 1] == "10.0"
    assert "-vf" not in command and "-s" not in command
    assert run.call_args.kwargs["timeout"] == 60


def readers(monkeypatch, source_frames, window_frames):
    def reader(frames):
        value = Mock()
        value.read.side_effect = [(True, frame) for frame in frames] + [(False, None)]
        value.get.side_effect = lambda key: {
            replay.cv2.CAP_PROP_FPS: 10,
            replay.cv2.CAP_PROP_POS_MSEC: (value.read.call_count - 1) * 100,
        }[key]
        value.isOpened.return_value = True
        return value

    a, b = reader(source_frames), reader(window_frames)
    monkeypatch.setattr(replay.cv2, "VideoCapture", Mock(side_effect=[a, b]))
    return a, b


def test_lossless_verification_checks_all_frames_and_releases_readers(monkeypatch):
    frames = [np.full((2, 3, 3), i, dtype=np.uint8) for i in range(10)]
    a, b = readers(monkeypatch, frames, frames)
    hashes = replay.verify_window(Path("source"), Path("clip"), replay.Window(0, 10, 10))
    assert len(hashes) == 10 and len(set(hashes)) == 10
    a.release.assert_called_once()
    b.release.assert_called_once()


@pytest.mark.parametrize("bad", ["pixels", "truncated", "timing"])
def test_a_changed_window_is_rejected_before_model_execution(monkeypatch, bad):
    frames = [np.full((2, 3, 3), i, dtype=np.uint8) for i in range(10)]
    other = list(frames)
    if bad == "pixels":
        other[7] = np.zeros((2, 3, 3), dtype=np.uint8)
    if bad == "truncated":
        other = other[:8]
    a, b = readers(monkeypatch, frames, other)
    if bad == "timing":
        b.get.side_effect = lambda key: 10 if key == replay.cv2.CAP_PROP_FPS else 5000
    with pytest.raises(ValueError, match="pixels|decode|timing"):
        replay.verify_window(Path("source"), Path("clip"), replay.Window(0, 10, 10))
    a.release.assert_called_once()
    b.release.assert_called_once()


def test_result_must_bind_exact_original_rgb_frame():
    result = {"outcome": "candidate", "frame_index": 1, "sampled_frame_sha256": "different"}
    with pytest.raises(ValueError, match="original"):
        replay.verify_result(result, ["first", "second"])
    result["sampled_frame_sha256"] = "second"
    replay.verify_result(result, ["first", "second"])
    replay.verify_result({"outcome": "person_rejected"}, [])


def test_private_output_refuses_reuse_and_is_owner_only(tmp_path):
    root = tmp_path / "report"
    replay.new_output(root)
    assert root.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        replay.new_output(root)


@pytest.mark.parametrize("sampling", [None, [3, 9]])
def test_replay_uses_current_worker_for_every_window_and_threshold_without_retaining_photos(
    tmp_path, monkeypatch, sampling
):
    source, model = tmp_path / "source.mp4", tmp_path / "model.onnx"
    source.write_bytes(b"recording")
    model.write_bytes(b"model")
    root = tmp_path / "output"
    replay.new_output(root)
    reader = Mock()
    reader.get.side_effect = lambda key: {
        replay.cv2.CAP_PROP_FPS: 30,
        replay.cv2.CAP_PROP_FRAME_COUNT: 615,
        replay.cv2.CAP_PROP_FRAME_WIDTH: 1920,
        replay.cv2.CAP_PROP_FRAME_HEIGHT: 1080,
    }[key]
    monkeypatch.setattr(replay.cv2, "VideoCapture", lambda *args: reader)
    monkeypatch.setattr(replay, "remux", lambda ffmpeg, source, clip, window: clip.write_bytes(b"clip"))
    verified = Mock(side_effect=lambda source, clip, window: ["rgb"] * window.frames)
    monkeypatch.setattr(replay, "verify_window", verified)

    def scan(payload, *, samples_per_window=3):
        Path(payload["photo"]).write_bytes(b"private photo")
        return {"outcome": "candidate", "frame_index": 1, "sampled_frame_sha256": "rgb"}

    worker = Mock(side_effect=scan)
    monkeypatch.setattr(replay, "scan_clip", worker)
    report = replay.replay_recording(
        source,
        model,
        {"model_sha256": "model", "names": []},
        Path("ffmpeg"),
        [0.5, 0.6],
        root,
        samples_per_window=sampling,
    )
    assert [row["frames"] for row in report["windows"]] == [300, 300, 15]
    policies = sampling or [3]
    assert [call.args[0]["duration"] for call in worker.call_args_list] == [
        duration for duration in [10, 10, 0.5] for _ in range(2 * len(policies))
    ]
    assert [call.args[0]["animal_confidence"] for call in worker.call_args_list] == [
        threshold for _ in range(3) for threshold in (0.5, 0.6) for _ in policies
    ]
    assert [call.kwargs["samples_per_window"] for call in worker.call_args_list] == policies * 6
    assert report["samples_per_window"] == policies
    assert [r["samples_per_window"] for r in report["windows"][0]["results"]] == policies * 2
    assert all(r["elapsed_seconds"] >= 0 for window in report["windows"] for r in window["results"])
    assert [row["results"][0]["source_frame_index"] for row in report["windows"]] == [1, 301, 601]
    assert verified.call_count == 3
    assert not list(root.rglob("*.jpg")) and not list(root.rglob("*.mp4"))
    assert len(list(root.glob("*-result.json"))) == 3
    assert not (root / "complete.json").exists()


@pytest.mark.parametrize("sampling", [[3, 3], [3, 9, 9], [], [True], [4], [9.0]])
def test_replay_rejects_unbounded_or_duplicate_policies_before_reading_any_recording(tmp_path, sampling):
    with pytest.raises(ValueError, match="sampling"):
        replay.replay_recording(
            tmp_path / "absent.mp4",
            tmp_path / "absent.onnx",
            {},
            Path("ffmpeg"),
            [0.5],
            tmp_path,
            samples_per_window=sampling,
        )


@pytest.mark.parametrize("failure", ["source checksum", "model checksum", "threshold nan", "threshold outside range"])
def test_cli_rejects_invalid_provenance_and_threshold_before_creating_output(tmp_path, monkeypatch, failure):
    source, model, bundle = [tmp_path / name for name in ("clip.mp4", "model.onnx", "bundle.json")]
    source.write_bytes(b"source")
    model.write_bytes(b"model")
    model_hash = replay.digest(model) if failure != "model checksum" else "0" * 64
    bundle.write_text(json.dumps({"model_sha256": model_hash, "names": ["animal", "person", "vehicle"]}))
    root = tmp_path / "report"
    checksum = replay.digest(source) if failure != "source checksum" else "0" * 64
    threshold = {"threshold nan": "nan", "threshold outside range": "0.4"}.get(failure, "0.6")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--source",
            str(source),
            "--model",
            str(model),
            "--source-sha256",
            checksum,
            "--bundle",
            str(bundle),
            "--ffmpeg",
            "unused",
            "--thresholds",
            threshold,
            "--root",
            str(root),
        ],
    )
    run = Mock()
    monkeypatch.setattr(replay, "replay_recording", run)
    with pytest.raises(SystemExit) as error:
        replay.main()
    assert error.value.code == 2
    run.assert_not_called()
    assert not root.exists()
