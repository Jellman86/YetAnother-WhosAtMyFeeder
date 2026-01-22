"""Integration tests for authentication endpoints."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.auth import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_auth_config():
    """Reset auth config before each test."""
    original_enabled = settings.auth.enabled
    original_hash = settings.auth.password_hash
    original_username = settings.auth.username

    yield

    # Restore original settings
    settings.auth.enabled = original_enabled
    settings.auth.password_hash = original_hash
    settings.auth.username = original_username


def test_auth_status_no_auth():
    """Test auth status when auth is disabled."""
    settings.auth.enabled = False
    settings.public_access.enabled = False

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] == False
    assert data["public_access_enabled"] == False
    assert data["needs_initial_setup"] == False


def test_auth_status_needs_setup():
    """Test auth status when password not set."""
    settings.auth.enabled = True
    settings.auth.password_hash = None

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    data = response.json()
    assert data["auth_required"] == True
    assert data["needs_initial_setup"] == True


def test_auth_status_public_enabled():
    """Test auth status with public access enabled."""
    settings.auth.enabled = True
    settings.public_access.enabled = True

    response = client.get("/api/auth/status")

    assert response.status_code == 200
    data = response.json()
    assert data["public_access_enabled"] == True


def test_login_success():
    """Test successful login."""
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["username"] == "admin"
    assert data["token_type"] == "bearer"
    assert data["expires_in_hours"] == 168


def test_login_invalid_username():
    """Test login with wrong username."""
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = client.post("/api/auth/login", json={
        "username": "wronguser",
        "password": "testpass123"
    })

    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


def test_login_invalid_password():
    """Test login with wrong password."""
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrongpass"
    })

    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


def test_login_auth_disabled():
    """Test login when auth is disabled."""
    settings.auth.enabled = False

    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })

    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"]


def test_login_no_password_set():
    """Test login when no password configured."""
    settings.auth.enabled = True
    settings.auth.password_hash = None

    response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })

    assert response.status_code == 500
    assert "not configured" in response.json()["detail"]


def test_initial_setup_success():
    """Test initial password setup."""
    settings.auth.password_hash = None

    response = client.post("/api/auth/initial-setup", json={
        "username": "newadmin",
        "password": "newpass123",
        "enable_auth": True
    })

    assert response.status_code == 200
    assert response.json()["message"] == "Setup completed successfully"


def test_initial_setup_already_configured():
    """Test that initial setup fails if password already set."""
    settings.auth.password_hash = hash_password("existing")

    response = client.post("/api/auth/initial-setup", json={
        "username": "admin",
        "password": "newpass123",
        "enable_auth": True
    })

    assert response.status_code == 403
    assert "already configured" in response.json()["detail"]


def test_initial_setup_skip_auth():
    """Test skipping authentication during setup."""
    settings.auth.password_hash = None

    response = client.post("/api/auth/initial-setup", json={
        "username": "admin",
        "password": None,
        "enable_auth": False
    })

    assert response.status_code == 200


def test_logout():
    """Test logout endpoint."""
    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert "message" in response.json()


def test_protected_endpoint_with_valid_token():
    """Test accessing endpoint with valid token."""
    # Setup auth
    settings.auth.enabled = True
    settings.auth.username = "admin"
    settings.auth.password_hash = hash_password("testpass123")

    # Login to get token
    login_response = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "testpass123"
    })
    token = login_response.json()["access_token"]

    # Access auth status with token
    response = client.get("/api/auth/status", headers={
        "Authorization": f"Bearer {token}"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["is_authenticated"] == True
    assert data["username"] == "admin"
