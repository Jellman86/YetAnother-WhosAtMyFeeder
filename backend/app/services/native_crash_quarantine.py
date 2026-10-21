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
import stat
import sys
import tempfile
import threading
import time
from typing import Any, Callable

import structlog

log = structlog.get_logger()
ARTIFACT_STAT_SETTLE_NS = 2_000_000_000
_MAX_INCIDENT_FILES = 1024
_MAX_INCIDENT_BYTES = 65536
_WINDOWS_NATIVE_FAULTS = {
    0xC0000005: "STATUS_ACCESS_VIOLATION",
    0xC000001D: "STATUS_ILLEGAL_INSTRUCTION",
    0xC000008E: "STATUS_FLOAT_DIVIDE_BY_ZERO",
    0xC0000094: "STATUS_INTEGER_DIVIDE_BY_ZERO",
    0xC00000FD: "STATUS_STACK_OVERFLOW",
    0xC0000374: "STATUS_HEAP_CORRUPTION",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",
}


def _native_fault_name(exit_code: int | None) -> str | None:
    if exit_code is None:
        return None
    if sys.platform == "win32":
        status = _WINDOWS_NATIVE_FAULTS.get(exit_code & 0xFFFFFFFF)
        if status is not None:
            return status
    for name in ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGILL", "SIGFPE"):
        if hasattr(signal, name) and exit_code == -int(getattr(signal, name)):
            return name
    return None


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
    # Same-size writes can share a filesystem timestamp tick, notably in WSL.
    # Recent revisions are hashed directly until their metadata has settled;
    # inode identity separately invalidates atomic replacements.
    if max(stat.st_mtime_ns, stat.st_ctime_ns) > time.time_ns() - ARTIFACT_STAT_SETTLE_NS:
        return _hash_artifact_file(candidate)
    return _artifact_digest(str(candidate), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_dev, stat.st_ino)


@lru_cache(maxsize=64)
def _artifact_digest(path: str, size: int, modified: int, changed: int, device: int, inode: int) -> str:
    return _hash_artifact_file(Path(path))


def _hash_artifact_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class NativeCrashQuarantinedError(RuntimeError):
    """The exact launch profile has retained evidence of a native process fault."""


class NativeCrashEvidenceUnavailableError(NativeCrashQuarantinedError):
    """Unknown evidence identity cannot be approved by a native probe."""


_EVIDENCE_UNAVAILABLE = (
    "Saved native crash evidence could not be verified. Inspect the saved incidents before retrying."
)


