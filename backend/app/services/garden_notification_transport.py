"""Text-only Garden messages with no media URL, session token or bird template."""

import html
import re
from urllib.parse import urlencode

import structlog
from httpx import URL

from app.config import settings
from app.repositories.garden_repository import GardenCapture
from app.services.i18n_service import i18n_service
from app.services.notification_links import instance_base
from app.services.notification_service import notification_service

log = structlog.get_logger()


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


def message(capture: GardenCapture) -> tuple[str, str, str | None]:
    lang = settings.notifications.notification_language
    identity = capture.identification
    name = identity.name if identity and identity.name else ""
    title = i18n_service.translate("notification.garden_title", lang=lang, name=name)
    source = i18n_service.translate(
        "notification.garden_automatic" if identity and identity.automatic else "notification.garden_owner", lang=lang
    )
    body = i18n_service.translate(
        "notification.garden_body", lang=lang, camera=capture.camera, timestamp=capture.observed_at + "Z", source=source
    )
    base = instance_base(settings.notifications)
    url = (
        f"{base}/events?{urlencode({'visitors': 'garden', 'review': 'confirmed', 'camera': capture.camera})}"
        if base
        else None
    )
    return title, body, url


async def send_garden_notification(channel: str, capture: GardenCapture) -> bool:
    if not channel_configured(channel):
        return False
    title, body, url = message(capture)
    client = notification_service.client
    cfg = settings.notifications
    try:
        if channel == "discord":
            # Model/camera names are data, never mentions or Markdown controls.
            def escape(text: str) -> str:
                return re.sub(r"([\\`*_~|>\[\]()])", r"\\\1", text)

            embed = {"title": escape(title), "description": escape(body), "footer": {"text": "YA-WAMF Garden"}}
            if url:
                embed["url"] = url
            response = await client.post(
                URL(cfg.discord.webhook_url).copy_merge_params({"wait": "true"}),
                json={"username": cfg.discord.username, "allowed_mentions": {"parse": []}, "embeds": [embed]},
            )
        elif channel == "telegram":
            text = f"<b>{html.escape(title)}</b>\n{html.escape(body)}"
            payload = {
                "chat_id": cfg.telegram.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True},
            }
            if url:
                payload["reply_markup"] = {"inline_keyboard": [[{"text": "Garden", "url": url}]]}
            response = await client.post(
                f"https://api.telegram.org/bot{cfg.telegram.bot_token}/sendMessage", json=payload
            )
            response.raise_for_status()
            return response.json().get("ok") is True
        elif channel == "pushover":
            payload = {
                "token": cfg.pushover.api_token,
                "user": cfg.pushover.user_key,
                "title": title,
                "message": body,
                "html": 0,
                "priority": 0,
            }
            if cfg.pushover.device:
                payload["device"] = cfg.pushover.device
            if url:
                payload.update(url=url, url_title="Garden")
            response = await client.post("https://api.pushover.net/1/messages.json", data=payload)
            response.raise_for_status()
            return response.json().get("status") == 1
        elif channel == "email":
            from app.services.smtp_service import smtp_service

            email = cfg.email
            plain = f"{title}\n{body}" + (f"\n{url}" if url else "")
            rendered = f"<h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>"
            if url:
                rendered += f'<p><a href="{html.escape(url, quote=True)}">Garden</a></p>'
            if email.use_oauth:
                return await smtp_service.send_email_oauth(
                    provider=email.oauth_provider,
                    to_email=email.to_email,
                    from_email=email.from_email,
                    subject=title,
                    html_body=rendered,
                    plain_body=plain,
                    image_data=None,
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
                image_data=None,
            )
        else:
            return False
        response.raise_for_status()
        return True
    except Exception as error:
        # Third-party failures can contain credential-bearing URLs or request bodies.
        log.warning("garden_channel_delivery_failed", channel=channel, error_type=type(error).__name__)
        return False
