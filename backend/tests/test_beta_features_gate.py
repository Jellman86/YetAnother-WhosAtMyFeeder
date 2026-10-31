"""Garden animals is a beta feature: off unless the owner turns it on.

Turning it off stops new collection, the motion scanner and the Garden API, but
never the privacy cleanup that removes stored photos a later person event covers.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.config_models import SystemSettings
from app.main import app

GARDEN_EVENT = {
    "type": "end",
    "after": {"id": "1792000000.1-abc", "camera": "patio", "label": "dog", "has_snapshot": True, "start_time": 1.0},
}
PERSON_EVENT = {
    "type": "update",
    "after": {"id": "1792000000.2-def", "camera": "patio", "label": "person", "start_time": 1.0, "end_time": 2.0},
}


@pytest.fixture
def garden_cameras(monkeypatch):
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    monkeypatch.setattr(settings.frigate, "garden_motion_cameras", ["patio"])
    monkeypatch.setattr(settings.frigate, "garden_labels", ["dog"])


@pytest.fixture
def beta(monkeypatch):
    def set_enabled(value: bool) -> None:
        monkeypatch.setattr(settings.system, "beta_garden_animals", value)

    return set_enabled


def test_garden_is_off_until_the_owner_turns_it_on():
    assert SystemSettings().beta_garden_animals is False


@pytest.mark.asyncio
async def test_switched_off_garden_ignores_new_animal_events(garden_cameras, beta, monkeypatch):
    from app.services.garden_capture_service import garden_capture_service

    beta(False)
    capture = AsyncMock()
    monkeypatch.setattr("app.repositories.garden_repository.GardenRepository.capture", capture)
    await garden_capture_service.process(GARDEN_EVENT)
    capture.assert_not_awaited()


@pytest.mark.asyncio
async def test_switched_off_garden_still_removes_photos_a_person_event_covers(garden_cameras, beta, monkeypatch):
    from app.services.garden_capture_service import garden_capture_service

    beta(False)
    monkeypatch.setattr(garden_capture_service, "has_history", True)
    overlap = AsyncMock()
    block = AsyncMock()
    monkeypatch.setattr("app.repositories.garden_repository.GardenRepository.block_motion_overlap", overlap)
    monkeypatch.setattr("app.repositories.garden_repository.GardenRepository.block", block)
    await garden_capture_service.process(PERSON_EVENT)
    overlap.assert_awaited_once()
    block.assert_awaited_once()
    # A person revokes every capture of the event, a domestic bird's included.
    assert block.await_args.kwargs == {"create": False, "keep_domestic": False}


def test_switched_off_garden_does_not_route_animal_events_from_mqtt(garden_cameras, beta):
    from app.services.garden_capture_policy import garden_collection_cameras

    beta(False)
    assert garden_collection_cameras() == []
    beta(True)
    assert garden_collection_cameras() == ["patio"]


def test_switched_off_garden_motion_scanner_has_no_cameras(garden_cameras, beta):
    from app.services.garden_motion import garden_motion_service

    beta(False)
    assert garden_motion_service.cameras() == []
    beta(True)
    assert garden_motion_service.cameras() == ["patio"]


@pytest.mark.asyncio
async def test_switched_off_garden_api_says_it_is_turned_off(beta, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    beta(False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/garden")
    assert response.status_code == 404
    assert "beta" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_the_beta_switch_round_trips_through_the_settings_api(beta, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    beta(False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        read = await client.get("/api/settings")
        assert read.json()["beta_garden_animals"] is False
        written = await client.post("/api/settings", json={"beta_garden_animals": True})
        assert written.status_code == 200, written.text
        assert settings.system.beta_garden_animals is True
        assert (await client.get("/api/settings")).json()["beta_garden_animals"] is True


def test_the_beta_switch_can_be_set_from_the_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("SYSTEM__BETA_GARDEN_ANIMALS", "true")
    assert Settings.load().system.beta_garden_animals is True
