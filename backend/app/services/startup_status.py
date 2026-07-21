"""Best-effort, non-sensitive startup progress for the monolithic web shell."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict


StartupState = Literal["starting", "ready", "failed"]


class StartupStatusPayload(TypedDict):
    status: StartupState
    phase: str
    progress: int
    started_at: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StartupStatusPublisher:
    """Atomically publish bounded progress without making startup depend on it."""

    def __init__(self, path: str | Path | None):
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        started_at = _utc_now()
        self._payload: StartupStatusPayload = {
            "status": "starting",
            "phase": "launching",
            "progress": 0,
            "started_at": started_at,
            "updated_at": started_at,
        }

    def snapshot(self) -> StartupStatusPayload:
        with self._lock:
            return dict(self._payload)

    def publish(self, phase: str, progress: int) -> None:
        with self._lock:
            if self._payload["status"] != "starting":
                return
            self._payload["phase"] = str(phase or "launching")
            self._payload["progress"] = max(self._payload["progress"], min(99, max(0, int(progress))))
            self._payload["updated_at"] = _utc_now()
            self._write_locked()

    def mark_ready(self) -> None:
        with self._lock:
            if self._payload["status"] == "failed":
                return
            self._payload.update(
                status="ready",
                phase="ready",
                progress=100,
                updated_at=_utc_now(),
            )
            self._write_locked()

    def mark_failed(self, phase: str) -> None:
        with self._lock:
            if self._payload["status"] != "starting":
                return
            self._payload.update(
                status="failed",
                phase=str(phase or self._payload["phase"]),
                updated_at=_utc_now(),
            )
            self._write_locked()

    def _write_locked(self) -> None:
        if self._path is None:
            return
        temporary_path = self._path.with_name(f".{self._path.name}.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(self._payload, separators=(",", ":")),
                encoding="utf-8",
            )
            os.replace(temporary_path, self._path)
        except OSError:
            # Reporting is observational. It must never make a healthy backend
            # or a legacy split deployment fail to start.
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


startup_status = StartupStatusPublisher(os.getenv("YA_WAMF_STARTUP_STATUS_PATH"))
