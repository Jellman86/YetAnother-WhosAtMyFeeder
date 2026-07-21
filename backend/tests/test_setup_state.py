"""Tests for the wizard setup-readiness service and the /api/setup/state endpoint."""

import httpx
import pytest
import pytest_asyncio

from app.config import Settings
from app.config_models import (
    AuthSettings,
    BirdWeatherSettings,
    EbirdSettings,
    FrigateSettings,
    LLMSettings,
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


def test_cameras_ok_when_empty_list_watches_all_cameras():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=[])
    state = compute_setup_state(_settings(frigate=frigate))
    cameras = _by_id(state)["cameras"]
    assert cameras.status == "ok"
    assert cameras.detail == "All cameras"


def test_cameras_ok_and_counts():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=["front", "back"])
    state = compute_setup_state(_settings(frigate=frigate))
    cameras = _by_id(state)["cameras"]
    assert cameras.status == "ok"
    assert cameras.detail == "2 cameras"


def test_model_is_always_ok():
    assert _by_id(compute_setup_state(_settings()))["model"].status == "ok"


def test_integrations_optional_when_all_disabled():
    frigate = FrigateSettings(frigate_url="http://frigate:5000", camera=["front"], birdnet_enabled=False)
    state = compute_setup_state(_settings(frigate=frigate))
    assert _by_id(state)["integrations"].status == "optional"


def test_integrations_ok_lists_enabled():
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
    assert integrations.status == "ok"
    for name in ("BirdNET-Go", "eBird", "BirdWeather", "AI analysis"):
        assert name in integrations.detail


@pytest.mark.asyncio
async def test_endpoint_returns_setup_state(client):
    response = await client.get("/api/setup/state")
    assert response.status_code == 200
    payload = response.json()
    assert "initial_setup_complete" in payload
    assert [s["id"] for s in payload["sections"]] == list(SETUP_SECTION_IDS)
