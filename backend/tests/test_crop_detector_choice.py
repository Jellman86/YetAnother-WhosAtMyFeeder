import pytest
from pydantic import ValidationError

from app.config import settings
from app.services.model_manager import ModelManager

RFDETR_ID = "bird_crop_detector_accurate_rfdetr_nano"
YOLOX_ID = "bird_crop_detector_accurate_yolox_tiny"


def _install(tmp_path, model_id: str) -> None:
    model_dir = tmp_path / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.onnx").write_bytes(b"model")
    (model_dir / "model_config.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def chosen_detector():
    original = settings.classification.bird_crop_accurate_detector

    def _choose(value: str) -> None:
        settings.classification.bird_crop_accurate_detector = value

    yield _choose
    settings.classification.bird_crop_accurate_detector = original


def test_accurate_detector_defaults_to_yolox_and_rejects_unknown_choices():
    from app.config_models import ClassificationSettings

    assert ClassificationSettings().bird_crop_accurate_detector == "yolox_tiny"
    assert (
        ClassificationSettings(bird_crop_accurate_detector="rfdetr_nano").bird_crop_accurate_detector == "rfdetr_nano"
    )
    with pytest.raises(ValidationError):
        ClassificationSettings(bird_crop_accurate_detector="yolo_world")


def test_rfdetr_registry_entry_declares_its_runtime_contract():
    meta = ModelManager()._get_registry_model_meta(RFDETR_ID)

    assert meta["artifact_kind"] == "crop_detector"
    assert meta["tier"] == "accurate"
    assert meta["input_size"] == 384
    assert meta["preprocessing"]["resize_mode"] == "stretch"
    assert meta["preprocessing"]["normalization"] == "imagenet"
    assert meta["detector"]["parser"] == "detr"
    assert meta["detector"]["target_class_id"] == 16
    assert meta["detector"]["min_confidence"] == 0.3
    assert meta["detector"]["frame_scan"] == {"tile_grid": 2, "tile_overlap": 0.2}
    assert meta["sha256"] and meta["labels_sha256"]
    assert "cuda" not in meta["supported_inference_providers"]


def test_accurate_spec_uses_the_chosen_detector_when_installed(tmp_path, monkeypatch, chosen_detector):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))
    _install(tmp_path, YOLOX_ID)
    _install(tmp_path, RFDETR_ID)
    chosen_detector("rfdetr_nano")

    spec = ModelManager().get_crop_detector_spec("accurate")

    assert spec["model_id"] == RFDETR_ID
    assert spec["chosen_model_id"] == RFDETR_ID
    assert spec["resolved_tier"] == "accurate"
    assert spec["reason"] == "ready"


def test_missing_rfdetr_falls_back_to_the_default_accurate_detector(tmp_path, monkeypatch, chosen_detector):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))
    _install(tmp_path, YOLOX_ID)
    _install(tmp_path, "bird_crop_detector")
    chosen_detector("rfdetr_nano")

    spec = ModelManager().get_crop_detector_spec("accurate")

    assert spec["model_id"] == YOLOX_ID
    assert spec["chosen_model_id"] == RFDETR_ID
    assert spec["resolved_tier"] == "accurate"
    assert spec["reason"] == "fallback_default_accurate"


def test_missing_rfdetr_and_yolox_fall_back_to_the_fast_detector(tmp_path, monkeypatch, chosen_detector):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))
    _install(tmp_path, "bird_crop_detector")
    chosen_detector("rfdetr_nano")

    spec = ModelManager().get_crop_detector_spec("accurate")

    assert spec["model_id"] == "bird_crop_detector"
    assert spec["resolved_tier"] == "fast"
    assert spec["reason"] == "fallback_fast"


@pytest.mark.asyncio
async def test_the_detector_choice_round_trips_through_the_api(chosen_detector):
    import httpx

    from app.main import app

    chosen_detector("yolox_tiny")
    auth_enabled = settings.auth.enabled
    settings.auth.enabled = False
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            read = await client.get("/api/settings")
            assert read.status_code == 200, read.text
            assert read.json()["bird_crop_accurate_detector"] == "yolox_tiny"

            written = await client.post("/api/settings", json={"bird_crop_accurate_detector": "rfdetr_nano"})
            assert written.status_code == 200, written.text
            assert settings.classification.bird_crop_accurate_detector == "rfdetr_nano"

            refused = await client.post("/api/settings", json={"bird_crop_accurate_detector": "yolo_world"})
            assert refused.status_code == 422
            assert settings.classification.bird_crop_accurate_detector == "rfdetr_nano"
    finally:
        settings.auth.enabled = auth_enabled
