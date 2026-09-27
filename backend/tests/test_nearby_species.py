import asyncio
from datetime import datetime, timedelta, timezone
import uuid

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.services import nearby_species_service as nearby_module
from app.services.nearby_species_service import (
    NearbySpeciesService,
    build_nearby_report,
    reported_nearby,
)

EBIRD_ROWS = [
    {"sciName": "Prunella modularis", "comName": "Dunnock"},
    {"sciName": "Erithacus rubecula", "comName": "European Robin"},
]


def test_a_species_birders_reported_nearby_is_reported_by_either_name():
    report = build_nearby_report(EBIRD_ROWS, radius_km=50, days_back=30)
    assert reported_nearby(report, scientific_name="Prunella modularis", common_name=None) is True
    assert reported_nearby(report, scientific_name=None, common_name="european robin") is True


def test_a_species_nobody_reported_nearby_is_not():
    report = build_nearby_report(EBIRD_ROWS, radius_km=50, days_back=30)
    assert (
        reported_nearby(report, scientific_name="Zonotrichia atricapilla", common_name="Golden-crowned Sparrow")
        is False
    )


def test_without_a_report_or_a_name_the_answer_is_unknown():
    report = build_nearby_report(EBIRD_ROWS, radius_km=50, days_back=30)
    assert reported_nearby(None, scientific_name="Prunella modularis", common_name="Dunnock") is None
    assert reported_nearby(report, scientific_name=None, common_name=None) is None


@pytest.fixture
def ebird_configured(monkeypatch):
    monkeypatch.setattr(settings.ebird, "enabled", True)
    monkeypatch.setattr(settings.ebird, "api_key", "test-key")
    monkeypatch.setattr(settings.location, "latitude", 52.123456)
    monkeypatch.setattr(settings.location, "longitude", -1.987654)


@pytest.mark.asyncio
async def test_the_lookup_sends_the_approximate_location_and_caches_it(monkeypatch, ebird_configured):
    calls: list[dict] = []

    async def fake_recent(**kwargs):
        calls.append(kwargs)
        return EBIRD_ROWS

    monkeypatch.setattr(nearby_module.ebird_service, "get_recent_observations", fake_recent)
    service = NearbySpeciesService()

    first = await service.get_report()
    second = await service.get_report()

    assert first is second
    assert len(calls) == 1
    assert (calls[0]["lat"], calls[0]["lng"]) == (52.1, -2.0)
    assert calls[0]["dist_km"] == 50 and calls[0]["back_days"] == 30


@pytest.mark.asyncio
async def test_a_freshly_booted_host_still_looks_up(monkeypatch, ebird_configured):
    # A CI runner or a just-rebooted host has a monotonic clock younger than the back-off.
    monkeypatch.setattr(nearby_module.time, "monotonic", lambda: 5.0)

    async def fake_recent(**_kwargs):
        return EBIRD_ROWS

    monkeypatch.setattr(nearby_module.ebird_service, "get_recent_observations", fake_recent)
    assert await NearbySpeciesService().get_report() is not None


@pytest.mark.asyncio
async def test_a_failed_or_slow_lookup_is_unknown_and_not_retried_at_once(monkeypatch, ebird_configured):
    calls = 0

    async def failing(**_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("eBird down")

    monkeypatch.setattr(nearby_module.ebird_service, "get_recent_observations", failing)
    service = NearbySpeciesService()
    assert await service.get_report() is None
    assert await service.get_report() is None
    assert calls == 1

    async def slow(**_kwargs):
        await asyncio.sleep(1)
        return EBIRD_ROWS

    monkeypatch.setattr(nearby_module.ebird_service, "get_recent_observations", slow)
    monkeypatch.setattr(nearby_module, "LOOKUP_TIMEOUT_SECONDS", 0.05)
    assert await NearbySpeciesService().get_report() is None


@pytest.mark.asyncio
async def test_no_lookup_runs_without_ebird_or_a_location(monkeypatch):
    async def must_not_run(**_kwargs):
        raise AssertionError("eBird was called")

    monkeypatch.setattr(nearby_module.ebird_service, "get_recent_observations", must_not_run)
    monkeypatch.setattr(settings.ebird, "enabled", False)
    assert await NearbySpeciesService().get_report() is None

    monkeypatch.setattr(settings.ebird, "enabled", True)
    monkeypatch.setattr(settings.ebird, "api_key", "test-key")
    monkeypatch.setattr(settings.location, "latitude", None)
    assert await NearbySpeciesService().get_report() is None


@pytest_asyncio.fixture
async def client():
    await init_db()
    original = (settings.auth.enabled, settings.public_access.enabled)
    settings.auth.enabled = False
    settings.public_access.enabled = False
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        settings.auth.enabled, settings.public_access.enabled = original
        await close_db()


@pytest.mark.asyncio
async def test_leaderboard_says_which_species_were_reported_nearby(client: httpx.AsyncClient, monkeypatch):
    prefix = f"lb-nearby-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    names = {"Nearby": f"Nearby Finch {prefix}", "Far": f"Far Finch {prefix}"}
    async with get_db() as db:
        for index, (tag, name) in enumerate(names.items()):
            await db.execute(
                """
                INSERT INTO detections (
                    detection_time, detection_index, score, display_name, category_name,
                    frigate_event, camera_name, is_hidden, manual_tagged, scientific_name
                ) VALUES (?, 1, 0.8, ?, ?, ?, 'test-camera', 0, 0, ?)
                """,
                ((now - timedelta(hours=1 + index)).isoformat(sep=" "), name, name, f"{prefix}-{tag}", name),
            )
        await db.commit()

    report = build_nearby_report([{"sciName": names["Nearby"], "comName": ""}], radius_km=50, days_back=30)

    async def fake_report():
        return report

    monkeypatch.setattr(nearby_module.nearby_species_service, "get_report", fake_report)
    try:
        response = await client.get("/api/leaderboard/species?span=day")
        assert response.status_code == 200, response.text
        payload = response.json()
        rows = {row["species"]: row for row in payload["species"]}
        assert rows[names["Nearby"]]["reported_nearby"] is True
        assert rows[names["Far"]]["reported_nearby"] is False
        assert (payload["nearby_radius_km"], payload["nearby_days_back"]) == (50, 30)
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event LIKE ?", (f"{prefix}%",))
            await db.commit()
