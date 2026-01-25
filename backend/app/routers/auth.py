"""Authentication endpoints for YA-WAMF."""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import structlog
import secrets
import os
import re

from app.auth import (
    verify_password,
    create_access_token,
    hash_password,
    AuthLevel,
    verify_token
)
from app.config import settings
from app.ratelimit import login_rate_limit

router = APIRouter()
log = structlog.get_logger()


class LoginRequest(BaseModel):
    """Login credentials."""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username contains only safe characters."""
        # Allow alphanumeric, underscore, hyphen, period
        if not re.match(r'^[a-zA-Z0-9_.-]+$', v):
            raise ValueError("Username must contain only letters, numbers, underscore, hyphen, and period")
        return v.strip()


class LoginResponse(BaseModel):
    """Login response with access token."""
    access_token: str
    token_type: str = "bearer"
    username: str
    expires_in_hours: int


class AuthStatusResponse(BaseModel):
    """Current authentication status."""
    auth_required: bool
    public_access_enabled: bool
    is_authenticated: bool
    birdnet_enabled: bool = False
    llm_enabled: bool = False
    username: Optional[str] = None
    needs_initial_setup: bool = False
    https_warning: bool = False  # True if auth enabled over HTTP


class InitialPasswordRequest(BaseModel):
    """Initial password setup request."""
    username: str = Field(..., min_length=1, max_length=50)
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    enable_auth: bool = True

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username contains only safe characters."""
        if not re.match(r'^[a-zA-Z0-9_.-]+$', v):
            raise ValueError("Username must contain only letters, numbers, underscore, hyphen, and period")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength."""
        if v is None:
            return v

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")

        # Check for basic complexity (at least one letter and one number)
        if not re.search(r'[A-Za-z]', v) or not re.search(r'\d', v):
            raise ValueError("Password must contain at least one letter and one number")

        return v


@router.post("/auth/login", response_model=LoginResponse)
@login_rate_limit()
async def login(request: Request, login_data: LoginRequest):
    """Authenticate user and return JWT token.

    Rate limited to 5 attempts per minute, 20 per hour per IP.

    Returns:
        JWT access token for authenticated requests

    Raises:
        HTTPException: If credentials invalid or auth not configured
    """
    if not settings.auth.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is not enabled"
        )

    if not settings.auth.password_hash:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication not configured - please complete initial setup"
        )

    # Verify username
    if login_data.username != settings.auth.username:
        log.warning(
            "AUTH_AUDIT: Login failed - invalid username",
            username=login_data.username,
            event_type="login_failure",
            reason="invalid_username"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Verify password
    if not verify_password(login_data.password, settings.auth.password_hash):
        log.warning(
            "AUTH_AUDIT: Login failed - invalid password",
            username=login_data.username,
            event_type="login_failure",
            reason="invalid_password"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Create token
    token = create_access_token(login_data.username, AuthLevel.OWNER)

    log.info(
        "AUTH_AUDIT: Login successful",
        username=login_data.username,
        event_type="login_success"
    )

    return LoginResponse(
        access_token=token,
        username=login_data.username,
        expires_in_hours=settings.auth.session_expiry_hours
    )


@router.get("/auth/status", response_model=AuthStatusResponse)
async def get_auth_status(request: Request):
    """Get current authentication status and public access settings.

    Used by frontend to determine if login is required.
    """
    auth_level: Optional[str] = None
    username: Optional[str] = None

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    if token:
        try:
            token_data = verify_token(token)
            auth_level = token_data.auth_level
            username = token_data.username
        except HTTPException:
            pass

    if not auth_level:
        legacy_key = settings.api_key
        if legacy_key:
            header_key = request.headers.get("X-API-Key")
            query_key = request.query_params.get("api_key")
            api_key = header_key or query_key
            if api_key and secrets.compare_digest(api_key, legacy_key):
                auth_level = AuthLevel.OWNER
                username = "legacy_api_key"

    needs_setup = settings.auth.enabled and settings.auth.password_hash is None

    # Optional proxy header debug logging (rate-limited)
    if os.getenv("DEBUG_PROXY_HEADERS", "").lower() == "true":
        now = datetime.now()
        last_logged = getattr(request.app.state, "_last_proxy_debug_detail", None)
        if not last_logged or (now - last_logged).total_seconds() > 60:
            request.app.state._last_proxy_debug_detail = now
            log.info(
                "Proxy header debug",
                scheme=request.url.scheme,
                x_forwarded_proto=request.headers.get("x-forwarded-proto"),
                x_forwarded_for=request.headers.get("x-forwarded-for"),
                x_forwarded_host=request.headers.get("x-forwarded-host"),
                cf_visitor=request.headers.get("cf-visitor"),
                host=request.headers.get("host"),
                client=request.client.host if request.client else None,
                trusted_proxy_hosts=settings.system.trusted_proxy_hosts
            )

    # Check if using HTTP with auth enabled (security warning)
    https_warning = settings.auth.enabled and request.url.scheme != "https"
    if https_warning:
        now = datetime.now()
        last_logged = getattr(request.app.state, "_last_https_warning_detail", None)
        if not last_logged or (now - last_logged).total_seconds() > 60:
            request.app.state._last_https_warning_detail = now
            log.warning(
                "Auth over HTTP detected",
                scheme=request.url.scheme,
                x_forwarded_proto=request.headers.get("x-forwarded-proto"),
                x_forwarded_for=request.headers.get("x-forwarded-for"),
                x_forwarded_host=request.headers.get("x-forwarded-host"),
                host=request.headers.get("host"),
                client=request.client.host if request.client else None,
                trusted_proxy_hosts=settings.system.trusted_proxy_hosts
            )

    return AuthStatusResponse(
        auth_required=settings.auth.enabled,
        public_access_enabled=settings.public_access.enabled,
        is_authenticated=auth_level == AuthLevel.OWNER,
        birdnet_enabled=settings.frigate.birdnet_enabled,
        llm_enabled=settings.llm.enabled,
        username=username if auth_level == AuthLevel.OWNER else None,
        needs_initial_setup=needs_setup,
        https_warning=https_warning
    )


@router.post("/auth/initial-setup")
async def set_initial_password(request: InitialPasswordRequest):
    """Set initial password for first-run setup.

    Can only be called when auth is disabled OR no password is set.
    This prevents unauthorized password changes.

    Args:
        request: Initial password setup request

    Returns:
        Success message

    Raises:
        HTTPException: If setup already completed or invalid request
    """
    # Security check: Only allow if no password currently set
    if settings.auth.password_hash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password already configured. Use Settings to change password."
        )

    # Update config
    if request.enable_auth and request.password:
        settings.auth.username = request.username
        settings.auth.password_hash = hash_password(request.password)
        settings.auth.enabled = True
    else:
        settings.auth.enabled = False

    # Save to config.json
    await settings.save()

    log.info(
        "AUTH_AUDIT: Initial setup completed",
        auth_enabled=settings.auth.enabled,
        username=request.username if request.enable_auth else None,
        event_type="initial_setup"
    )

    return {"message": "Setup completed successfully"}


@router.post("/auth/logout")
async def logout():
    """Logout endpoint (client-side token deletion).

    Note: JWT tokens cannot be invalidated server-side without a blacklist.
    Client should delete token from storage.
    """
    return {"message": "Logged out successfully. Please clear your token."}
