import json
import os
import structlog
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field

log = structlog.get_logger()

# Use /config directory for persistent config (matches Docker volume mount)
CONFIG_PATH = Path("/config/config.json")

class FrigateSettings(BaseModel):
    frigate_url: str = Field(..., description="URL of the Frigate instance")
    frigate_auth_token: Optional[str] = Field(None, description="Optional Bearer token for Frigate proxy auth")
    main_topic: str = "frigate"
    camera: list[str] = Field(default_factory=list, description="List of cameras to monitor")
    mqtt_server: str = "mqtt"
    mqtt_port: int = 1883
    mqtt_auth: bool = False
    mqtt_username: str = ""
    mqtt_password: str = ""

class ClassificationSettings(BaseModel):
    model: str = "model.tflite"
    threshold: float = 0.7
    min_confidence: float = Field(default=0.4, ge=0.0, le=1.0, description="Minimum confidence floor (reject below this)")
    blocked_labels: list[str] = Field(
        default=[],
        description="Labels to filter out completely (won't be saved)"
    )
    unknown_bird_labels: list[str] = Field(
        default=["background", "Background"],
        description="Labels to relabel as 'Unknown Bird' (unidentifiable detections)"
    )

class MaintenanceSettings(BaseModel):
    retention_days: int = Field(default=0, ge=0, description="Days to keep detections (0 = unlimited)")
    cleanup_enabled: bool = Field(default=True, description="Enable automatic cleanup")

class Settings(BaseSettings):
    frigate: FrigateSettings
    classification: ClassificationSettings = ClassificationSettings()
    maintenance: MaintenanceSettings = MaintenanceSettings()
    
    # General app settings
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(env_nested_delimiter='__', env_file='.env', extra='ignore')

    def save(self):
        with open(CONFIG_PATH, 'w') as f:
            f.write(self.model_dump_json(indent=2))
            
    @classmethod
    def load(cls):
        # Build frigate settings from environment variables
        frigate_data = {
            'frigate_url': os.environ.get('FRIGATE__FRIGATE_URL', 'http://frigate:5000'),
            'frigate_auth_token': os.environ.get('FRIGATE__FRIGATE_AUTH_TOKEN', None),
            'main_topic': os.environ.get('FRIGATE__MAIN_TOPIC', 'frigate'),
            'mqtt_server': os.environ.get('FRIGATE__MQTT_SERVER', 'mqtt'),
            'mqtt_port': int(os.environ.get('FRIGATE__MQTT_PORT', '1883')),
            'mqtt_auth': os.environ.get('FRIGATE__MQTT_AUTH', 'false').lower() == 'true',
            'mqtt_username': os.environ.get('FRIGATE__MQTT_USERNAME', ''),
            'mqtt_password': os.environ.get('FRIGATE__MQTT_PASSWORD', ''),
        }

        # Maintenance settings
        maintenance_data = {
            'retention_days': int(os.environ.get('MAINTENANCE__RETENTION_DAYS', '0')),
            'cleanup_enabled': os.environ.get('MAINTENANCE__CLEANUP_ENABLED', 'true').lower() == 'true',
        }

        # Classification settings (loaded from file only, no env vars)
        classification_data = {
            'model': 'model.tflite',
            'threshold': 0.7,
            'min_confidence': 0.4,
            'blocked_labels': [],
            'unknown_bird_labels': ["background", "Background"]
        }

        # Load from config file if it exists, env vars take precedence
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r') as f:
                    file_data = json.load(f)
                # Merge file data with env vars (env vars win)
                # Only use file values if the env var is not set at all
                # (checking 'in os.environ' ensures empty strings from compose defaults are respected)
                if 'frigate' in file_data:
                    for key, value in file_data['frigate'].items():
                        env_key = f'FRIGATE__{key.upper()}'
                        if env_key not in os.environ:
                            frigate_data[key] = value

                if 'maintenance' in file_data:
                    for key, value in file_data['maintenance'].items():
                        env_key = f'MAINTENANCE__{key.upper()}'
                        if env_key not in os.environ:
                            maintenance_data[key] = value

                if 'classification' in file_data:
                    for key, value in file_data['classification'].items():
                        if value is not None:  # Guard against null values in config
                            classification_data[key] = value

                log.info("Loaded config from file", path=str(CONFIG_PATH))
            except Exception as e:
                log.warning("Failed to load config from file", path=str(CONFIG_PATH), error=str(e))

        log.info("MQTT config", server=frigate_data['mqtt_server'], port=frigate_data['mqtt_port'], auth=frigate_data['mqtt_auth'])
        log.info("Maintenance config", retention_days=maintenance_data['retention_days'])
        log.info("Classification config",
                 threshold=classification_data['threshold'],
                 min_confidence=classification_data['min_confidence'],
                 blocked_labels=classification_data['blocked_labels'],
                 unknown_bird_labels=classification_data['unknown_bird_labels'])

        return cls(
            frigate=FrigateSettings(**frigate_data),
            classification=ClassificationSettings(**classification_data),
            maintenance=MaintenanceSettings(**maintenance_data)
        )

settings = Settings.load()