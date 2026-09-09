"""Authentication and authorization module for YA-WAMF.

Provides JWT-based authentication with bcrypt password hashing.
Supports both owner (full access) and guest (public read-only) auth levels.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import re
import secrets
from dataclasses import dataclass

from fastapi import Response
from fastapi import HTTPException, Request, status, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader, APIKeyQuery
import jwt
import bcrypt
from pydantic import BaseModel
import structlog

log = structlog.get_logger()
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

BCRYPT_MAX_PASSWORD_BYTES = 72
BCRYPT_PASSWORD_MAX_BYTES_MESSAGE = "Password must use 72 UTF-8 bytes or fewer"


def validate_bcrypt_password_length(password: str) -> str:
    """Return a password that fits bcrypt's byte limit or raise a safe validation error."""
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(BCRYPT_PASSWORD_MAX_BYTES_MESSAGE)
    return password


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
    password_bytes = validate_bcrypt_password_length(password).encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash to check against

    Returns:
        True if password matches hash
    """
    try:
        # bcrypt 4 silently truncated at 72 bytes. Preserve that behaviour only for
        # verification so existing installations cannot be locked out after upgrading.
        password_bytes = password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
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
    payload = {"username": username, "auth_level": auth_level, "exp": expiry, "iat": datetime.now(timezone.utc)}

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
        return token_data
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


SESSION_COOKIE = "yawamf_session"

# The only routes a cookie may authorise. `<img>`, `<video>` and `EventSource`
# cannot send headers, so these carry the session in a cookie the browser adds
# by itself. Everything else keeps requiring a Bearer header, which a cross-site
# page cannot forge, so the cookie adds no CSRF surface. Read-only methods only.
_COOKIE_METHODS = frozenset({"GET", "HEAD"})
_COOKIE_ROUTES = (
    re.compile(
        r"^/api/frigate/[^/]+/(snapshot\.jpg|thumbnail\.jpg|clip\.mp4|recording-clip\.mp4|clip-thumbnails\.(vtt|jpg))$"
    ),
    re.compile(r"^/api/frigate/[^/]+/snapshot/(original\.jpg|candidates/[^/]+/(image|thumbnail)\.jpg)$"),
    re.compile(r"^/api/frigate/camera/[^/]+/latest\.jpg$"),
    re.compile(r"^/api/audio/(spectrogram|clip)/[^/]+$"),
    re.compile(r"^/api/sse$"),
)


def session_cookie_allowed(request: Request) -> bool:
    """Whether this request is one the session cookie is permitted to authorise."""
    if request.method not in _COOKIE_METHODS:
        return False
    path = request.url.path
    return any(route.match(path) for route in _COOKIE_ROUTES)


def session_cookie_token(request: Request) -> Optional[TokenData]:
    """The session carried in the cookie, or None when absent, expired or forged."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return verify_token(raw)
    except HTTPException:
        return None


def set_session_cookie(response: Response, token: str, request: Request) -> None:
    """Attach the session to the browser as an HttpOnly cookie scoped to /api.

    ``Secure`` follows the request scheme (behind a trusted proxy that is the
    forwarded one), so a plain-HTTP LAN install still receives the cookie.
    """
    from app.config import settings

    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(settings.auth.session_expiry_hours) * 3600,
        path="/api",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api")


