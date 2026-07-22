"""Validation shared by owner-driven server-to-server integration diagnostics."""

import httpx


def validated_http_base_url(value: str | None, *, integration_name: str) -> str:
    """Return a credential-free HTTP(S) base URL suitable for an integration probe."""
    candidate = str(value or "").strip().rstrip("/")
    if not candidate:
        raise ValueError(f"{integration_name} URL is empty")
    try:
        parsed = httpx.URL(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{integration_name} URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise ValueError(f"{integration_name} URL must use http:// or https://")
    if parsed.username or parsed.password:
        raise ValueError(f"{integration_name} URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{integration_name} URL must not contain a query string or fragment")
    return candidate
