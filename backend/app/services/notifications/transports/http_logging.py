"""Verbose HTTP logs print request URLs, and Telegram tokens, Discord webhooks and reverse-proxied
integration addresses carry credentials in them.

Every address in an HTTP client log line is reduced to ``scheme://host[:port]``: a token in the
path of a configured Frigate, BirdNET-Go or Home Assistant URL is not a setting anyone names as a
secret, so filtering known values alone would let it through.
"""

import logging
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.config import settings
from app.utils.diagnostic_redaction import configured_secrets, redact_connection_error

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
        *configured_secrets(),
    )


# A debug body dump is no use in a log line. Lines are cut after redaction, so a cut can never
# split a credential into a part that is no longer recognised.
_MAX_LOGGED_CHARS = 8192
_WITHHELD = "HTTP client log line withheld: it could not be checked for credentials"


class _NotificationCredentialLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            self._redact(record)
        except Exception:  # A log filter that raises breaks the request that logged.
            record.msg, record.args = _WITHHELD, ()
            record.exc_info, record.exc_text = None, None
        return True

    @staticmethod
    def _redact(record: logging.LogRecord) -> None:
        message = record.getMessage()
        secrets = _url_credentials()
        sanitized = redact_connection_error(message, secrets, mark_dropped=True)
        if len(sanitized) > _MAX_LOGGED_CHARS:
            sanitized = sanitized[:_MAX_LOGGED_CHARS] + " [truncated]"
        if sanitized != message:
            record.msg, record.args = sanitized, ()
        if record.exc_info:
            record.exc_text = redact_connection_error(
                "".join(traceback.format_exception(*record.exc_info)), secrets, mark_dropped=True
            )
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_connection_error(record.exc_text, secrets, mark_dropped=True)


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
