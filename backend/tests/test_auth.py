"""Tests for authentication module."""

import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token,
    AuthLevel,
    AuthContext
)


def test_password_hashing():
    """Test bcrypt hashing."""
    password = "test123"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_password_hashing_different_hashes():
    """Test that same password produces different hashes (salt)."""
    password = "test123"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)


def test_jwt_token_creation():
    """Test JWT token creation and verification."""
    token = create_access_token("admin", AuthLevel.OWNER)

    token_data = verify_token(token)
    assert token_data.username == "admin"
    assert token_data.auth_level == AuthLevel.OWNER


def test_expired_token():
    """Test that expired tokens are rejected."""
    import jwt
    from app.config import settings

    payload = {
        "username": "admin",
        "auth_level": AuthLevel.OWNER,
        "exp": datetime.utcnow() - timedelta(hours=1)  # Already expired
    }
    expired_token = jwt.encode(payload, settings.auth.session_secret, algorithm="HS256")

    with pytest.raises(HTTPException) as exc:
        verify_token(expired_token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_invalid_token():
    """Test that invalid tokens are rejected."""
    with pytest.raises(HTTPException) as exc:
        verify_token("invalid.token.here")
    assert exc.value.status_code == 401


def test_auth_context_owner():
    """Test AuthContext for owner."""
    context = AuthContext(auth_level=AuthLevel.OWNER, username="admin")

    assert context.is_owner
    assert context.is_authenticated
    assert context.auth_level == AuthLevel.OWNER
    assert context.username == "admin"


def test_auth_context_guest():
    """Test AuthContext for guest."""
    context = AuthContext(auth_level=AuthLevel.GUEST)

    assert not context.is_owner
    assert not context.is_authenticated
    assert context.auth_level == AuthLevel.GUEST
    assert context.username is None


def test_token_contains_expiry():
    """Test that token includes expiry time."""
    token = create_access_token("testuser", AuthLevel.OWNER)
    token_data = verify_token(token)

    assert token_data.exp > datetime.utcnow()
    assert token_data.exp < datetime.utcnow() + timedelta(hours=169)  # 7 days + buffer
