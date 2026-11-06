"""Garden messages: their own text, the accepted photo as an attachment, and no media URL or token."""

from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import HTTPException

from app.config import settings
from app.database import get_db
from app.repositories.garden_repository import GardenCapture, GardenPhotoUnavailable, GardenRepository
from app.services import garden_motion_privacy
from app.services.i18n_service import i18n_service
from app.services.notification_links import instance_base
from app.services.notifications.message import Attachment, DeliveryResult, NotificationMessage, SubjectLink
from app.services.notifications.transports.discord import DiscordCredentials, DiscordOptions, DiscordTransport
from app.services.notifications.transports.email import EmailCredentials, EmailTransport
from app.services.notifications.transports.pushover import PushoverCredentials, PushoverOptions, PushoverTransport
from app.services.notifications.transports.telegram import TelegramCredentials, TelegramTransport

log = structlog.get_logger()

# Pushover's attachment ceiling, and well inside Discord's and Telegram's photo limits.
PHOTO_LIMIT_BYTES = 5 * 1024 * 1024
PHOTO_NAME = "garden.jpg"
# Garden alerts own their HTTP client rather than borrowing the bird notification service's.
http_client = httpx.AsyncClient(timeout=10.0)


def channel_configured(channel: str) -> bool:
    cfg = settings.notifications
    if channel == "discord":
        return bool(cfg.discord.webhook_url)
    if channel == "telegram":
        return bool(cfg.telegram.bot_token and cfg.telegram.chat_id)
    if channel == "pushover":
        return bool(cfg.pushover.api_token and cfg.pushover.user_key)
    if channel == "email":
        return bool(
            cfg.email.to_email
            and (
                (cfg.email.use_oauth and cfg.email.oauth_provider)
                or (not cfg.email.use_oauth and cfg.email.smtp_host and cfg.email.from_email)
            )
        )
    return False


async def garden_photo(capture: GardenCapture) -> bytes | None:
    """The saved animal crop, else the capture's photo; None when neither can be read now."""
    image = None
    async with garden_motion_privacy.lock:
        async with get_db() as db:
            try:
                image = await GardenRepository(db).crop_photo(capture.id)
            except GardenPhotoUnavailable:
                image = None
    if image is None:
        from app.services.garden_capture_service import garden_capture_service

        try:
            image = await garden_capture_service.snapshot(capture.id)
        except HTTPException:
            return None
    return image if image and len(image) <= PHOTO_LIMIT_BYTES else None


def observed_utc(observed_at: str) -> datetime:
    observed = datetime.fromisoformat(observed_at.removesuffix("Z"))
    return observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed.astimezone(timezone.utc)


def sighting_time(observed_at: str) -> str:
    """When the animal was seen, which can be minutes before it was named and the alert sent."""
    return observed_utc(observed_at).strftime("%Y-%m-%d %H:%M UTC")


def capture_link(capture: GardenCapture) -> str | None:
    """The Explorer with this capture's record open, on this install's public address."""
    base = instance_base(settings.notifications)
    if not base:
        return None
    query = {"visitors": "garden", "review": "confirmed", "camera": capture.camera, "garden_capture": capture.id}
    return f"{base}/events?{urlencode(query)}"


def message(capture: GardenCapture) -> tuple[str, str, str | None]:
    lang = settings.notifications.notification_language
    identity = capture.identification
    name = identity.name if identity and identity.name else ""
    title = i18n_service.translate("notification.garden_title", lang=lang, name=name)
    source = i18n_service.translate(
        "notification.garden_automatic" if identity and identity.automatic else "notification.garden_owner", lang=lang
    )
    body = i18n_service.translate(
        "notification.garden_body",
        lang=lang,
        camera=capture.camera,
        timestamp=sighting_time(capture.observed_at),
        source=source,
    )
    return title, body, capture_link(capture)


GARDEN_DISCORD_FOOTER = "YA-WAMF Garden"


def garden_message(capture: GardenCapture, photo: bytes | None) -> NotificationMessage:
    title, body, url = message(capture)
    link_text = i18n_service.translate("notification.garden_view", lang=settings.notifications.notification_language)
    return NotificationMessage(
        title=title,
        body=body,
        link=SubjectLink(url, link_text) if url else None,
        attachment=Attachment(PHOTO_NAME, photo) if photo else None,
        occurred_at=observed_utc(capture.observed_at),
    )


async def _send_through_transport(channel: str, alert: NotificationMessage) -> DeliveryResult | None:
    cfg = settings.notifications
    if channel == "discord":
        options = DiscordOptions(username=cfg.discord.username, footer=GARDEN_DISCORD_FOOTER)
        return await DiscordTransport(http_client).send(alert, DiscordCredentials(cfg.discord.webhook_url), options)
    if channel == "telegram":
        credentials = TelegramCredentials(cfg.telegram.bot_token, cfg.telegram.chat_id)
        return await TelegramTransport(http_client).send(alert, credentials)
    if channel == "email":
        from app.services.smtp_service import smtp_service

        email = cfg.email
        credentials = EmailCredentials(
            to_email=email.to_email,
            from_email=email.from_email,
            oauth_provider=email.oauth_provider if email.use_oauth else None,
            smtp_host=email.smtp_host,
            smtp_port=email.smtp_port,
            smtp_username=email.smtp_username,
            smtp_password=email.smtp_password,
            use_tls=email.smtp_use_tls,
        )
        return await EmailTransport(smtp_service).send(alert, credentials)
    if channel == "pushover":
        credentials = PushoverCredentials(cfg.pushover.api_token, cfg.pushover.user_key)
        return await PushoverTransport(http_client).send(
            alert, credentials, PushoverOptions(device=cfg.pushover.device)
        )
    return None


async def send_garden_notification(channel: str, capture: GardenCapture, photo: bytes | None = None) -> bool:
    if not channel_configured(channel):
        return False
    result = await _send_through_transport(channel, garden_message(capture, photo))
    if result is None:
        return False
    if not result.sent:
        # The result names the failure's type and status only, never provider text or credentials.
        log.warning("garden_channel_delivery_failed", channel=channel, error_type=result.error_type)
    return result.sent
