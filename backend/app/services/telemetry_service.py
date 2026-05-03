import uuid
import structlog
import asyncio
import httpx
import platform
import os
import hashlib
from datetime import datetime, timezone
from typing import Any
from app.config import settings
from app.utils.enrichment import get_effective_enrichment_settings, is_ebird_active
from app.utils.tasks import create_background_task

log = structlog.get_logger()

HEALTH_REPORT_SCHEMA_VERSION = "2026-05-03.health-issues.v1"
HEALTH_REPORT_MAX_ISSUES = 25
HEALTH_CONTEXT_MAX_KEYS = 20
HEALTH_CONTEXT_MAX_STRING = 160
HEALTH_CONTEXT_MAX_LIST_ITEMS = 10

_ALLOWED_HEALTH_CONTEXT_KEYS = {
    "active_provider",
    "attempt",
    "backend",
    "batch_limit",
    "cache_enabled",
    "circuit_failures",
    "circuit_open",
    "compile_device",
    "compile_ok",
    "configured_provider",
    "cuda_available",
    "device",
    "error_type",
    "failure_count",
    "fallback_active",
    "inference_backend",
    "intel_gpu_available",
    "kind",
    "lease_age_seconds",
    "max_concurrent",
    "model_id",
    "openvino_available",
    "pending",
    "pressure_level",
    "provider",
    "queue_depth",
    "reason",
    "reason_code",
    "runtime",
    "runtime_backend",
    "source",
    "stage",
    "status",
    "timeout_seconds",
    "worker_pool",
}


def _safe_text(value: Any, *, limit: int = HEALTH_CONTEXT_MAX_STRING) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _sanitize_health_context(value: Any, *, depth: int = 0) -> Any:
    if depth > 2:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, list):
        sanitized_list = [
            _sanitize_health_context(item, depth=depth + 1)
            for item in value[:HEALTH_CONTEXT_MAX_LIST_ITEMS]
        ]
        return [item for item in sanitized_list if item is not None]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:HEALTH_CONTEXT_MAX_KEYS]:
            key = _safe_text(raw_key, limit=80)
            normalized_key = key.lower()
            if normalized_key not in _ALLOWED_HEALTH_CONTEXT_KEYS:
                continue
            sanitized_value = _sanitize_health_context(raw_value, depth=depth + 1)
            if sanitized_value is not None:
                sanitized[key] = sanitized_value
        return sanitized
    return _safe_text(value)


def _fingerprint_issue(event: dict[str, Any]) -> str:
    parts = [
        _safe_text(event.get("source"), limit=80).lower(),
        _safe_text(event.get("component"), limit=80).lower(),
        _safe_text(event.get("reason_code"), limit=120).lower(),
        _safe_text(event.get("stage"), limit=80).lower(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_health_issue_report(
    *,
    installation_id: str | None,
    app_version: str,
    diagnostics_snapshot: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a bounded, sanitized health issue report from backend diagnostics."""
    raw_events = diagnostics_snapshot.get("events")
    if not isinstance(raw_events, list):
        return None

    grouped: dict[str, dict[str, Any]] = {}
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        severity = _safe_text(raw_event.get("severity"), limit=20).lower() or "warning"
        if severity not in {"warning", "error", "critical"}:
            continue
        fingerprint = _fingerprint_issue(raw_event)
        timestamp = _safe_text(raw_event.get("timestamp"), limit=80)
        issue = grouped.setdefault(
            fingerprint,
            {
                "fingerprint": fingerprint,
                "source": _safe_text(raw_event.get("source"), limit=80) or "unknown",
                "component": _safe_text(raw_event.get("component"), limit=80) or "unknown",
                "reason_code": _safe_text(raw_event.get("reason_code"), limit=120) or "unknown_reason",
                "stage": _safe_text(raw_event.get("stage"), limit=80) or None,
                "severity": severity,
                "count": 0,
                "first_seen_at": timestamp or None,
                "last_seen_at": timestamp or None,
                "sample_context": _sanitize_health_context(raw_event.get("context") or {}),
            },
        )
        issue["count"] += 1
        if timestamp:
            first_seen = issue.get("first_seen_at")
            last_seen = issue.get("last_seen_at")
            issue["first_seen_at"] = min(first_seen, timestamp) if first_seen else timestamp
            issue["last_seen_at"] = max(last_seen, timestamp) if last_seen else timestamp
        if severity == "critical" or (severity == "error" and issue.get("severity") == "warning"):
            issue["severity"] = severity

    if not grouped:
        return None

    issues = sorted(
        grouped.values(),
        key=lambda issue: (
            {"critical": 0, "error": 1, "warning": 2}.get(str(issue.get("severity")), 3),
            -int(issue.get("count") or 0),
        ),
    )[:HEALTH_REPORT_MAX_ISSUES]

    return {
        "schema_version": HEALTH_REPORT_SCHEMA_VERSION,
        "installation_id": installation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": app_version,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "runtime": {
            "model_type": getattr(settings.classification, "model", None),
            "inference_provider": getattr(settings.classification, "inference_provider", None),
            "image_execution_mode": getattr(settings.classification, "image_execution_mode", None),
            "bird_crop_detector_tier": getattr(settings.classification, "bird_crop_detector_tier", None),
            "auto_video_classification": getattr(settings.classification, "auto_video_classification", None),
        },
        "integrations": {
            "birdnet_enabled": settings.frigate.birdnet_enabled,
            "birdweather_enabled": settings.birdweather.enabled,
            "ebird_enabled": is_ebird_active(),
            "inaturalist_enabled": settings.inaturalist.enabled,
            "llm_enabled": settings.llm.enabled,
        },
        "diagnostics_window": {
            "captured_at": diagnostics_snapshot.get("captured_at"),
            "total_events": diagnostics_snapshot.get("total_events"),
            "returned_events": diagnostics_snapshot.get("returned_events"),
            "severity_counts": diagnostics_snapshot.get("severity_counts"),
            "component_counts": diagnostics_snapshot.get("component_counts"),
        },
        "issues": issues,
    }

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

    async def force_health_report(self):
        """Force an immediate health issue report if enabled."""
        if settings.telemetry.health_enabled:
            log.info("Forcing health issue telemetry report")
            await self._send_health_report()

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
                if settings.telemetry.health_enabled:
                    await self._send_health_report()
                
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

    async def _send_health_report(self):
        """Gather sanitized health issue groups and send them to the health endpoint."""
        try:
            if not settings.telemetry.installation_id:
                await self._ensure_installation_id()

            from app.services.error_diagnostics import error_diagnostics_history

            diagnostics_snapshot = error_diagnostics_history.snapshot(limit=250)
            payload = build_health_issue_report(
                installation_id=settings.telemetry.installation_id,
                app_version=os.environ.get("APP_VERSION", "unknown"),
                diagnostics_snapshot=diagnostics_snapshot,
            )
            if not payload:
                log.debug("No health issues to report")
                return

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.post(settings.telemetry.health_url, json=payload)
                if resp.status_code == 200:
                    log.info(
                        "Health issue telemetry sent successfully",
                        url=settings.telemetry.health_url,
                        issue_count=len(payload.get("issues") or []),
                    )
                else:
                    log.warning("Health issue telemetry server returned error", status=resp.status_code)
        except Exception as e:
            log.warning("Failed to send health issue telemetry", error=str(e), url=settings.telemetry.health_url)

telemetry_service = TelemetryService()
