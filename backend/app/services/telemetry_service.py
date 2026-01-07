import uuid
import structlog
import asyncio
import httpx
import platform
import os
from datetime import datetime
from app.config import settings

log = structlog.get_logger()

class TelemetryService:
    def __init__(self):
        self._running = False
        self._task = None
        self._ensure_installation_id()

    def _ensure_installation_id(self):
        """Generate a persistent anonymous ID if one doesn't exist."""
        if not settings.telemetry.installation_id:
            new_id = str(uuid.uuid4())
            settings.telemetry.installation_id = new_id
            settings.save()
            log.info("Generated new anonymous installation ID", id=new_id)

    async def start(self):
        """Start the background telemetry reporter."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._report_loop())
        log.info("Telemetry service started", enabled=settings.telemetry.enabled)

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
        await asyncio.sleep(60) 
        
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
                "timestamp": datetime.utcnow().isoformat(),
                "version": os.environ.get("APP_VERSION", "unknown"), # Should be set in main.py or env
                "platform": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                },
                "configuration": {
                    "model_type": model_manager.active_model_id,
                    "birdnet_enabled": settings.frigate.birdnet_enabled,
                    "birdweather_enabled": settings.birdweather.enabled,
                    "llm_enabled": settings.llm.enabled,
                    "llm_provider": settings.llm.provider,
                    "media_cache_enabled": settings.media_cache.enabled,
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
