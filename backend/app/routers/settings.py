from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

router = APIRouter()
log = structlog.get_logger()

class SettingsUpdate(BaseModel):
    frigate_url: str = Field(..., min_length=1, description="Frigate instance URL")
    mqtt_server: str = Field(..., min_length=1, description="MQTT server hostname")
    mqtt_port: int = Field(1883, ge=1, le=65535, description="MQTT server port")
    mqtt_auth: bool = Field(False, description="Enable MQTT authentication")
    mqtt_username: Optional[str] = Field(None, description="MQTT username")
    mqtt_password: Optional[str] = Field(None, description="MQTT password")
    classification_threshold: float = Field(..., ge=0.0, le=1.0, description="Classification confidence threshold (0-1)")
    cameras: List[str] = Field(default_factory=list, description="List of cameras to monitor")
    retention_days: int = Field(0, ge=0, description="Days to keep detections (0 = unlimited)")
    blocked_labels: List[str] = Field(default_factory=list, description="Labels to filter out from detections")

    @field_validator('frigate_url')
    @classmethod
    def validate_frigate_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError('frigate_url must start with http:// or https://')
        return v.rstrip('/')

@router.get("/settings")
async def get_settings():
    return {
        "frigate_url": settings.frigate.frigate_url,
        "mqtt_server": settings.frigate.mqtt_server,
        "mqtt_port": settings.frigate.mqtt_port,
        "mqtt_auth": settings.frigate.mqtt_auth,
        "mqtt_username": settings.frigate.mqtt_username,
        "mqtt_password": settings.frigate.mqtt_password,
        "classification_threshold": settings.classification.threshold,
        "cameras": settings.frigate.camera,
        "retention_days": settings.maintenance.retention_days,
        "blocked_labels": settings.classification.blocked_labels
    }

@router.post("/settings")
async def update_settings(update: SettingsUpdate):
    settings.frigate.frigate_url = update.frigate_url
    settings.frigate.mqtt_server = update.mqtt_server
    settings.frigate.mqtt_port = update.mqtt_port
    settings.frigate.mqtt_auth = update.mqtt_auth
    if update.mqtt_username is not None:
        settings.frigate.mqtt_username = update.mqtt_username
    if update.mqtt_password is not None:
        settings.frigate.mqtt_password = update.mqtt_password

    settings.frigate.camera = update.cameras
    settings.classification.threshold = update.classification_threshold
    settings.maintenance.retention_days = update.retention_days
    settings.classification.blocked_labels = update.blocked_labels
    settings.save()
    return {"status": "updated"}

@router.get("/maintenance/stats")
async def get_maintenance_stats():
    """Get database maintenance statistics."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        total_count = await repo.get_count()
        oldest_date = await repo.get_oldest_detection_date()

        # Calculate how many would be deleted with current retention
        to_delete = 0
        if settings.maintenance.retention_days > 0:
            cutoff = datetime.now() - timedelta(days=settings.maintenance.retention_days)
            to_delete = await repo.get_count(end_date=cutoff)

        return {
            "total_detections": total_count,
            "oldest_detection": oldest_date.isoformat() if oldest_date else None,
            "retention_days": settings.maintenance.retention_days,
            "detections_to_cleanup": to_delete
        }

@router.post("/maintenance/cleanup")
async def run_cleanup():
    """Manually trigger cleanup of old detections."""
    if settings.maintenance.retention_days <= 0:
        return {
            "status": "skipped",
            "message": "Retention is set to unlimited (0 days)",
            "deleted_count": 0
        }

    cutoff = datetime.now() - timedelta(days=settings.maintenance.retention_days)

    async with get_db() as db:
        repo = DetectionRepository(db)
        deleted_count = await repo.delete_older_than(cutoff)

    log.info("Manual cleanup completed", deleted_count=deleted_count, cutoff=cutoff.isoformat())

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "cutoff_date": cutoff.isoformat()
    }