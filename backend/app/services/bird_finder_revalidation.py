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
import json
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


def newest_snapshots(directory: Path, *, limit: int) -> list[str]:
    """Newest full-size cached snapshots; thumbnails are too small to compare boxes on."""
    try:
        candidates = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".jpg" and not path.name.endswith("_thumb.jpg")
        ]
    except OSError:
        return []
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path) for path in candidates[:limit]]


def recent_bird_photos() -> list[str]:
    """This host's own bird snapshots: real feeder frames that never leave the process."""
    from app.services.media_cache import SNAPSHOTS_DIR

    return newest_snapshots(SNAPSHOTS_DIR, limit=MAX_CHECK_PHOTOS)


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


def retry_due(entry: dict[str, Any], *, photo_signature: str, now: datetime) -> bool:
    """Only a completed comparison consumes a runtime/preference context."""
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
        return entry.get("photo_signature") != photo_signature and (clock_ran_ahead or now >= checked + wait)
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
        and set(stale) <= set(entry.get("requested_providers") or [])
        and _runtime_signatures_current(entry)
    )


@dataclass(frozen=True)
class PreparedFinderCheck:
    status: BirdFinderCheckStatus
    key: str | None = None
    providers: tuple[str, ...] = ()
    attempt_count: int = 0
    photo_signature: str = ""
    empty_baseline_count: int = 0


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

    def _prepare(self, model_id: str, artifact: str | None, *, photos: list[str] | None = None) -> PreparedFinderCheck:
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
                "runtime": {
                    provider: validation.current_provider_runtime_signature(provider)
                    for provider in sorted({"cpu"} | (set(previous) & ACCELERATED_PROVIDERS & set(packaged)))
                },
            }
        )
        photo_signature = photo_set_signature(photos or [])
        owner_check = attempts.get(f"{OWNER_CHECK_PREFIX}{model_id}")
        if _owner_check_covers(owner_check, artifact=artifact, preference=preference, stale=stale) and not retry_due(
            owner_check, photo_signature=photo_signature, now=self._clock()
        ):
            return PreparedFinderCheck(status)
        count = 1
        empty_baselines = 0
        if key in attempts:
            entry = attempts[key]
            status = BirdFinderCheckStatus.model_validate(entry)
            status.runtime_current = True
            if status.state == "running":
                status.state, status.reason_code = "interrupted", "interrupted"
                status.reason = (
                    "The previous check was interrupted. Check devices for this finder to retry."
                    if status.attempt_count >= 3
                    else "The previous check was interrupted. A bounded automatic retry will follow."
                )
            if not retry_due(
                entry | {"reason_code": status.reason_code}, photo_signature=photo_signature, now=self._clock()
            ):
                return PreparedFinderCheck(status)
            if status.reason_code == "no_positive_baseline":
                empty_baselines = int(entry.get("empty_baseline_count") or 1)
            else:
                count = int(entry.get("attempt_count") or 1) + 1
        return PreparedFinderCheck(status, key, tuple(providers), count, photo_signature, empty_baselines)

    def _warn_rate_limited(self, event: str, **fields: Any) -> None:
        now = self._clock()
        if self._last_ledger_warning is None or now - self._last_ledger_warning >= timedelta(hours=1):
            self._last_ledger_warning = now
            log.warning(event, **fields)

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
                photos = await asyncio.to_thread(recent_bird_photos)
                prepared = await asyncio.to_thread(self._prepare, model_id, artifact, photos=photos)
                self._status = prepared.status
                if prepared.key is None:
                    return
                providers = list(prepared.providers)
                accelerators = [provider for provider in providers if provider in ACCELERATED_PROVIDERS]
                previous_result = self._status.last_result
                if self._status.checked_at and self._status.state not in {"idle", "waiting", "running"}:
                    previous_result = BirdFinderCheckResult.model_validate(self.status())
                if not photos:
                    self._status = BirdFinderCheckStatus(
                        state="waiting",
                        reason_code="no_photos",
                        model_id=model_id,
                        providers=accelerators,
                        reason="No saved bird photos to compare devices on yet. The check waits for saved photos.",
                        last_result=previous_result,
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
