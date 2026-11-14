"""Connection-error redaction runs on every verbose HTTP client log line, so its cost must grow
linearly with the line: a long debug message must never stall the request that logged it."""

import time

import pytest

from app.utils.diagnostic_redaction import redact_connection_error


@pytest.mark.parametrize(
    "text",
    [
        "a" * 200_000,  # one long scheme-like run with no "://"
        "a-" * 100_000,  # many word boundaries inside one name-like run
        "a." * 100_000,
        "token" * 40_000,  # a credential keyword with no ":" or "=" after it
        "http:/" * 30_000,
    ],
    ids=["letters", "hyphenated", "dotted", "keyword", "near-address"],
)
def test_redaction_of_a_long_line_takes_linear_time(text):
    started = time.perf_counter()
    redact_connection_error(text, mark_dropped=True)
    # Linear scanning takes a few milliseconds here; the quadratic patterns took minutes.
    assert time.perf_counter() - started < 1.0


def test_addresses_and_named_credentials_are_still_found_inside_long_text():
    padding = "a-" * 20_000
    text = f"{padding} cannot reach 9https://user:pw@frigate.example:8443/private-path. x-api-token=abc123 {padding}"

    redacted = redact_connection_error(text, mark_dropped=True)

    for secret in ("user", "pw@", "private-path", "abc123"):
        assert secret not in redacted
    assert "9https://frigate.example:8443/***REDACTED***. " in redacted
    assert "x-api-token=***REDACTED***" in redacted
