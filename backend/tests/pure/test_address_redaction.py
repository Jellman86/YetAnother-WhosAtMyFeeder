"""Addresses and connection errors are shown and logged without the credentials they may carry."""

import pytest

from app.utils.diagnostic_redaction import REDACTED_VALUE, redact_address, redact_connection_error


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("http://admin:hunter2@frigate:5000", "http://frigate:5000"),
        ("https://user@frigate.example/api", "https://frigate.example/api"),
        ("mqtt://bob:mqttpass@broker:1883", "mqtt://broker:1883"),
        ("bob:mqttpass@broker", "broker"),
        ("broker.local", "broker.local"),
        ("http://frigate:5000", "http://frigate:5000"),
    ],
)
def test_userinfo_is_stripped_from_any_address(address, expected):
    assert redact_address(address) == expected


@pytest.mark.parametrize(
    "parameter",
    [
        "token",
        "access_token",
        "api_key",
        "apikey",
        "key",
        "password",
        "pass",
        "secret",
        "client_secret",
        "auth",
        "authorization",
        "sig",
        "signature",
    ],
)
def test_secret_shaped_query_values_are_redacted(parameter):
    address = redact_address(f"http://frigate:5000/api?{parameter}=s3cr3t&camera=feeder")
    assert "s3cr3t" not in address
    assert f"{parameter}={REDACTED_VALUE}" in address
    assert "camera=feeder" in address


def test_a_known_secret_anywhere_in_the_address_is_redacted():
    assert "pathsecret" not in redact_address("http://frigate:5000/pathsecret/api", secrets=("pathsecret",))


def test_an_address_that_will_not_parse_is_still_redacted():
    shown = redact_address("http://[broken:pw@host?token=abc", secrets=("pw",))
    assert "abc" not in shown
    assert ":pw@" not in shown


def test_connection_errors_lose_embedded_credentials():
    error = (
        "Failed to connect to http://admin:hunter2@frigate:5000/api/version?token=abc123: "
        "mqtt://bob:mqttpass@broker refused, password=mqttpass auth=xyz"
    )
    shown = redact_connection_error(error, secrets=("mqttpass",))
    for secret in ("hunter2", "abc123", "mqttpass", "xyz", "admin:", "bob:"):
        assert secret not in shown
    assert "frigate:5000/api/version" in shown


def test_plain_errors_are_kept_whole():
    for error in (
        "[Errno -2] Name or service not known",
        "Connection refused; the check passed: no",
        "keyboard interrupt",
    ):
        assert redact_connection_error(error) == error
