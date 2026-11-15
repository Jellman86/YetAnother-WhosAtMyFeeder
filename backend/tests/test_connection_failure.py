"""A failed connection test names its cause and the next step, never an exception class or "check logs"."""

import socket

import httpx
import pytest
from aiomqtt import MqttCodeError, MqttError

from app.services.connection_failure import classify_connection_failure, describe_connection_failure


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        (socket.gaierror(-2, "Name or service not known"), "host_not_found"),
        (MqttError("[Errno -2] Name or service not known"), "host_not_found"),
        (httpx.ConnectError("[Errno -3] Temporary failure in name resolution"), "host_not_found"),
        (ConnectionRefusedError(111, "Connection refused"), "refused"),
        (MqttError("[Errno 111] Connection refused"), "refused"),
        (httpx.ConnectError("All connection attempts failed"), "refused"),
        (TimeoutError(), "timeout"),
        (MqttError("Operation timed out"), "timeout"),
        (httpx.ConnectTimeout("timed out"), "timeout"),
        (MqttCodeError(4, "Connection refused"), "not_authorised"),
        (MqttCodeError(5, "Connection refused"), "not_authorised"),
        (MqttError("something else entirely"), "unreachable"),
    ],
)
def test_the_cause_is_read_from_the_error(error, cause):
    assert classify_connection_failure(error) == cause


def test_a_cause_is_found_through_the_chain_of_causes():
    try:
        try:
            raise ConnectionRefusedError(111, "Connection refused")
        except ConnectionRefusedError as inner:
            raise httpx.ConnectError("could not connect") from inner
    except httpx.ConnectError as outer:
        assert classify_connection_failure(outer) == "refused"


@pytest.mark.parametrize("cause", ["host_not_found", "refused", "timeout", "not_authorised", "unreachable"])
def test_every_cause_is_a_sentence_with_a_next_step_and_no_machine_words(cause):
    message = describe_connection_failure(cause, service="the MQTT broker", address="mqtt.invalid:1883")
    assert "Check" in message
    assert "mqtt.invalid:1883" in message or cause == "not_authorised"
    for machine_word in ("logs", "Error", "Errno", "Exception", "("):
        assert machine_word not in message
    assert "—" not in message
