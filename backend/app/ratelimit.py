from __future__ import annotations

import secrets
from typing import Any, Callable

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth import AuthLevel, verify_token
from app.config import settings


def get_real_client_ip(request: Request) -> str:
    """
    Get real client IP address, handling proxies and load balancers.

    Checks headers in order of priority:
    1. X-Forwarded-For (standard proxy header, takes first IP)
    2. X-Real-IP (alternative proxy header)
    3. Remote address (direct connection)

    Returns the IP address as a string.
    """
    # Check X-Forwarded-For header (can have multiple IPs)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to remote address
    return get_remote_address(request)


limiter = Limiter(key_func=get_real_client_ip, default_limits=["100/minute"])


def _guest_limit_value(*_args: Any, **_kwargs: Any) -> str:
    return f"{settings.public_access.rate_limit_per_minute}/minute"


def _is_owner_request(request: Request) -> bool:
    if not settings.auth.enabled:
        return True

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.query_params.get("token")

    if token:
        try:
            token_data = verify_token(token)
            if token_data.auth_level == AuthLevel.OWNER:
                return True
        except Exception:
            pass

    legacy_key = settings.api_key
    if legacy_key:
        header_key = request.headers.get("X-API-Key")
        query_key = request.query_params.get("api_key")
        api_key = header_key or query_key
        if api_key and secrets.compare_digest(api_key, legacy_key):
            return True

    return False


def _rate_limit_key(request: Request) -> str:
    role = "owner" if _is_owner_request(request) else "guest"
    return f"{role}:{get_real_client_ip(request)}"


def _limit_for_key(key: str) -> str:
    if key.startswith("owner:"):
        return "1000/minute"
    return _guest_limit_value()


def guest_rate_limit() -> Callable:
    return limiter.limit(_limit_for_key, key_func=_rate_limit_key)


def login_rate_limit() -> Callable:
    """
    Strict rate limiting for login endpoint to prevent brute force attacks.

    Limits:
    - 5 attempts per minute per IP
    - 20 attempts per hour per IP

    This applies regardless of authentication status since login
    attempts come from unauthenticated users.

    Uses get_real_client_ip to work correctly behind proxies/load balancers.
    """
    return limiter.limit("5/minute;20/hour", key_func=get_real_client_ip)
