from copy import deepcopy
from dataclasses import dataclass, field
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


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def dismissal_covers(dismissal: dict[str, Any] | None, entry: dict[str, Any]) -> bool:
    """Whether a dismissal still hides an entry.

    A dismissal names one entry by its id, component and reason code, and the newest occurrence
    the owner saw. An occurrence recorded after that shows the entry again. A time that cannot
    be read never hides anything.
    """
    if not dismissal:
        return False
    if dismissal.get("component") != entry.get("component") or dismissal.get("reason_code") != entry.get("reason_code"):
        return False
    through = _instant(dismissal.get("dismissed_through"))
    last_seen = _instant(entry.get("last_seen") or entry.get("timestamp"))
    return through is not None and last_seen is not None and last_seen <= through


@dataclass
class DismissResult:
    dismissed: list[dict[str, Any]] = field(default_factory=list)
    # Entries that left the history (cleared, restarted or pushed out) before the dismissal arrived.
    missing: list[str] = field(default_factory=list)


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
        # Rises with every record and every clear, so a reader can tell the history changed
        # without copying it.
        self._revision = 0
        self._secret_provider = secret_provider
        # Entry id -> the owner's dismissal of it. Held beside the history it hides, so a clear or
        # a restart, which empty the history, take the dismissals with it.
        self._dismissals: dict[str, dict[str, Any]] = {}

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

    @staticmethod
    def _with_dismissal(record: dict[str, Any], dismissal: dict[str, Any] | None) -> dict[str, Any]:
        covers = dismissal_covers(dismissal, record)
        return {
            **record,
            "dismissed": covers,
            "dismissal": (
                {"dismissed_through": dismissal["dismissed_through"], "dismissed_at": dismissal["dismissed_at"]}
                if covers and dismissal
                else None
            ),
        }

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def capacity(self) -> int:
        return self._capacity

    def clear(self) -> int:
        with self._lock:
            cleared = len(self._events)
            self._events.clear()
            self._dismissals.clear()
            self._counter = 0
            self._revision += 1
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
            self._revision += 1
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
                _evicted_key, evicted = self._events.popitem(last=False)
                self._dismissals.pop(evicted["id"], None)
            return deepcopy(sanitized)

    def dismiss(self, entries: Sequence[tuple[str, str]], *, now: str | None = None) -> DismissResult:
        """Hide entries, each up to the occurrence the owner saw (`last_seen`), for everyone.

        The dismissal never reaches past the entry's own newest occurrence, so a clock ahead of
        the server cannot hide an occurrence that has not happened yet.
        """
        dismissed_at = _normalize_string(now) or datetime.now(timezone.utc).isoformat()
        result = DismissResult()
        with self._lock:
            by_id = {entry["id"]: entry for entry in self._events.values()}
            for entry_id, seen in entries:
                entry = by_id.get(entry_id)
                seen_at = _instant(seen)
                newest = _instant(entry.get("last_seen")) if entry else None
                if entry is None or seen_at is None or newest is None:
                    result.missing.append(entry_id)
                    continue
                dismissal = {
                    "id": entry_id,
                    "component": entry["component"],
                    "reason_code": entry["reason_code"],
                    "dismissed_through": min(seen_at, newest).isoformat(),
                    "dismissed_at": dismissed_at,
                }
                self._dismissals[entry_id] = dismissal
                result.dismissed.append(dict(dismissal))
            if result.dismissed:
                self._revision += 1
        return result

    def restore(self, entry_ids: Sequence[str]) -> list[str]:
        """Show dismissed entries again; returns the ids that had a dismissal."""
        with self._lock:
            restored = [entry_id for entry_id in entry_ids if self._dismissals.pop(entry_id, None) is not None]
            if restored:
                self._revision += 1
        return restored

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
            dismissals = dict(self._dismissals)

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
        returned = [
            self._with_dismissal(self._sanitized(record, secrets), dismissals.get(record["id"]))
            for record in filtered[:bounded_limit]
        ]

        severity_counts = Counter(str(record.get("severity", "warning")) for record in returned)
        component_counts = Counter(str(record.get("component", "unknown")) for record in returned)

        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "capacity": self._capacity,
            "total_events": len(events),
            "total_occurrences": sum(int(record.get("count", 1)) for record in events),
            "dismissed_events": sum(dismissal_covers(dismissals.get(record["id"]), record) for record in events),
            "filtered_events": len(filtered),
            "returned_events": len(returned),
            "severity_counts": dict(severity_counts),
            "component_counts": dict(component_counts),
            "events": returned,
        }


error_diagnostics_history = ErrorDiagnosticsHistory(secret_provider=configured_secrets)
