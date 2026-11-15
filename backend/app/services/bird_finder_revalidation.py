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


def _read_ledger() -> dict[str, Any]:
    path = _ledger_path()
    if not path.exists():
        return {}
    # An unreadable ledger cannot safely enforce bounded retries.
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid finder revalidation ledger")
    return data


def _write_ledger_entry(key: str, status: dict[str, Any]) -> None:
    attempts = _read_ledger()
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


def retry_due(entry: dict[str, Any], *, photo_signature: str, now: datetime) -> bool:
    """Only a completed comparison consumes a runtime/preference context."""
    state = entry.get("state")
    code = entry.get("reason_code")
    if state == "succeeded" or (state == "failed" and code == "mismatch"):
        return False
    if code == "no_positive_baseline":
        return entry.get("photo_signature") != photo_signature
    count = int(entry.get("attempt_count") or 1)
    if count >= 3:
        return False
    try:
        checked = datetime.fromisoformat(str(entry.get("checked_at") or "").replace("Z", "+00:00"))
        checked = checked.replace(tzinfo=timezone.utc) if checked.tzinfo is None else checked
    except ValueError:
        return False
    delay = timedelta(hours=1 if count == 1 else 4)
    if entry.get("next_retry_at"):
        try:
            deadline = datetime.fromisoformat(str(entry["next_retry_at"]).replace("Z", "+00:00"))
            deadline = deadline.replace(tzinfo=timezone.utc) if deadline.tzinfo is None else deadline
            return now >= deadline
        except ValueError:
            return False
    return now >= checked + delay


