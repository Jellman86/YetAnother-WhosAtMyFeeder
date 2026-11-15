from copy import deepcopy
import os
import re
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from collections.abc import Callable, Sequence

from app.utils.diagnostic_redaction import configured_secrets, redact_diagnostic


DIAGNOSTICS_HISTORY_MAX_EVENTS = max(
    50,
    int(os.getenv("DIAGNOSTICS_HISTORY_MAX_EVENTS", "500")),
)

_ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}

# Event ids, counts and durations vary between repeats of one fault; the words do not.
_VARYING_TOKEN = re.compile(r"\S*\d\S*")

GroupKey = tuple[str, str, str, str, str]


def _message_template(message: str) -> str:
    return _VARYING_TOKEN.sub("#", message)


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
    """Bounded in-memory diagnostics history for operator-visible error bundles.

    Repeats of one fault (same source, component, reason code, severity and message
    template) are one entry carrying `count`, `first_seen` and `last_seen`. A flood of one
    fault therefore neither fills the history nor pushes other faults out of it.
    """

    def __init__(
        self, max_events: int = DIAGNOSTICS_HISTORY_MAX_EVENTS, *, secret_provider: Callable[[], Sequence[str]] = tuple
    ):
        self._capacity = max(1, int(max_events))
        # Newest entry last; a repeat moves its entry to the end.
        self._events: OrderedDict[GroupKey, dict[str, Any]] = OrderedDict()
        self._lock = Lock()
        self._counter = 0
        self._secret_provider = secret_provider

    def _secrets(self) -> Sequence[str] | None:
        try:
            return self._secret_provider()
        except Exception:
            # Optional diagnostics must neither expose raw details nor break
            # ingestion when configuration cannot supply a redaction context.
            return None

    @staticmethod
    def _sanitized(record: dict[str, Any], secrets: Sequence[str] | None) -> dict[str, Any]:
        if secrets is None:
            record = {
                **record,
                "message": "Diagnostic details unavailable",
                "context": None,
                "runtime_recovery": None,
                "event_id": None,
                "job_id": None,
                "snapshot_ref": None,
                "correlation_key": None,
            }
        # Bound payload fields separately so a large context cannot remove the
        # event's machine-readable identity or correlation fields.
        machine_fields = {
            "id",
            "timestamp",
            "source",
            "component",
            "stage",
            "reason_code",
            "severity",
            "worker_pool",
            "count",
            "first_seen",
            "last_seen",
        }
        return {
            key: redact_diagnostic(value, () if key in machine_fields else secrets or ())
            for key, value in record.items()
        }

    @property
    def capacity(self) -> int:
        return self._capacity

    def clear(self) -> int:
        with self._lock:
            cleared = len(self._events)
            self._events.clear()
            self._counter = 0
            return cleared

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

        secrets = self._secrets()
        group_key: GroupKey = (
            normalized_source,
            normalized_component,
            normalized_reason,
            _normalize_severity(severity),
            _message_template(normalized_message),
        )
        with self._lock:
            self._counter += 1
            earlier = self._events.pop(group_key, None)
            record = {
                "id": earlier["id"] if earlier else f"diag:{int(time.time() * 1000)}:{self._counter}",
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
                "count": (earlier["count"] if earlier else 0) + 1,
                "first_seen": earlier["first_seen"] if earlier else now_iso,
                "last_seen": now_iso,
            }
            sanitized = self._sanitized(record, secrets)
            self._events[group_key] = sanitized
            while len(self._events) > self._capacity:
                self._events.popitem(last=False)
            return deepcopy(sanitized)

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
            events = list(reversed(self._events.values()))

        def _matches(record: dict[str, Any]) -> bool:
            if source_filter and str(record.get("source", "")).lower() != source_filter:
                return False
            if component_filter and str(record.get("component", "")).lower() != component_filter:
                return False
            if severity_filter and str(record.get("severity", "")).lower() != severity_filter:
                return False
            return True

        filtered = [record for record in events if _matches(record)]
        secrets = self._secrets()
        returned = [self._sanitized(record, secrets) for record in filtered[:bounded_limit]]

        severity_counts = Counter(str(record.get("severity", "warning")) for record in returned)
        component_counts = Counter(str(record.get("component", "unknown")) for record in returned)

        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "capacity": self._capacity,
            "total_events": len(events),
            "total_occurrences": sum(int(record.get("count", 1)) for record in events),
            "filtered_events": len(filtered),
            "returned_events": len(returned),
            "severity_counts": dict(severity_counts),
            "component_counts": dict(component_counts),
            "events": returned,
        }


error_diagnostics_history = ErrorDiagnosticsHistory(secret_provider=configured_secrets)
