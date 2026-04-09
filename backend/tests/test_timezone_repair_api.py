import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.services.timezone_repair_service import timezone_repair_service


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def owner_auth_override():
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_timezone_repair_preview_endpoint_returns_service_payload(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_preview():
        return {
            "summary": {
                "scanned_count": 3,
                "repair_candidate_count": 1,
                "ok_count": 1,
                "missing_frigate_event_count": 1,
                "unsupported_delta_count": 0,
            },
            "candidates": [],
        }

    monkeypatch.setattr(timezone_repair_service, "preview", _fake_preview)

    response = await client.get("/api/maintenance/timezone-repair/preview")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["scanned_count"] == 3
    assert payload["summary"]["repair_candidate_count"] == 1


@pytest.mark.asyncio
async def test_timezone_repair_apply_endpoint_requires_confirmation(client: httpx.AsyncClient):
    response = await client.post("/api/maintenance/timezone-repair/apply", json={"confirm": False})

    assert response.status_code == 400, response.text
    assert "confirmation" in response.text.lower()


@pytest.mark.asyncio
async def test_timezone_repair_apply_endpoint_returns_apply_result(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_apply(*, confirm: bool):
        assert confirm is True
        return {
            "status": "ok",
            "repaired_count": 2,
            "skipped_count": 1,
            "preview": {
                "summary": {
                    "scanned_count": 3,
                    "repair_candidate_count": 2,
                    "ok_count": 1,
                    "missing_frigate_event_count": 0,
                    "unsupported_delta_count": 0,
                },
                "candidates": [],
            },
        }

    monkeypatch.setattr(timezone_repair_service, "apply", _fake_apply)

    response = await client.post("/api/maintenance/timezone-repair/apply", json={"confirm": True})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["repaired_count"] == 2
