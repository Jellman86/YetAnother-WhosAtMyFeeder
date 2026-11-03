import app.config_models as config_models
from app.routers.debug import redact_config, router


def test_redact_config_redacts_nested_secrets_without_mutating_input():
    config = {
        "frigate": {"frigate_auth_token": "secret", "frigate_url": "http://frigate"},
        "notifications": [{"bot_token": "secret", "enabled": True}],
        "empty_password": "",
    }

    redacted = redact_config(config)

    assert redacted == {
        "frigate": {"frigate_auth_token": "***REDACTED***", "frigate_url": "http://frigate"},
        "notifications": [{"bot_token": "***REDACTED***", "enabled": True}],
        "empty_password": "",
    }
    assert config["frigate"]["frigate_auth_token"] == "secret"


def test_redact_config_redacts_auth_and_access_secrets():
    config = {
        "auth": {
            "session_secret": "signing-secret",
            "password_hash": "bcrypt-hash",
            "oauth_token_secret": "oauth-secret",
            "username": "admin",
        },
        "homeassistant": {"access_token": "ha-token"},
    }

    redacted = redact_config(config)

    assert redacted["auth"]["session_secret"] == "***REDACTED***"
    assert redacted["auth"]["password_hash"] == "***REDACTED***"
    assert redacted["auth"]["oauth_token_secret"] == "***REDACTED***"
    assert redacted["auth"]["username"] == "admin"
    assert redacted["homeassistant"]["access_token"] == "***REDACTED***"


def test_redact_config_fails_closed_for_unlisted_secret_shaped_keys():
    config = {"future": {"refresh_token": "x", "service_secret": "y", "label": "keep"}}

    redacted = redact_config(config)

    assert redacted["future"]["refresh_token"] == "***REDACTED***"
    assert redacted["future"]["service_secret"] == "***REDACTED***"
    assert redacted["future"]["label"] == "keep"


def test_every_secret_shaped_settings_field_is_redacted():
    markers = ("secret", "password", "token", "hash", "api_key", "user_key")
    field_names = set()
    for value in vars(config_models).values():
        fields = getattr(value, "model_fields", None)
        if fields:
            field_names.update(fields)
    secret_fields = sorted(name for name in field_names if any(marker in name for marker in markers))

    assert secret_fields
    for name in secret_fields:
        assert redact_config({name: "value"}) == {name: "***REDACTED***"}, name


def test_every_debug_endpoint_declares_a_response_model():
    debug_routes = [route for route in router.routes if getattr(route, "path", "").startswith("/debug/")]

    assert debug_routes
    assert all(route.response_model is not None for route in debug_routes)
