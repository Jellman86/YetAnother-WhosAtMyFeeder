"""Garden messages: their own text, the accepted photo as an attachment, and no media URL or token."""

import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import structlog
from fastapi import HTTPException
from httpx import URL

from app.config import settings
from app.database import get_db
from app.repositories.garden_repository import GardenCapture, GardenPhotoUnavailable, GardenRepository
from app.services import garden_motion_privacy
from app.services.i18n_service import i18n_service
from app.services.notification_links import instance_base
from app.services.notification_service import notification_service

log = structlog.get_logger()

# Pushover's attachment ceiling, and well inside Discord's and Telegram's photo limits.
PHOTO_LIMIT_BYTES = 5 * 1024 * 1024
PHOTO_NAME = "garden.jpg"
# Telegram counts a caption after entity parsing, so the raw text is clipped before escaping.
TELEGRAM_CAPTION_TEXT_LIMIT = 900


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


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def _discord_escape(text: str) -> str:
    # Model/camera names are data, never mentions or Markdown controls.
    return re.sub(r"([\\`*_~|>\[\]()])", r"\\\1", text)


async def send_garden_notification(channel: str, capture: GardenCapture, photo: bytes | None = None) -> bool:
    if not channel_configured(channel):
        return False
    title, body, url = message(capture)
    lang = settings.notifications.notification_language
    link_text = i18n_service.translate("notification.garden_view", lang=lang)
    client = notification_service.client
    cfg = settings.notifications
    try:
        if channel == "discord":
            embed: dict[str, object] = {
                "title": _discord_escape(title),
                "description": _discord_escape(body),
                "timestamp": observed_utc(capture.observed_at).isoformat(),
                "footer": {"text": "YA-WAMF Garden"},
            }
            if url:
                embed["url"] = url
            payload = {"username": cfg.discord.username, "allowed_mentions": {"parse": []}, "embeds": [embed]}
            webhook = URL(cfg.discord.webhook_url).copy_merge_params({"wait": "true"})
            if photo:
                embed["image"] = {"url": f"attachment://{PHOTO_NAME}"}
                response = await client.post(
                    webhook,
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": (PHOTO_NAME, photo, "image/jpeg")},
                )
            else:
                response = await client.post(webhook, json=payload)
        elif channel == "telegram":
            base = f"https://api.telegram.org/bot{cfg.telegram.bot_token}"
            button = {"inline_keyboard": [[{"text": link_text, "url": url}]]} if url else None
            if photo:
                caption = f"<b>{html.escape(_clip(title, 300))}</b>\n{html.escape(_clip(body, TELEGRAM_CAPTION_TEXT_LIMIT - 300))}"
                data = {"chat_id": cfg.telegram.chat_id, "caption": caption, "parse_mode": "HTML"}
                if button:
                    data["reply_markup"] = json.dumps(button)
                response = await client.post(
                    f"{base}/sendPhoto", data=data, files={"photo": (PHOTO_NAME, photo, "image/jpeg")}
                )
            else:
                payload = {
                    "chat_id": cfg.telegram.chat_id,
                    "text": f"<b>{html.escape(title)}</b>\n{html.escape(body)}",
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                }
                if button:
                    payload["reply_markup"] = button
                response = await client.post(f"{base}/sendMessage", json=payload)
            response.raise_for_status()
            return response.json().get("ok") is True
        elif channel == "pushover":
            fields = {
                "token": cfg.pushover.api_token,
                "user": cfg.pushover.user_key,
                "title": title,
                "message": body,
                "html": 0,
                "priority": 0,
            }
            if cfg.pushover.device:
                fields["device"] = cfg.pushover.device
            if url:
                fields.update(url=url, url_title=link_text)
            if photo:
                response = await client.post(
                    "https://api.pushover.net/1/messages.json",
                    data=fields,
                    files={"attachment": (PHOTO_NAME, photo, "image/jpeg")},
                )
            else:
                response = await client.post("https://api.pushover.net/1/messages.json", data=fields)
            response.raise_for_status()
            return response.json().get("status") == 1
        elif channel == "email":
            from app.services.smtp_service import smtp_service

            email = cfg.email
            plain = f"{title}\n{body}" + (f"\n{url}" if url else "")
            rendered = f"<h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>"
            if photo:
                # smtp_service attaches the image inline under this Content-ID.
                rendered += f'<p><img src="cid:bird_snapshot" alt="{html.escape(title, quote=True)}" style="max-width:100%"></p>'
            if url:
                rendered += f'<p><a href="{html.escape(url, quote=True)}">{html.escape(link_text)}</a></p>'
            if email.use_oauth:
                return await smtp_service.send_email_oauth(
                    provider=email.oauth_provider,
                    to_email=email.to_email,
                    from_email=email.from_email,
                    subject=title,
                    html_body=rendered,
                    plain_body=plain,
                    image_data=photo,
                )
            return await smtp_service.send_email_password(
                smtp_host=email.smtp_host,
                smtp_port=email.smtp_port,
                username=email.smtp_username,
                password=email.smtp_password,
                from_email=email.from_email,
                to_email=email.to_email,
                subject=title,
                html_body=rendered,
                plain_body=plain,
                use_tls=email.smtp_use_tls,
                image_data=photo,
            )
        else:
            return False
        response.raise_for_status()
        return True
    except Exception as error:
        # Third-party failures can contain credential-bearing URLs or request bodies.
        log.warning("garden_channel_delivery_failed", channel=channel, error_type=type(error).__name__)
        return False
