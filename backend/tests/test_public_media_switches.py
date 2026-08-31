"""What an unauthenticated visitor may see is the owner's call, per medium (#291).

Audio had no switch at all - BirdNET detections and spectrograms were visible
to any visitor with no way to turn them off. Snapshots and clips had windows
but no off. And nothing coarsened the location guest-facing features search
from. The contract under test: three per-medium switches enforced at the API,
and a location precision that defaults to approximate for the public view -
the person who gets doxxed by an exact location is the person who never found
the setting.
"""

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.utils.public_access import approximate_coordinate, guest_location


@pytest_asyncio.fixture(autouse=True)
async def public_instance(monkeypatch):
    await init_db()
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_audio", True)
    monkeypatch.setattr(settings.public_access, "show_snapshots", True)
    monkeypatch.setattr(settings.public_access, "show_clips", True)
    monkeypatch.setattr(settings.auth, "enabled", True)
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
                   VALUES ('event_media', 'cam1', ?, 1, 0.9, 'Robin', 'Robin', 0)""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
            )
            await db.commit()
        yield
    finally:
        await close_db()


def test_location_approximation_rounds_to_a_town_not_a_garden():
    # One decimal place is roughly 11 km - a town, not an address.
    assert approximate_coordinate(51.50721895) == pytest.approx(51.5)
    assert approximate_coordinate(-0.1275542) == pytest.approx(-0.1)
    assert approximate_coordinate(None) is None


def test_guest_location_honours_the_precision_setting(monkeypatch):
    monkeypatch.setattr(settings.location, "latitude", 51.50721895)
    monkeypatch.setattr(settings.location, "longitude", -0.1275542)

    monkeypatch.setattr(settings.public_access, "location_precision", "approximate")
    assert guest_location() == (pytest.approx(51.5), pytest.approx(-0.1))

    monkeypatch.setattr(settings.public_access, "location_precision", "exact")
    assert guest_location() == (pytest.approx(51.50721895), pytest.approx(-0.1275542))


@pytest.mark.asyncio
async def test_defaults_preserve_media_and_approximate_location():
    from app.config_models import PublicAccessSettings

    fresh = PublicAccessSettings()
    assert fresh.show_audio is True
    assert fresh.show_snapshots is True
    assert fresh.show_clips is True
    # The privacy-by-default commitment from #291: approximate for visitors
    # unless the owner explicitly says exact.
    assert fresh.location_precision == "approximate"


@pytest.mark.asyncio
async def test_guest_audio_is_refused_when_the_switch_is_off(monkeypatch):
    monkeypatch.setattr(settings.public_access, "show_audio", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/audio/recent")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_guest_audio_flows_when_the_switch_is_on():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/audio/recent")
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_guest_snapshot_and_clip_switches_are_enforced(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        monkeypatch.setattr(settings.public_access, "show_snapshots", False)
        res = await client.get("/api/frigate/event_media/thumbnail.jpg")
        assert res.status_code == 404

        monkeypatch.setattr(settings.public_access, "show_clips", False)
        res = await client.get("/api/frigate/event_media/clip.mp4")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_auth_status_carries_the_media_switches(monkeypatch):
    monkeypatch.setattr(settings.public_access, "show_audio", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/auth/status")
        payload = res.json()
        assert payload["public_access_show_audio"] is False
        assert payload["public_access_show_snapshots"] is True
        assert payload["public_access_show_clips"] is True


@pytest.mark.asyncio
async def test_guest_ebird_search_centres_on_the_approximate_location(monkeypatch):
    from app.routers import ebird as ebird_router

    monkeypatch.setattr(settings.location, "latitude", 51.50721895)
    monkeypatch.setattr(settings.location, "longitude", -0.1275542)
    monkeypatch.setattr(settings.public_access, "location_precision", "approximate")
    monkeypatch.setattr(settings.ebird, "enabled", True)
    monkeypatch.setattr(settings.ebird, "api_key", "test-key")

    seen: dict = {}

    async def fake_observations(*, lat, lng, dist_km, back_days, max_results, species_code=None):
        seen["lat"], seen["lng"] = lat, lng
        return []

    monkeypatch.setattr(ebird_router.ebird_service, "get_recent_observations", fake_observations)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/ebird/nearby")
        assert res.status_code == 200
        assert seen["lat"] == pytest.approx(51.5)
        assert seen["lng"] == pytest.approx(-0.1)
