"""Authentication endpoints for YA-WAMF."""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional
import structlog
import secrets

from app.auth import (
    verify_password,
    create_access_token,
    hash_password,
    AuthLevel,
    verify_token
)
from app.config import settings

router = APIRouter()
log = structlog.get_logger()


class LoginRequest(BaseModel):
    """Login credentials."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


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
    username: Optional[str] = None
    needs_initial_setup: bool = False


class InitialPasswordRequest(BaseModel):
    """Initial password setup request."""
    username: str = Field(..., min_length=1, max_length=100)
    password: Optional[str] = Field(None, min_length=8)
    enable_auth: bool = True


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user and return JWT token.

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
    if request.username != settings.auth.username:
        log.warning("Login attempt with invalid username", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Verify password
    if not verify_password(request.password, settings.auth.password_hash):
        log.warning("Login attempt with invalid password", username=request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Create token
    token = create_access_token(request.username, AuthLevel.OWNER)

    log.info("Successful login", username=request.username)

    return LoginResponse(
        access_token=token,
        username=request.username,
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

    needs_setup = settings.auth.password_hash is None

    return AuthStatusResponse(
        auth_required=settings.auth.enabled,
        public_access_enabled=settings.public_access.enabled,
        is_authenticated=auth_level == AuthLevel.OWNER,
        username=username if auth_level == AuthLevel.OWNER else None,
        needs_initial_setup=needs_setup
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

    log.info("Initial setup completed",
             auth_enabled=settings.auth.enabled,
             username=request.username if request.enable_auth else None)

    return {"message": "Setup completed successfully"}


@router.post("/auth/logout")
async def logout():
    """Logout endpoint (client-side token deletion).

    Note: JWT tokens cannot be invalidated server-side without a blacklist.
    Client should delete token from storage.
    """
    return {"message": "Logged out successfully. Please clear your token."}
