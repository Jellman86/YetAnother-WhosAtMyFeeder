"""Bounded recovery checks for the bird finder's previously verified accelerators.

Device evidence is bound to the kernel, drivers and inference packages, so a
host or image update makes it stale. The identification model re-checks its own
accelerator once after such a change; without the same step the bird finder
silently stayed on the CPU after every update until an owner re-ran the check.

Previously checked accelerators and an explicitly saved accelerator are checked
per runtime and preference, with capped retries for inconclusive attempts. Failed
checks never authorize accelerator use.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from collections.abc import Callable
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator
import structlog

from app.config import settings
from app.models.classifier_status import FinderCheckReasonCode
from app.services import model_validation as validation
from app.services.bird_finder_health import RFDETR_FINDER, present_accelerators
from app.services.model_validation import sweep_crop_model_devices

log = structlog.get_logger()

ACCELERATED_PROVIDERS = frozenset({"cuda", "intel_gpu", "intel_npu"})
LEDGER_FILENAME = "bird_finder_revalidation.json"
MAX_CHECK_PHOTOS = 12


class BirdFinderCheckResult(BaseModel):
    state: Literal["idle", "waiting", "running", "succeeded", "failed", "superseded", "interrupted"] = "idle"
    model_id: str | None = None
    providers: list[str] = Field(default_factory=list)
    reason: str | None = None
    checked_at: str | None = None
    runtime_current: bool = True
    reason_code: FinderCheckReasonCode | None = None

    @model_validator(mode="after")
    def restore_legacy_reason_code(self) -> Self:
        if self.reason_code is None:
            reason = self.reason or ""
            if "did not match the CPU" in reason:
                self.reason_code = "mismatch"
            elif "could not finish" in reason:
                self.reason_code = "unfinished"
            else:
                codes: dict[str, FinderCheckReasonCode] = {
                    "waiting": "no_photos",
                    "running": "driver_changed",
                    "interrupted": "interrupted",
                    "superseded": "superseded",
                    "succeeded": "passed",
                }
                self.reason_code = codes.get(self.state)
        return self


class BirdFinderCheckStatus(BirdFinderCheckResult):
    last_result: BirdFinderCheckResult | None = None
    attempt_count: int = 0
    next_retry_at: str | None = None


def selected_finder() -> tuple[str, str | None] | None:
    """The accurate-tier finder that actually loads, with its artifact checksum."""
    from app.services.model_manager import model_manager

    spec = model_manager.get_crop_detector_spec("accurate")
    if not spec.get("healthy") or spec.get("resolved_tier") != "accurate":
        return None
    artifact = str((spec.get("metadata") or {}).get("sha256") or "").strip().lower() or None
    return str(spec["model_id"]), artifact


# A wide-frame finder looks for birds in whole camera frames. The cache also
# holds model crops, Frigate-hint crops, retained snapshots and event snapshots
# that HQ processing replaced with a bird crop; a frame finder finds nothing in
# a tight crop, which once left a host with an empty CPU baseline and the
# finder stuck on the CPU.
_CROP_VARIANT_MARKERS = ("__model_crop__", "__frigate_hint_crop__", "__frigate_region_crop__", "__retained_snapshot__")
_VARIANT_FRAME = re.compile(r"__(full_frame|model_crop|frigate_hint_crop|frigate_region_crop)__(f-?\d+|final)__")
MIN_FRAME_SHORT_SIDE = 480
MIN_CHECK_FRAMES = 3
MAX_FRAMES_PER_VISIT = 2
# Each file costs at most a header read; the cache holds tens of thousands.
MAX_FRAME_HEADER_READS = 240
# A JPEG's size sits in its first segments. Anything that pushes it further is
# not a camera frame, and must not make selection read megabytes to find out.
MAX_HEADER_BYTES = 256 * 1024
MAX_FRAME_BYTES = 24 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024
# Part of the retry ledger key: a new selection rule deserves a fresh check.
PHOTO_SELECTION_POLICY = 2

_FULL_FRAME_WITH_BIRD, _FULL_FRAME, _EVENT_SNAPSHOT = 0, 1, 2


def _read_regular_file(path: str, limit: int) -> bytes | None:
    """At most ``limit`` bytes of a regular file; never a symlink, FIFO or device."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        chunks: list[bytes] = []
        remaining = limit
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _frame_variant(name: str) -> tuple[str, str | None] | None:
    """("full", frame), ("crop", frame) or ("event", None); None for anything unusable."""
    if not name.endswith(".jpg") or name.endswith("_thumb.jpg"):
        return None
    variant = _VARIANT_FRAME.search(name)
    if variant is not None:
        if variant.group(1) != "full_frame":
            return "crop", variant.group(2)
        return ("full", variant.group(2)) if name.endswith("__image.jpg") else None
    if any(marker in name for marker in _CROP_VARIANT_MARKERS) or "__" in name:
        return None
    return "event", None