@dataclass(frozen=True)
class PreparedFinderCheck:
    status: BirdFinderCheckStatus
    key: str | None = None
    providers: tuple[str, ...] = ()
    attempt_count: int = 0
    photo_signature: str = ""


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
            latest = max(matching, key=lambda entry: str(entry.get("checked_at") or ""))
            status = BirdFinderCheckStatus.model_validate(latest)
            signatures = latest.get("runtime_signatures") or {}
            status.runtime_current = bool(signatures) and all(
                signature == validation.current_provider_runtime_signature(provider)
                for provider, signature in signatures.items()
            )
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
        from app.services.bird_finder_health import RFDETR_FINDER

        if model_id == RFDETR_FINDER and preference in {"auto", "intel_npu", "intel_gpu"}:
            preferred = "intel_gpu" if preference == "intel_gpu" else "intel_npu"
            if preferred in current:
                return PreparedFinderCheck(status)
            previous.extend(provider for provider in ("intel_npu", "intel_gpu") if provider in packaged)
        stale = stale_accelerators(previous, current, packaged)
        if not stale:
            return PreparedFinderCheck(status)
        providers = sorted({"cpu", *stale} | ({"intel_cpu"} & set(previous) & set(packaged)))
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
        count = 1
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
            count = 1 if status.reason_code == "no_positive_baseline" else int(entry.get("attempt_count") or 1) + 1
        return PreparedFinderCheck(status, key, tuple(providers), count, photo_signature)

    async def run(self) -> None:
        async with self._lock:
            prepared: PreparedFinderCheck | None = None
            result: dict[str, Any] = {}
            metadata: dict[str, Any] = {}
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
                if validation.crop_validation_lock(model_id).locked():
                    prepared = None
                    return
                metadata = {
                    "artifact_sha256": artifact,
                    "requested_providers": accelerators,
                    "photo_signature": prepared.photo_signature,
                    "attempt_count": prepared.attempt_count,
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
                from app.services.bird_finder_health import RFDETR_FINDER

                if model_id == RFDETR_FINDER:
                    result = await sweep_crop_model_devices(
                        model_id, image_paths=photos, only_providers=set(providers), prefer_accelerators=True
                    )
                else:
                    result = await sweep_crop_model_devices(model_id, image_paths=photos, only_providers=set(providers))
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
                    self._publish(
                        state="failed",
                        reason_code="unfinished",
                        reason="The CPU baseline could not finish, so accelerator agreement was not checked. Previous evidence is unchanged.",
                    )
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
                usable_accelerators = ACCELERATED_PROVIDERS if model_id == RFDETR_FINDER else set(accelerators)
                if baseline == "no_positive" or any(
                    entry.get("baseline_has_birds") is False for entry in result.get("providers") or []
                ):
                    self._publish(
                        state="failed",
                        reason_code="no_positive_baseline",
                        reason="The CPU found no admitted birds in the saved photos, so accelerator agreement could not be checked. Previous accelerator evidence is unchanged.",
                    )
                elif usable_accelerators & set(eligible):
                    gpu_recovery = model_id == RFDETR_FINDER and "intel_npu" not in eligible and "intel_gpu" in eligible
                    self._publish(
                        state="succeeded",
                        reason_code="gpu_recovery" if gpu_recovery else "passed",
                        reason="The NPU did not pass; the finder uses its verified GPU from the next frame."
                        if gpu_recovery
                        else "The finder has current passing accelerator evidence and uses it from the next frame.",
                    )
                else:
                    entries = [
                        entry
                        for entry in result.get("providers") or []
                        if entry.get("provider") in ACCELERATED_PROVIDERS
                    ]
                    mismatch = bool(entries) and all(
                        entry.get("comparison_mismatch", entry.get("ok") is False and not entry.get("error"))
                        for entry in entries
                    )
                    self._publish(
                        state="failed",
                        reason_code="mismatch" if mismatch else "unfinished",
                        reason="The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU."
                        if mismatch
                        else "The automatic finder check could not finish. A bounded automatic retry will follow.",
                    )
            except asyncio.CancelledError:
                self._publish(
                    state="interrupted",
                    reason_code="interrupted",
                    reason="The check was interrupted. A bounded automatic retry will follow.",
                )
                raise
            except Exception as exc:
                self._publish(
                    state="failed",
                    reason_code="unfinished",
                    reason="The automatic finder check could not finish. A bounded automatic retry will follow.",
                )
                now = self._clock()
                if self._last_ledger_warning is None or now - self._last_ledger_warning >= timedelta(hours=1):
                    self._last_ledger_warning = now
                    log.warning("bird_finder_revalidation_failed", error_type=type(exc).__name__)
            finally:
                if prepared is not None and prepared.key is not None and metadata:
                    next_retry = None
                    if (
                        self._status.reason_code in {"unfinished", "interrupted", "superseded"}
                        and prepared.attempt_count < 3
                    ):
                        next_retry = (
                            self._clock() + timedelta(hours=1 if prepared.attempt_count == 1 else 4)
                        ).isoformat()
                    if (
                        self._status.reason_code in {"unfinished", "interrupted", "superseded"}
                        and prepared.attempt_count >= 3
                    ):
                        reason = (self._status.reason or "").replace(" A bounded automatic retry will follow.", "")
                        self._publish(
                            reason=f"{reason} Automatic retry limit reached. Check devices for this finder to retry."
                        )
                    self._publish(
                        next_retry_at=next_retry, last_result=BirdFinderCheckResult.model_validate(self.status())
                    )
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
                                    "worst_box_iou",
                                    "error",
                                )
                            }
                            for entry in result.get("providers") or []
                        ],
                    )
                    try:
                        await asyncio.to_thread(_write_ledger_entry, prepared.key, self.status() | metadata)
                    except (OSError, ValueError):
                        log.warning("bird_finder_revalidation_outcome_write_failed", model_id=self._status.model_id)


def _reset_in_process_finder() -> None:
    """Workers re-read evidence on each crop; this process's own copy needs a reset."""
    try:
        from app.services.bird_crop_service import bird_crop_service

        bird_crop_service.reset_models()
    except Exception as exc:
        log.warning("bird_finder_revalidation_reset_failed", error=str(exc))


bird_finder_revalidation = BirdFinderRevalidation()
