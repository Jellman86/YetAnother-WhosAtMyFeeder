"""Owner-only scan admission exposes safe status without private scene provenance."""

from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.repositories.bird_scan_repository import BirdScanBusyError, BirdScanNotFoundError
from app.services.bird_scan_service import BirdScanUnavailable, bird_scan_service


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    payload = dict(
        event_id="scan-event",
        candidate_id="scene",
        status="queued",
        available=True,
        image_ref="private-image",
        content_sha256="private-hash",
        generation="private-generation",
    )
    get = AsyncMock(return_value=payload)
    enqueue = AsyncMock(return_value=payload)
    monkeypatch.setattr(bird_scan_service, "get_status", get)
    monkeypatch.setattr(bird_scan_service, "enqueue", enqueue)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, get, enqueue, {"Authorization": f"Bearer {create_access_token('owner')}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("public,expected", [(False, 401), (True, 403)])
async def test_scan_read_and_write_require_owner(api, monkeypatch, public, expected):
    client, get, enqueue, _ = api
    monkeypatch.setattr(settings.public_access, "enabled", public)
    assert (await client.get("/api/frigate/scan-event/birds/scan?candidate_id=scene")).status_code == expected
    assert (
        await client.post(
            "/api/frigate/scan-event/birds/scan", json={"expected_media_version": "version-1", "candidate_id": "scene"}
        )
    ).status_code == expected
    get.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_can_request_scan_and_response_excludes_private_input(api):
    client, get, enqueue, headers = api
    response = await client.post(
        "/api/frigate/scan-event/birds/scan",
        json={"expected_media_version": "version-1", "candidate_id": "scene", "force": True},
        headers=headers,
    )
    assert response.status_code == 202
    enqueue.assert_awaited_once_with("scan-event", "scene", force=True, expected_media_version="version-1")
    assert not {"image_ref", "content_sha256", "generation"} & response.json().keys()
    assert response.json()["status"] == "queued"
    response = await client.get("/api/frigate/scan-event/birds/scan?candidate_id=scene", headers=headers)
    assert response.status_code == 200
    get.assert_awaited_once_with("scan-event", "scene", expected_media_version=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("event,expected", [("bad%20event", 400), ("x" * 65, 422)])
async def test_invalid_event_ids_never_reach_service(api, event, expected):
    client, get, enqueue, headers = api
    url = f"/api/frigate/{event}/birds/scan"
    assert (await client.get(url, params={"candidate_id": "scene"}, headers=headers)).status_code == expected
    assert (
        await client.post(url, json={"expected_media_version": "version-1", "candidate_id": "scene"}, headers=headers)
    ).status_code == expected
    get.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate", ["", "x" * 257, None])
async def test_invalid_candidate_ids_are_rejected(api, candidate):
    client, get, enqueue, headers = api
    url = "/api/frigate/scan-event/birds/scan"
    assert (
        await client.post(url, json={"expected_media_version": "version-1", "candidate_id": candidate}, headers=headers)
    ).status_code == 422
    params = {} if candidate is None else {"candidate_id": candidate}
    assert (await client.get(url, params=params, headers=headers)).status_code == 422
    get.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status,detail",
    [
        (BirdScanNotFoundError("private missing path"), 404, "Detection not found"),
        (BirdScanBusyError("private active scene"), 409, "scan_in_progress"),
        (BirdScanUnavailable("queue_full"), 429, "queue_full"),
        (BirdScanUnavailable("media_changed"), 409, "media_changed"),
        (BirdScanUnavailable("reviewed_other_frame"), 409, "reviewed_other_frame"),
        (BirdScanUnavailable("crop_model_unavailable"), 409, "crop_model_unavailable"),
    ],
)
async def test_admission_errors_have_stable_public_codes(api, error, status, detail):
    client, _, enqueue, headers = api
    enqueue.side_effect = error
    response = await client.post(
        "/api/frigate/scan-event/birds/scan",
        json={"expected_media_version": "version-1", "candidate_id": "scene"},
        headers=headers,
    )
    assert response.status_code == status and response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_missing_detection_status_hides_internal_error(api):
    client, get, _, headers = api
    get.side_effect = BirdScanNotFoundError("private database location")
    response = await client.get("/api/frigate/scan-event/birds/scan?candidate_id=scene", headers=headers)
    assert response.status_code == 404 and response.json()["detail"] == "Detection not found"


@pytest.mark.asyncio
async def test_media_session_cookie_cannot_authorize_scan_admission(api):
    client, get, enqueue, _ = api
    client.cookies.set("yawamf_session", create_access_token("owner"))
    response = await client.post(
        "/api/frigate/scan-event/birds/scan", json={"expected_media_version": "version-1", "candidate_id": "scene"}
    )
    assert response.status_code == 401
    response = await client.get("/api/frigate/scan-event/birds/scan?candidate_id=scene")
    assert response.status_code == 401
    enqueue.assert_not_awaited()
    get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [None, "", "x" * 129])
async def test_admission_requires_a_valid_displayed_media_version(api, version):
    client, _, enqueue, headers = api
    body = {"candidate_id": "scene"}
    if version is not None:
        body["expected_media_version"] = version
    response = await client.post("/api/frigate/scan-event/birds/scan", json=body, headers=headers)
    assert response.status_code == 422
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_forwards_the_displayed_media_version(api):
    client, get, _, headers = api
    response = await client.get(
        "/api/frigate/scan-event/birds/scan",
        params={"candidate_id": "scene", "expected_media_version": "displayed-version"},
        headers=headers,
    )
    assert response.status_code == 200
    get.assert_awaited_once_with("scan-event", "scene", expected_media_version="displayed-version")


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["", "x" * 129])
async def test_status_rejects_invalid_optional_media_version(api, version):
    client, get, _, headers = api
    response = await client.get(
        "/api/frigate/scan-event/birds/scan",
        params={"candidate_id": "scene", "expected_media_version": version},
        headers=headers,
    )
    assert response.status_code == 422
    get.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_displayed_media_version_returns_conflict(api):
    client, _, enqueue, headers = api
    enqueue.side_effect = BirdScanUnavailable("media_changed")
    response = await client.post(
        "/api/frigate/scan-event/birds/scan",
        json={"candidate_id": "scene", "expected_media_version": "stale-version"},
        headers=headers,
    )
    assert response.status_code == 409 and response.json()["detail"] == "media_changed"
    enqueue.assert_awaited_once_with("scan-event", "scene", force=False, expected_media_version="stale-version")