def _uncropped_event_snapshot_identity(path: str) -> str | None:
    """The image hash a sidecar vouches for, when it records an uncropped source and an identity.

    Older sidecars recorded no identity, so they cannot vouch for any image.
    """
    from app.services.classification_input_provenance import snapshot_source_is_uncropped_frame

    raw = _read_regular_file(f"{path}.meta.json", MAX_METADATA_BYTES)
    if raw is None or len(raw) >= MAX_METADATA_BYTES:
        return None
    try:
        metadata = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(metadata, dict) or not snapshot_source_is_uncropped_frame(metadata.get("source")):
        return None
    identity = metadata.get("image_sha256")
    return identity if isinstance(identity, str) and len(identity) == 64 else None


def _is_full_camera_frame(path: str, *, expected_sha256: str | None = None) -> bool:
    """A whole, decodable frame at least ``MIN_FRAME_SHORT_SIDE`` on its short side.

    With ``expected_sha256``, the bytes decoded here must be the image a sidecar
    vouched for, so a replacement written between the two reads is rejected.
    """
    import io

    from PIL import Image

    header = _read_regular_file(path, MAX_HEADER_BYTES)
    if not header:
        return False
    try:
        with Image.open(io.BytesIO(header)) as image:
            if image.format != "JPEG" or min(image.size) < MIN_FRAME_SHORT_SIDE:
                return False
    except (OSError, ValueError, Image.DecompressionBombError):
        return False
    data = _read_regular_file(path, MAX_FRAME_BYTES + 1)
    if not data or len(data) > MAX_FRAME_BYTES:
        return False
    if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
        return False
    try:
        with Image.open(io.BytesIO(data)) as image:
            # Decoding at 1/8 scale still reads every entropy-coded byte, so a
            # truncated file fails here instead of in a heavy device sweep.
            image.draft("RGB", (image.width // 8, image.height // 8))
            image.load()
    except (OSError, ValueError, Image.DecompressionBombError):
        return False
    return True


def select_check_frames(directory: Path, *, limit: int) -> list[str]:
    """Full camera frames for a device check: newest visits first, one per visit, then a second.

    Saved full frames are tried across all visits before any event snapshot, so
    a run of small or cropped snapshots cannot spend the read budget first.
    Returns nothing when fewer than ``MIN_CHECK_FRAMES`` qualify.
    """
    from app.services.media_cache import cache_name_event_id

    candidates: dict[str, list[tuple[str, str | None, float, str]]] = {}
    cropped_frames: set[tuple[str, str]] = set()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                variant = _frame_variant(entry.name)
                if variant is None:
                    continue
                visit = cache_name_event_id(entry.name)
                kind, frame = variant
                if kind == "crop":
                    if frame is not None:
                        cropped_frames.add((visit, frame))
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    modified = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                candidates.setdefault(visit, []).append((kind, frame, -modified, entry.path))
    except OSError:
        return []

    def full_frames(visit: str, frames: list[tuple[str, str | None, float, str]]) -> list[tuple[int, float, str]]:
        # A crop at the same frame means production found a bird in it.
        return sorted(
            (_FULL_FRAME_WITH_BIRD if (visit, frame) in cropped_frames else _FULL_FRAME, modified, path)
            for kind, frame, modified, path in frames
            if kind == "full"
        )

    def newest_first(visits: dict[str, list[tuple[int, float, str]]]) -> list[tuple[str, list[str]]]:
        ordered = sorted(visits.items(), key=lambda item: min(modified for _, modified, _ in item[1]))
        return [(visit, [path for _, _, path in frames]) for visit, frames in ordered]

    by_visit = {visit: full_frames(visit, frames) for visit, frames in candidates.items()}
    stages = [
        # Saved full frames across every visit first, then a second from the
        # same visits; event snapshots only fill what remains, so a run of small
        # or cropped snapshots cannot spend the read budget first.
        (newest_first({visit: frames for visit, frames in by_visit.items() if frames}), MAX_FRAMES_PER_VISIT, False),
        (
            newest_first(
                {
                    visit: [(_EVENT_SNAPSHOT, modified, path) for kind, _, modified, path in frames if kind == "event"]
                    for visit, frames in candidates.items()
                    if any(kind == "event" for kind, _, _, _ in frames)
                }
            ),
            1,
            True,
        ),
    ]
    chosen: list[str] = []
    taken: dict[str, int] = {}
    reads = 0
    for visits, rounds, needs_provenance in stages:
        queues = [(visit, list(paths)) for visit, paths in visits]
        # Rounds count this stage's own picks; the per-visit cap counts both stages.
        taken_this_stage: dict[str, int] = {}
        for round_index in range(rounds):
            for visit, paths in queues:
                if taken.get(visit, 0) >= MAX_FRAMES_PER_VISIT or taken_this_stage.get(visit, 0) > round_index:
                    continue
                while paths and len(chosen) < limit and reads < MAX_FRAME_HEADER_READS:
                    path = paths.pop(0)
                    reads += 1
                    expected = None
                    if needs_provenance:
                        expected = _uncropped_event_snapshot_identity(path)
                        if expected is None:
                            continue
                    if _is_full_camera_frame(path, expected_sha256=expected):
                        chosen.append(path)
                        taken[visit] = taken.get(visit, 0) + 1
                        taken_this_stage[visit] = taken_this_stage.get(visit, 0) + 1
                        break
    return chosen if len(chosen) >= MIN_CHECK_FRAMES else []


# Only reached when a check is due or waiting for frames; a settled context
# never lists the cache. The age limit covers filesystems whose coarse
# timestamps can leave the directory mtime unchanged across a write.
SELECTION_CACHE_MAX_AGE_SECONDS = 30 * 60
_monotonic = time.monotonic
_selection_cache: tuple[str, int, int, float, list[str], bool] | None = None


def _cached_selection() -> tuple[list[str], bool]:
    """The panel and whether any snapshot exists, listed again only after the directory changes.

    Any write, rename or delete in the snapshot cache changes its mtime, so an
    unchanged directory reuses the last listing instead of scanning it again,
    for at most ``SELECTION_CACHE_MAX_AGE_SECONDS``.
    """
    global _selection_cache
    from app.services.media_cache import SNAPSHOTS_DIR

    directory = str(SNAPSHOTS_DIR)
    try:
        info = os.stat(directory)
    except OSError:
        return [], False
    now = _monotonic()
    if (
        _selection_cache is not None
        and _selection_cache[:3] == (directory, info.st_mtime_ns, info.st_ino)
        and now - _selection_cache[3] < SELECTION_CACHE_MAX_AGE_SECONDS
    ):
        return list(_selection_cache[4]), _selection_cache[5]
    frames = select_check_frames(SNAPSHOTS_DIR, limit=MAX_CHECK_PHOTOS)
    present = bool(frames) or _any_snapshot(directory)
    _selection_cache = (directory, info.st_mtime_ns, info.st_ino, now, list(frames), present)
    return frames, present


def _any_snapshot(directory: str) -> bool:
    try:
        with os.scandir(directory) as entries:
            return any(entry.name.endswith(".jpg") for entry in entries)
    except OSError:
        return False


def recent_bird_photos() -> list[str]:
    """This host's own full camera frames: real feeder views that never leave the process."""
    return _cached_selection()[0]


def saved_bird_photos_present() -> bool:
    """Whether any saved snapshot exists, so an empty panel can say crops rather than nothing."""
    return _cached_selection()[1]


def stale_accelerators(previous: list[str], current: list[str], packaged: list[str]) -> list[str]:
    """Accelerators that passed for this finder before but are no longer current here."""
    return sorted(
        provider
        for provider in set(previous)
        if provider in ACCELERATED_PROVIDERS and provider in packaged and provider not in current
    )


def _ledger_path() -> Path:
    return validation._eval_root() / LEDGER_FILENAME


class FinderLedgerUnreadable(ValueError):
    """The record of earlier checks is damaged, so retries cannot be bounded."""


def _read_ledger() -> dict[str, Any]:
    path = _ledger_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FinderLedgerUnreadable(str(path)) from exc
    if not isinstance(data, dict):
        raise FinderLedgerUnreadable(str(path))
    return data


def _write_ledger_entry(key: str, status: dict[str, Any], *, replace_unreadable: bool = False) -> None:
    try:
        attempts = _read_ledger()
    except FinderLedgerUnreadable:
        # Only an owner-run check may start a fresh record; automatic checks
        # stay paused rather than lose the bound on their own retries.
        if not replace_unreadable:
            raise
        attempts = {}
    attempts[key] = status
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    validation._write_json_atomic(path, attempts)


def photo_set_signature(photos: list[str]) -> str:
    rows = []
    for name in sorted(set(photos)):
        try:
            stat = Path(name).stat()
            rows.append((name, stat.st_size, stat.st_mtime_ns))
        except OSError:
            rows.append((name, None, None))
    return validation._identity_digest({"photos": rows})


# A busy feeder saves a snapshot most minutes, so a changed photo set alone
# would rerun a full device check on every five-minute scheduler pass. Each
# further empty baseline doubles the wait, up to once a day.
EMPTY_BASELINE_FIRST_WAIT = timedelta(hours=4)
EMPTY_BASELINE_MAX_WAIT = timedelta(hours=24)
# Results that settle a runtime/preference context: rerunning cannot change them.
FINAL_FAILURE_CODES = frozenset({"mismatch", "no_accelerator"})
INCONCLUSIVE_CODES = frozenset({"unfinished", "interrupted", "superseded"})
MAX_INCONCLUSIVE_ATTEMPTS = 3
OWNER_CHECK_PREFIX = "owner:"


def _parse_utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _latest_first_key(entry: dict[str, Any]) -> datetime:
    return _parse_utc(entry.get("checked_at")) or datetime.min.replace(tzinfo=timezone.utc)


def empty_baseline_wait(rechecks: int) -> timedelta:
    return min(EMPTY_BASELINE_FIRST_WAIT * 2 ** min(max(rechecks, 1) - 1, 5), EMPTY_BASELINE_MAX_WAIT)


def retry_due(entry: dict[str, Any], *, photo_signature: str | None, now: datetime) -> bool:
    """Only a completed comparison consumes a runtime/preference context.

    ``photo_signature=None`` asks the time rules alone, before any photo is listed.
    """
    state = entry.get("state")
    code = entry.get("reason_code")
    if state == "succeeded" or (state == "failed" and code in FINAL_FAILURE_CODES):
        return False
    checked = _parse_utc(entry.get("checked_at"))
    if checked is None:
        return False
    # A clock that ran ahead before NTP corrected it would otherwise postpone
    # the next check by its whole offset.
    clock_ran_ahead = checked > now
    if code == "no_positive_baseline":
        wait = empty_baseline_wait(int(entry.get("empty_baseline_count") or 1))
        photos_changed = photo_signature is None or entry.get("photo_signature") != photo_signature
        return photos_changed and (clock_ran_ahead or now >= checked + wait)
    count = int(entry.get("attempt_count") or 1)
    if count >= MAX_INCONCLUSIVE_ATTEMPTS:
        return False
    if clock_ran_ahead:
        return True
    if entry.get("next_retry_at"):
        deadline = _parse_utc(entry["next_retry_at"])
        return deadline is not None and now >= deadline
    return now >= checked + timedelta(hours=1 if count == 1 else 4)


def classify_check_outcome(
    result: dict[str, Any], *, model_id: str, requested: list[str], eligible: list[str]
) -> tuple[str, FinderCheckReasonCode, str]:
    """State, stable code and plain reason for one finished device sweep."""
    entries = [entry for entry in result.get("providers") or [] if entry.get("provider") in ACCELERATED_PROVIDERS]
    baseline = result.get("baseline_status")
    if baseline == "unavailable":
        return (
            "failed",
            "unfinished",
            "The CPU baseline could not finish, so accelerator agreement was not checked. Previous evidence is unchanged.",
        )
    if baseline == "no_positive" or any(entry.get("baseline_has_birds") is False for entry in entries):
        return (
            "failed",
            "no_positive_baseline",
            "The CPU found no admitted birds in the saved photos, so accelerator agreement could not be checked. Previous accelerator evidence is unchanged.",
        )
    usable = ACCELERATED_PROVIDERS if model_id == RFDETR_FINDER else set(requested)
    if usable & set(eligible):
        if model_id == RFDETR_FINDER and "intel_npu" not in eligible and "intel_gpu" in eligible:
            return (
                "succeeded",
                "gpu_recovery",
                "The NPU did not pass; the finder uses its verified GPU from the next frame.",
            )
        return (
            "succeeded",
            "passed",
            "The finder has current passing accelerator evidence and uses it from the next frame.",
        )
    if not entries:
        return (
            "failed",
            "no_accelerator",
            "No NPU or GPU could be opened when the check ran, so the finder stays on the CPU. Restore device access to the container, then Check devices.",
        )
    mismatch = all(
        entry.get("comparison_mismatch", entry.get("ok") is False and not entry.get("error")) for entry in entries
    )
    if mismatch:
        return (
            "failed",
            "mismatch",
            "The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU.",
        )
    return "failed", "unfinished", "The automatic finder check could not finish. A bounded automatic retry will follow."


def _runtime_signatures_current(entry: dict[str, Any]) -> bool:
    signatures = entry.get("runtime_signatures") or {}
    return bool(signatures) and all(
        signature == validation.current_provider_runtime_signature(provider)
        for provider, signature in signatures.items()
    )


def _owner_check_covers(entry: Any, *, artifact: str | None, preference: str, stale: list[str]) -> bool:
    """An owner-run check on this runtime already answered what an automatic one would ask."""
    return (
        isinstance(entry, dict)
        and entry.get("artifact_sha256") == artifact
        and entry.get("preference") == preference
        and entry.get("photo_selection") == PHOTO_SELECTION_POLICY
        and set(stale) <= set(entry.get("requested_providers") or [])
        and _runtime_signatures_current(entry)
    )


def waiting_for_photos_status(
    model_id: str,
    accelerators: list[str],
    *,
    crops_only: bool,
    last_result: BirdFinderCheckResult | None = None,
) -> BirdFinderCheckStatus:
    """A check that cannot start yet; waiting never spends an attempt."""
    if crops_only:
        return BirdFinderCheckStatus(
            state="waiting",
            reason_code="no_full_frames",
            model_id=model_id,
            providers=accelerators,
            reason=f"The saved bird photos are close crops, not full camera frames, so devices cannot be compared yet. The check runs once YA-WAMF has saved at least {MIN_CHECK_FRAMES} full frames.",
            last_result=last_result,
        )
    return BirdFinderCheckStatus(
        state="waiting",
        reason_code="no_photos",
        model_id=model_id,
        providers=accelerators,
        reason="No saved bird photos to compare devices on yet. The check waits for saved photos.",
        last_result=last_result,
    )


def _entry_status(entry: dict[str, Any]) -> BirdFinderCheckStatus:
    """A stored context's status; a check still marked running was cut off by a restart."""
    status = BirdFinderCheckStatus.model_validate(entry)
    status.runtime_current = True
    if status.state == "running":
        status.state, status.reason_code = "interrupted", "interrupted"
        status.reason = (
            "The previous check was interrupted. Check devices for this finder to retry."
            if status.attempt_count >= MAX_INCONCLUSIVE_ATTEMPTS
            else "The previous check was interrupted. A bounded automatic retry will follow."
        )
    return status


@dataclass(frozen=True)
class PreparedFinderCheck:
    status: BirdFinderCheckStatus
    key: str | None = None
    providers: tuple[str, ...] = ()
    attempt_count: int = 0
    photo_signature: str = ""
    empty_baseline_count: int = 0
    photos: tuple[str, ...] = ()


class BirdFinderRevalidation:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._status = BirdFinderCheckStatus()
        self._lock = asyncio.Lock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_ledger_warning: datetime | None = None

    def status(self) -> dict[str, Any]:
        return self._status.model_dump()

    def _publish(self, **fields: Any) -> None:
        # Status readers also run in diagnostic worker threads. Publish one
        # complete immutable snapshot instead of mutating shared fields.
        self._status = self._status.model_copy(update=fields)

    def _prepare(
        self,
        model_id: str,
        artifact: str | None,
        *,
        photos: list[str] | None = None,
        load_photos: Callable[[], list[str]] | None = None,
    ) -> PreparedFinderCheck:
        attempts = _read_ledger()
        matching = [
            entry
            for entry in attempts.values()
            if isinstance(entry, dict)
            and entry.get("model_id") == model_id
            and entry.get("artifact_sha256", artifact) == artifact
        ]
        status = BirdFinderCheckStatus()
        if matching:
            latest = max(matching, key=_latest_first_key)
            status = BirdFinderCheckStatus.model_validate(latest)
            status.runtime_current = _runtime_signatures_current(latest)
            if status.last_result is not None:
                status.last_result.runtime_current = status.runtime_current and (
                    status.state != "running" or status.last_result.runtime_current
                )
            if status.state == "running":
                status.state, status.reason_code = "interrupted", "interrupted"
                status.reason = (
                    "The previous check was interrupted. Check devices for this finder to retry."
                    if status.attempt_count >= 3
                    else "The previous check was interrupted. A bounded automatic retry will follow."
                )
        data = validation._read_current_eligibility_payload()
        previous = [str(provider) for provider in (data.get("models") or {}).get(model_id) or []]
        previous.extend(
            provider
            for entry in matching
            for provider in entry.get("requested_providers", entry.get("providers") or [])
        )
        current = validation.host_eligible_providers(model_id, artifact_sha256=artifact)
        packaged = validation.packaged_inference_providers(validation.get_image_flavor())
        preference = settings.classification.bird_crop_inference_provider
        if preference != "auto":
            previous = [provider for provider in previous if provider in {"cpu", "intel_cpu", preference}]
            if preference in ACCELERATED_PROVIDERS:
                previous.append(preference)
        # Packaging is not presence: an image can ship the NPU and GPU runtimes to
        # a host that never passed the devices through, where a sweep could
        # probe only the CPU and prove nothing.
        present = present_accelerators()
        if model_id == RFDETR_FINDER and preference in {"auto", "intel_npu", "intel_gpu"}:
            preferred = "intel_gpu" if preference == "intel_gpu" else "intel_npu"
            if preferred in current:
                return PreparedFinderCheck(status)
            previous.extend(provider for provider in ("intel_npu", "intel_gpu") if provider in packaged)
        stale = [provider for provider in stale_accelerators(previous, current, packaged) if provider in present]
        if not stale:
            return PreparedFinderCheck(status)
        # OpenVINO CPU cannot move RF-DETR off the CPU, so it never earns a probe.
        openvino_cpu = set() if model_id == RFDETR_FINDER else {"intel_cpu"} & set(previous) & set(packaged)
        providers = sorted({"cpu", *stale} | openvino_cpu)
        key = validation._identity_digest(
            {
                "model": model_id,
                "artifact": artifact,
                "preference": preference,
                "comparison_policy": 3,
                "photo_selection": PHOTO_SELECTION_POLICY,
                "runtime": {
                    provider: validation.current_provider_runtime_signature(provider)
                    for provider in sorted({"cpu"} | (set(previous) & ACCELERATED_PROVIDERS & set(packaged)))
                },
            }
        )
        # Time decides first, so a settled context never lists the snapshot
        # cache; the photo set is read only when a check could actually run.
        now = self._clock()
        owner_check = attempts.get(f"{OWNER_CHECK_PREFIX}{model_id}")
        owner_applies = _owner_check_covers(owner_check, artifact=artifact, preference=preference, stale=stale)
        if owner_applies and not retry_due(owner_check, photo_signature=None, now=now):
            return PreparedFinderCheck(status)
        entry = attempts.get(key)
        previous_code = None
        if entry is not None:
            previous_code = "interrupted" if entry.get("state") == "running" else entry.get("reason_code")
            if not retry_due(entry | {"reason_code": previous_code}, photo_signature=None, now=now):
                return PreparedFinderCheck(_entry_status(entry))
        if photos is None:
            photos = load_photos() if load_photos is not None else []
        photo_signature = photo_set_signature(photos)
        if owner_applies and not retry_due(owner_check, photo_signature=photo_signature, now=now):
            return PreparedFinderCheck(status)
        count = 1
        empty_baselines = 0
        if entry is not None:
            status = _entry_status(entry)
            if not retry_due(entry | {"reason_code": previous_code}, photo_signature=photo_signature, now=now):
                return PreparedFinderCheck(status)
            if status.reason_code == "no_positive_baseline":
                empty_baselines = int(entry.get("empty_baseline_count") or 1)
            else:
                count = int(entry.get("attempt_count") or 1) + 1
        return PreparedFinderCheck(
            status, key, tuple(providers), count, photo_signature, empty_baselines, tuple(photos)
        )

    def _warn_rate_limited(self, event: str, **fields: Any) -> None:
        now = self._clock()
        if self._last_ledger_warning is None or now - self._last_ledger_warning >= timedelta(hours=1):
            self._last_ledger_warning = now
            log.warning(event, **fields)

    async def note_owner_check_waiting(self, model_id: str) -> None:
        """An owner-run check found no full frames; say so where Settings reads the check."""
        crops_only = await asyncio.to_thread(saved_bird_photos_present)
        finder = await asyncio.to_thread(selected_finder)
        if finder is not None and finder[0] == model_id:
            self._status = waiting_for_photos_status(
                model_id,
                sorted(ACCELERATED_PROVIDERS & present_accelerators()),
                crops_only=crops_only,
                last_result=self._status.last_result,
            )

    async def record_owner_check(self, model_id: str, artifact: str | None, result: dict[str, Any] | None) -> None:
        """Remember an owner-run sweep so the automatic check does not repeat it minutes later."""
        crashed = not result
        result = result or {}
        probed = [str(entry["provider"]) for entry in result.get("providers") or [] if entry.get("provider")]
        accelerators = [provider for provider in probed if provider in ACCELERATED_PROVIDERS]
        if crashed:
            # An owner sweep tries every device it can reach; a crash leaves no
            # list, so it stands for all of them.
            accelerators = sorted(ACCELERATED_PROVIDERS & present_accelerators())
        state, code, reason = classify_check_outcome(
            result, model_id=model_id, requested=accelerators, eligible=list(result.get("eligible_providers") or [])
        )
        if crashed:
            state, code, reason = (
                "failed",
                "unfinished",
                "The device check could not finish. Check devices for this finder to retry.",
            )
        status = BirdFinderCheckStatus(
            state=state,
            reason_code=code,
            reason=reason.replace(" A bounded automatic retry will follow.", ""),
            model_id=model_id,
            providers=accelerators,
            checked_at=self._clock().isoformat(),
            attempt_count=1,
        )
        status.last_result = BirdFinderCheckResult.model_validate(status.model_dump())
        entry = status.model_dump() | {
            "artifact_sha256": artifact,
            "requested_providers": accelerators,
            "preference": settings.classification.bird_crop_inference_provider,
            "photo_selection": PHOTO_SELECTION_POLICY,
            "photo_signature": "",
            "runtime_signatures": {
                provider: validation.current_provider_runtime_signature(provider)
                for provider in {"cpu", *probed, *accelerators}
            },
        }
        try:
            await asyncio.to_thread(
                _write_ledger_entry, f"{OWNER_CHECK_PREFIX}{model_id}", entry, replace_unreadable=True
            )
        except OSError:
            self._warn_rate_limited("bird_finder_owner_check_write_failed", model_id=model_id)
        finder = await asyncio.to_thread(selected_finder)
        if finder is not None and finder[0] == model_id:
            self._status = status

    async def run(self) -> None:
        async with self._lock:
            prepared: PreparedFinderCheck | None = None
            result: dict[str, Any] = {}
            metadata: dict[str, Any] = {}
            guard: asyncio.Lock | None = None
            try:
                finder = await asyncio.to_thread(selected_finder)
                if finder is None:
                    return
                model_id, artifact = finder
                if validation.crop_validation_lock(model_id).locked():
                    return
                preference = settings.classification.bird_crop_inference_provider
                prepared = await asyncio.to_thread(
                    self._prepare, model_id, artifact, load_photos=lambda: recent_bird_photos()
                )
                self._status = prepared.status
                if prepared.key is None:
                    return
                photos = list(prepared.photos)
                providers = list(prepared.providers)
                accelerators = [provider for provider in providers if provider in ACCELERATED_PROVIDERS]
                previous_result = self._status.last_result
                if self._status.checked_at and self._status.state not in {"idle", "waiting", "running"}:
                    previous_result = BirdFinderCheckResult.model_validate(self.status())
                if not photos:
                    crops_only = await asyncio.to_thread(saved_bird_photos_present)
                    self._status = waiting_for_photos_status(
                        model_id, accelerators, crops_only=crops_only, last_result=previous_result
                    )
                    prepared = None
                    return
                hardware_guard = validation.crop_validation_lock(model_id)
                if hardware_guard.locked():
                    prepared = None
                    return
                # Taken before the ledger write yields, so an owner check that
                # starts in that window waits for this sweep instead of
                # following it with a duplicate.
                await hardware_guard.acquire()
                guard = hardware_guard
                metadata = {
                    "artifact_sha256": artifact,
                    "requested_providers": accelerators,
                    "photo_signature": prepared.photo_signature,
                    "attempt_count": prepared.attempt_count,
                    "empty_baseline_count": prepared.empty_baseline_count,
                    "preference": preference,
                    "runtime_signatures": {
                        provider: validation.current_provider_runtime_signature(provider) for provider in providers
                    },
                }
                self._status = BirdFinderCheckStatus(
                    state="running",
                    reason_code="driver_changed",
                    model_id=model_id,
                    providers=accelerators,
                    checked_at=self._clock().isoformat(),
                    attempt_count=prepared.attempt_count,
                    reason="The inference runtime changed. Re-checking this finder's accelerators once on saved bird photos.",
                    last_result=previous_result,
                )
                await asyncio.to_thread(_write_ledger_entry, prepared.key, self.status() | metadata)
                if model_id == RFDETR_FINDER:
                    result = await sweep_crop_model_devices(
                        model_id,
                        image_paths=photos,
                        only_providers=set(providers),
                        prefer_accelerators=True,
                        hardware_guard_held=True,
                    )
                else:
                    result = await sweep_crop_model_devices(
                        model_id, image_paths=photos, only_providers=set(providers), hardware_guard_held=True
                    )
                self._publish(
                    providers=[
                        entry["provider"]
                        for entry in result.get("providers") or []
                        if entry.get("provider") in ACCELERATED_PROVIDERS
                    ]
                )
                if (
                    await asyncio.to_thread(selected_finder) != finder
                    or settings.classification.bird_crop_inference_provider != preference
                ):
                    self._publish(
                        state="superseded",
                        reason_code="superseded",
                        reason="The bird finder changed while the check ran; no result was applied.",
                    )
                    return
                baseline = result.get("baseline_status")
                if baseline == "unavailable":
                    state, code, reason = classify_check_outcome(
                        result, model_id=model_id, requested=accelerators, eligible=[]
                    )
                    self._publish(state=state, reason_code=code, reason=reason)
                    return
                current = await asyncio.to_thread(
                    validation.host_eligible_providers, model_id, artifact_sha256=artifact
                )
                current_results = await asyncio.to_thread(
                    validation.host_provider_validation_results, model_id, artifact_sha256=artifact
                )
                checked = {entry["provider"] for entry in result.get("providers") or []}
                if baseline == "no_positive":
                    checked = {"cpu"}
                eligible = list(
                    dict.fromkeys(
                        [provider for provider in current if provider not in checked]
                        + list(result.get("eligible_providers") or [])
                    )
                )
                await asyncio.to_thread(
                    validation.write_eligibility_entry,
                    model_id,
                    eligible,
                    image_flavor=str(result.get("image_flavor") or validation.get_image_flavor()),
                    provider_results=list(current_results.values()) + list(result.get("providers") or []),
                    artifact_sha256=artifact,
                )
                saved = await asyncio.to_thread(validation.host_eligible_providers, model_id, artifact_sha256=artifact)
                if set(saved) != set(eligible):
                    raise RuntimeError("Could not persist finder provider validation")
                best = result.get("best") or {}
                await asyncio.to_thread(
                    validation.write_validation_record,
                    model_id,
                    provider=str(best.get("provider") or "cpu"),
                    ok=bool(eligible),
                    reason="crop detector re-validated against the CPU box baseline on saved bird photos",
                    latency_ms=best.get("latency_ms"),
                    artifact_sha256=artifact,
                )
                _reset_in_process_finder()
                state, code, reason = classify_check_outcome(
                    result, model_id=model_id, requested=accelerators, eligible=eligible
                )
                self._publish(state=state, reason_code=code, reason=reason)
            except asyncio.CancelledError:
                self._publish(
                    state="interrupted",
                    reason_code="interrupted",
                    reason="The check was interrupted. A bounded automatic retry will follow.",
                )
                raise
            except FinderLedgerUnreadable:
                self._publish(
                    state="failed",
                    reason_code="ledger_unreadable",
                    reason="The record of earlier finder checks could not be read, so automatic checks are paused instead of repeating. Check devices for this finder to run one and start a new record.",
                )
                self._warn_rate_limited("bird_finder_revalidation_ledger_unreadable")
            except Exception as exc:
                self._publish(
                    state="failed",
                    reason_code="unfinished",
                    reason="The automatic finder check could not finish. A bounded automatic retry will follow.",
                )
                self._warn_rate_limited("bird_finder_revalidation_failed", error_type=type(exc).__name__)
            finally:
                try:
                    if (
                        prepared is not None
                        and prepared.key is not None
                        and metadata
                        and self._status.reason_code != "ledger_unreadable"
                    ):
                        await self._finish(prepared.key, prepared, metadata, result)
                finally:
                    if guard is not None:
                        guard.release()

    async def _finish(
        self, key: str, prepared: PreparedFinderCheck, metadata: dict[str, Any], result: dict[str, Any]
    ) -> None:
        inconclusive = self._status.reason_code in INCONCLUSIVE_CODES
        next_retry = None
        if inconclusive and prepared.attempt_count < MAX_INCONCLUSIVE_ATTEMPTS:
            next_retry = (self._clock() + timedelta(hours=1 if prepared.attempt_count == 1 else 4)).isoformat()
        if inconclusive and prepared.attempt_count >= MAX_INCONCLUSIVE_ATTEMPTS:
            reason = (self._status.reason or "").replace(" A bounded automatic retry will follow.", "")
            self._publish(reason=f"{reason} Automatic retry limit reached. Check devices for this finder to retry.")
        if self._status.reason_code == "no_positive_baseline":
            metadata = metadata | {"empty_baseline_count": prepared.empty_baseline_count + 1}
        self._publish(next_retry_at=next_retry, last_result=BirdFinderCheckResult.model_validate(self.status()))
        log.info(
            "bird_finder_revalidation_result",
            model_id=self._status.model_id,
            outcome=self._status.state,
            reason_code=self._status.reason_code,
            providers=self._status.providers,
            attempt_count=prepared.attempt_count,
            box_diff=[
                {
                    field: entry.get(field)
                    for field in (
                        "provider",
                        "ok",
                        "finite",
                        "compiles",
                        "baseline_has_birds",
                        "baseline_boxes",
                        "provider_boxes",
                        "matched_boxes",
                        "ignored_boundary_boxes",
                        "nms_grouped_boxes",
                        "worst_box_iou",
                        "error",
                    )
                }
                for entry in result.get("providers") or []
            ],
        )
        try:
            await asyncio.to_thread(_write_ledger_entry, key, self.status() | metadata)
        except (OSError, ValueError):
            self._warn_rate_limited("bird_finder_revalidation_outcome_write_failed", model_id=self._status.model_id)


def _reset_in_process_finder() -> None:
    """Workers re-read evidence on each crop; this process's own copy needs a reset."""
    try:
        from app.services.bird_crop_service import bird_crop_service

        bird_crop_service.reset_models()
    except Exception as exc:
        log.warning("bird_finder_revalidation_reset_failed", error=str(exc))


bird_finder_revalidation = BirdFinderRevalidation()
