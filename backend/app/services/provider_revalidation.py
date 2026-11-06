"""One bounded recovery attempt for a previously verified active accelerator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import partial
import json
from typing import Any, Literal

from pydantic import BaseModel
import structlog

from app.services import model_validation as validation
from app.services.model_validation import sweep_model_devices
from app.services.native_crash_quarantine import NativeCrashQuarantinedError

log = structlog.get_logger()


class ProviderValidationStatus(BaseModel):
    state: Literal["idle", "running", "succeeded", "failed", "interrupted", "superseded"] = "idle"
    model_id: str | None = None
    provider: str | None = None
    reason: str | None = None
    checked_at: str | None = None


def active_configuration() -> tuple[dict[str, Any], str]:
    from app.config import settings
    from app.services.model_manager import model_manager

    return model_manager.get_active_model_spec(), settings.classification.inference_provider


class _RevalidationProfileChanged(RuntimeError):
    """The launch profile no longer matches the configuration being prepared."""


def guard_revalidation_profile(spec: dict[str, Any], requested: str, probe_provider: str | None = None) -> None:
    from app.services.classifier_service import get_classifier

    classifier = get_classifier()
    profile = classifier._native_launch_profile()
    if (
        profile.get("model_id") != spec.get("model_id")
        or not spec.get("artifact_sha256")
        or profile.get("model_sha256") != spec.get("artifact_sha256")
        or profile.get("provider") != requested
    ):
        raise _RevalidationProfileChanged()
    classifier._native_crash_quarantine.guard(profile)
    if probe_provider is not None:
        classifier._native_crash_quarantine.guard(profile | {"provider": probe_provider})


async def reload_active_classifier() -> None:
    from app.services.classifier_service import get_classifier

    await get_classifier().reload_bird_model()


def revalidation_providers(spec: dict[str, Any], accelerator: str, current: list[str]) -> set[str]:
    """Cover CPU recovery routes without probing other accelerators at startup."""
    declared = set(spec.get("candidate_inference_providers") or spec.get("supported_inference_providers") or [])
    packaged = set(validation.packaged_inference_providers(validation.get_image_flavor()))
    # A partial passing list becomes authoritative for the active model. Omitting
    # OpenVINO CPU here would silently remove that recovery route even though it
    # was never tested. The sweep still checks hardware, output and baseline agreement.
    return {"cpu", accelerator} | (({"intel_cpu"} & declared & packaged) - set(current))


class ProviderRevalidation:
    def __init__(self) -> None:
        self._status = ProviderValidationStatus()
        self._lock = asyncio.Lock()

    def status(self) -> dict[str, Any]:
        return self._status.model_dump()

    def _prepare(self, spec: dict[str, Any], requested: str) -> tuple[str, str, set[str]] | None:
        model_id = str(spec.get("model_id") or "")
        artifact = str(spec.get("artifact_sha256") or "")
        data = validation._read_current_eligibility_payload()
        previous = (data.get("models") or {}).get(model_id) or []
        provider = requested
        if provider == "auto":
            record = validation.read_validation_record(model_id) or {}
            provider = str(record.get("provider") or "")
        if provider not in {"cuda", "intel_gpu", "intel_npu"} or provider not in previous:
            return None
        current = validation.host_eligible_providers(model_id, artifact_sha256=artifact)
        if provider in current:
            return None
        if provider not in validation.packaged_inference_providers(validation.get_image_flavor()):
            return None
        guard_revalidation_profile(spec, requested)
        key = validation._identity_digest(
            {
                "model": model_id,
                "artifact": artifact,
                "provider": provider,
                "runtime": validation.current_provider_runtime_signature(provider),
                "baseline": validation.current_provider_runtime_signature("cpu"),
            }
        )
        path = validation._eval_root() / "provider_revalidation.json"
        attempts: dict[str, Any] = {}
        if path.exists():
            # An unreadable ledger cannot safely promise an at-most-once attempt.
            attempts = json.loads(path.read_text(encoding="utf-8"))
        if key in attempts:
            self._status = ProviderValidationStatus.model_validate(attempts[key])
            if self._status.state == "running":
                self._status.state = "interrupted"
                self._status.reason = "The previous check was interrupted. Validate the model in AI Models to retry."
            return None
        self._status = ProviderValidationStatus(
            state="running",
            model_id=model_id,
            provider=provider,
            reason="The inference runtime changed. Checking the previously validated accelerator once.",
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
        attempts[key] = self.status()
        path.parent.mkdir(parents=True, exist_ok=True)
        validation._write_json_atomic(path, attempts)
        return key, provider, revalidation_providers(spec, provider, current)

    def _save_outcome(self, key: str) -> None:
        path = validation._eval_root() / "provider_revalidation.json"
        attempts = json.loads(path.read_text(encoding="utf-8"))
        attempts[key] = self.status()
        validation._write_json_atomic(path, attempts)

    async def run(self) -> None:
        async with self._lock:
            key: str | None = None
            spec: dict[str, Any] = {}
            requested = ""
            try:
                spec, requested = await asyncio.to_thread(active_configuration)
                prepared = await asyncio.to_thread(self._prepare, spec, requested)
                if prepared is None:
                    return
                key, provider, providers = prepared
                model_id = str(spec["model_id"])
                artifact = str(spec.get("artifact_sha256") or "")
                result = await sweep_model_devices(
                    model_id,
                    only_providers=providers,
                    provider_guard=partial(guard_revalidation_profile, spec, requested),
                )
                current, current_requested = await asyncio.to_thread(active_configuration)
                if (current.get("model_id"), current.get("artifact_sha256"), current_requested) != (
                    spec.get("model_id"),
                    spec.get("artifact_sha256"),
                    requested,
                ):
                    self._status.state = "superseded"
                    self._status.reason = "Model or provider changed while the check ran; no result was applied."
                else:
                    current_providers = await asyncio.to_thread(
                        validation.host_eligible_providers, model_id, artifact_sha256=artifact
                    )
                    current_results = await asyncio.to_thread(
                        validation.host_provider_validation_results, model_id, artifact_sha256=artifact
                    )
                    checked = {
                        entry.get("provider")
                        for entry in result.get("providers", [])
                        if isinstance(entry, dict) and isinstance(entry.get("provider"), str)
                    }
                    # Fresh failures supersede older passes; preserve evidence only
                    # for routes this bounded sweep did not check.
                    retained = [provider for provider in current_providers if provider not in checked]
                    eligible = list(dict.fromkeys(retained + result["eligible_providers"]))
                    await asyncio.to_thread(
                        validation.write_eligibility_entry,
                        model_id,
                        eligible,
                        image_flavor=validation.get_image_flavor(),
                        provider_results=list(current_results.values()) + result.get("providers", []),
                        artifact_sha256=artifact,
                    )
                    saved = await asyncio.to_thread(
                        validation.host_eligible_providers, model_id, artifact_sha256=artifact
                    )
                    if set(eligible) != set(saved):
                        raise RuntimeError("Could not persist provider validation")
                    if provider not in result.get("eligible_providers", []):
                        self._status.state = "failed"
                        retained_cpu = any(route in saved for route in ("cpu", "intel_cpu"))
                        self._status.reason = (
                            "The accelerator did not pass validation. Passing CPU results were retained; review AI Models before retrying."
                            if retained_cpu
                            else "The accelerator did not pass validation. Review AI Models before retrying."
                        )
                        return
                    await asyncio.to_thread(
                        validation.write_validation_record,
                        model_id,
                        provider=provider,
                        ok=True,
                        reason="Previously validated accelerator passed automatic revalidation",
                        artifact_sha256=artifact,
                    )
                    await reload_active_classifier()
                    self._status.state = "succeeded"
                    self._status.reason = "The accelerator passed validation and the classifier was reloaded."
            except NativeCrashQuarantinedError:
                self._status = ProviderValidationStatus(
                    state="failed",
                    model_id=str(spec.get("model_id") or "") or None,
                    provider=requested or None,
                    reason="Automatic validation skipped: this model/provider is quarantined. Investigate the saved crash evidence; restarting does not clear the block.",
                    checked_at=datetime.now(timezone.utc).isoformat(),
                )
            except _RevalidationProfileChanged:
                self._status = ProviderValidationStatus(
                    state="superseded",
                    reason="Model or provider changed before or during validation; no result was applied.",
                )
            except asyncio.CancelledError:
                self._status.state = "interrupted"
                self._status.reason = "Validation was interrupted. Retry from AI Models."
                raise
            except Exception as exc:
                self._status.state = "failed"
                self._status.reason = "Automatic validation could not finish. Review AI Models before retrying."
                log.warning("provider_revalidation_failed", error=str(exc))
            finally:
                if key is not None:
                    try:
                        await asyncio.to_thread(self._save_outcome, key)
                    except OSError as exc:
                        log.warning("provider_revalidation_outcome_write_failed", error=str(exc))


provider_revalidation = ProviderRevalidation()
