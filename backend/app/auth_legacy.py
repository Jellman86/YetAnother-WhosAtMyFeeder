from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery, HTTPAuthorizationCredentials
import secrets
import structlog

from app.auth import AuthContext, AuthLevel, get_auth_context, security
from app.config import settings

log = structlog.get_logger()

# Legacy API key authentication (DEPRECATED - will be removed in v2.9.0)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


async def verify_api_key_legacy(
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query)
) -> bool:
    """
    DEPRECATED: Legacy API key authentication.

    This function is maintained for backward compatibility.
    New installations should use the JWT auth system.

    Will be removed in v2.9.0 (approximately 3 months).
    """
    legacy_api_key = settings.api_key

    if not legacy_api_key:
        return False  # No legacy key configured

    api_key = header_key or query_key
    if not api_key:
        return False

    if secrets.compare_digest(api_key, legacy_api_key):
        log.warning(
            "Using deprecated API key authentication",
            notice="Migrate to password-based auth in Settings. "
                   "API key support will be removed in v2.9.0"
        )
        return True

    return False


async def get_auth_context_with_legacy(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query)
) -> AuthContext:
    """
    Get auth context with legacy API key fallback.

    Priority:
    1. New JWT token authentication
    2. Legacy API key (deprecated)
    3. Public access (if enabled)
    4. Deny
    """
    # Try new auth first
    try:
        return await get_auth_context(request, credentials)
    except HTTPException as e:
        # New auth failed - try legacy
        if await verify_api_key_legacy(header_key, query_key):
            return AuthContext(auth_level=AuthLevel.OWNER, username="legacy_api_key")

        # Both failed - re-raise original exception
        raise e
