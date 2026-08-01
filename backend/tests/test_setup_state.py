"""Tests for the wizard setup-readiness service and the /api/setup/state endpoint."""

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.config_models import (
    AuthSettings,
    BirdWeatherSettings,
    ClassificationSettings,
    EbirdSettings,
    FrigateSettings,
    InaturalistSettings,
    LLMSettings,
    NotificationSettings,
)
from app.services.setup_state_service import SETUP_SECTION_IDS, compute_setup_state


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _settings(*, frigate=None, auth=None, **overrides) -> Settings:
    """Build an isolated Settings (no env/.env) with sensible defaults for the wizard tests."""
    return Settings(
        _env_file=None,
        frigate=frigate or FrigateSettings(frigate_url="http://frigate:5000", camera=["front"]),
        auth=auth or AuthSettings(),
        **overrides,
    )


def _by_id(state):
    return {s.id: s for s in state.sections}


def test_all_wizard_sections_present():
    state = compute_setup_state(_settings())
    assert [s.id for s in state.sections] == list(SETUP_SECTION_IDS)


def test_account_attention_when_not_set_up():
    state = compute_setup_state(_settings(auth=AuthSettings(initial_setup_complete=False)))
    assert _by_id(state)["account"].status == "attention"


def test_account_ok_when_password_set():
    state = compute_setup_state(_settings(auth=AuthSettings(password_hash="hashed")))
    assert _by_id(state)["account"].status == "ok"


def test_account_ok_when_auth_explicitly_skipped():
    state = compute_setup_state(_settings(auth=AuthSettings(initial_setup_complete=True)))
    account = _by_id(state)["account"]
    assert account.status == "ok"
    assert account.detail == "Authentication disabled"
    assert state.initial_setup_complete is True


def test_connection_attention_when_url_missing():
    frigate = FrigateSettings(frigate_url="", camera=["front"])
    state = compute_setup_state(_settings(frigate=frigate))
    assert _by_id(state)["connection"].status == "attention"


def test_connection_ok_when_url_set():
    state = compute_setup_state(_settings())
    conn = _by_id(state)["connection"]
    assert conn.status == "ok"
    assert conn.detail == "http://frigate:5000"


def test_connection_attention_when_mqtt_broker_missing():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", mqtt_server="", camera=["front"])
    state = compute_setup_state(_settings(frigate=frigate))

    connection = _by_id(state)["connection"]
    assert connection.status == "attention"
    assert "MQTT" in connection.detail


def test_connection_attention_when_mqtt_auth_credentials_are_missing():
    frigate = FrigateSettings(
        frigate_url="http://frigate:5000",
        mqtt_server="mqtt",
        mqtt_auth=True,
        mqtt_username="",
        mqtt_password="",
        camera=["front"],
    )
    state = compute_setup_state(_settings(frigate=frigate))

    connection = _by_id(state)["connection"]
    assert connection.status == "attention"
    assert connection.detail_values == {"items": "mqtt_username,mqtt_password"}


def test_cameras_ok_when_empty_list_watches_all_cameras():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=[])
    state = compute_setup_state(_settings(frigate=frigate))
    cameras = _by_id(state)["cameras"]
    assert cameras.status == "ok"
    assert cameras.detail == "All cameras"
    assert cameras.detail_code == "cameras_all"


def test_cameras_ok_and_counts():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=["front", "back"])
    state = compute_setup_state(_settings(frigate=frigate))
    cameras = _by_id(state)["cameras"]
    assert cameras.status == "ok"
    assert cameras.detail == "2 cameras"
    assert cameras.detail_values == {"count": 2}


def test_model_is_always_ok():
    assert _by_id(compute_setup_state(_settings()))["model"].status == "ok"


def test_model_needs_attention_when_crop_detector_was_saved_as_classifier():
    state = compute_setup_state(_settings(classification=ClassificationSettings(model="bird_crop_detector")))

    model = _by_id(state)["model"]
    assert model.status == "attention"
    assert "crop detector" in model.detail.lower()
    assert model.detail_code == "model_wrong_kind"


def test_model_needs_attention_when_saved_classifier_was_retired():
    state = compute_setup_state(_settings(classification=ClassificationSettings(model="moganet_s_eu_common")))

    model = _by_id(state)["model"]
    assert model.status == "attention"
    assert "retired" in model.detail.lower()
    assert model.detail_code == "model_retired"


def test_integrations_optional_when_all_disabled():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=["front"], birdnet_enabled=False)
    state = compute_setup_state(_settings(frigate=frigate))
    assert _by_id(state)["integrations"].status == "optional"


def test_integrations_need_attention_when_enabled_without_required_credentials():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=["front"], birdnet_enabled=True)
    state = compute_setup_state(
        _settings(
            frigate=frigate,
            ebird=EbirdSettings(enabled=True),
            birdweather=BirdWeatherSettings(enabled=True),
            llm=LLMSettings(enabled=True),
        )
    )
    integrations = _by_id(state)["integrations"]
    assert integrations.status == "attention"
    assert integrations.detail_code == "integrations_incomplete"
    for name in ("BirdNET-Go", "eBird", "BirdWeather", "AI analysis"):
        assert name in integrations.detail


def test_integrations_ok_only_when_enabled_integrations_have_required_configuration():
    frigate = FrigateSettings(
        frigate_url="http://frigate:5000",
        mqtt_server="mqtt",
        audio_topic="birdnet",
        camera=["front"],
        birdnet_enabled=True,
    )
    notifications = NotificationSettings()
    notifications.discord.enabled = True
    notifications.discord.webhook_url = "https://discord.example/webhook"
    state = compute_setup_state(
        _settings(
            frigate=frigate,
            notifications=notifications,
            ebird=EbirdSettings(enabled=True, api_key="ebird-key"),
            inaturalist=InaturalistSettings(enabled=True, client_id="client", client_secret="secret"),
            birdweather=BirdWeatherSettings(enabled=True, station_token="station"),
            llm=LLMSettings(enabled=True, api_key="llm-key"),
        )
    )

    integrations = _by_id(state)["integrations"]
    assert integrations.status == "ok"
    assert integrations.detail_code == "integrations_configured"
    for name in ("BirdNET-Go", "Notifications", "eBird", "iNaturalist", "BirdWeather", "AI analysis"):
        assert name in integrations.detail


@pytest.mark.asyncio
async def test_endpoint_returns_setup_state(client):
    response = await client.get("/api/setup/state")
    assert response.status_code == 200
    payload = response.json()
    assert "initial_setup_complete" in payload
    assert [s["id"] for s in payload["sections"]] == list(SETUP_SECTION_IDS)
