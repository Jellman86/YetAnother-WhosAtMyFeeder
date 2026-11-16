"""An installed model says whether it ships with the app, so the UI never calls a model built in
when this install would have to download it."""

from app.services import model_manager as module


def _manager(tmp_path, monkeypatch, *, bundled_dir):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(module, "MODELS_DIR", str(models_dir))
    monkeypatch.setattr(module, "BUNDLED_MODELS_DIR", str(bundled_dir))
    monkeypatch.setattr(module, "is_model_validated", lambda *args, **kwargs: (True, "validated"))
    monkeypatch.setattr(module, "host_eligible_providers", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "host_provider_preference_order", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "activation_provider_recommendation", lambda *args, **kwargs: None)
    return module.ModelManager(), models_dir


def test_the_model_in_the_image_assets_is_reported_as_bundled(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "model.tflite").write_bytes(b"tflite")
    (assets / "labels.txt").write_text("Bird\n")
    manager, _ = _manager(tmp_path, monkeypatch, bundled_dir=assets)

    installed = manager._list_installed_models_sync([])

    bundled = [model for model in installed if model.id == "mobilenet_v2_birds"]
    assert len(bundled) == 1
    assert bundled[0].bundled is True


def test_a_downloaded_model_is_not_reported_as_bundled(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    manager, models_dir = _manager(tmp_path, monkeypatch, bundled_dir=assets)
    downloaded = models_dir / "mobilenet_v2_birds"
    downloaded.mkdir()
    (downloaded / "model.tflite").write_bytes(b"tflite")
    (downloaded / "labels.txt").write_text("Bird\n")

    installed = manager._list_installed_models_sync([])

    assert [(model.id, model.bundled) for model in installed] == [("mobilenet_v2_birds", False)]


def test_an_install_without_the_bundled_assets_lists_nothing_as_bundled(tmp_path, monkeypatch):
    manager, _ = _manager(tmp_path, monkeypatch, bundled_dir=tmp_path / "missing-assets")

    assert manager._list_installed_models_sync([]) == []
