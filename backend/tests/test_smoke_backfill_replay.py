import os

from scripts.smoke_backfill_replay import isolate_environment


def test_hardware_replay_cannot_inherit_live_settings_or_fake_inference(monkeypatch, tmp_path):
    # The smoke harness is a standalone process; restore its whole environment here.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ.update(
        CLASSIFICATION__INFERENCE_PROVIDER="intel_npu",
        CLASSIFICATION__IMAGE_EXECUTION_MODE="in_process",
        FRIGATE__MQTT_PASSWORD="private",
        NOTIFICATIONS__TELEGRAM_ENABLED="true",
        YA_WAMF_CLASSIFIER_WORKER_TEST_MODE="1",
        DB_PATH="/data/speciesid.db",
        LD_LIBRARY_PATH="/device-libraries",
    )
    isolate_environment(tmp_path)
    assert not any(
        key.startswith(("CLASSIFICATION__", "FRIGATE__", "NOTIFICATIONS__", "YA_WAMF_")) for key in os.environ
    )
    assert os.environ["DB_PATH"] == str(tmp_path / "detections.db")
    assert os.environ["CONFIG_FILE"] == str(tmp_path / "config.json")
    assert os.environ["MODEL_DIR"] == str(tmp_path / "models")
    assert os.environ["SPECIES_CATALOG_PATH"] == str(tmp_path / "catalog.db")
    assert os.environ["LD_LIBRARY_PATH"] == "/device-libraries"
