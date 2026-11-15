"""Why a connection test failed, in words a person can act on.

A diagnostic that answers "check logs" or names an exception class has told its reader
nothing. The cause is read from the error itself and stated with the next step.
"""

from typing import Literal
from urllib.parse import urlsplit

ConnectionFailure = Literal["host_not_found", "refused", "timeout", "not_authorised", "unreachable"]
ConnectionService = Literal["mqtt", "birdnet"]

# The English names used in the fallback sentence; the page names the service in its own language.
_SERVICE_NAMES: dict[ConnectionService, str] = {"mqtt": "the MQTT broker", "birdnet": "BirdNET-Go"}

# MQTT 3.1.1 answers 4 (bad user name or password) and 5 (not authorised); MQTT 5 uses 134 and 135.
_NOT_AUTHORISED_CODES = frozenset({4, 5, 134, 135})
_HOST_NOT_FOUND_MARKERS = ("name or service not known", "name resolution", "nodename nor servname", "getaddrinfo")
_REFUSED_MARKERS = ("connection refused", "all connection attempts failed")
_TIMEOUT_MARKERS = ("timed out", "timeout")


def _chain(error: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in seen:
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def classify_connection_failure(error: BaseException) -> ConnectionFailure:
    """The cause of a failed connection, from the error and whatever caused it."""
    import socket

    chain = _chain(error)
    for link in chain:
        code = getattr(getattr(link, "rc", None), "value", getattr(link, "rc", None))
        if isinstance(code, int) and code in _NOT_AUTHORISED_CODES:
            return "not_authorised"
    for link in chain:
        text = str(link).lower()
        if isinstance(link, socket.gaierror) or any(marker in text for marker in _HOST_NOT_FOUND_MARKERS):
            return "host_not_found"
    for link in chain:
        text = str(link).lower()
        if isinstance(link, TimeoutError) or "timeout" in type(link).__name__.lower():
            return "timeout"
        if any(marker in text for marker in _TIMEOUT_MARKERS):
            return "timeout"
    for link in chain:
        if isinstance(link, ConnectionRefusedError) or any(marker in str(link).lower() for marker in _REFUSED_MARKERS):
            return "refused"
    return "unreachable"


def describe_connection_failure(cause: ConnectionFailure, *, service: str, address: str) -> str:
    """One sentence for the cause and one for what to check; ``service`` reads like "the MQTT broker"."""
    named = f"{service[0].upper()}{service[1:]}"
    if cause == "host_not_found":
        return f"The host name in {address} was not found. Check the address for {service}."
    if cause == "refused":
        return f"Nothing answered at {address}. Check that {service} is running and that the port is right."
    if cause == "timeout":
        return f"{named} did not answer at {address} in time. Check the address and that this machine can reach it."
    if cause == "not_authorised":
        return f"{named} refused the user name or password. Check them, or turn authentication off if it accepts anonymous clients."
    return f"Could not connect to {service} at {address}. Check the address and the port."


def reduced_address(address: str) -> str:
    """Host and port only: no scheme, user, password, path or query ever leaves in a failure."""
    parts = urlsplit(address if "//" in address else f"//{address}")
    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{host}:{port}" if host and port else host


def connection_failure_payload(cause: ConnectionFailure, *, service: ConnectionService, address: str) -> dict[str, str]:
    """What a failed connection test answers: a stable cause code, the service, and the reduced address.

    The page translates the cause and its next step from the code. ``message`` is the same thing in
    English, for clients that read nothing else.
    """
    safe_address = reduced_address(address)
    return {
        "status": "error",
        "cause": cause,
        "service": service,
        "address": safe_address,
        "message": describe_connection_failure(cause, service=_SERVICE_NAMES[service], address=safe_address),
    }
