"""
Email notification OAuth and management endpoints
"""

import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Query, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import structlog
import os
from typing import Optional
from urllib.parse import urlencode
import secrets
import json

import httpx

from google_auth_oauthlib.flow import Flow

from app.config import settings
from app.services.smtp_service import smtp_service
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.utils.font_theme import get_email_font_family
from app.auth import require_owner, AuthContext
from jinja2 import Template
import aiofiles

router = APIRouter(prefix="/email", tags=["email"])
log = structlog.get_logger()
_oauth_state_cache: dict[str, datetime] = {}
OAUTH_STATE_TTL = timedelta(minutes=10)

def _decode_jwt_payload(token: str) -> dict:
    """Best-effort decode of a JWT payload without verification (for display only)."""
    try:
        import base64
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        # Base64url padding
        payload += "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


class OAuthCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None


class TestEmailRequest(BaseModel):
    test_subject: str = "YA-WAMF Test Email"
    test_message: str = "This is a test email from YA-WAMF to verify your email configuration."


@router.get("/oauth/gmail/authorize")
async def gmail_oauth_authorize(
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Initiate Gmail OAuth2 authorization flow. Owner only.

    Returns redirect URL for user to authorize application
    """
    lang = get_user_language(request)
    try:
        if not settings.notifications.email.gmail_client_id or not settings.notifications.email.gmail_client_secret:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.gmail_oauth_not_configured", lang))

        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.notifications.email.gmail_client_id,
                    "client_secret": settings.notifications.email.gmail_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [f"{str(request.base_url)}api/email/oauth/gmail/callback"]
                }
            },
            # NOTE: XOAUTH2 for SMTP requires the full mail scope; openid/email allows us to
            # resolve the user's email address for UI display.
            scopes=["openid", "email", "https://mail.google.com/"]
        )

        # Set redirect URI
        redirect_uri = f"{str(request.base_url)}api/email/oauth/gmail/callback"
        flow.redirect_uri = redirect_uri

        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent to get refresh token
        )
        _oauth_state_cache[state] = datetime.utcnow() + OAUTH_STATE_TTL

        log.info("gmail_oauth_initiated", redirect_uri=redirect_uri)

        return {"authorization_url": authorization_url, "state": state}

    except HTTPException:
        raise
    except Exception as e:
        log.error("gmail_oauth_authorize_error", error=str(e))
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.email.gmail_oauth_failed", lang, error=str(e)))


@router.get("/oauth/gmail/callback")
async def gmail_oauth_callback(request: Request, code: str = Query(...), state: str = Query(None)):
    """
    Handle Gmail OAuth2 callback and store tokens
    """
    try:
        # Validate state to reduce CSRF risk (best-effort in-memory cache).
        if not state or state not in _oauth_state_cache:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.invalid_state", get_user_language(request)))
        expires_at = _oauth_state_cache.get(state)
        if expires_at and expires_at < datetime.utcnow():
            _oauth_state_cache.pop(state, None)
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.state_expired", get_user_language(request)))
        _oauth_state_cache.pop(state, None)

        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.notifications.email.gmail_client_id,
                    "client_secret": settings.notifications.email.gmail_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [f"{str(request.base_url)}api/email/oauth/gmail/callback"]
                }
            },
            scopes=["openid", "email", "https://mail.google.com/"],
            state=state
        )

        flow.redirect_uri = f"{str(request.base_url)}api/email/oauth/gmail/callback"

        # Exchange authorization code for tokens
        flow.fetch_token(code=code)

        credentials = flow.credentials

        # Get user email from token info
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                headers={"Authorization": f"Bearer {credentials.token}"}
            )
            response.raise_for_status()
            user_info = response.json()
            email = user_info.get("email")
            if not email:
                raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.email_missing", get_user_language(request)))

        # Store tokens in database
        expires_in = 3600
        if credentials.expiry:
            expiry = credentials.expiry
            if expiry.tzinfo is None:
                now = datetime.utcnow()
            else:
                now = datetime.now(expiry.tzinfo)
            expires_in = max(0, int((expiry - now).total_seconds()))

        await smtp_service.store_oauth_token(
            provider="gmail",
            email=email,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_in=expires_in,
            scope=" ".join(credentials.scopes) if credentials.scopes else None
        )

        log.info("gmail_oauth_completed", email=email)

        # Return success HTML page
        return HTMLResponse(content="""
        <html>
            <head><title>Gmail Connected</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #10b981;">✓ Gmail Connected Successfully!</h1>
                <p>You can close this window and return to YA-WAMF settings.</p>
                <p style="color: #64748b; font-size: 14px;">Email: {email}</p>
                <script>
                    // Try to close popup window after 3 seconds
                    setTimeout(() => window.close(), 3000);
                </script>
            </body>
        </html>
        """.format(email=email))

    except Exception as e:
        log.error("gmail_oauth_callback_error", error=str(e))
        return HTMLResponse(content=f"""
        <html>
            <head><title>Gmail Connection Failed</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #ef4444;">✗ Gmail Connection Failed</h1>
                <p>{str(e)}</p>
                <p><a href="javascript:window.close()">Close Window</a></p>
            </body>
        </html>
        """, status_code=500)


@router.get("/oauth/outlook/authorize")
async def outlook_oauth_authorize(
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Initiate Outlook/Office 365 OAuth2 authorization flow. Owner only.
    """
    lang = get_user_language(request)
    try:
        if not settings.notifications.email.outlook_client_id or not settings.notifications.email.outlook_client_secret:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.outlook_oauth_not_configured", lang))

        # Generate authorization URL (Microsoft identity platform v2.0).
        # We request offline_access so we can obtain refresh tokens for long-lived setups.
        redirect_uri = f"{str(request.base_url)}api/email/oauth/outlook/callback"
        state_value = secrets.token_urlsafe(32)
        _oauth_state_cache[state_value] = datetime.utcnow() + OAUTH_STATE_TTL
        params = {
            "client_id": settings.notifications.email.outlook_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            # SMTP AUTH delegated permission scope per Microsoft docs.
            "scope": "offline_access openid email https://outlook.office.com/SMTP.Send",
            "state": state_value,
            "response_mode": "query",
        }
        auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

        log.info("outlook_oauth_initiated", redirect_uri=redirect_uri)

        return {"authorization_url": auth_url, "state": state_value}

    except HTTPException:
        raise
    except Exception as e:
        log.error("outlook_oauth_authorize_error", error=str(e))
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.email.outlook_oauth_failed", lang, error=str(e)))


@router.get("/oauth/outlook/callback")
async def outlook_oauth_callback(request: Request, code: str = Query(...), state: str = Query(None)):
    """
    Handle Outlook OAuth2 callback and store tokens
    """
    lang = get_user_language(request)
    try:
        # Validate state to reduce CSRF risk (best-effort in-memory cache).
        if not state or state not in _oauth_state_cache:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.invalid_state", lang))
        expires_at = _oauth_state_cache.get(state)
        if expires_at and expires_at < datetime.utcnow():
            _oauth_state_cache.pop(state, None)
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.state_expired", lang))
        _oauth_state_cache.pop(state, None)

        redirect_uri = f"{str(request.base_url)}api/email/oauth/outlook/callback"

        # Exchange authorization code for tokens (store refresh token for long-lived setups).
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "client_id": settings.notifications.email.outlook_client_id,
                    "client_secret": settings.notifications.email.outlook_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "scope": "offline_access openid email https://outlook.office.com/SMTP.Send",
                },
            )
            token_resp.raise_for_status()
            result = token_resp.json()

        access_token = result.get("access_token")
        if not access_token:
            error_desc = result.get("error_description", i18n_service.translate("errors.email.access_token_failed", lang))
            raise HTTPException(status_code=400, detail=error_desc)

        # Best-effort email extraction from id_token for display and SMTP user.
        email = None
        id_token = result.get("id_token")
        if id_token:
            claims = _decode_jwt_payload(id_token)
            email = claims.get("preferred_username") or claims.get("upn") or claims.get("email")
        if not email:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.email_missing", lang))

        # Store tokens in database
        await smtp_service.store_oauth_token(
            provider="outlook",
            email=email,
            access_token=access_token,
            refresh_token=result.get("refresh_token"),
            expires_in=result.get("expires_in", 3600),
            scope=result.get("scope")
        )

        log.info("outlook_oauth_completed", email=email)

        # Return success HTML page
        return HTMLResponse(content=f"""
        <html>
            <head><title>Outlook Connected</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #10b981;">✓ Outlook Connected Successfully!</h1>
                <p>You can close this window and return to YA-WAMF settings.</p>
                <p style="color: #64748b; font-size: 14px;">Email: {email}</p>
                <script>
                    setTimeout(() => window.close(), 3000);
                </script>
            </body>
        </html>
        """)

    except Exception as e:
        log.error("outlook_oauth_callback_error", error=str(e))
        return HTMLResponse(content=f"""
        <html>
            <head><title>Outlook Connection Failed</title></head>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #ef4444;">✗ Outlook Connection Failed</h1>
                <p>{str(e)}</p>
                <p><a href="javascript:window.close()">Close Window</a></p>
            </body>
        </html>
        """, status_code=500)


