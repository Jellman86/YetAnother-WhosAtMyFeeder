"""Authentication and authorization module for YA-WAMF.

Provides JWT-based authentication with bcrypt password hashing.
Supports both owner (full access) and guest (public read-only) auth levels.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, Request, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt
from pydantic import BaseModel
import structlog

log = structlog.get_logger()
security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    """JWT token payload."""
    username: str
    exp: datetime
    auth_level: str  # "owner" or "guest"


class AuthLevel:
    """Authorization levels."""
    OWNER = "owner"
    GUEST = "guest"


class AuthContext:
    """Request authentication context.

    Attached to request.state by get_auth_context() dependency.
    """

    def __init__(self, auth_level: str, username: Optional[str] = None):
        self.auth_level = auth_level
        self.username = username
        self.is_owner = auth_level == AuthLevel.OWNER
        self.is_authenticated = auth_level == AuthLevel.OWNER

    def __repr__(self):
        return f"AuthContext(level={self.auth_level}, user={self.username})"


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash to check against

    Returns:
        True if password matches hash
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        log.error("Password verification failed", error=str(e))
        return False


def create_access_token(username: str, auth_level: str = AuthLevel.OWNER) -> str:
    """Create a JWT access token.

    Args:
        username: Username to encode in token
        auth_level: "owner" or "guest"

    Returns:
        Encoded JWT token string
    """
    from app.config import settings

    expiry = datetime.now(timezone.utc) + timedelta(hours=settings.auth.session_expiry_hours)
    payload = {
        "username": username,
        "auth_level": auth_level,
        "exp": expiry,
        "iat": datetime.now(timezone.utc)
    }

    return jwt.encode(payload, settings.auth.session_secret, algorithm="HS256")


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token data

    Raises:
        HTTPException: If token is invalid or expired
    """
    from app.config import settings

    try:
        payload = jwt.decode(token, settings.auth.session_secret, algorithms=["HS256"])
        token_data = TokenData(**payload)
        if token_data.exp.tzinfo is not None:
            token_data.exp = token_data.exp.replace(tzinfo=None)
        return token_data
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_auth_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthContext:
    """Extract authentication context from request.

    Priority:
    1. Valid JWT token -> owner access
    2. Public access enabled -> guest access
    3. Auth disabled completely -> owner access
    4. Auth required but no token -> 401 error

    Args:
        request: FastAPI request
        credentials: Optional Bearer token credentials

    Returns:
        AuthContext with auth_level set to "owner" or "guest"

    Raises:
        HTTPException: If auth required and no valid token provided
    """
    from app.config import settings

    # Try to extract token from Bearer header or Authorization header
    token = None
    if credentials:
        token = credentials.credentials
    elif "Authorization" in request.headers:
        auth_header = request.headers["Authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    # If token provided, verify it
    if token:
        try:
            token_data = verify_token(token)
            context = AuthContext(
                auth_level=token_data.auth_level,
                username=token_data.username
            )
            log.debug("Authenticated request", username=token_data.username, level=token_data.auth_level)
            return context
        except HTTPException:
            # Invalid token - fall through to public access check
            log.debug("Invalid token provided, checking public access")
            pass

    # No valid token - check if public access allowed
    if settings.public_access.enabled:
        log.debug("Request using public guest access", path=request.url.path)
        return AuthContext(auth_level=AuthLevel.GUEST)

    # Check if auth is disabled completely (backward compatibility)
    if not settings.auth.enabled:
        log.debug("Auth disabled - granting owner access")
        return AuthContext(auth_level=AuthLevel.OWNER, username="unauthenticated")

    # Public access disabled and no valid token - require auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"}
    )


def require_owner(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Dependency that requires owner-level authentication.

    Use this on endpoints that need full privileges:
    - Settings management
    - Deletion operations
    - Backfill
    - Model management

    Args:
        auth: Authentication context from get_auth_context

    Returns:
        AuthContext if user is owner

    Raises:
        HTTPException: If user is not owner

    Example:
        @router.delete("/events/{event_id}")
        async def delete_event(
            event_id: int,
            auth: AuthContext = Depends(require_owner)
        ):
            # Only owners can reach here
            ...
    """
    if not auth.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner privileges required for this operation"
        )
    return auth
