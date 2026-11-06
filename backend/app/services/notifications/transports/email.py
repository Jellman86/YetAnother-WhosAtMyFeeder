"""Email delivery through the configured mailbox: OAuth or SMTP, with the photo inline."""

import html
from dataclasses import dataclass, field
from typing import Protocol

from app.services.notifications.message import DeliveryResult, NotificationMessage

# smtp_service attaches the image inline under this Content-ID.
INLINE_IMAGE_CID = "bird_snapshot"


class Mailer(Protocol):
    async def send_email_oauth(
        self,
        provider: str,
        to_email: str,
        subject: str,
        html_body: str,
        plain_body: str | None = None,
        from_email: str | None = None,
        image_data: bytes | None = None,
    ) -> bool: ...

    async def send_email_password(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        to_email: str,
        subject: str,
        html_body: str,
        plain_body: str | None = None,
        use_tls: bool = True,
        image_data: bytes | None = None,
    ) -> bool: ...


@dataclass(frozen=True)
class EmailCredentials:
    """The mailbox: an OAuth provider when one is set, otherwise SMTP with a password."""

    to_email: str
    from_email: str | None = None
    oauth_provider: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    use_tls: bool = True


@dataclass(frozen=True)
class EmailOptions:
    """Bodies a builder rendered itself, such as the bird detection template; otherwise the plain layout."""

    html_body: str | None = None
    plain_body: str | None = None


def render_html(message: NotificationMessage) -> str:
    """A heading, the body and, when given, the inline photo and the subject link, all escaped."""
    rendered = f"<h1>{html.escape(message.title)}</h1><p>{html.escape(message.body)}</p>"
    if message.attachment is not None:
        alt = html.escape(message.title, quote=True)
        rendered += f'<p><img src="cid:{INLINE_IMAGE_CID}" alt="{alt}" style="max-width:100%"></p>'
    if message.link is not None:
        url, label = html.escape(message.link.url, quote=True), html.escape(message.link.label)
        rendered += f'<p><a href="{url}">{label}</a></p>'
    return rendered


def render_plain(message: NotificationMessage) -> str:
    return f"{message.title}\n{message.body}" + (f"\n{message.link.url}" if message.link else "")


class EmailTransport:
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def send(
        self, message: NotificationMessage, credentials: EmailCredentials, options: EmailOptions = EmailOptions()
    ) -> DeliveryResult:
        html_body = options.html_body if options.html_body is not None else render_html(message)
        plain_body = options.plain_body if options.plain_body is not None else render_plain(message)
        image = message.attachment.content if message.attachment is not None else None
        try:
            if credentials.oauth_provider:
                sent = await self._mailer.send_email_oauth(
                    provider=credentials.oauth_provider,
                    to_email=credentials.to_email,
                    from_email=credentials.from_email,
                    subject=message.title,
                    html_body=html_body,
                    plain_body=plain_body,
                    image_data=image,
                )
            else:
                sent = await self._mailer.send_email_password(
                    smtp_host=credentials.smtp_host or "",
                    smtp_port=credentials.smtp_port,
                    username=credentials.smtp_username,
                    password=credentials.smtp_password,
                    from_email=credentials.from_email or "",
                    to_email=credentials.to_email,
                    subject=message.title,
                    html_body=html_body,
                    plain_body=plain_body,
                    use_tls=credentials.use_tls,
                    image_data=image,
                )
            return DeliveryResult(sent=sent is True)
        except Exception as error:
            # SMTP errors can quote the login exchange: keep only the type.
            return DeliveryResult(sent=False, error_type=type(error).__name__)