async def get_auth_context(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
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

    # Try to extract token from Bearer header, Authorization header, or query param
    token = None
    if credentials:
        token = credentials.credentials
    elif "Authorization" in request.headers:
        auth_header = request.headers["Authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        token = request.query_params.get("token")

    # If token provided, verify it
    if token:
        try:
            token_data = verify_token(token)
            context = AuthContext(auth_level=token_data.auth_level, username=token_data.username)
            log.debug("Authenticated request", username=token_data.username, level=token_data.auth_level)
            return context
        except HTTPException:
            # Invalid token - fall through to public access check
            log.debug("Invalid token provided, checking public access")
            pass

    # A session cookie may authorise read-only media and the stream, and nothing else.
    if session_cookie_allowed(request):
        cookie_session = session_cookie_token(request)
        if cookie_session is not None:
            log.debug("Authenticated media request via session cookie", username=cookie_session.username)
            return AuthContext(auth_level=cookie_session.auth_level, username=cookie_session.username)

    # Check if auth is disabled completely (backward compatibility).
    # Auth-disabled mode must remain owner-equivalent even when public access
    # is enabled; otherwise protected settings routes become unreachable.
    if not settings.auth.enabled:
        log.debug("Auth disabled - granting owner access")
        return AuthContext(auth_level=AuthLevel.OWNER, username="unauthenticated")

    # No valid token - check if public access allowed
    if settings.public_access.enabled:
        log.debug("Request using public guest access", path=request.url.path)
        return AuthContext(auth_level=AuthLevel.GUEST)

    # Public access disabled and no valid token - require auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def verify_api_key_legacy(
    header_key: str = Security(api_key_header), query_key: str = Security(api_key_query)
) -> bool:
    """Validate legacy API key credentials for backward compatibility."""
    from app.config import settings

    legacy_api_key = settings.api_key
    if not legacy_api_key:
        return False

    api_key = header_key or query_key
    if not api_key:
        return False

    if secrets.compare_digest(api_key, legacy_api_key):
        log.warning(
            "Using deprecated API key authentication",
            notice=("Migrate to password-based auth in Settings. API key support will be removed in v3.0"),
        )
        return True

    return False


async def get_auth_context_with_legacy(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    header_key: str = Security(api_key_header),
    query_key: str = Security(api_key_query),
) -> AuthContext:
    """Return auth context with deprecated API-key fallback support."""
    try:
        return await get_auth_context(request, credentials)
    except HTTPException as exc:
        if await verify_api_key_legacy(header_key, query_key):
            return AuthContext(auth_level=AuthLevel.OWNER, username="legacy_api_key")
        raise exc


@dataclass(frozen=True)
class StreamAuth:
    """Who opened the live stream, and when their session would have ended."""

    context: AuthContext
    session_exp: Optional[datetime]


async def get_stream_auth_context(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    header_key: Optional[str] = Security(api_key_header),
    query_key: Optional[str] = Security(api_key_query),
) -> StreamAuth:
    """Resolve who may open the live stream.

    Accepted, in order: a Bearer header (for clients that can send one), a
    single-use ``?ticket=`` from ``POST /api/auth/stream-ticket``, then the
    same fallbacks as every other route (auth disabled, public access, the
    deprecated API key). The session token is deliberately *not* read from the
    query string: nginx logs the full request line to its error log while the
    upstream is starting, and a token logged there is a week of owner access.
    """
    from app.config import settings
    from app.services.stream_tickets import stream_tickets

    token = None
    if credentials:
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token:
        try:
            token_data = verify_token(token)
            return StreamAuth(
                context=AuthContext(auth_level=token_data.auth_level, username=token_data.username),
                session_exp=token_data.exp,
            )
        except HTTPException:
            log.debug("Invalid bearer token on stream, checking ticket and public access")

    cookie_session = session_cookie_token(request)
    if cookie_session is not None:
        return StreamAuth(
            context=AuthContext(auth_level=cookie_session.auth_level, username=cookie_session.username),
            session_exp=cookie_session.exp,
        )

    ticket = request.query_params.get("ticket")
    if ticket:
        grant = stream_tickets.redeem(ticket)
        if grant is not None:
            log.debug("Stream opened with ticket", username=grant.username, level=grant.auth_level)
            return StreamAuth(
                context=AuthContext(auth_level=grant.auth_level, username=grant.username),
                session_exp=grant.session_exp,
            )
        log.debug("Stream ticket rejected: unknown, spent, or expired")

    if not settings.auth.enabled:
        return StreamAuth(context=AuthContext(auth_level=AuthLevel.OWNER, username="unauthenticated"), session_exp=None)

    if settings.public_access.enabled:
        log.debug("Stream opened as public guest")
        return StreamAuth(context=AuthContext(auth_level=AuthLevel.GUEST), session_exp=None)

    if await verify_api_key_legacy(header_key, query_key):
        return StreamAuth(context=AuthContext(auth_level=AuthLevel.OWNER, username="legacy_api_key"), session_exp=None)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
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
            status_code=status.HTTP_403_FORBIDDEN, detail="Owner privileges required for this operation"
        )
    return auth
