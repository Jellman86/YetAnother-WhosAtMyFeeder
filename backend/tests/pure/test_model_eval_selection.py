from types import SimpleNamespace

import pytest

from app.services.model_eval_service import select_evaluation_models


def installed(model_id, kind="classifier", ready=True):
    return SimpleNamespace(id=model_id, ready=ready, metadata=SimpleNamespace(artifact_kind=kind))


def test_crop_only_compatibility_does_not_select_or_require_a_classifier():
    classifier = installed("bird_classifier")
    crop = installed("bird_crop_detector_accurate_rfdetr_nano", "crop_detector")
    unrelated = installed("bird_crop_detector", "crop_detector")
    assert select_evaluation_models(
        [classifier, crop, unrelated], model_ids=[crop.id], compat_only=True, sweep_devices=True
    ) == ([], [crop])


def test_targeting_a_classifier_does_not_silently_sweep_unrelated_crop_models():
    classifier = installed("bird_classifier")
    crop = installed("bird_crop_detector", "crop_detector")
    assert select_evaluation_models(
        [classifier, crop], model_ids=[classifier.id], compat_only=True, sweep_devices=True
    ) == ([classifier], [])


@pytest.mark.parametrize("compat_only,sweep_devices", [(False, True), (True, False), (False, False)])
def test_crop_only_requires_a_device_compatibility_run(compat_only, sweep_devices):
    crop = installed("bird_crop_detector", "crop_detector")
    with pytest.raises(RuntimeError, match="crop detectors require"):
        select_evaluation_models([crop], model_ids=[crop.id], compat_only=compat_only, sweep_devices=sweep_devices)


def test_missing_or_incomplete_requested_models_fail_instead_of_testing_something_else():
    with pytest.raises(RuntimeError, match="not installed and ready"):
        select_evaluation_models(
            [installed("requested", "crop_detector", ready=False), installed("other")],
            model_ids=["requested"],
            compat_only=True,
            sweep_devices=True,
        )


def test_untargeted_compatibility_still_selects_all_ready_models():
    classifier = installed("bird_classifier")
    crop = installed("bird_crop_detector", "crop_detector")
    assert select_evaluation_models(
        [classifier, crop, installed("incomplete", ready=False)], model_ids=[], compat_only=True, sweep_devices=True
    ) == ([classifier], [crop])


def test_crop_only_compatibility_results_are_in_the_summary_instead_of_an_empty_run():
    from app.services.model_eval_service import _compatibility_model_summaries

    rows = _compatibility_model_summaries(
        {
            "models": {},
            "crop_detectors": {
                "rfdetr": {
                    "best_provider": "intel_gpu",
                    "providers": {"intel_gpu": {"ok": True, "latency_ms": 70.0, "images_evaluated": 11}},
                }
            },
        }
    )
    assert len(rows) == 1
    assert rows[0]["model_id"] == "rfdetr"
    assert rows[0]["ready"] is True
    assert rows[0]["validated_providers"] == ["intel_gpu"]


@pytest.mark.asyncio
async def test_crop_only_run_reaches_the_device_sweep_without_activating_a_classifier(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from app.services import classifier_service, model_eval_service
    from app.services.model_manager import model_manager

    crop = installed("bird_crop_detector_accurate_rfdetr_nano", "crop_detector")
    runner = model_eval_service.ModelEvalRunner()
    panel = [model_eval_service.SpeciesEntry(1, "Test bird", "Test bird", "shared_core")]
    monkeypatch.setattr(model_eval_service, "build_panel", AsyncMock(return_value=panel))
    monkeypatch.setattr(
        model_eval_service, "fetch_panel_images", AsyncMock(return_value={1: [SimpleNamespace(source="inat")]})
    )
    monkeypatch.setattr(model_eval_service, "cleanup_image_dir", Mock())
    monkeypatch.setattr(model_manager, "list_installed_models", AsyncMock(return_value=[crop]))
    activate = AsyncMock()
    monkeypatch.setattr(model_manager, "activate_model", activate)
    primary = SimpleNamespace(reload_bird_model=AsyncMock())
    monkeypatch.setattr(classifier_service, "get_classifier", lambda: primary)
    sweep = AsyncMock(return_value={"models": {}, "crop_detectors": {}})
    monkeypatch.setattr(runner, "_device_sweep", sweep)
    monkeypatch.setattr(runner, "_emit", AsyncMock())

    await runner._do_run(
        run_id="crop-only",
        run_dir=tmp_path,
        include_per_image=False,
        region_override=None,
        sweep_devices=True,
        compat_only=True,
        model_ids=[crop.id],
    )

    sweep.assert_awaited_once_with("crop-only", tmp_path, [], [crop], discover_providers=False)
    activate.assert_not_awaited()
    primary.reload_bird_model.assert_not_awaited()
    assert (tmp_path / "summary.json").is_file()
