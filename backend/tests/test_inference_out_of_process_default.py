"""Inference does not share a process with the web service by default (#312).

The interface being starved by its own classifier was the root of #300: with
`in_process` inference, a busy feeder takes the web service away from itself,
and the setting that fixes it lives on the Settings page being starved. A
fresh install now runs inference in supervised worker processes, and the
worker count follows the configured concurrency so every admitted job has a
process to run in — a pool smaller than admission burns leases in a queue,
which is the abandonment pathology #314 closed.
"""

import pytest

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


def test_worker_counts_follow_configured_concurrency():
    assert resolve_image_worker_counts(
        configured_live=None,
        configured_background=None,
        image_max_concurrent=2,
        inference_provider="cpu",
    ) == (2, 1)
    assert resolve_image_worker_counts(
        configured_live=None,
        configured_background=None,
        image_max_concurrent=4,
        inference_provider="auto",
    ) == (4, 1)


@pytest.mark.parametrize("provider", ["cuda", "intel_gpu", "intel_npu"])
def test_a_single_accelerator_gets_one_derived_worker(provider):
    """One accelerator serialises the work; extra workers add a model copy
    apiece and no parallelism, so they are memory spent on nothing."""
    assert resolve_image_worker_counts(
        configured_live=None,
        configured_background=None,
        image_max_concurrent=4,
        inference_provider=provider,
    ) == (1, 1)


def test_an_explicit_worker_count_is_kept():
    assert resolve_image_worker_counts(
        configured_live=3,
        configured_background=2,
        image_max_concurrent=2,
        inference_provider="intel_npu",
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
        assert service._classification_admission._live_capacity == 1
        assert service._classifier_supervisor is not None
        assert service._classifier_supervisor._worker_counts["live"] == 1
        assert service._classifier_supervisor._worker_counts["background"] == 1
    finally:
        service._image_executor.shutdown(wait=False)
        service._live_image_executor.shutdown(wait=False)
        service._background_image_executor.shutdown(wait=False)
        service._video_executor.shutdown(wait=False)
