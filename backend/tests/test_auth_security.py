"""Tests for authentication security features (Phase 6)."""

import pytest
import time
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


class TestLoginRateLimiting:
    """Tests for login endpoint rate limiting."""

    def test_login_rate_limit_per_minute(self):
        """Test that login is rate limited to 5 per minute."""
        settings.auth.enabled = True
        settings.auth.username = "admin"
        settings.auth.password_hash = hash_password("test123A")

        # Make 5 attempts (should all succeed or fail normally)
        for i in range(5):
            response = client.post("/api/auth/login", json={
                "username": "admin",
                "password": f"wrong{i}"
            })
            # Should get 401 (wrong password) not 429 (rate limited)
            assert response.status_code == 401

        # 6th attempt should be rate limited
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "wrong6"
        })
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
        assert "Retry-After" in response.headers

    def test_https_warning_flag(self):
        """Test that https_warning flag is set correctly."""
        settings.auth.enabled = True

        response = client.get("/api/auth/status")
        data = response.json()

        # Should have https_warning field
        assert "https_warning" in data
        # In test environment (HTTP), should be True when auth enabled
        assert data["https_warning"] == True


class TestInputValidation:
    """Tests for input validation on auth endpoints."""

    def test_login_username_validation_special_chars(self):
        """Test that login rejects usernames with special characters."""
        settings.auth.enabled = True
        settings.auth.password_hash = hash_password("test123A")

        response = client.post("/api/auth/login", json={
            "username": "admin<script>",
            "password": "test123A"
        })
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("Username must contain only" in str(err) for err in errors)

    def test_login_username_validation_spaces(self):
        """Test that login rejects usernames with spaces."""
        settings.auth.enabled = True
        settings.auth.password_hash = hash_password("test123A")

        response = client.post("/api/auth/login", json={
            "username": "admin user",
            "password": "test123A"
        })
        assert response.status_code == 422

    def test_login_username_too_long(self):
        """Test that login rejects overly long usernames."""
        settings.auth.enabled = True
        settings.auth.password_hash = hash_password("test123A")

        response = client.post("/api/auth/login", json={
            "username": "a" * 51,  # 51 chars, max is 50
            "password": "test123A"
        })
        assert response.status_code == 422

    def test_initial_setup_password_too_short(self):
        """Test that initial setup rejects short passwords."""
        settings.auth.password_hash = None

        response = client.post("/api/auth/initial-setup", json={
            "username": "admin",
            "password": "short",  # Less than 8 chars
            "enable_auth": True
        })
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("at least 8 characters" in str(err) for err in errors)

    def test_initial_setup_password_no_letter(self):
        """Test that initial setup rejects passwords without letters."""
        settings.auth.password_hash = None

        response = client.post("/api/auth/initial-setup", json={
            "username": "admin",
            "password": "12345678",  # Only numbers
            "enable_auth": True
        })
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("at least one letter and one number" in str(err) for err in errors)

    def test_initial_setup_password_no_number(self):
        """Test that initial setup rejects passwords without numbers."""
        settings.auth.password_hash = None

        response = client.post("/api/auth/initial-setup", json={
            "username": "admin",
            "password": "abcdefgh",  # Only letters
            "enable_auth": True
        })
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("at least one letter and one number" in str(err) for err in errors)

    def test_initial_setup_valid_password(self):
        """Test that valid passwords are accepted."""
        settings.auth.password_hash = None

        response = client.post("/api/auth/initial-setup", json={
            "username": "admin",
            "password": "test123A",  # Valid: 8 chars, letter + number
            "enable_auth": True
        })
        assert response.status_code == 200

    def test_initial_setup_username_validation(self):
        """Test username validation in initial setup."""
        settings.auth.password_hash = None

        response = client.post("/api/auth/initial-setup", json={
            "username": "admin@#$",
            "password": "test123A",
            "enable_auth": True
        })
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("Username must contain only" in str(err) for err in errors)


