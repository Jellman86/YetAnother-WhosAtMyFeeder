"""Addresses and connection errors are shown and logged as scheme://host[:port] and nothing more.

Nothing else in an address is needed to recognise which server is meant, and every other part
(userinfo, path, query, fragment) can carry a credential that no list of secrets knows about.
"""

import pytest

from app.utils.diagnostic_redaction import REDACTED_VALUE, redact_address, redact_connection_error


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        # Userinfo, plain and percent-encoded, including an unencoded "@" in the password.
        ("http://admin:hunter2@frigate:5000", "http://frigate:5000"),
        ("https://us%40er:p%40ss%3Aword@frigate.example", "https://frigate.example"),
        ("http://user:p@ss@frigate:5000/api", "http://frigate:5000"),
        ("mqtt://bob:mqttpass@broker:1883", "mqtt://broker:1883"),
        ("bob:mqttpass@broker", "broker"),
        # Path, query and fragment, whatever they hold.
        ("https://gateway/private-access-token/frigate", "https://gateway"),
        ("http://frigate:5000/api?token=abc&camera=feeder#frag", "http://frigate:5000"),
        ("https://gateway:8443/t/0123456789abcdef/?x=1", "https://gateway:8443"),
        # IPv6 hosts keep their brackets and port.
        ("http://[2001:db8::1]:5000/secret-path", "http://[2001:db8::1]:5000"),
        ("http://user:pw@[::1]/frigate", "http://[::1]"),
        ("[fd00::5]:1883", "[fd00::5]:1883"),
        # Plain hosts stay as typed.
        ("broker.local", "broker.local"),
        ("broker.local:1883", "broker.local:1883"),
        ("http://frigate:5000", "http://frigate:5000"),
        ("", ""),
    ],
)
def test_only_scheme_host_and_port_are_shown(address, expected):
    assert redact_address(address) == expected


def test_an_address_that_will_not_parse_shows_nothing_of_itself():
    shown = redact_address("http://[broken:pw@host/private-access-token?token=abc")
    for secret in ("pw", "private-access-token", "abc", "broken"):
        assert secret not in shown
    assert shown == f"http://{REDACTED_VALUE}"


def test_a_port_that_is_not_a_number_is_not_shown():
    assert redact_address("http://frigate:notaport/secret") == f"http://{REDACTED_VALUE}"


def test_connection_errors_reduce_every_embedded_address():
    error = (
        "Failed to connect to https://gateway/private-access-token/frigate/api/version?token=abc123: "
        "mqtt://bob:mqttpass@broker:1883 refused, password=mqttpass auth=xyz; see http://[::1]:5000/x."
    )
    shown = redact_connection_error(error)
    for secret in ("private-access-token", "abc123", "mqttpass", "xyz", "bob", "/x"):
        assert secret not in shown
    assert "https://gateway:" in shown or "https://gateway " in shown
    assert "mqtt://broker:1883" in shown
    assert "http://[::1]:5000." in shown


def test_plain_errors_are_kept_whole():
    for error in (
        "[Errno -2] Name or service not known",
        "Connection refused; the check passed: no",
        "keyboard interrupt",
    ):
        assert redact_connection_error(error) == error
