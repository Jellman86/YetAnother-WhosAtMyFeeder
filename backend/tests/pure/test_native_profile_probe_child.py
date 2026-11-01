import numpy as np
import pytest

from scripts.probe_native_profile import validate_vectors, validate_predictions, ExactProfileProbePolicy
from app.services.native_crash_quarantine import NativeCrashQuarantinedError


@pytest.mark.parametrize(
    "vectors",
    [
        [np.array([np.nan, 0.2])] * 3,
        [np.array([np.inf, 0.2])] * 3,
        [np.array([0.0, 0.0])] * 3,
        [np.array([0.5, 0.5])] * 3,
        [np.array([0.1, 0.9])] * 3,
        [np.array([0.1, 0.9])],
    ],
)
def test_degenerate_or_nonfinite_representative_inference_fails(vectors):
    with pytest.raises(ValueError):
        validate_vectors(vectors)


def test_different_finite_predictions_do_not_require_different_top_species():
    validate_vectors([np.array([0.1, 0.9]), np.array([0.2, 0.8]), np.array([0.3, 0.7])])


@pytest.mark.parametrize("predictions", [[], [{"score": float("nan")}], [{"score": float("inf")}], [{"score": 0}]])
def test_missing_or_invalid_pipeline_predictions_fail(predictions):
    with pytest.raises(ValueError):
        validate_predictions(predictions)


def test_probe_policy_allows_only_exact_captured_profile_and_preserves_evidence(tmp_path):
    profile = {"model_id": "bird", "provider": "intel_gpu"}
    policy = ExactProfileProbePolicy(lambda: profile, profile, root=tmp_path)
    assert policy.guard() == profile
    with pytest.raises(NativeCrashQuarantinedError):
        policy.guard(profile | {"provider": "cpu"})
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure", [None, "provider", "video"])
def test_normal_image_and_video_pipeline_must_keep_exact_provider(monkeypatch, failure):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services import classifier_service
    from app.utils import image_io
    from scripts import probe_native_profile as child

    profile = {"model_id": "bird", "provider": "intel_gpu", "model_sha256": "weights", "video_frames": 3}
    outputs = iter([np.array([0.1, 0.9]), np.array([0.2, 0.8]), np.array([0.3, 0.7])] * 2)
    close = Mock()
    service = SimpleNamespace(
        classify=Mock(return_value=[{"score": 0.9}]),
        _classify_raw_with_runtime_recovery=lambda _image: (next(outputs), {}),
        runtime_identity=lambda: {
            "active_provider": "cpu" if failure == "provider" else "intel_gpu",
            "model_sha256": "weights",
        },
        latest_runtime_recovery=lambda: None,
        _native_launch_profile=lambda: dict(profile),
        classify_video=Mock(return_value=[] if failure == "video" else [{"score": 0.9}]),
    )
    monkeypatch.setattr(classifier_service, "ClassifierService", lambda **_kwargs: service)
    monkeypatch.setattr(image_io, "load_rgb_image", lambda _path: SimpleNamespace(close=close))
    monkeypatch.setattr(child, "_video_frames", lambda _path: [SimpleNamespace(close=close) for _ in range(3)])
    payload = {"profile": profile, "images": ["one", "two", "three"], "video": "clip"}
    if failure:
        with pytest.raises(ValueError):
            child.run(payload)
    else:
        report = child.run(payload)
        assert report["images_checked"] == report["video_frames_checked"] == 3
        assert report["pipeline_checked"] is True
        assert service.classify.call_count == 3
        service.classify_video.assert_called_once_with("clip", max_frames=3)
        assert close.call_count == 6


@pytest.mark.parametrize(
    "available,result",
    [
        (False, {"reason": "load_failed"}),
        (True, {"reason": "inference_failed"}),
    ],
)
def test_failed_crop_tier_cannot_be_approved_by_its_normal_fast_fallback(available, result):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from scripts.probe_native_profile import check_crop_tier

    crop = SimpleNamespace(
        _generate_crop_for_tier=Mock(return_value=(result, available)),
        generate_crop=Mock(return_value={"reason": "selected", "detector_tier": "fast"}),
    )
    with pytest.raises(ValueError, match="crop detector"):
        check_crop_tier(crop, object(), "accurate")
    crop.generate_crop.assert_not_called()


def test_successful_crop_check_releases_its_temporary_crop():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from scripts.probe_native_profile import check_crop_tier

    selected = SimpleNamespace(close=Mock())
    crop = SimpleNamespace(
        _generate_crop_for_tier=Mock(return_value=({"reason": "selected", "crop_image": selected}, True))
    )
    check_crop_tier(crop, object(), "accurate")
    selected.close.assert_called_once()


@pytest.mark.parametrize("failure", ["indistinguishable", "unexpected", "device"])
def test_child_persists_a_safe_failure_report_and_exits_unsuccessfully(monkeypatch, tmp_path, failure):
    import ctypes
    import io
    import json
    import resource
    from types import SimpleNamespace
    from unittest.mock import Mock
    from scripts import probe_native_profile as child
    from app.services.classifier_worker_protocol import ClassifierWorkerRetirementError

    result = tmp_path / "result.json"
    payload = {"result": str(result)}
    monkeypatch.setattr(child.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode())))
    monkeypatch.setattr(resource, "setrlimit", Mock())
    monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace(prctl=lambda *_args: 0))

    def fail(_payload):
        if failure == "indistinguishable":
            child.validate_vectors([np.array([0.1, 0.9])] * 3)
        if failure == "device":
            raise ClassifierWorkerRetirementError(error_code="CL_OUT_OF_RESOURCES", detail="DUMMY-private-token/path")
        raise RuntimeError("DUMMY-private-token/path")

    monkeypatch.setattr(child, "run", fail)
    assert child.main() == 1
    report = json.loads(result.read_text())
    assert "DUMMY" not in result.read_text()
    assert (
        report["failure"]["reason"]
        == {
            "indistinguishable": "indistinguishable_photos",
            "unexpected": "unexpected_failure",
            "device": "device_failure",
        }[failure]
    )
    if failure == "device":
        assert report["failure"]["device_code"] == "CL_OUT_OF_RESOURCES"