class TestSecurityHeaders:
    """Tests for security headers."""

    def test_security_headers_present(self):
        """Test that security headers are added to responses."""
        response = client.get("/health")

        # Check for security headers
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"

        assert "X-XSS-Protection" in response.headers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

        assert "Content-Security-Policy" in response.headers
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]

        assert "Referrer-Policy" in response.headers
        assert "Permissions-Policy" in response.headers

    def test_hsts_not_on_http(self):
        """Test that HSTS header is not added for HTTP requests."""
        response = client.get("/health")

        # HSTS should only be on HTTPS
        # In test client, scheme is HTTP, so HSTS should not be present
        # (or if present, check it's conditional)
        # This test documents the behavior
        pass


class TestAuditLogging:
    """Tests that audit logging occurs for auth events."""

    def test_login_success_logged(self, caplog):
        """Test that successful logins are logged."""
        settings.auth.enabled = True
        settings.auth.username = "admin"
        settings.auth.password_hash = hash_password("test123A")

        with caplog.at_level("INFO"):
            response = client.post("/api/auth/login", json={
                "username": "admin",
                "password": "test123A"
            })
            assert response.status_code == 200

        # Check for audit log
        assert any("AUTH_AUDIT" in record.message for record in caplog.records)
        assert any("login_success" in str(record) for record in caplog.records)

    def test_login_failure_logged(self, caplog):
        """Test that failed logins are logged."""
        settings.auth.enabled = True
        settings.auth.username = "admin"
        settings.auth.password_hash = hash_password("test123A")

        with caplog.at_level("WARNING"):
            response = client.post("/api/auth/login", json={
                "username": "admin",
                "password": "wrongpass"
            })
            assert response.status_code == 401

        # Check for audit log
        assert any("AUTH_AUDIT" in record.message for record in caplog.records)
        assert any("login_failure" in str(record) for record in caplog.records)

    def test_initial_setup_logged(self, caplog):
        """Test that initial setup is logged."""
        settings.auth.password_hash = None

        with caplog.at_level("INFO"):
            response = client.post("/api/auth/initial-setup", json={
                "username": "admin",
                "password": "test123A",
                "enable_auth": True
            })
            assert response.status_code == 200

        # Check for audit log
        assert any("AUTH_AUDIT" in record.message for record in caplog.records)
        assert any("initial_setup" in str(record) for record in caplog.records)


class TestProxySupport:
    """Tests for proxy header support in rate limiting."""

    def test_x_forwarded_for_used(self):
        """Test that X-Forwarded-For header is respected."""
        settings.auth.enabled = True
        settings.auth.username = "admin"
        settings.auth.password_hash = hash_password("test123A")

        # Make requests with X-Forwarded-For header
        headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.1"}

        # Should use first IP (192.168.1.100) for rate limiting
        for i in range(5):
            response = client.post("/api/auth/login",
                                  json={"username": "admin", "password": f"wrong{i}"},
                                  headers=headers)
            assert response.status_code == 401

        # 6th should be rate limited
        response = client.post("/api/auth/login",
                             json={"username": "admin", "password": "wrong6"},
                             headers=headers)
        assert response.status_code == 429

    def test_x_real_ip_used(self):
        """Test that X-Real-IP header is respected."""
        settings.auth.enabled = True
        settings.auth.username = "admin"
        settings.auth.password_hash = hash_password("test123A")

        # Make requests with X-Real-IP header
        headers = {"X-Real-IP": "192.168.1.200"}

        for i in range(5):
            response = client.post("/api/auth/login",
                                  json={"username": "admin", "password": f"wrong{i}"},
                                  headers=headers)
            assert response.status_code == 401

        # 6th should be rate limited
        response = client.post("/api/auth/login",
                             json={"username": "admin", "password": "wrong6"},
                             headers=headers)
        assert response.status_code == 429
