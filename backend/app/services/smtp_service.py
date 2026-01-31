"""
SMTP Email Service with OAuth2 and Traditional Auth Support

Supports:
- Gmail with OAuth2
- Outlook/Office 365 with OAuth2
- Traditional SMTP with username/password
- HTML and plain text emails
- Token persistence and auto-refresh
"""

import aiosmtplib
import structlog
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from typing import Optional, Dict, Any
import base64
import json

from google.oauth2.credentials import Credentials as GoogleCredentials
from google.auth.transport.requests import Request as GoogleRequest
from msal import ConfidentialClientApplication

from app.database import get_db

log = structlog.get_logger()


class SMTPService:
    """SMTP Email Service with OAuth2 support for Gmail and Outlook"""

    def __init__(self):
        self.logger = log.bind(service="smtp")

    async def send_email_oauth(
        self,
        provider: str,
        to_email: str,
        subject: str,
        html_body: str,
        plain_body: Optional[str] = None,
        from_email: Optional[str] = None,
        image_data: Optional[bytes] = None
    ) -> bool:
        """
        Send email using OAuth2 authentication

        Args:
            provider: 'gmail' or 'outlook'
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            plain_body: Plain text email body (optional)
            from_email: Sender email (optional, uses token email if not provided)
            image_data: Optional image to attach (for bird snapshot)

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Get OAuth token from database
            token_data = await self._get_oauth_token(provider)
            if not token_data:
                self.logger.error("oauth_token_not_found", provider=provider)
                return False

            # Refresh token if expired
            if await self._is_token_expired(token_data):
                self.logger.info("token_expired_refreshing", provider=provider)
                token_data = await self._refresh_oauth_token(provider, token_data)
                if not token_data:
                    self.logger.error("token_refresh_failed", provider=provider)
                    return False

            # Build email message
            message = await self._build_email_message(
                to_email=to_email,
                from_email=from_email or token_data["email"],
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
                image_data=image_data
            )

            # Send via appropriate provider
            if provider == "gmail":
                success = await self._send_via_gmail_oauth(token_data, message, to_email)
            elif provider == "outlook":
                success = await self._send_via_outlook_oauth(token_data, message, to_email)
            else:
                self.logger.error("unsupported_provider", provider=provider)
                return False

            if success:
                self.logger.info("email_sent_oauth", provider=provider, to=to_email)
            else:
                self.logger.error("email_send_failed_oauth", provider=provider, to=to_email)

            return success

        except Exception as e:
            self.logger.error("send_email_oauth_error", error=str(e), provider=provider)
            return False

    async def send_email_password(
        self,
        smtp_host: str,
        smtp_port: int,
        username: Optional[str],
        password: Optional[str],
        from_email: str,
        to_email: str,
        subject: str,
        html_body: str,
        plain_body: Optional[str] = None,
        use_tls: bool = True,
        image_data: Optional[bytes] = None
    ) -> bool:
        """
        Send email using traditional SMTP authentication

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            from_email: Sender email address
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body
            plain_body: Plain text email body (optional)
            use_tls: Whether to use TLS (default: True)
            image_data: Optional image to attach

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # Build email message
            message = await self._build_email_message(
                to_email=to_email,
                from_email=from_email,
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
                image_data=image_data
            )

            # Send via SMTP
            async with aiosmtplib.SMTP(
                hostname=smtp_host,
                port=smtp_port,
                use_tls=use_tls
            ) as smtp:
                if username and password:
                    await smtp.login(username, password)
                await smtp.send_message(message)

            self.logger.info("email_sent_password", smtp_host=smtp_host, to=to_email)
            return True

        except Exception as e:
            self.logger.error("send_email_password_error", error=str(e), smtp_host=smtp_host)
            return False

    async def _build_email_message(
        self,
        to_email: str,
        from_email: str,
        subject: str,
        html_body: str,
        plain_body: Optional[str] = None,
        image_data: Optional[bytes] = None
    ) -> MIMEMultipart:
        """Build MIME email message with HTML and optional image"""
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        from_name, from_addr = parseaddr(from_email)
        to_name, to_addr = parseaddr(to_email)
        message['From'] = formataddr((from_name or "YA-WAMF", from_addr))
        message['To'] = formataddr((to_name or "Recipient", to_addr))
        message['Date'] = formatdate(localtime=True)
        message['Message-ID'] = make_msgid(domain=(from_addr.split("@")[-1] if "@" in from_addr else None))

        # Add plain text part
        if plain_body:
            text_part = MIMEText(plain_body, 'plain')
            message.attach(text_part)

        # Add HTML part with inline image if provided
        if image_data:
            # Create a multipart/related container for HTML + embedded image
            msg_related = MIMEMultipart('related')

            # Add HTML part to the related container
            html_part = MIMEText(html_body, 'html')
            msg_related.attach(html_part)

            # Add embedded image with Content-ID
            image = MIMEImage(image_data)
            image.add_header('Content-ID', '<bird_snapshot>')
            image.add_header('Content-Disposition', 'inline', filename='bird.jpg')
            msg_related.attach(image)

            # Attach the related container to the alternative message
            message.attach(msg_related)
        else:
            # No image, just add HTML part directly
            html_part = MIMEText(html_body, 'html')
            message.attach(html_part)

        return message

    async def _send_via_gmail_oauth(
        self,
        token_data: Dict[str, Any],
        message: MIMEMultipart,
        to_email: str
    ) -> bool:
        """Send email via Gmail using OAuth2"""
        try:
            # Create XOAUTH2 string
            auth_string = f"user={token_data['email']}\1auth=Bearer {token_data['access_token']}\1\1"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')

            # Connect to Gmail SMTP
            async with aiosmtplib.SMTP(
                hostname="smtp.gmail.com",
                port=587,
                use_tls=False  # We'll start TLS manually
            ) as smtp:
                await smtp.connect()
                await smtp.starttls()

                # Authenticate with OAuth2
                await smtp.execute_command(b"AUTH", b"XOAUTH2", auth_b64.encode())

                # Send message
                await smtp.send_message(message)

            return True

        except Exception as e:
            self.logger.error("gmail_oauth_send_error", error=str(e))
            return False

    async def _send_via_outlook_oauth(
        self,
        token_data: Dict[str, Any],
        message: MIMEMultipart,
        to_email: str
    ) -> bool:
        """Send email via Outlook/Office 365 using OAuth2"""
        try:
            # Create XOAUTH2 string
            auth_string = f"user={token_data['email']}\1auth=Bearer {token_data['access_token']}\1\1"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')

            # Connect to Outlook SMTP
            async with aiosmtplib.SMTP(
                hostname="smtp.office365.com",
                port=587,
                use_tls=False
            ) as smtp:
                await smtp.connect()
                await smtp.starttls()

                # Authenticate with OAuth2
                await smtp.execute_command(b"AUTH", b"XOAUTH2", auth_b64.encode())

                # Send message
                await smtp.send_message(message)

            return True

        except Exception as e:
            self.logger.error("outlook_oauth_send_error", error=str(e))
            return False

    async def _get_oauth_token(self, provider: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth token from database"""
        try:
            async with get_db() as db:
                cursor = await db.execute(
                    """SELECT provider, email, access_token, refresh_token, expires_at, scope, created_at, updated_at
                       FROM oauth_tokens WHERE provider = ?""",
                    (provider,)
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                return {
                    "provider": row[0],
                    "email": row[1],
                    "access_token": row[2],
                    "refresh_token": row[3],
                    "expires_at": row[4],
                    "scope": row[5],
                    "created_at": row[6],
                    "updated_at": row[7]
                }

        except Exception as e:
            self.logger.error("get_oauth_token_error", error=str(e), provider=provider)
            return None

    async def get_oauth_status(self, provider: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Return connected OAuth provider/email for UI display."""
        providers = [provider] if provider else ["gmail", "outlook"]
        for candidate in providers:
            if not candidate:
                continue
            token = await self._get_oauth_token(candidate)
            if token:
                return {"provider": candidate, "email": token["email"]}
        return None

    async def _is_token_expired(self, token_data: Dict[str, Any]) -> bool:
        """Check if OAuth token is expired"""
        if not token_data.get("expires_at"):
            return False

        expires_at = token_data["expires_at"]
        # Add 5 minute buffer
        return datetime.utcnow() + timedelta(minutes=5) >= expires_at

    async def _refresh_oauth_token(
        self,
        provider: str,
        token_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Refresh expired OAuth token"""
        try:
            if provider == "gmail":
                return await self._refresh_gmail_token(token_data)
            elif provider == "outlook":
                return await self._refresh_outlook_token(token_data)
            else:
                self.logger.error("unsupported_provider_refresh", provider=provider)
                return None

        except Exception as e:
            self.logger.error("refresh_token_error", error=str(e), provider=provider)
            return None

    async def _refresh_gmail_token(self, token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh Gmail OAuth token using refresh_token"""
        try:
            # Note: This requires OAuth client credentials from config
            from app.config import settings

            if (not settings.notifications.email.gmail_client_id or
                not settings.notifications.email.gmail_client_secret):
                self.logger.error("gmail_oauth_credentials_missing")
                return None

            creds = GoogleCredentials(
                token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.notifications.email.gmail_client_id,
                client_secret=settings.notifications.email.gmail_client_secret
            )

            # Refresh the token
            creds.refresh(GoogleRequest())

            # Update database
            new_expires_at = None
            if creds.expiry:
                expiry = creds.expiry
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                new_expires_at = expiry.astimezone(timezone.utc).replace(tzinfo=None)

            async with get_db() as db:
                await db.execute(
                    """UPDATE oauth_tokens SET access_token = ?, expires_at = ?, updated_at = ?
                       WHERE provider = ?""",
                    (creds.token, new_expires_at, datetime.utcnow(), "gmail")
                )
                await db.commit()

            # Return updated token data
            token_data["access_token"] = creds.token
            token_data["expires_at"] = new_expires_at

            self.logger.info("gmail_token_refreshed")
            return token_data

        except Exception as e:
            self.logger.error("gmail_token_refresh_error", error=str(e))
            return None

    async def _refresh_outlook_token(self, token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh Outlook OAuth token using MSAL"""
        try:
            from app.config import settings

            if (not settings.notifications.email.outlook_client_id or
                not settings.notifications.email.outlook_client_secret):
                self.logger.error("outlook_oauth_credentials_missing")
                return None

            app = ConfidentialClientApplication(
                client_id=settings.notifications.email.outlook_client_id,
                client_credential=settings.notifications.email.outlook_client_secret,
                authority="https://login.microsoftonline.com/common"
            )

            # Try to refresh using refresh token
            result = app.acquire_token_by_refresh_token(
                refresh_token=token_data.get("refresh_token"),
                scopes=["https://outlook.office365.com/SMTP.Send"]
            )

            if "access_token" not in result:
                self.logger.error("outlook_token_refresh_failed", error=result.get("error_description"))
                return None

            # Update database
            new_expires_at = datetime.utcnow() + timedelta(seconds=result.get("expires_in", 3600))

            async with get_db() as db:
                await db.execute(
                    """UPDATE oauth_tokens SET access_token = ?, refresh_token = ?, expires_at = ?, updated_at = ?
                       WHERE provider = ?""",
                    (result["access_token"], result.get("refresh_token", token_data.get("refresh_token")),
                     new_expires_at, datetime.utcnow(), "outlook")
                )
                await db.commit()

            # Return updated token data
            token_data["access_token"] = result["access_token"]
            token_data["expires_at"] = new_expires_at

            self.logger.info("outlook_token_refreshed")
            return token_data

        except Exception as e:
            self.logger.error("outlook_token_refresh_error", error=str(e))
            return None

    async def store_oauth_token(
        self,
        provider: str,
        email: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_in: Optional[int],
        scope: Optional[str] = None
    ) -> bool:
        """Store or update OAuth token in database"""
        try:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

            # Check if token exists
            existing = await self._get_oauth_token(provider)

            async with get_db() as db:
                if existing:
                    # Update existing token
                    await db.execute(
                        """UPDATE oauth_tokens SET email = ?, access_token = ?, refresh_token = ?,
                           token_type = 'Bearer', expires_at = ?, scope = ?, updated_at = ?
                           WHERE provider = ?""",
                        (email, access_token, refresh_token, expires_at, scope, datetime.utcnow(), provider)
                    )
                else:
                    # Insert new token
                    await db.execute(
                        """INSERT INTO oauth_tokens (provider, email, access_token, refresh_token, token_type,
                           expires_at, scope, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'Bearer', ?, ?, ?, ?)""",
                        (provider, email, access_token, refresh_token, expires_at, scope,
                         datetime.utcnow(), datetime.utcnow())
                    )
                await db.commit()
            self.logger.info("oauth_token_stored", provider=provider, email=email)
            return True

        except Exception as e:
            self.logger.error("store_oauth_token_error", error=str(e), provider=provider)
            return False

    async def delete_oauth_token(self, provider: str) -> bool:
        """Delete OAuth token from database"""
        try:
            async with get_db() as db:
                await db.execute(
                    "DELETE FROM oauth_tokens WHERE provider = ?",
                    (provider,)
                )
                await db.commit()
            self.logger.info("oauth_token_deleted", provider=provider)
            return True

        except Exception as e:
            self.logger.error("delete_oauth_token_error", error=str(e), provider=provider)
            return False


# Singleton instance
smtp_service = SMTPService()
