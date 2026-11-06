from app.routers import settings as settings_router


def test_config_backup_payload_includes_unredacted_config_secrets():
    original_mqtt_password = settings_router.settings.frigate.mqtt_password
    original_llm_api_key = settings_router.settings.llm.api_key
    try:
        settings_router.settings.frigate.mqtt_password = "mqtt-secret"
        settings_router.settings.llm.api_key = "llm-secret"

        payload = settings_router._config_backup_payload()

        assert payload["format"] == settings_router.CONFIG_BACKUP_FORMAT
        assert payload["format_version"] == settings_router.CONFIG_BACKUP_FORMAT_VERSION
        assert payload["includes_secrets"] is True
        assert payload["config"]["frigate"]["mqtt_password"] == "mqtt-secret"
        assert payload["config"]["llm"]["api_key"] == "llm-secret"
    finally:
        settings_router.settings.frigate.mqtt_password = original_mqtt_password
        settings_router.settings.llm.api_key = original_llm_api_key


def test_config_backup_import_payload_roundtrip_validates_as_settings():
    payload = settings_router._config_backup_payload()

    config = settings_router._extract_import_config(payload)
    imported = settings_router.AppSettings.model_validate(config)

    assert imported.frigate.frigate_url == settings_router.settings.frigate.frigate_url
    assert imported.auth.session_secret == settings_router.settings.auth.session_secret
