"""Telegram Bot API delivery: HTML escaping, caption limits, photo or text, and a link button."""

import html
import json
import logging
import traceback
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.services.notifications.message import DeliveryResult, NotificationMessage
from app.utils.diagnostic_redaction import redact_text

API_BASE = "https://api.telegram.org"
# Telegram counts a caption (1,024) or message (4,096) after entity parsing, so raw text is
# clipped before escaping, leaving room for the markup.
CAPTION_TEXT_LIMIT = 900
MESSAGE_TEXT_LIMIT = 3600
# With a body under it, the bold title keeps to this and the body has the rest.
TITLE_LIMIT_WITH_BODY = 300


class _TelegramCredentialLogFilter(logging.Filter):
    """The bot token is part of every request URL, so verbose HTTP logs must never print it."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        secrets = (settings.notifications.telegram.bot_token or "",)
        sanitized = redact_text(message, secrets)
        if sanitized != message:
            record.msg, record.args = sanitized, ()
        if record.exc_info:
            record.exc_text = redact_text("".join(traceback.format_exception(*record.exc_info)), secrets)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text, secrets)
        return True


for _logger in (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_logger).addFilter(_TelegramCredentialLogFilter())


@dataclass(frozen=True)
class TelegramCredentials:
    bot_token: str = field(repr=False)
    chat_id: str = field(repr=False)


@dataclass(frozen=True)
class TelegramOptions:
    # Shown before the bold title: bird alerts open with a bird.
    icon: str = ""


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def render_text(message: NotificationMessage, options: TelegramOptions, *, with_photo: bool) -> str:
    """The HTML Telegram shows: a bold title, then the body, with every piece of data escaped."""
    limit = CAPTION_TEXT_LIMIT if with_photo else MESSAGE_TEXT_LIMIT
    title_limit = TITLE_LIMIT_WITH_BODY if message.body else limit
    text = f"<b>{html.escape(clip(message.title, title_limit))}</b>"
    if options.icon:
        text = f"{options.icon} {text}"
    if message.body:
        text += "\n" + html.escape(clip(message.body, limit - TITLE_LIMIT_WITH_BODY))
    # A photo stands in for its own link; a text message points at it when there is no button.
    if not with_photo and message.link is None and message.fallback_link is not None:
        fallback = message.fallback_link
        text += f'\n<a href="{html.escape(fallback.url, quote=True)}">{html.escape(fallback.label)}</a>'
    return text


def _button(message: NotificationMessage) -> dict[str, object] | None:
    if message.link is None:
        return None
    return {"inline_keyboard": [[{"text": message.link.label, "url": message.link.url}]]}


class TelegramTransport:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def send(
        self,
        message: NotificationMessage,
        credentials: TelegramCredentials,
        options: TelegramOptions = TelegramOptions(),
    ) -> DeliveryResult:
        base = f"{API_BASE}/bot{credentials.bot_token}"
        button = _button(message)
        photo = message.attachment
        try:
            if photo is not None:
                data = {
                    "chat_id": credentials.chat_id,
                    "caption": render_text(message, options, with_photo=True),
                    "parse_mode": "HTML",
                }
                if button:
                    data["reply_markup"] = json.dumps(button)
                response = await self._client.post(
                    f"{base}/sendPhoto",
                    data=data,
                    files={"photo": (photo.filename, photo.content, photo.content_type)},
                )
            else:
                payload: dict[str, object] = {
                    "chat_id": credentials.chat_id,
                    "text": render_text(message, options, with_photo=False),
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                }
                if button:
                    payload["reply_markup"] = button
                response = await self._client.post(f"{base}/sendMessage", json=payload)
            response.raise_for_status()
            accepted = response.json().get("ok") is True
            return DeliveryResult(sent=accepted, status_code=response.status_code)
        except httpx.HTTPStatusError as error:
            return DeliveryResult(sent=False, error_type=type(error).__name__, status_code=error.response.status_code)
        except Exception as error:
            # Request errors and provider text can carry the token-bearing URL: keep only the type.
            return DeliveryResult(sent=False, error_type=type(error).__name__)
