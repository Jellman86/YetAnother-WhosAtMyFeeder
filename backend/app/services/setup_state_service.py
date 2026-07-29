"""Per-section setup readiness for the first-run / re-runnable setup wizard.

The wizard is a guided editor over the normal config (`/api/settings`); this service
answers the cheap, deterministic question "which sections look configured?" so both the
first-run flow and the re-run section map can render ✅/⚠/optional markers without the SPA
re-deriving readiness rules. Live connection checks stay in the per-step *test* endpoints.

The core is a pure function over a settings object so it is unit-testable without a live
Frigate/MQTT/model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.model_manager import is_retired_model, registry_artifact_kind

# Section ids line up with the wizard steps (welcome/language is not a config section).
SETUP_SECTION_IDS = ("account", "connection", "cameras", "model", "quality", "integrations")

SectionStatus = Literal["ok", "attention", "optional"]


class SetupSectionState(BaseModel):
    """Readiness of one wizard section.

    - ``ok``: functional (explicitly configured, or a working default).
    - ``attention``: needs the user's input to work properly (e.g. no Frigate URL, no cameras).
    - ``optional``: an optional feature that is simply not enabled.
    """

    id: str
    status: SectionStatus
    detail: str | None = None
    detail_code: str | None = None
    detail_values: dict[str, str | int] = Field(default_factory=dict)


class SetupState(BaseModel):
    initial_setup_complete: bool
    sections: list[SetupSectionState]


def _account(settings) -> SetupSectionState:
    auth = settings.auth
    if getattr(auth, "password_hash", None):
        return SetupSectionState(
            id="account", status="ok", detail="Password protected", detail_code="account_password_protected"
        )
    if getattr(auth, "initial_setup_complete", False):
        return SetupSectionState(
            id="account", status="ok", detail="Authentication disabled", detail_code="account_auth_disabled"
        )
    return SetupSectionState(
        id="account", status="attention", detail="Not configured", detail_code="account_not_configured"
    )


def _connection(settings) -> SetupSectionState:
    url = (settings.frigate.frigate_url or "").strip()
    mqtt_server = (settings.frigate.mqtt_server or "").strip()
    missing: list[str] = []
    if not url.startswith(("http://", "https://")):
        missing.append("Frigate URL")
    if not mqtt_server:
        missing.append("MQTT broker")
    if settings.frigate.mqtt_auth and not (settings.frigate.mqtt_username or "").strip():
        missing.append("MQTT username")
    if settings.frigate.mqtt_auth and not settings.frigate.mqtt_password:
        missing.append("MQTT password")
    if not missing:
        return SetupSectionState(
            id="connection", status="ok", detail=url, detail_code="connection_ready", detail_values={"url": url}
        )
    missing_codes = {
        "Frigate URL": "frigate_url",
        "MQTT broker": "mqtt_broker",
        "MQTT username": "mqtt_username",
        "MQTT password": "mqtt_password",
    }
    return SetupSectionState(
        id="connection",
        status="attention",
        detail=f"Set {', '.join(missing)}",
        detail_code="connection_missing",
        detail_values={"items": ",".join(missing_codes[item] for item in missing)},
    )


def _cameras(settings) -> SetupSectionState:
    cameras = settings.frigate.camera or []
    if cameras:
        label = "1 camera" if len(cameras) == 1 else f"{len(cameras)} cameras"
        return SetupSectionState(
            id="cameras", status="ok", detail=label, detail_code="cameras_count", detail_values={"count": len(cameras)}
        )
    return SetupSectionState(id="cameras", status="ok", detail="All cameras", detail_code="cameras_all")


def _model(settings) -> SetupSectionState:
    # A bundled classifier always ships, so this is functional out of the box.
    model_id = str(settings.classification.model or "").strip()
    if is_retired_model(model_id):
        return SetupSectionState(
            id="model",
            status="attention",
            detail="The saved classifier has been retired",
            detail_code="model_retired",
        )
    if model_id and registry_artifact_kind(model_id) != "classifier":
        return SetupSectionState(
            id="model",
            status="attention",
            detail="A crop detector is selected as the classifier",
            detail_code="model_wrong_kind",
        )
    if model_id:
        return SetupSectionState(
            id="model", status="ok", detail=model_id, detail_code="model_selected", detail_values={"model": model_id}
        )
    return SetupSectionState(id="model", status="ok", detail="Bundled fallback", detail_code="model_fallback")


def _quality(settings) -> SetupSectionState:
    # HQ snapshot / crop settings have working defaults; always functional.
    detail = "Best available snapshots" if settings.media_cache.high_quality_event_snapshots else "Standard snapshots"
    return SetupSectionState(
        id="quality",
        status="ok",
        detail=detail,
        detail_code="quality_best" if settings.media_cache.high_quality_event_snapshots else "quality_standard",
    )


def _integrations(settings) -> SetupSectionState:
    notifications = settings.notifications
    configured: list[str] = []
    incomplete: list[str] = []
    if settings.frigate.birdnet_enabled:
        target = configured if settings.frigate.mqtt_server and settings.frigate.audio_topic else incomplete
        target.append("BirdNET-Go")

    enabled_notification_channels = [
        channel
        for channel in ("discord", "pushover", "telegram", "email")
        if getattr(getattr(notifications, channel, None), "enabled", False)
    ]
    if enabled_notification_channels:
        notification_ready = True
        if "discord" in enabled_notification_channels:
            notification_ready = notification_ready and bool(notifications.discord.webhook_url)
        if "pushover" in enabled_notification_channels:
            notification_ready = notification_ready and bool(
                notifications.pushover.user_key and notifications.pushover.api_token
            )
        if "telegram" in enabled_notification_channels:
            notification_ready = notification_ready and bool(
                notifications.telegram.bot_token and notifications.telegram.chat_id
            )
        if "email" in enabled_notification_channels:
            email = notifications.email
            if email.use_oauth:
                provider = str(email.oauth_provider or "").lower()
                notification_ready = notification_ready and (
                    bool(email.gmail_client_id and email.gmail_client_secret)
                    if provider == "gmail"
                    else bool(email.outlook_client_id and email.outlook_client_secret)
                    if provider == "outlook"
                    else False
                )
            else:
                notification_ready = notification_ready and bool(
                    email.smtp_host and email.from_email and email.to_email
                )
        (configured if notification_ready else incomplete).append("Notifications")

    if settings.ebird.enabled:
        (configured if settings.ebird.api_key else incomplete).append("eBird")
    if settings.inaturalist.enabled:
        (configured if settings.inaturalist.client_id and settings.inaturalist.client_secret else incomplete).append(
            "iNaturalist"
        )
    if settings.birdweather.enabled:
        (configured if settings.birdweather.station_token else incomplete).append("BirdWeather")
    if settings.llm.enabled:
        (configured if settings.llm.api_key else incomplete).append("AI analysis")

    if incomplete:
        detail = f"Needs setup: {', '.join(incomplete)}"
        if configured:
            detail += f" · Configured: {', '.join(configured)}"
        return SetupSectionState(
            id="integrations",
            status="attention",
            detail=detail,
            detail_code="integrations_incomplete",
            detail_values={"incomplete": ", ".join(incomplete), "configured": ", ".join(configured)},
        )
    if configured:
        return SetupSectionState(
            id="integrations",
            status="ok",
            detail=", ".join(configured),
            detail_code="integrations_configured",
            detail_values={"configured": ", ".join(configured)},
        )
    return SetupSectionState(
        id="integrations", status="optional", detail="None enabled", detail_code="integrations_none"
    )


def compute_setup_state(settings) -> SetupState:
    """Derive per-section readiness from the current settings (pure, no I/O)."""
    return SetupState(
        initial_setup_complete=bool(getattr(settings.auth, "initial_setup_complete", False)),
        sections=[
            _account(settings),
            _connection(settings),
            _cameras(settings),
            _model(settings),
            _quality(settings),
            _integrations(settings),
        ],
    )
