"""Inference does not share a process with the web service by default (#312).

The interface being starved by its own classifier was the root of #300: with
`in_process` inference, a busy feeder takes the web service away from itself,
and the setting that fixes it lives on the Settings page being starved. A
fresh install now runs inference in supervised worker processes, and the
worker count follows the configured concurrency so every admitted job has a
process to run in — a pool smaller than admission burns leases in a queue,
which is the abandonment pathology #314 closed.
"""

import app.config as config_module
from app.config import Settings
from app.services.classifier_service import resolve_image_worker_counts


def test_a_fresh_install_runs_inference_out_of_process(monkeypatch, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.delenv("CLASSIFICATION__IMAGE_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("CLASSIFICATION__LIVE_WORKER_COUNT", raising=False)

    loaded = Settings.load()

    assert loaded.classification.image_execution_mode == "subprocess"
    # None means "derive from the configured concurrency", not "no workers".
    assert loaded.classification.live_worker_count is None


def test_one_worker_of_each_kind_is_the_default():
    """Each worker holds its own copy of the model, so the count is the
    memory price: one live and one background copy by default, on any
    provider, and scaling upward is a deliberate act, never a default."""
    for provider in ("cpu", "auto", "cuda", "intel_gpu", "intel_npu"):
        assert resolve_image_worker_counts(
            configured_live=None,
            configured_background=None,
        ) == (1, 1), provider


def test_an_explicit_worker_count_is_kept():
    assert resolve_image_worker_counts(
        configured_live=3,
        configured_background=2,
    ) == (3, 2)


def test_status_reports_the_resolved_worker_plan(monkeypatch):
    """The worker count is derived now, so the owner must be able to see what
    it resolved to — Settings states the price in workers, not a mechanism."""
    from unittest.mock import patch

    from app.config import settings
    from app.services.classifier_service import ClassifierService

    monkeypatch.setattr(settings.classification, "image_execution_mode", "subprocess")
    monkeypatch.setattr(settings.classification, "live_worker_count", None)
    monkeypatch.setattr(settings.classification, "background_worker_count", None)
    monkeypatch.setattr(settings.classification, "inference_provider", "intel_npu")

    with (
        patch.object(ClassifierService, "_init_bird_model", return_value=None),
        patch(
            "app.services.classifier_service._detect_acceleration_capabilities",
            return_value={},
        ),
    ):
        service = ClassifierService()

    try:
        status = service.get_status()
        assert status["resolved_live_workers"] == 1
        assert status["resolved_background_workers"] == 1
    finally:
        service._image_executor.shutdown(wait=False)
        service._live_image_executor.shutdown(wait=False)
        service._background_image_executor.shutdown(wait=False)
        service._video_executor.shutdown(wait=False)


def test_admission_capacity_matches_the_worker_pool(monkeypatch):
    """Every admitted job has a worker; a pool smaller than admission burns
    leases in a queue the caller cannot see."""
    from unittest.mock import patch

    from app.config import settings
    from app.services.classifier_service import ClassifierService

    monkeypatch.setattr(settings.classification, "image_execution_mode", "subprocess")
    monkeypatch.setattr(settings.classification, "live_worker_count", None)
    monkeypatch.setattr(settings.classification, "background_worker_count", None)
    monkeypatch.setattr(settings.classification, "inference_provider", "cpu")

    with (
        patch.object(ClassifierService, "_init_bird_model", return_value=None),
        patch(
            "app.services.classifier_service._detect_acceleration_capabilities",
            return_value={},
        ),
    ):
        service = ClassifierService()

    try:
        assert service._classification_admission._live_capacity == 1
        assert service._classifier_supervisor is not None
        assert service._classifier_supervisor._worker_counts["live"] == 1
        assert service._classifier_supervisor._worker_counts["background"] == 1
    finally:
        service._image_executor.shutdown(wait=False)
        service._live_image_executor.shutdown(wait=False)
        service._background_image_executor.shutdown(wait=False)
        service._video_executor.shutdown(wait=False)


def test_status_reports_label_count_without_a_resident_model(monkeypatch, tmp_path):
    """The API process holds no model in subprocess mode, but the active
    model's label count is a fact about the install, not about which process
    holds the weights - status must not report a default install as having no
    labels."""
    from unittest.mock import patch

    from app.config import settings
    from app.services.classifier_service import ClassifierService

    labels = tmp_path / "labels.txt"
    labels.write_text("Robin\nDunnock\n\nWren\n", encoding="utf-8")

    monkeypatch.setattr(settings.classification, "image_execution_mode", "subprocess")
    monkeypatch.setattr(settings.classification, "live_worker_count", None)
    monkeypatch.setattr(settings.classification, "background_worker_count", None)

    with (
        patch.object(ClassifierService, "_init_bird_model", return_value=None),
        patch(
            "app.services.classifier_service._detect_acceleration_capabilities",
            return_value={},
        ),
    ):
        service = ClassifierService()

    service._resolve_active_bird_model_spec = lambda: {  # type: ignore[method-assign]
        "model_id": "test-model",
        "labels_path": str(labels),
    }

    try:
        status = service.get_status()
        assert status["labels_count"] == 3
    finally:
        service._image_executor.shutdown(wait=False)
        service._live_image_executor.shutdown(wait=False)
        service._background_image_executor.shutdown(wait=False)
        service._video_executor.shutdown(wait=False)


def test_video_concurrency_follows_background_workers():
    """The models classify one image at a time, so video-job concurrency above
    the background worker count only queues, and below it starves paid-for
    workers. The knob is collapsed: concurrency IS the resolved background
    worker count."""
    from app.services.auto_video_classifier_service import resolve_video_concurrency

    assert resolve_video_concurrency(configured_background=None) == 1
    assert resolve_video_concurrency(configured_background=3) == 3


def test_video_pool_follows_background_workers_not_the_retired_knob():
    """The video worker pool must match the video-job concurrency, which follows
    the background worker count. It was the last consumer of the retired
    video_classification_max_concurrent setting - observed live as a video-0
    worker holding a third model copy that no prediction accounted for."""
    import inspect

    from app.services import classifier_service

    source = inspect.getsource(classifier_service)
    start = source.index("video_workers = max")
    window = source[start - 600 : start + 200]
    assert 'settings.classification, "video_classification_max_concurrent"' not in window
    assert "background_worker_count" in window
