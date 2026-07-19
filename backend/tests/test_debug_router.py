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


def test_every_debug_endpoint_declares_a_response_model():
    debug_routes = [route for route in router.routes if getattr(route, "path", "").startswith("/debug/")]

    assert debug_routes
    assert all(route.response_model is not None for route in debug_routes)
