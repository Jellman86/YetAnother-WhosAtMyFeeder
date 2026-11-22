"""What a fresh install runs: the bundled MobileNet V2, whatever path builds its settings.

The saved selection on an install where nobody chose a model is the bundled model's file name.
The model manager reads that as no choice and runs ``mobilenet_v2_birds`` from the bundled assets;
the TFLite backend opens the file by that name. The loader and the settings model once disagreed:
the model declared RoPE ViT-B14, which is not bundled, so settings built without the loader (an
imported backup with no ``classification.model``) named a model the install did not have.
"""

import os

import app.config as config_module
from app.config import Settings
from app.config_models import BUNDLED_CLASSIFIER_FILE, ClassificationSettings
from app.services import model_manager as model_manager_module


def _fresh_settings(monkeypatch, tmp_path) -> Settings:
    for key in [key for key in os.environ if key.startswith("CLASSIFICATION__")]:
        monkeypatch.delenv(key)
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "missing" / "config.json")
    return Settings.load()


def test_a_fresh_install_saves_the_bundled_model_file_as_its_selection(monkeypatch, tmp_path):
    assert _fresh_settings(monkeypatch, tmp_path).classification.model == "model.tflite"
    assert BUNDLED_CLASSIFIER_FILE == "model.tflite"


def test_settings_built_without_the_loader_select_the_same_bundled_model(monkeypatch, tmp_path):
    fresh = _fresh_settings(monkeypatch, tmp_path)
    assert ClassificationSettings().model == fresh.classification.model
    # A backup that does not name a model, imported the way the settings import validates it.
    backup = fresh.model_dump(mode="json")
    del backup["classification"]["model"]
    assert Settings.model_validate(backup).classification.model == "model.tflite"


def test_a_fresh_install_runs_the_bundled_mobilenet_from_the_bundled_assets(monkeypatch, tmp_path):
    settings = _fresh_settings(monkeypatch, tmp_path)
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(model_manager_module, "MODELS_DIR", str(models_dir))
    monkeypatch.setattr(model_manager_module.settings, "classification", settings.classification)

    manager = model_manager_module.ModelManager()
    spec = manager.get_active_model_spec()

    assert manager.active_model_id == "model.tflite"
    assert spec["model_id"] == "mobilenet_v2_birds"
    assert spec["runtime"] == "tflite"
    assert spec["model_path"] == os.path.join(model_manager_module.BUNDLED_MODELS_DIR, "model.tflite")
    assert spec["labels_path"] == os.path.join(model_manager_module.BUNDLED_MODELS_DIR, "labels.txt")
