import os
import time
from collections import Counter, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any


DIAGNOSTICS_HISTORY_MAX_EVENTS = max(
    50,
    int(os.getenv("DIAGNOSTICS_HISTORY_MAX_EVENTS", "500")),
)

_ALLOWED_SEVERITIES = {"warning", "error", "critical"}


def _normalize_string(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    trimmed = value.strip()
    return trimmed if trimmed else fallback


def _normalize_severity(value: Any) -> str:
    severity = _normalize_string(value, "warning").lower()
    if severity in _ALLOWED_SEVERITIES:
        return severity
    return "warning"


def _normalize_optional_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


class ErrorDiagnosticsHistory:
    """Bounded in-memory diagnostics history for operator-visible error bundles."""

    def __init__(self, max_events: int = DIAGNOSTICS_HISTORY_MAX_EVENTS):
        self._capacity = max(1, int(max_events))
        self._events: deque[dict[str, Any]] = deque(maxlen=self._capacity)
        self._lock = Lock()
        self._counter = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._counter = 0

    def record(
        self,
        *,
        source: str,
        component: str,
        reason_code: str,
        message: str,
        severity: str = "warning",
        stage: str | None = None,
        event_id: str | None = None,
        context: dict[str, Any] | None = None,
        timestamp: str | None = None,
        correlation_key: str | None = None,
        job_id: str | None = None,
        worker_pool: str | None = None,
        runtime_recovery: dict[str, Any] | None = None,
        snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        now_iso = _normalize_string(timestamp) or datetime.now(timezone.utc).isoformat()
        normalized_source = _normalize_string(source, "unknown")
        normalized_component = _normalize_string(component, "unknown")
        normalized_reason = _normalize_string(reason_code, "unknown_reason")
        normalized_message = _normalize_string(message, "Unknown diagnostic event")
        normalized_stage = _normalize_string(stage) or None
        normalized_event_id = _normalize_string(event_id) or None
        normalized_context = context if isinstance(context, dict) else None
        normalized_correlation_key = _normalize_string(correlation_key) or None
        normalized_job_id = _normalize_string(job_id) or None
        normalized_worker_pool = _normalize_string(worker_pool) or None
        normalized_runtime_recovery = _normalize_optional_dict(runtime_recovery)
        normalized_snapshot_ref = _normalize_string(snapshot_ref) or None

        with self._lock:
            self._counter += 1
            record = {
                "id": f"diag:{int(time.time() * 1000)}:{self._counter}",
                "timestamp": now_iso,
                "source": normalized_source,
                "component": normalized_component,
                "stage": normalized_stage,
                "reason_code": normalized_reason,
                "message": normalized_message,
                "severity": _normalize_severity(severity),
                "event_id": normalized_event_id,
                "context": normalized_context,
                "correlation_key": normalized_correlation_key,
                "job_id": normalized_job_id,
                "worker_pool": normalized_worker_pool,
                "runtime_recovery": normalized_runtime_recovery,
                "snapshot_ref": normalized_snapshot_ref,
            }
            self._events.appendleft(record)
            return dict(record)

    def snapshot(
        self,
        *,
        limit: int = 100,
        source: str | None = None,
        component: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        bounded_limit = min(max(1, int(limit)), 1000)
        source_filter = _normalize_string(source).lower()
        component_filter = _normalize_string(component).lower()
        severity_filter = _normalize_string(severity).lower()

        with self._lock:
            events = list(self._events)

        def _matches(record: dict[str, Any]) -> bool:
            if source_filter and str(record.get("source", "")).lower() != source_filter:
                return False
            if component_filter and str(record.get("component", "")).lower() != component_filter:
                return False
            if severity_filter and str(record.get("severity", "")).lower() != severity_filter:
                return False
            return True

        filtered = [record for record in events if _matches(record)]
        returned = filtered[:bounded_limit]

        severity_counts = Counter(str(record.get("severity", "warning")) for record in returned)
        component_counts = Counter(str(record.get("component", "unknown")) for record in returned)

        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "capacity": self._capacity,
            "total_events": len(events),
            "filtered_events": len(filtered),
            "returned_events": len(returned),
            "severity_counts": dict(severity_counts),
            "component_counts": dict(component_counts),
            "events": returned,
        }


error_diagnostics_history = ErrorDiagnosticsHistory()