class NativeCrashQuarantine:
    def __init__(
        self,
        profile_getter: Callable[[], dict[str, Any]],
        *,
        root: Path | None = None,
        inherited_approval: dict[str, Any] | None = None,
    ) -> None:
        self._profile_getter = profile_getter
        self._root = root or Path(os.environ.get("CONFIG_DIR", "/config")) / "native-crashes"
        self._blocked: set[str] = set()
        self._reported: set[str] = set()
        self._incident_revisions: dict[str, int] = {}
        self._revalidated: dict[str, dict[str, Any]] = {}
        self._inherited_approval = inherited_approval
        self._lock = threading.RLock()
        # Persistence and compatibility scans have separate locks. Neither
        # holds _lock, so event-loop remember() calls do not wait for those
        # disk operations. File-based guard/approval lookups belong in worker
        # threads; only the final grant uses a short existing-file snapshot.
        self._persist_lock = threading.Lock()
        self._index_lock = threading.Lock()
        self._index_identity: tuple[int, ...] | None = None
        self._incident_index: dict[str, set[str]] = {}
        self._index_files: dict[str, tuple[int, ...]] = {}

    @staticmethod
    def _key(profile: dict[str, Any]) -> str:
        identity = {
            key: value
            for key, value in profile.items()
            if key not in {"legacy_runtime_signature", "legacy_profile_keys"}
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def _negative_key(cls, profile: dict[str, Any]) -> str:
        # Ordinary auxiliary changes must not authorize retries of a failed
        # primary model/provider. Positive approval still uses the full _key.
        return cls._key({k: v for k, v in profile.items() if k not in {"auxiliary_artifacts", "video_frames"}})

    def _directory_identity(self) -> tuple[int, ...] | None:
        try:
            metadata = self._root.stat()
        except FileNotFoundError:
            return None
        return metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_ctime_ns

    def _persisted_incident_keys(self, profile: dict[str, Any]) -> tuple[set[str], tuple[int, ...] | None]:
        # Releases predating the stable negative key wrote expanded-key files.
        # Index their profiles without rewriting evidence. This I/O must stay
        # outside _lock so remember() never waits for disk or compatibility reads.
        with self._index_lock:
            identity = self._directory_identity()
            if identity is None:
                self._index_identity = None
                self._incident_index = {}
                self._index_files = {}
                return set(), None
            paths = []
            files = {}
            for count, path in enumerate(self._root.iterdir(), start=1):
                if count > _MAX_INCIDENT_FILES:
                    raise OSError("Quarantine evidence index exceeded its bound")
                if (
                    path.suffix != ".json"
                    or len(path.stem) != 64
                    or any(c not in "0123456789abcdef" for c in path.stem)
                ):
                    continue
                metadata = path.lstat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_INCIDENT_BYTES:
                    raise OSError("Quarantine evidence cannot be safely indexed")
                files[path.name] = (
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                )
                paths.append(path)
            if identity != self._index_identity or files != self._index_files:
                index: dict[str, set[str]] = {}
                for path in paths:
                    with path.open("rb") as stream:
                        raw = stream.read(_MAX_INCIDENT_BYTES + 1)
                    try:
                        record = json.loads(raw) if len(raw) <= _MAX_INCIDENT_BYTES else None
                        recorded_profile = record.get("profile") if isinstance(record, dict) else None
                        if not isinstance(recorded_profile, dict):
                            raise ValueError
                        negative_key = self._negative_key(recorded_profile)
                        if path.stem not in {self._key(recorded_profile), negative_key}:
                            raise ValueError
                    except (ValueError, TypeError, RecursionError):
                        raise OSError("Quarantine evidence cannot be safely indexed") from None
                    index.setdefault(negative_key, set()).add(path.stem)
                if self._directory_identity() != identity:
                    raise OSError("Quarantine evidence changed during indexing")
                self._incident_index = index
                self._index_identity = identity
                self._index_files = files
            keys = {self._negative_key(profile)}
            if legacy := profile.get("legacy_runtime_signature"):
                keys.add(self._negative_key(profile | {"runtime_signature": legacy}))
            return set().union(*(self._incident_index.get(key, set()) for key in keys)), identity

    def guard(self, profile: dict[str, Any] | None = None, *, allow_revalidated: bool = True) -> dict[str, Any]:
        profile = json.loads(json.dumps(self._profile_getter() if profile is None else profile))
        key = self._key(profile)
        try:
            persisted_keys, _ = self._persisted_incident_keys(profile)
        except OSError:
            with self._lock:
                self._inherited_approval = None
            raise NativeCrashEvidenceUnavailableError(_EVIDENCE_UNAVAILABLE) from None
        with self._lock:
            try:
                incidents = self._incident_snapshot(profile, persisted_keys)
                approval, self._inherited_approval = self._inherited_approval, None
                if allow_revalidated and isinstance(approval, dict) and approval.get("profile_key") == key:
                    files = {k: v["file"] for k, v in incidents.items()}
                    blocked_keys = approval.get("blocked_keys")
                    if (
                        approval.get("files") == files
                        and isinstance(blocked_keys, list)
                        and all(isinstance(value, str) for value in blocked_keys)
                        and set(blocked_keys) <= set(incidents)
                        and all(v["revision"] == 0 for v in incidents.values())
                    ):
                        self._blocked.update(blocked_keys)
                        incidents = self._incident_snapshot(profile, persisted_keys)
                        self._revalidated[key] = incidents
                blocked = any(value["blocked"] for value in incidents.values())
                blocked = blocked and (not allow_revalidated or self._revalidated.get(key) != incidents)
            except OSError:
                blocked = True
            if blocked:
                raise NativeCrashQuarantinedError(
                    "Native classifier crash quarantine: this worker configuration is blocked. "
                    "Choose a different validated provider/model or investigate the saved crash evidence; "
                    "a restart does not clear quarantine."
                )
        return profile

    def guard_in_process(self, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        """Owner diagnostics authorize isolated workers, never the API process."""
        return self.guard(profile, allow_revalidated=False)

    def worker_approval(self, profile: dict[str, Any]) -> dict[str, Any] | None:
        """Export current authority only through the trusted worker launch path."""
        try:
            persisted_keys, _ = self._persisted_incident_keys(profile)
        except OSError:
            return None
        with self._lock:
            key = self._key(profile)
            try:
                incidents = self._incident_snapshot(profile, persisted_keys)
            except OSError:
                return None
            if self._revalidated.get(key) != incidents:
                return None
            return {
                "profile_key": key,
                "files": {k: v["file"] for k, v in incidents.items()},
                "blocked_keys": [k for k, v in incidents.items() if v["blocked"]],
            }

    def _incident_snapshot(self, profile: dict[str, Any], persisted_keys: set[str]) -> dict[str, Any]:
        keys = {self._key(profile), self._negative_key(profile), *persisted_keys}
        # Derive old aliases from this primary identity: captured metadata may
        # still contain GPU aliases after a CPU/provider/model override.
        legacy_signature = profile.get("legacy_runtime_signature")
        if legacy_signature:
            # Adding driver identity must invalidate positive qualification,
            # never silently release negative evidence from older versions.
            keys.add(self._key(profile | {"runtime_signature": legacy_signature}))
            keys.add(self._negative_key(profile | {"runtime_signature": legacy_signature}))
        incidents = {}
        for incident_key in sorted(keys):
            try:
                metadata = (self._root / f"{incident_key}.json").stat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise OSError("Quarantine evidence is not a regular file")
                identity = [
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                    metadata.st_ctime_ns,
                ]
            except FileNotFoundError:
                identity = None
            incidents[incident_key] = {
                "blocked": incident_key in self._blocked or identity is not None,
                "revision": self._incident_revisions.get(incident_key, 0),
                "file": identity,
            }
        return incidents

    def capture_revalidation(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Bind one explicit owner check to the exact incidents it observed."""
        try:
            persisted_keys, directory = self._persisted_incident_keys(profile)
        except OSError:
            raise ValueError(_EVIDENCE_UNAVAILABLE) from None
        with self._lock:
            incidents = self._incident_snapshot(profile, persisted_keys)
            key = self._key(profile)
            if not any(value["blocked"] for value in incidents.values()) or self._revalidated.get(key) == incidents:
                raise ValueError("The selected profile is not quarantined")
            return {"profile_key": key, "incidents": incidents, "evidence_directory": directory}

    def release_after_revalidation(self, profile: dict[str, Any], token: dict[str, Any]) -> bool:
        """Grant this process only; original evidence remains blocking on restart."""
        # Never perform a compatibility scan in this final, non-yielding grant.
        # A changed directory requires a fresh explicit check, even if its new
        # file belongs to another profile. Existing files are checked by stat.
        if self._directory_identity() != token.get("evidence_directory"):
            return False
        with self._lock:
            if self._key(profile) != token.get("profile_key"):
                return False
            incidents = self._incident_snapshot(profile, set(token["incidents"]))
            if incidents != token.get("incidents"):
                return False
            self._revalidated[self._key(profile)] = incidents
            return True

    def remember(self, profile: dict[str, Any] | None, exit_code: int | None) -> bool:
        """Block in memory before any cancellable persistence await."""
        # SIGKILL can mean our deadline or the OOM killer. SIGTERM is normal
        # shutdown. Neither establishes a native memory/compiler fault.
        if profile is None or _native_fault_name(exit_code) is None:
            return False
        key = self._negative_key(profile)
        with self._lock:
            self._blocked.add(key)
            self._incident_revisions[key] = self._incident_revisions.get(key, 0) + 1
        return True

    def record(self, profile: dict[str, Any] | None, exit_code: int | None) -> bool:
        if not self.remember(profile, exit_code):
            return False
        key = self._negative_key(profile)
        self._persist_incident(profile, {"profile": profile, "exit_code": exit_code, "recorded_at": time.time()})
        log.error("native_classifier_crash_quarantined", fingerprint=key, exit_code=exit_code)
        with self._lock:
            if key not in self._reported:
                self._reported.add(key)
                from .error_diagnostics import error_diagnostics_history

                error_diagnostics_history.record(
                    source="classifier",
                    component="classifier_worker",
                    severity="error",
                    reason_code="native_classifier_crash",
                    message="A native classifier process crashed; its launch profile is quarantined.",
                    context={
                        "error_type": _native_fault_name(exit_code),
                        "configured_provider": profile.get("provider"),
                        "model_id": profile.get("model_id"),
                        "status": "quarantined",
                    },
                )
        return True

    def remember_retirement(self, profile: dict[str, Any] | None) -> bool:
        """Block a profile whose worker retired itself after a GPU device
        failure. Deliberate retirement is established by the worker's
        retirement record, so unlike ``remember`` it needs no native-fault
        exit code; the in-memory block lands before any respawn attempt."""
        if profile is None:
            return False
        key = self._negative_key(profile)
        with self._lock:
            self._blocked.add(key)
            self._incident_revisions[key] = self._incident_revisions.get(key, 0) + 1
        return True

    def record_retirement(self, profile: dict[str, Any] | None, error_code: str, detail: str) -> bool:
        if not self.remember_retirement(profile):
            return False
        key = self._negative_key(profile)
        retirement = {"error_code": str(error_code), "detail": str(detail)[:280]}
        self._persist_incident(
            profile, {"profile": profile, "exit_code": None, "retirement": retirement, "recorded_at": time.time()}
        )
        log.error("native_classifier_gpu_retirement_quarantined", fingerprint=key, error_code=retirement["error_code"])
        with self._lock:
            if key not in self._reported:
                self._reported.add(key)
                from .error_diagnostics import error_diagnostics_history

                error_diagnostics_history.record(
                    source="classifier",
                    component="classifier_worker",
                    severity="error",
                    reason_code="gpu_worker_retired",
                    message="A GPU classifier worker retired itself after a device failure; its launch profile is quarantined.",
                    context={
                        "error_type": retirement["error_code"],
                        "configured_provider": profile.get("provider"),
                        "model_id": profile.get("model_id"),
                        "status": "quarantined",
                    },
                )
        return True

    def _persist_incident(self, profile: dict[str, Any], evidence: dict[str, Any]) -> None:
        # Retain the full incident identity as well as its conservative base
        # alias; a later sibling fault must not overwrite the original profile.
        for key in dict.fromkeys((self._key(profile), self._negative_key(profile))):
            try:
                self._persist(key, evidence)
            except OSError:
                log.error("native_crash_quarantine_persistence_failed", fingerprint=key)

    def _persist(self, key: str, evidence: dict[str, Any]) -> None:
        # One file per launch profile holds every incident kind for it: a
        # native abort recorded after a retirement must not erase the
        # original OpenCL cause, and vice versa. Workers sharing a profile
        # can record concurrently, so the whole read-merge-replace is one
        # transaction under the lock; otherwise the last writer wins and
        # silently drops the other incident.
        with self._persist_lock:
            self._persist_locked(key, evidence)

    def _persist_locked(self, key: str, evidence: dict[str, Any]) -> None:
        existing_path = self._root / f"{key}.json"
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
        if isinstance(existing, dict):
            merged = {**existing, **evidence}
            if "retirement" in existing and "retirement" not in evidence:
                merged["retirement"] = existing["retirement"]
            if merged.get("exit_code") is None and existing.get("exit_code") is not None:
                merged["exit_code"] = existing["exit_code"]
            evidence = merged
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
