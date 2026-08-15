"""Integration tests for authentication endpoints.

Note: We use httpx.ASGITransport instead of fastapi.TestClient because TestClient
hangs in this environment.
"""

import pytest
import pytest_asyncio
import httpx

from app.main import app
from app.config import settings
from app.auth import hash_password


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def reset_auth_config():
    """Reset auth config before each test."""
    original_enabled = settings.auth.enabled
    original_hash = settings.auth.password_hash
    original_username = settings.auth.username
    original_initial_setup_complete = settings.auth.initial_setup_complete
    original_public = settings.public_access.enabled
    original_weather_unit_system = settings.location.weather_unit_system
    original_ebird_radius = settings.ebird.default_radius_km

    yield

    settings.auth.enabled = original_enabled
    settings.auth.password_hash = original_hash
    settings.auth.username = original_username
    settings.auth.initial_setup_complete = original_initial_setup_complete
    settings.public_access.enabled = original_public
    settings.location.weather_unit_system = original_weather_unit_system
    settings.ebird.default_radius_km = original_ebird_radius


@pytest.mark.asyncio
async def test_auth_status_no_auth(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = False

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is False
    assert data["public_access_enabled"] is False
    assert data["needs_initial_setup"] is False


@pytest.mark.asyncio
async def test_auth_status_needs_setup_before_first_run(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.auth.initial_setup_complete = False
    settings.auth.password_hash = None

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is False
    assert data["needs_initial_setup"] is True


@pytest.mark.asyncio
async def test_auth_status_needs_setup_when_auth_enabled_without_password(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.initial_setup_complete = False
    settings.auth.password_hash = None

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is True
    assert data["needs_initial_setup"] is True


@pytest.mark.asyncio
async def test_auth_status_public_enabled(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = True

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["public_access_enabled"] is True


@pytest.mark.asyncio
async def test_auth_status_exposes_weather_unit_system(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = False
    settings.location.weather_unit_system = "imperial"

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["location_weather_unit_system"] == "imperial"


@pytest.mark.asyncio
async def test_auth_status_exposes_ebird_radius_for_guests(client: httpx.AsyncClient):
    """A guest dashboard states the search radius it actually used.

    Without this the public view falls back to a hard-coded 25 km and claims a
    scope the owner never configured.
    """
    settings.auth.enabled = True
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = True
    settings.ebird.default_radius_km = 40

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ebird_default_radius_km"] == 40


@pytest.mark.asyncio
async def test_login_success(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["username"] == "admin"
    assert data["token_type"] == "bearer"
    assert data["expires_in_hours"] == 168


@pytest.mark.asyncio
async def test_login_invalid_username(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = await client.post("/api/auth/login", json={"username": "wronguser", "password": "testpass123"})
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_invalid_password(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = await client.post("/api/auth/login", json={"username": "admin", "password": "wrongpass"})
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_auth_disabled(client: httpx.AsyncClient):
    settings.auth.enabled = False

    response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_no_password_set(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.password_hash = None

    response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
    assert response.status_code == 500
    assert "not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_initial_setup_success(client: httpx.AsyncClient):
    settings.auth.password_hash = None
    settings.auth.initial_setup_complete = False

    response = await client.post(
        "/api/auth/initial-setup", json={"username": "newadmin", "password": "newpass123", "enable_auth": True}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Setup completed successfully"
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"
    assert payload["username"] == "newadmin"
    assert payload["expires_in_hours"] == settings.auth.session_expiry_hours
    assert settings.auth.initial_setup_complete is True

    setup_response = await client.get(
        "/api/setup/state",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert setup_response.status_code == 200


@pytest.mark.asyncio
async def test_initial_setup_already_configured(client: httpx.AsyncClient):
    settings.auth.password_hash = hash_password("existing")
    settings.auth.initial_setup_complete = False

    response = await client.post(
        "/api/auth/initial-setup", json={"username": "admin", "password": "newpass123", "enable_auth": True}
    )
    assert response.status_code == 403
    assert "already configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_initial_setup_skip_auth(client: httpx.AsyncClient):
    settings.auth.password_hash = None
    settings.auth.initial_setup_complete = False

    response = await client.post(
        "/api/auth/initial-setup", json={"username": "admin", "password": None, "enable_auth": False}
    )
    assert response.status_code == 200
    assert response.json()["access_token"] is None
    assert settings.auth.enabled is False
    assert settings.auth.initial_setup_complete is True


@pytest.mark.asyncio
async def test_initial_setup_requires_password_when_enabling_auth(client: httpx.AsyncClient):
    settings.auth.password_hash = None
    settings.auth.initial_setup_complete = False

    response = await client.post(
        "/api/auth/initial-setup",
        json={"username": "admin", "password": None, "enable_auth": True},
    )

    assert response.status_code == 422
    assert settings.auth.initial_setup_complete is False
    assert settings.auth.password_hash is None


@pytest.mark.asyncio
async def test_initial_setup_rolls_back_in_memory_state_when_config_save_fails(
    client: httpx.AsyncClient,
    monkeypatch,
):
    settings.auth.enabled = False
    settings.auth.username = "admin"
    settings.auth.password_hash = None
    settings.auth.initial_setup_complete = False

    async def fail_save(_self):
        raise OSError("disk unavailable")

    monkeypatch.setattr(type(settings), "save", fail_save)

    with pytest.raises(OSError, match="disk unavailable"):
        await client.post(
            "/api/auth/initial-setup",
            json={"username": "newadmin", "password": "newpass123", "enable_auth": True},
        )

    assert settings.auth.enabled is False
    assert settings.auth.username == "admin"
    assert settings.auth.password_hash is None
    assert settings.auth.initial_setup_complete is False


@pytest.mark.asyncio
async def test_initial_setup_cannot_take_over_completed_auth_disabled_install(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.auth.password_hash = None
    settings.auth.initial_setup_complete = True

    response = await client.post(
        "/api/auth/initial-setup", json={"username": "attacker", "password": "newpass123", "enable_auth": True}
    )

    assert response.status_code == 403
    assert "already completed" in response.json()["detail"].lower()
    assert settings.auth.password_hash is None


@pytest.mark.asyncio
async def test_logout_requires_auth(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = await client.post("/api/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_valid_token(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    login_response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
    token = login_response.json()["access_token"]

    response = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    login_response = await client.post("/api/auth/login", json={"username": "admin", "password": "testpass123"})
    token = login_response.json()["access_token"]

    response = await client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] is True
    assert data["username"] == "admin"
