import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config_loader import load_settings_instance
from .config_models import (
    AuthSettings,
    AccessibilitySettings,
    AppearanceSettings,
    BirdWeatherSettings,
    ClassificationSettings,
    EbirdSettings,
    EnrichmentSettings,
    FrigateSettings,
    InaturalistSettings,
    LLMSettings,
    LocationSettings,
    MaintenanceSettings,
    MediaCacheSettings,
    NotificationSettings,
    PublicAccessSettings,
    SystemSettings,
    TelemetrySettings,
    _expand_trusted_hosts,
)

# Use /config directory for persistent config (matches Docker volume mount)
# Allow override via environment variable for testing
if "pytest" in sys.modules or os.getenv("YA_WAMF_TESTING") == "1":
    # Tests run in a sandbox where writing to /config may be blocked.
    # Default to a writable location unless explicitly overridden.
    CONFIG_PATH = Path(os.getenv("CONFIG_FILE", "/tmp/yawamf-test-config.json"))
else:
    CONFIG_PATH = Path(os.getenv("CONFIG_FILE", "/config/config.json"))


class Settings(BaseSettings):
    frigate: FrigateSettings
    classification: ClassificationSettings = ClassificationSettings()
    maintenance: MaintenanceSettings = MaintenanceSettings()
    media_cache: MediaCacheSettings = MediaCacheSettings()
    location: LocationSettings = LocationSettings()
    birdweather: BirdWeatherSettings = BirdWeatherSettings()
    ebird: EbirdSettings = EbirdSettings()
    inaturalist: InaturalistSettings = InaturalistSettings()
    enrichment: EnrichmentSettings = EnrichmentSettings()
    llm: LLMSettings = LLMSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    notifications: NotificationSettings = NotificationSettings()
    accessibility: AccessibilitySettings = AccessibilitySettings()
    appearance: AppearanceSettings = AppearanceSettings()
    system: SystemSettings = SystemSettings()
    auth: AuthSettings = AuthSettings()
    public_access: PublicAccessSettings = PublicAccessSettings()
    species_info_source: str = Field(default="auto", description="Species info source: auto, inat, or wikipedia")
    date_format: str = Field(default="locale", description="Date format: locale, mdy, dmy, ymd")

    # General app settings
    log_level: str = "INFO"
    api_key: Optional[str] = None

    model_config = SettingsConfigDict(env_nested_delimiter="__", env_file=".env", extra="ignore")

    async def save(self):
        # Avoid aiofiles here: in this environment it can hang indefinitely.
        # asyncio.to_thread keeps the API async without relying on aiofiles.
        payload = self.model_dump_json(indent=2)
        path = CONFIG_PATH

        # Tests run in a sandbox and config persistence isn't what we're validating.
        # Keep this simple and synchronous to avoid executor/FS edge cases.
        if "pytest" in sys.modules or os.getenv("YA_WAMF_TESTING") == "1":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            return

        def _write_atomic() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)

        await asyncio.to_thread(_write_atomic)

    @classmethod
    def load(cls):
        return load_settings_instance(cls, CONFIG_PATH)


settings = Settings.load()

__all__ = [
    "CONFIG_PATH",
    "Settings",
    "settings",
    "_expand_trusted_hosts",
    "FrigateSettings",
    "ClassificationSettings",
    "MaintenanceSettings",
    "MediaCacheSettings",
    "LocationSettings",
    "BirdWeatherSettings",
    "EbirdSettings",
    "InaturalistSettings",
    "EnrichmentSettings",
    "LLMSettings",
    "TelemetrySettings",
    "NotificationSettings",
    "AccessibilitySettings",
    "AppearanceSettings",
    "SystemSettings",
    "AuthSettings",
    "PublicAccessSettings",
]
