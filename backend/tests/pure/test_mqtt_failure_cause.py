"""A failed MQTT test is reported by its cause, read from the error chain, never as "check logs"."""

import socket

import pytest

from app.services.mqtt_service import mqtt_failure_cause


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        (OSError(-2, "Name or service not known"), "unresolved"),
        (ConnectionRefusedError(111, "Connection refused"), "refused"),
        (TimeoutError(), "timeout"),
        (OSError(113, "No route to host"), "unreachable"),
    ],
)
def test_mqtt_failure_causes_are_read_from_the_error(error, cause):
    if cause == "unresolved":
        error = socket.gaierror(-2, "Name or service not known")
    assert mqtt_failure_cause(error) == cause


def test_a_wrapped_error_is_read_through_its_cause():
    try:
        try:
            raise socket.gaierror(-2, "Name or service not known")
        except socket.gaierror as inner:
            raise RuntimeError("[Errno -2] Name or service not known") from inner
    except RuntimeError as outer:
        assert mqtt_failure_cause(outer) == "unresolved"


def test_refused_credentials_are_named_as_such():
    class _Refused(Exception):
        rc = 5

    assert mqtt_failure_cause(_Refused()) == "auth"
