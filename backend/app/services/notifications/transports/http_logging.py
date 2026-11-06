"""Verbose HTTP logs print request URLs, and Telegram tokens and Discord webhooks are URLs."""

import logging
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.config import settings
from app.utils.diagnostic_redaction import redact_text

_active_webhooks: ContextVar[tuple[str, ...]] = ContextVar("notification_webhooks", default=())


def _webhook_credentials(webhook: str) -> tuple[str, ...]:
    try:
        url = httpx.URL(webhook)
    except httpx.InvalidURL:
        return (webhook,)
    # HTTPX normalises URLs and Discord replaces `wait`; HTTPcore also logs paths alone.
    paths = (url.path, url.raw_path.decode("ascii").split("?", 1)[0])
    return (webhook, str(url.copy_with(query=None, fragment=None)), *(path for path in paths if path != "/"))


@contextmanager
def redact_webhook_url(webhook: str) -> Iterator[None]:
    """Keep per-send credentials local to the sending task, including concurrent sends."""
    token = _active_webhooks.set((*_active_webhooks.get(), webhook))
    try:
        yield
    finally:
        _active_webhooks.reset(token)


def _url_credentials() -> tuple[str, ...]:
    cfg = settings.notifications
    webhooks = (cfg.discord.webhook_url or "", *_active_webhooks.get())
    return (
        cfg.telegram.bot_token or "",
        *(value for webhook in webhooks if webhook for value in _webhook_credentials(webhook)),
    )


class _NotificationCredentialLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        secrets = _url_credentials()
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
    logging.getLogger(_logger).addFilter(_NotificationCredentialLogFilter())
