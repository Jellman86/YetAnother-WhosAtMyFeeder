"""Record what the MQTT broker session and Frigate's API actually did.

Both trackers are plain state holders with the time passed in, so the rules about what counts
as connected or reachable are tested without a broker, a Frigate or a clock.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.models.service_connections import (
    FrigateApiState,
    FrigateApiStatus,
    FrigateAvailability,
    FrigateFailureKind,
    MqttConnectionState,
    MqttConnectionStatus,
)
from app.utils.api_datetime import serialize_api_datetime

_MAX_ERROR_LENGTH = 200


class MqttConnectionTracker:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._on_change = on_change
        self.state: MqttConnectionState = "stopped"
        self.connected_since: datetime | None = None
        self.last_attempt_at: datetime | None = None
        self.last_failure_at: datetime | None = None
        self.last_error: str | None = None

    def _set_state(self, state: MqttConnectionState) -> None:
        if state == self.state:
            return
        self.state = state
        if self._on_change is not None:
            self._on_change()

    def attempting(self, now: datetime) -> None:
        self.last_attempt_at = now
        # A broker that failed stays reported as down while it is retried; only a
        # completed connection changes that.
        if self.state != "disconnected":
            self._set_state("connecting")

    def connected(self, now: datetime) -> None:
        self.connected_since = now
        self._set_state("connected")

    def failed(self, now: datetime, error: str) -> None:
        self.connected_since = None
        self.last_failure_at = now
        self.last_error = error.strip()[:_MAX_ERROR_LENGTH] or None
        self._set_state("disconnected")

    def not_configured(self) -> None:
        self.connected_since = None
        self._set_state("not_configured")

    def stopped(self) -> None:
        self.connected_since = None
        self._set_state("stopped")

    def snapshot(self, *, server: str, port: int) -> MqttConnectionStatus:
        return MqttConnectionStatus(
            state=self.state,
            server=server,
            port=port,
            connected_since=serialize_api_datetime(self.connected_since),
            last_attempt_at=serialize_api_datetime(self.last_attempt_at),
            last_failure_at=serialize_api_datetime(self.last_failure_at),
            last_error=self.last_error,
        )


class FrigateReachabilityTracker:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._on_change = on_change
        self.reset()

    def reset(self) -> None:
        self.state: FrigateApiState = "unchecked"
        self.checked_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.last_failure_at: datetime | None = None
        self.last_failure: FrigateFailureKind | None = None

    def _set_state(self, state: FrigateApiState) -> None:
        if state == self.state:
            return
        self.state = state
        if self._on_change is not None:
            self._on_change()

    def record_response(self, status_code: int, now: datetime) -> None:
        # A missing event or a bad query is still Frigate answering. Refusing our token or
        # failing on its own side means nothing it serves can be used.
        if status_code in (401, 403):
            self.record_failure("unauthorized", now)
        elif status_code >= 500:
            self.record_failure("server_error", now)
        else:
            self.checked_at = now
            self.last_success_at = now
            self.last_failure = None
            self._set_state("reachable")

    def record_failure(self, kind: FrigateFailureKind, now: datetime) -> None:
        self.checked_at = now
        self.last_failure_at = now
        self.last_failure = kind
        self._set_state("unreachable")

    def age_seconds(self, now: datetime) -> float | None:
        if self.checked_at is None:
            return None
        return (now - self.checked_at).total_seconds()

    def snapshot(self, *, url: str, availability: FrigateAvailability) -> FrigateApiStatus:
        return FrigateApiStatus(
            state=self.state,
            url=url,
            checked_at=serialize_api_datetime(self.checked_at),
            last_success_at=serialize_api_datetime(self.last_success_at),
            last_failure_at=serialize_api_datetime(self.last_failure_at),
            last_failure=self.last_failure,
            availability=availability,
        )
