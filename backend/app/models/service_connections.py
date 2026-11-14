"""What this instance has measured about its connections to the MQTT broker and Frigate.

Every field is a measurement or null. Nothing here is inferred from configuration, so a page
that reads it can only claim a connection state that was actually observed.
"""

from typing import Literal

from pydantic import BaseModel, Field

MqttConnectionState = Literal["connecting", "connected", "disconnected", "not_configured", "stopped"]
FrigateApiState = Literal["reachable", "unreachable", "unchecked"]
FrigateFailureKind = Literal["timeout", "connection", "unauthorized", "server_error"]
FrigateAvailability = Literal["online", "offline", "unknown"]


class MqttConnectionStatus(BaseModel):
    """The broker session, as the MQTT service last saw it."""

    state: MqttConnectionState = Field(
        description=(
            "connecting: the first attempt since start has not finished. connected: subscribed and "
            "receiving. disconnected: the last attempt failed or the session dropped; it keeps "
            "retrying. not_configured: no broker address is saved. stopped: the service is not running."
        )
    )
    server: str = Field(description="The broker host the service connects to.")
    port: int
    connected_since: str | None = Field(default=None, description="UTC time the current session started.")
    last_attempt_at: str | None = Field(default=None, description="UTC time of the latest connection attempt.")
    last_failure_at: str | None = Field(default=None, description="UTC time the latest attempt or session failed.")
    last_error: str | None = Field(default=None, description="The broker client's own words for that failure.")


class FrigateApiStatus(BaseModel):
    """Frigate's HTTP API, judged by the latest request this instance made to it."""

    state: FrigateApiState = Field(
        description=(
            "reachable: the latest request was answered. unreachable: it was not, or Frigate refused "
            "it or failed. unchecked: no request has been made since this instance started."
        )
    )
    url: str = Field(description="The Frigate address requests go to.")
    checked_at: str | None = Field(default=None, description="UTC time of the latest request.")
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_failure: FrigateFailureKind | None = Field(
        default=None, description="Why the latest failed request failed, when the latest request failed."
    )
    availability: FrigateAvailability = Field(
        default="unknown",
        description="What Frigate last announced on its MQTT availability topic; unknown without the broker.",
    )


class ServiceConnectionsResponse(BaseModel):
    """The two connections every detection depends on."""

    mqtt: MqttConnectionStatus
    frigate: FrigateApiStatus
    generated_at: str