@router.delete("/oauth/{provider}/disconnect")
async def disconnect_oauth(
    provider: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Disconnect OAuth email provider and delete stored tokens. Owner only.
    """
    lang = get_user_language(request)
    if provider not in ["gmail", "outlook"]:
        raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.invalid_provider", lang))

    try:
        success = await smtp_service.delete_oauth_token(provider)

        if success:
            log.info("oauth_disconnected", provider=provider)
            return {"message": f"{provider.capitalize()} disconnected successfully"}
        else:
            raise HTTPException(status_code=500, detail=i18n_service.translate("errors.email.disconnect_failed", lang))

    except HTTPException:
        raise
    except Exception as e:
        log.error("oauth_disconnect_error", error=str(e), provider=provider)
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.email.disconnect_error", lang, error=str(e)))


@router.post("/test")
async def send_test_email(
    test_request: TestEmailRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Send a test email to verify configuration. Owner only.
    """
    lang = get_user_language(request)
    send_mode = "unknown"
    try:
        email_config = settings.notifications.email
        send_mode = "oauth" if (email_config.use_oauth and email_config.oauth_provider) else "smtp"
        log.info(
            "test_email_requested",
            mode=send_mode,
            oauth_provider=email_config.oauth_provider,
            smtp_host=email_config.smtp_host,
            smtp_port=email_config.smtp_port,
            smtp_use_tls=email_config.smtp_use_tls,
            smtp_username_set=bool(email_config.smtp_username),
            smtp_password_set=bool(email_config.smtp_password),
            from_email_set=bool(email_config.from_email),
            to_email_set=bool(email_config.to_email),
        )

        if not email_config.enabled:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.not_enabled", lang))

        if not email_config.to_email:
            raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.recipient_not_configured", lang))

        # Prepare email content using the notification-style template
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates", "email")
        async with aiofiles.open(os.path.join(template_dir, "test_email.html"), 'r') as f:
            html_template = Template(await f.read())
        async with aiofiles.open(os.path.join(template_dir, "test_email.txt"), 'r') as f:
            text_template = Template(await f.read())

        template_data = {
            "subject": test_request.test_subject,
            "message": test_request.test_message,
            "species": "Test Sparrow",
            "audio_confirmed": False,
            "has_image": False,
            "confidence": 88,
            "camera": "Test Camera",
            "timestamp": "Just now",
            "scientific_name": "Testus sparrowii",
            "weather": "Clear skies",
            "dashboard_url": email_config.dashboard_url,
            "font_family": get_email_font_family(
                getattr(settings, "appearance", None).font_theme if getattr(settings, "appearance", None) else "classic",
                settings.accessibility.dyslexia_font
            ),
        }

        html_body = html_template.render(**template_data)
        plain_body = text_template.render(**template_data)

        # Send using OAuth or traditional SMTP
        if email_config.use_oauth and email_config.oauth_provider:
            success = await asyncio.wait_for(
                smtp_service.send_email_oauth(
                    provider=email_config.oauth_provider,
                    to_email=email_config.to_email,
                    subject=test_request.test_subject,
                    html_body=html_body,
                    plain_body=plain_body
                ),
                timeout=30,
            )
        else:
            # Traditional SMTP
            if not email_config.smtp_host or not email_config.from_email:
                raise HTTPException(status_code=400, detail=i18n_service.translate("errors.email.smtp_incomplete", lang))

            success = await asyncio.wait_for(
                smtp_service.send_email_password(
                    smtp_host=email_config.smtp_host,
                    smtp_port=email_config.smtp_port,
                    username=email_config.smtp_username,
                    password=email_config.smtp_password,
                    from_email=email_config.from_email,
                    to_email=email_config.to_email,
                    subject=test_request.test_subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    use_tls=email_config.smtp_use_tls
                ),
                timeout=30,
            )

        if success:
            log.info("test_email_sent", to=email_config.to_email)
            return {"message": "Test email sent successfully!", "to": email_config.to_email}
        else:
            raise HTTPException(status_code=500, detail=i18n_service.translate("errors.email.send_failed", lang))

    except HTTPException:
        raise
    except asyncio.TimeoutError:
        log.error("test_email_timeout", timeout_seconds=30, mode=send_mode)
        raise HTTPException(
            status_code=504,
            detail=i18n_service.translate("errors.email.send_error", lang, error="request timed out"),
        )
    except Exception as e:
        log.error("test_email_error", error=str(e), error_type=type(e).__name__, mode=send_mode)
        raise HTTPException(status_code=500, detail=i18n_service.translate("errors.email.send_error", lang, error=str(e)))
