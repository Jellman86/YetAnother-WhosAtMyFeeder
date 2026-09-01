"""The settings a viewer legitimately needs, and nothing else.

`/api/settings` is owner-only and returns everything, so the SPA had no way to read
a single display preference as a guest. Every setting that shapes what a visitor
sees was therefore copied onto `/api/auth/status` one field at a time as somebody
noticed it was missing, which only ever finds a defect after a visitor has already
been given the wrong interface.

This module is the decision point. A setting is public because it is declared here,
not because anyone remembered, and because the projection names its fields rather
than filtering a copy of the settings, a secret added later cannot arrive in it by
accident.
"""

from pydantic import BaseModel, Field

from app.config import settings


class PublicSettings(BaseModel):
    """Display preferences served identically to a guest and to an owner."""

    # Below this score a visit is flagged as needing a person. Without it a guest
    # saw no row flagged at all, while the layout standard names that flag as one
    # of the three signals a visit carries.
    classification_threshold: float = Field(description="Score below which a detection is flagged as needing review")
    # The window the nearby-sightings panel reports. The radius beside it already
    # travelled publicly, so a guest read a real radius against a default window.
    ebird_default_days_back: int = Field(description="Days back used for nearby eBird sightings")
    # Whether clips exist at all. Whether a guest may download one is a separate
    # decision that `public_access_allow_clip_downloads` already makes.
    clips_enabled: bool = Field(description="Whether Frigate clip capture is enabled")
    recording_clip_enabled: bool = Field(description="Whether recording-backed clips are enabled")


PUBLIC_SETTING_FIELDS: tuple[str, ...] = tuple(PublicSettings.model_fields)


def build_public_settings() -> PublicSettings:
    """Read the projection from configuration. Pure enough to test on its own."""
    return PublicSettings(
        classification_threshold=settings.classification.threshold,
        ebird_default_days_back=settings.ebird.default_days_back,
        clips_enabled=settings.frigate.clips_enabled,
        recording_clip_enabled=settings.frigate.recording_clip_enabled,
    )
