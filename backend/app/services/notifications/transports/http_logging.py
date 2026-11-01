"""Verbose HTTP logs print request URLs, and Telegram tokens and Discord webhooks are URLs."""

import logging
import traceback

from app.config import settings
from app.utils.diagnostic_redaction import redact_text


def _url_credentials() -> tuple[str, ...]:
    cfg = settings.notifications
    return (cfg.telegram.bot_token or "", cfg.discord.webhook_url or "")


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
