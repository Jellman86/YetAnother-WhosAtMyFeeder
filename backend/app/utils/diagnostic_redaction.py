"""Bounded diagnostic copies and credential redaction without raw errors."""

from collections.abc import Sequence
import json
import math
import re
from typing import Any
from urllib.parse import quote, quote_plus

REDACTED_VALUE = "***REDACTED***"
SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "api_key",
        "frigate_auth_token",
        "mqtt_password",
        "station_token",
        "webhook_url",
        "user_key",
        "api_token",
        "bot_token",
        "chat_id",
        "smtp_password",
        "gmail_client_secret",
        "outlook_client_secret",
        "client_secret",
        "oauth_client_secret",
        "token",
        "password",
        "access_token",
        "session_secret",
        "password_hash",
        "oauth_token_secret",
    }
)
# Fail closed for future secret-bearing settings: a new field whose name is
# secret-shaped must not leak just because nobody updated the set above.
SENSITIVE_KEY_SUFFIXES = ("_secret", "_token", "_password", "_hash")


def sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return (
        normalized in SENSITIVE_CONFIG_KEYS
        or normalized in {"authorization", "proxy_authorization", "cookie", "set_cookie", "x_api_key", "apikey"}
        or normalized.endswith(SENSITIVE_KEY_SUFFIXES)
    )


def configured_secrets() -> tuple[str, ...]:
    # Read current values while sanitizing, without caching old credentials.
    from app.config import settings

    values: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if sensitive_key(key) and isinstance(item, str) and item and item != REDACTED_VALUE:
                    values.add(item)
                else:
                    visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(settings.model_dump(mode="json"))
    return tuple(values)


_CREDENTIAL_PATTERNS = (
    (re.compile(r"(https?://api\.telegram\.org/(?:file/)?bot)[^/\s\"'<>]+", re.I), r"\1" + REDACTED_VALUE),
    (re.compile(r"(https?://app\.birdweather\.com/api/v1/stations/)[^/\s\"'<>]+", re.I), r"\1" + REDACTED_VALUE),
    (re.compile(r"(https?://)[^/\s:@]+(?::[^/\s@]*)?@", re.I), r"\1" + REDACTED_VALUE + "@"),
    (
        re.compile(r"(https?://(?:discord\.com|discordapp\.com)/api/webhooks/)[^/\s]+/[^/\s\"'<>]+", re.I),
        r"\1" + REDACTED_VALUE,
    ),
    (re.compile(r"\b((?:Bearer|Basic)\s+)[A-Za-z0-9._~+/-]+=*", re.I), r"\1" + REDACTED_VALUE),
    (re.compile(r"(\b(?:set-cookie|cookie)\s*:\s*)[^\r\n]+", re.I), r"\1" + REDACTED_VALUE),
    (
        re.compile(
            r"""((?:["']?)\b(?:password|token|secret|api[_-]?key|authorization|[\w-]{1,64}[_-](?:token|secret|password|key))["']?\s*[:=]\s*["']?)[^"'&,;\s<>]+""",
            re.I,
        ),
        r"\1" + REDACTED_VALUE,
    ),
)


def _known_pattern(secrets: Sequence[str]) -> re.Pattern[str] | None:
    variants = {
        variant
        for secret in secrets
        if secret and secret != REDACTED_VALUE
        for variant in (secret, quote(secret, safe=""), quote_plus(secret), json.dumps(secret)[1:-1])
    }
    return (
        re.compile("|".join(re.escape(value) for value in sorted(variants, key=len, reverse=True)))
        if variants
        else None
    )


def _redact_text(text: str, known: re.Pattern[str] | None) -> str:
    # Preserve markers on repeated exports, even with short credentials.
    pieces = text.split(REDACTED_VALUE)
    for index, piece in enumerate(pieces):
        # Recognize credential URLs before known-value replacement can obscure
        # their hostname/key. Protect newly inserted markers from short secrets.
        for pattern, replacement in _CREDENTIAL_PATTERNS:
            piece = pattern.sub(replacement, piece)
        if known is not None:
            piece = REDACTED_VALUE.join(
                known.sub(lambda _match: REDACTED_VALUE, segment) for segment in piece.split(REDACTED_VALUE)
            )
        pieces[index] = piece
    return REDACTED_VALUE.join(pieces)


def redact_text(text: str, secrets: Sequence[str] = ()) -> str:
    return _redact_text(text, _known_pattern(secrets))


def redact_diagnostic(value: Any, secrets: Sequence[str] = ()) -> Any:
    known = _known_pattern(secrets)
    remaining = 512

    def copy(item: Any, depth: int = 0) -> Any:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 8:
            return "[truncated]"
        if isinstance(item, str):
            return _redact_text(item, known)[:2048]
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            return item if math.isfinite(item) else None
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for index, (key, child) in enumerate(item.items()):
                if index >= 64 or remaining <= 0:
                    result["__truncated__"] = True
                    break
                name = key if isinstance(key, str) else type(key).__name__
                result[_redact_text(name, known)[:256]] = (
                    REDACTED_VALUE if sensitive_key(name) and child else copy(child, depth + 1)
                )
            return result
        if isinstance(item, (list, tuple)):
            result = []
            for index, child in enumerate(item):
                if index >= 64 or remaining <= 0:
                    result.append("[truncated]")
                    break
                result.append(copy(child, depth + 1))
            return result
        return f"[{type(item).__name__}]"

    return copy(value)
