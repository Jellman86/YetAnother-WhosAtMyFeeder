"""Persist negative native-worker evidence without guessing the faulting library.

The launch profile is intentionally broader than a reported provider: a worker
may crash during compilation or while video/crop code runs, before it can identify
the failing runtime. Never turn that uncertainty into an automatic retry loop.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import time
from typing import Any, Callable

import structlog

log = structlog.get_logger()


def artifact_digest(path: str) -> str | None:
    """Hash weights once per file revision; paths never enter persisted evidence."""
    if not path:
        return None
    candidate = Path(path)
    try:
        stat = candidate.stat()
    except FileNotFoundError:
        return None
    if not candidate.is_file():
        return None
    return _artifact_digest(str(candidate), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


@lru_cache(maxsize=64)
def _artifact_digest(path: str, size: int, modified: int, changed: int) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class NativeCrashQuarantinedError(RuntimeError):
    """The exact launch profile has retained evidence of a native process fault."""


class NativeCrashQuarantine:
    def __init__(self, profile_getter: Callable[[], dict[str, Any]], *, root: Path | None = None) -> None:
        self._profile_getter = profile_getter
        self._root = root or Path(os.environ.get("CONFIG_DIR", "/config")) / "native-crashes"
        self._blocked: set[str] = set()
        self._lock = threading.RLock()

    @staticmethod
    def _key(profile: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def guard(self, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        profile = json.loads(json.dumps(self._profile_getter() if profile is None else profile))
        key = self._key(profile)
        with self._lock:
            try:
                blocked = key in self._blocked or (self._root / f"{key}.json").is_file()
            except OSError:
                blocked = True
            if blocked:
                raise NativeCrashQuarantinedError(
                    "Native classifier crash quarantine: this worker configuration is blocked. "
                    "Choose a different validated provider/model or investigate the saved crash evidence; "
                    "a restart does not clear quarantine."
                )
        return profile

    def remember(self, profile: dict[str, Any] | None, exit_code: int | None) -> bool:
        """Block in memory before any cancellable persistence await."""
        # SIGKILL can mean our deadline or the OOM killer. SIGTERM is normal
        # shutdown. Neither establishes a native memory/compiler fault.
        faults = {
            -int(getattr(signal, name))
            for name in ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGILL", "SIGFPE")
            if hasattr(signal, name)
        }
        if profile is None or exit_code not in faults:
            return False
        key = self._key(profile)
        with self._lock:
            self._blocked.add(key)
        return True

    def record(self, profile: dict[str, Any] | None, exit_code: int | None) -> bool:
        if not self.remember(profile, exit_code):
            return False
        key = self._key(profile)
        try:
            self._persist(key, {"profile": profile, "exit_code": exit_code, "recorded_at": time.time()})
        except OSError:
            log.error("native_crash_quarantine_persistence_failed", fingerprint=key)
        log.error("native_classifier_crash_quarantined", fingerprint=key, exit_code=exit_code)
        return True

    def _persist(self, key: str, evidence: dict[str, Any]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", dir=self._root, prefix=".crash-", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with temporary.open("w") as stream:
                json.dump(evidence, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._root / f"{key}.json")
        finally:
            temporary.unlink(missing_ok=True)
