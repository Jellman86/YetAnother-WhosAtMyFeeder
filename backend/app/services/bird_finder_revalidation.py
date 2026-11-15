"""One bounded recovery attempt for the bird finder's previously verified accelerators.

Device evidence is bound to the kernel, drivers and inference packages, so a
host or image update makes it stale. The identification model re-checks its own
accelerator once after such a change; without the same step the bird finder
silently stayed on the CPU after every update until an owner re-ran the check.

Previously checked accelerators and an explicitly saved accelerator are checked
once per runtime. Failed checks never authorize accelerator use.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
    # An unreadable ledger cannot safely promise an at-most-once attempt.
    return json.loads(path.read_text(encoding="utf-8"))


def _write_ledger_entry(key: str, status: dict[str, Any]) -> None:
    attempts = _read_ledger()
    attempts[key] = status
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    validation._write_json_atomic(path, attempts)


class BirdFinderRevalidation:
    def __init__(self) -> None:
        self._status = BirdFinderCheckStatus()
        self._lock = asyncio.Lock()

    def status(self) -> dict[str, Any]:
        return self._status.model_dump()

    def _prepare(self, model_id: str, artifact: str | None) -> tuple[str, list[str]] | None:
        attempts = _read_ledger()
        matching = [
            (key, entry)
            for key, entry in attempts.items()
            if entry.get("model_id") == model_id and entry.get("artifact_sha256", artifact) == artifact
        ]
        if matching:
            _, latest = max(matching, key=lambda item: str(item[1].get("checked_at") or ""))
            self._status = BirdFinderCheckStatus.model_validate(latest)
            signatures = latest.get("runtime_signatures") or {}
            self._status.runtime_current = bool(signatures) and all(
                signature == validation.current_provider_runtime_signature(provider)
                for provider, signature in signatures.items()
            )
            if self._status.last_result is not None:
                self._status.last_result.runtime_current = self._status.runtime_current and (
                    self._status.state != "running" or self._status.last_result.runtime_current
                )
            if self._status.state == "running":
                self._status.state = "interrupted"
                self._status.reason_code = "interrupted"
                self._status.reason = "The previous check was interrupted. Check devices for this finder to retry."
        data = validation._read_current_eligibility_payload()
        previous = [str(provider) for provider in (data.get("models") or {}).get(model_id) or []]
        previous.extend(
            provider
            for _, entry in matching
            for provider in entry.get("requested_providers", entry.get("providers") or [])
        )
        current = validation.host_eligible_providers(model_id, artifact_sha256=artifact)
        packaged = validation.packaged_inference_providers(validation.get_image_flavor())
        preference = settings.classification.bird_crop_inference_provider
        if preference != "auto":
            # A failed check may have erased all historical passing eligibility.
            # The owner's explicit preference still deserves one bounded check.
            previous = [provider for provider in previous if provider in {"cpu", "intel_cpu", preference}]
            if preference in ACCELERATED_PROVIDERS:
                previous.append(preference)
        from app.services.bird_finder_health import RFDETR_FINDER

        if model_id == RFDETR_FINDER and preference in {"auto", "intel_npu", "intel_gpu"}:
            preferred = "intel_gpu" if preference == "intel_gpu" else "intel_npu"
            if preferred in current:
                return None
            previous.extend(provider for provider in ("intel_npu", "intel_gpu") if provider in packaged)
        stale = stale_accelerators(previous, current, packaged)
        if not stale:
            return None
        retest = sorted({"cpu", *stale} | ({"intel_cpu"} & set(previous) & set(packaged)))
        key = validation._identity_digest(
            {
                "model": model_id,
                "artifact": artifact,
                "comparison_policy": 2,
                "runtime": {
                    provider: validation.current_provider_runtime_signature(provider)
                    for provider in sorted({"cpu"} | (set(previous) & ACCELERATED_PROVIDERS & set(packaged)))
                },
            }
        )
        if key in attempts:
            self._status = BirdFinderCheckStatus.model_validate(attempts[key])
            self._status.runtime_current = True
            if self._status.state == "running":
                self._status.state = "interrupted"
                self._status.reason_code = "interrupted"
                self._status.reason = "The previous check was interrupted. Check devices for this finder to retry."
            return None
        return key, retest

    async def run(self) -> None:
        async with self._lock:
            key: str | None = None
            result: dict[str, Any] = {}
            runtime_signatures: dict[str, str] = {}
            artifact: str | None = None
            try:
                finder = await asyncio.to_thread(selected_finder)
                if finder is None:
                    return
                model_id, artifact = finder
                preference = settings.classification.bird_crop_inference_provider
                prepared = await asyncio.to_thread(self._prepare, model_id, artifact)
                if prepared is None:
                    return
                prepared_key, providers = prepared
                accelerators = [provider for provider in providers if provider in ACCELERATED_PROVIDERS]
                photos = await asyncio.to_thread(recent_bird_photos)
                if not photos:
                    self._status = BirdFinderCheckStatus(
                        state="waiting",
                        reason_code="no_photos",
                        model_id=model_id,
                        providers=accelerators,
                        reason="No saved bird photos to compare devices on yet. The check waits for saved photos.",
                        last_result=self._status.last_result
                        or (BirdFinderCheckResult.model_validate(self.status()) if self._status.checked_at else None),
                    )
                    return
                key = prepared_key
                last_result = self._status.last_result
                if self._status.state in {"succeeded", "failed", "superseded", "interrupted"}:
                    last_result = BirdFinderCheckResult.model_validate(self.status())
                runtime_signatures = {
                    provider: validation.current_provider_runtime_signature(provider) for provider in providers
                }
                self._status = BirdFinderCheckStatus(
                    state="running",
                    reason_code="driver_changed",
                    last_result=last_result,
                    model_id=model_id,
                    providers=accelerators,
                    reason="The inference runtime changed. Re-checking this finder's accelerators once on saved bird photos.",
                    checked_at=datetime.now(timezone.utc).isoformat(),
                )
                await asyncio.to_thread(
                    _write_ledger_entry,
                    key,
                    self.status()
                    | {
                        "artifact_sha256": artifact,
                        "runtime_signatures": runtime_signatures,
                        "requested_providers": accelerators,
                    },
                )

                from app.services.bird_finder_health import RFDETR_FINDER

                if model_id == RFDETR_FINDER:
                    result = await sweep_crop_model_devices(
                        model_id, image_paths=photos, only_providers=set(providers), prefer_accelerators=True
                    )
                else:
                    result = await sweep_crop_model_devices(model_id, image_paths=photos, only_providers=set(providers))
                checked_providers = {entry.get("provider") for entry in result.get("providers") or []}
                runtime_signatures = {
                    provider: signature
                    for provider, signature in runtime_signatures.items()
                    if provider in checked_providers
                }
                self._status.providers = [
                    entry["provider"]
                    for entry in result.get("providers") or []
                    if entry.get("provider") in ACCELERATED_PROVIDERS
                ]

                if (
                    await asyncio.to_thread(selected_finder) != finder
                    or settings.classification.bird_crop_inference_provider != preference
                ):
                    self._status.state = "superseded"
                    self._status.reason_code = "superseded"
                    self._status.reason = "The bird finder changed while the check ran; no result was applied."
                    return
                current = await asyncio.to_thread(
                    validation.host_eligible_providers, model_id, artifact_sha256=artifact
                )
                current_results = await asyncio.to_thread(
                    validation.host_provider_validation_results, model_id, artifact_sha256=artifact
                )
                checked = {entry["provider"] for entry in result.get("providers") or []}
                eligible = list(
                    dict.fromkeys(
                        [provider for provider in current if provider not in checked]
                        + list(result.get("eligible_providers") or [])
                    )
                )
                best = result.get("best") or {}
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
                if usable_accelerators & set(eligible):
                    self._status.state = "succeeded"
                    self._status.reason_code = (
                        "gpu_recovery"
                        if model_id == RFDETR_FINDER and "intel_npu" not in eligible and "intel_gpu" in eligible
                        else "passed"
                    )
                    self._status.reason = (
                        "The NPU did not pass; the finder uses its verified GPU from the next frame."
                        if model_id == RFDETR_FINDER and "intel_npu" not in eligible and "intel_gpu" in eligible
                        else "The finder has current passing accelerator evidence and uses it from the next frame."
                    )
                else:
                    self._status.state = "failed"
                    self._status.reason_code = (
                        "no_positive_baseline"
                        if any(entry.get("baseline_has_birds") is False for entry in result.get("providers") or [])
                        else "mismatch"
                    )
                    self._status.reason = (
                        "The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU."
                    )
            except asyncio.CancelledError:
                self._status.state = "interrupted"
                self._status.reason_code = "interrupted"
                self._status.reason = "The check was interrupted. Check devices for this finder to retry."
                raise
            except Exception as exc:
                self._status.state = "failed"
                self._status.reason_code = "unfinished"
                self._status.reason = (
                    "The automatic finder check could not finish. Check devices for this finder to retry."
                )
                log.warning("bird_finder_revalidation_failed", error=str(exc))
            finally:
                if key is not None:
                    if self._status.state != "running":
                        self._status.last_result = BirdFinderCheckResult.model_validate(self.status())
                    log.info(
                        "bird_finder_revalidation_result",
                        model_id=self._status.model_id,
                        providers=self._status.providers,
                        outcome=self._status.state,
                        reason=self._status.reason,
                        reason_code=self._status.reason_code,
                        checked_at=self._status.checked_at,
                        box_diff=[
                            {
                                field: entry.get(field)
                                for field in (
                                    "provider",
                                    "ok",
                                    "compiles",
                                    "finite",
                                    "baseline_has_birds",
                                    "baseline_boxes",
                                    "provider_boxes",
                                    "matched_boxes",
                                    "worst_box_iou",
                                    "images_compared",
                                    "error",
                                )
                            }
                            for entry in result.get("providers") or []
                        ],
                    )
                    try:
                        await asyncio.to_thread(
                            _write_ledger_entry,
                            key,
                            self.status()
                            | {
                                "artifact_sha256": artifact,
                                "runtime_signatures": runtime_signatures,
                                "requested_providers": accelerators,
                            },
                        )
                    except (OSError, ValueError) as exc:
                        log.warning("bird_finder_revalidation_outcome_write_failed", error=str(exc))


def _reset_in_process_finder() -> None:
    """Workers re-read evidence on each crop; this process's own copy needs a reset."""
    try:
        from app.services.bird_crop_service import bird_crop_service

        bird_crop_service.reset_models()
    except Exception as exc:
        log.warning("bird_finder_revalidation_reset_failed", error=str(exc))


bird_finder_revalidation = BirdFinderRevalidation()
