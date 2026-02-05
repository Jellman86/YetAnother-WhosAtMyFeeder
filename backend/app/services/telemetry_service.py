import uuid
import structlog
import asyncio
import httpx
import platform
import os
from datetime import datetime, timezone
from app.config import settings
from app.utils.enrichment import get_effective_enrichment_settings, is_ebird_active
from app.utils.tasks import create_background_task

log = structlog.get_logger()

class TelemetryService:
    def __init__(self):
        self._running = False
        self._task = None
        # Note: Do NOT call _ensure_installation_id here - it's async and called in start()

    async def _ensure_installation_id(self, max_retries: int = 3) -> bool:
        """Generate a persistent anonymous ID if one doesn't exist.

        This is async-safe and includes retry logic with timeout protection.

        Args:
            max_retries: Maximum number of save attempts (default: 3)

        Returns:
            True if ID was successfully persisted, False if using in-memory only
        """
        if settings.telemetry.installation_id:
            # Already have an ID
            return True

        # Generate new UUID
        new_id = str(uuid.uuid4())
        settings.telemetry.installation_id = new_id
        log.info("Generated new anonymous installation ID", id=new_id[:8] + "...")

        # Try to persist it to config file with retries
        for attempt in range(1, max_retries + 1):
            try:
                # Add timeout protection - never hang more than 5 seconds
                await asyncio.wait_for(settings.save(), timeout=5.0)
                log.info("Installation ID persisted to config", attempt=attempt)
                return True
            except asyncio.TimeoutError:
                log.warning("Config save timed out, will retry",
                           attempt=attempt, max_retries=max_retries)
            except Exception as e:
                log.warning("Failed to save installation ID to config",
                           error=str(e), attempt=attempt, max_retries=max_retries)

            # Wait before retry (exponential backoff: 1s, 2s, 4s)
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))

        # All retries failed - continue with in-memory ID
        log.warning("Using in-memory installation ID (config save failed)",
                   id=new_id[:8] + "...",
                   note="Telemetry will work but ID may change on restart")
        return False

    async def start(self):
        """Start the background telemetry reporter."""
        if self._running:
            return

        # Ensure we have an installation ID (async-safe, non-blocking)
        try:
            await asyncio.wait_for(self._ensure_installation_id(), timeout=20.0)
        except asyncio.TimeoutError:
            log.error("Installation ID generation timed out after 20s - using temporary ID")
            # Generate temporary in-memory ID as fallback
            if not settings.telemetry.installation_id:
                settings.telemetry.installation_id = str(uuid.uuid4())
        except Exception as e:
            log.error("Unexpected error during installation ID generation", error=str(e))
            # Generate temporary in-memory ID as fallback
            if not settings.telemetry.installation_id:
                settings.telemetry.installation_id = str(uuid.uuid4())

        self._running = True
        self._task = create_background_task(self._report_loop(), name="telemetry_report_loop")
        log.info("Telemetry service started",
                enabled=settings.telemetry.enabled,
                has_persistent_id=bool(settings.telemetry.installation_id))

    async def stop(self):
        """Stop the background reporter."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def force_heartbeat(self):
        """Force an immediate heartbeat if enabled."""
        if settings.telemetry.enabled:
            log.info("Forcing telemetry heartbeat")
            await self._send_heartbeat()

    async def _report_loop(self):
        """Periodically send heartbeat."""
        # Initial delay to let app startup
        try:
            await asyncio.sleep(60) 
        except asyncio.CancelledError:
            return
        
        while self._running:
            try:
                if settings.telemetry.enabled:
                    await self._send_heartbeat()
                
                # Report every 24 hours
                await asyncio.sleep(24 * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Telemetry loop error", error=str(e))
                await asyncio.sleep(3600) # Retry in an hour on error

    async def _send_heartbeat(self):
        """Gather stats and send to the telemetry endpoint."""
        try:
            from app.services.model_manager import model_manager
            
            # Gather anonymous stats
            payload = {
                "installation_id": settings.telemetry.installation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": os.environ.get("APP_VERSION", "unknown"),
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                },
                "configuration": {
                    "model_type": model_manager.active_model_id,
                    "llm_enabled": settings.llm.enabled,
                    "llm_provider": settings.llm.provider,
                    "media_cache_enabled": settings.media_cache.enabled,
                    "media_cache_clips": settings.media_cache.cache_clips,
                    "auto_video_classification": settings.classification.auto_video_classification,
                },
                "integrations": {
                    "birdnet_enabled": settings.frigate.birdnet_enabled,
                    "birdweather_enabled": settings.birdweather.enabled,
                    "ebird_enabled": is_ebird_active(),
                    "inaturalist_enabled": settings.inaturalist.enabled,
                },
                "notifications": {
                    "discord_enabled": settings.notifications.discord.enabled,
                    "pushover_enabled": settings.notifications.pushover.enabled,
                    "telegram_enabled": settings.notifications.telegram.enabled,
                    "email_enabled": settings.notifications.email.enabled,
                    "mode": settings.notifications.mode,
                },
                "enrichment": {
                    "mode": get_effective_enrichment_settings()["mode"],
                    "summary_source": get_effective_enrichment_settings()["summary_source"],
                    "sightings_source": get_effective_enrichment_settings()["sightings_source"],
                    "taxonomy_source": get_effective_enrichment_settings()["taxonomy_source"],
                },
                "access": {
                    "auth_enabled": settings.auth.enabled,
                    "public_access_enabled": settings.public_access.enabled,
                }
            }

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.post(settings.telemetry.url, json=payload)
                if resp.status_code == 200:
                    log.info("Telemetry heartbeat sent successfully", url=settings.telemetry.url)
                else:
                    log.warning("Telemetry server returned error", status=resp.status_code)
                    
        except Exception as e:
            # Fail silently-ish to not spam logs too hard
            log.warning("Failed to send telemetry heartbeat", error=str(e), url=settings.telemetry.url)

telemetry_service = TelemetryService()
