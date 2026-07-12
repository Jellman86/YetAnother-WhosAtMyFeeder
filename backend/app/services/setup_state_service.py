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

from pydantic import BaseModel

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


class SetupState(BaseModel):
    initial_setup_complete: bool
    sections: list[SetupSectionState]


def _account(settings) -> SetupSectionState:
    auth = settings.auth
    if getattr(auth, "password_hash", None):
        return SetupSectionState(id="account", status="ok", detail="Password protected")
    if getattr(auth, "initial_setup_complete", False):
        return SetupSectionState(id="account", status="ok", detail="Authentication disabled")
    return SetupSectionState(id="account", status="attention", detail="Not configured")


def _connection(settings) -> SetupSectionState:
    url = (settings.frigate.frigate_url or "").strip()
    if url.startswith(("http://", "https://")):
        return SetupSectionState(id="connection", status="ok", detail=url)
    return SetupSectionState(id="connection", status="attention", detail="Frigate URL not set")


def _cameras(settings) -> SetupSectionState:
    cameras = settings.frigate.camera or []
    if cameras:
        label = "1 camera" if len(cameras) == 1 else f"{len(cameras)} cameras"
        return SetupSectionState(id="cameras", status="ok", detail=label)
    return SetupSectionState(id="cameras", status="attention", detail="No cameras selected")


def _model(settings) -> SetupSectionState:
    # A bundled classifier always ships, so this is functional out of the box.
    return SetupSectionState(id="model", status="ok", detail=settings.classification.model or None)


def _quality(settings) -> SetupSectionState:
    # HQ snapshot / crop settings have working defaults; always functional.
    return SetupSectionState(
        id="quality", status="ok", detail=settings.classification.bird_crop_source_priority
    )


def _integrations(settings) -> SetupSectionState:
    notifications = settings.notifications
    enabled: list[str] = []
    if settings.frigate.birdnet_enabled:
        enabled.append("BirdNET-Go")
    if any(
        getattr(getattr(notifications, channel, None), "enabled", False)
        for channel in ("discord", "pushover", "telegram", "email")
    ):
        enabled.append("Notifications")
    if settings.ebird.enabled:
        enabled.append("eBird")
    if settings.inaturalist.enabled:
        enabled.append("iNaturalist")
    if settings.birdweather.enabled:
        enabled.append("BirdWeather")
    if settings.llm.enabled:
        enabled.append("AI analysis")
    if enabled:
        return SetupSectionState(id="integrations", status="ok", detail=", ".join(enabled))
    return SetupSectionState(id="integrations", status="optional", detail="None enabled")


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
