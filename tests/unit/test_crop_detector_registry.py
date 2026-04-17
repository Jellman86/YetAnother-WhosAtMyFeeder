import pytest

from app.services.model_manager import ModelManager


@pytest.mark.asyncio
async def test_available_models_expose_fast_and_accurate_crop_detectors():
    models = await ModelManager().list_available_models()
    by_id = {model.id: model for model in models}

    assert by_id["bird_crop_detector"].artifact_kind == "crop_detector"
    assert by_id["bird_crop_detector"].tier == "fast"
    assert by_id["bird_crop_detector"].input_size == 300
    assert by_id["bird_crop_detector"].preprocessing["resize_mode"] == "direct_resize"
    assert by_id["bird_crop_detector_accurate_yolox_tiny"].artifact_kind == "crop_detector"
    assert by_id["bird_crop_detector_accurate_yolox_tiny"].tier == "accurate"
    assert by_id["bird_crop_detector_accurate_yolox_tiny"].runtime == "onnx"
    assert by_id["bird_crop_detector_accurate_yolox_tiny"].labels_url
    assert by_id["bird_crop_detector_accurate_yolox_tiny"].model_config_url

    internal = ModelManager()._get_registry_model_meta("bird_crop_detector_accurate_yolox_tiny")
    assert internal["sha256"]
    assert internal["labels_sha256"]


def test_crop_detector_specs_include_selected_and_fallback_tiers(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))
    manager = ModelManager()

    fast_dir = tmp_path / "bird_crop_detector"
    fast_dir.mkdir(parents=True, exist_ok=True)
    (fast_dir / "model.onnx").write_bytes(b"fast")
    (fast_dir / "model_config.json").write_text("{}", encoding="utf-8")

    spec = manager.get_crop_detector_spec("accurate")

    assert spec["selected_tier"] == "accurate"
    assert spec["resolved_tier"] == "fast"
    assert spec["model_id"] == "bird_crop_detector"
    assert spec["enabled_for_runtime"] is True
    assert spec["reason"] == "fallback_fast"
