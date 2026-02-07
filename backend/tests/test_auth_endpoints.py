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
    original_public = settings.public_access.enabled

    yield

    settings.auth.enabled = original_enabled
    settings.auth.password_hash = original_hash
    settings.auth.username = original_username
    settings.public_access.enabled = original_public


@pytest.mark.asyncio
async def test_auth_status_no_auth(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is False
    assert data["public_access_enabled"] is False
    assert data["needs_initial_setup"] is False


@pytest.mark.asyncio
async def test_auth_status_needs_setup(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.password_hash = None

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] is True
    assert data["needs_initial_setup"] is True


@pytest.mark.asyncio
async def test_auth_status_public_enabled(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True

    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["public_access_enabled"] is True


@pytest.mark.asyncio
async def test_login_success(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })
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

    response = await client.post("/api/auth/login", json={
        "username": "wronguser",
        "password": "testpass123"
    })
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_invalid_password(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrongpass"
    })
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_auth_disabled(client: httpx.AsyncClient):
    settings.auth.enabled = False

    response = await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })
    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_no_password_set(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.password_hash = None

    response = await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })
    assert response.status_code == 500
    assert "not configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_initial_setup_success(client: httpx.AsyncClient):
    settings.auth.password_hash = None

    response = await client.post("/api/auth/initial-setup", json={
        "username": "newadmin",
        "password": "newpass123",
        "enable_auth": True
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Setup completed successfully"


@pytest.mark.asyncio
async def test_initial_setup_already_configured(client: httpx.AsyncClient):
    settings.auth.password_hash = hash_password("existing")

    response = await client.post("/api/auth/initial-setup", json={
        "username": "admin",
        "password": "newpass123",
        "enable_auth": True
    })
    assert response.status_code == 403
    assert "already configured" in response.json()["detail"]


@pytest.mark.asyncio
async def test_initial_setup_skip_auth(client: httpx.AsyncClient):
    settings.auth.password_hash = None

    response = await client.post("/api/auth/initial-setup", json={
        "username": "admin",
        "password": None,
        "enable_auth": False
    })
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_logout(client: httpx.AsyncClient):
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    login_response = await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })
    token = login_response.json()["access_token"]

    response = await client.get("/api/auth/status", headers={
        "Authorization": f"Bearer {token}"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] is True
    assert data["username"] == "admin"
