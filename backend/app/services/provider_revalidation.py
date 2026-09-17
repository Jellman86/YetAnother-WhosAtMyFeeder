"""One bounded recovery attempt for a previously verified active accelerator."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Literal

from pydantic import BaseModel
import structlog

from app.services import model_validation as validation
from app.services.model_validation import sweep_model_devices

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


async def reload_active_classifier() -> None:
    from app.services.classifier_service import get_classifier

    await get_classifier().reload_bird_model()


class ProviderRevalidation:
    def __init__(self) -> None:
        self._status = ProviderValidationStatus()
        self._lock = asyncio.Lock()

    def status(self) -> dict[str, Any]:
        return self._status.model_dump()

    def _prepare(self, spec: dict[str, Any], requested: str) -> tuple[str, str] | None:
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
        if provider in validation.host_eligible_providers(model_id, artifact_sha256=artifact):
            return None
        if provider not in validation.packaged_inference_providers(validation.get_image_flavor()):
            return None
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
        return key, provider

    def _save_outcome(self, key: str) -> None:
        path = validation._eval_root() / "provider_revalidation.json"
        attempts = json.loads(path.read_text(encoding="utf-8"))
        attempts[key] = self.status()
        validation._write_json_atomic(path, attempts)

    async def run(self) -> None:
        async with self._lock:
            key: str | None = None
            try:
                spec, requested = await asyncio.to_thread(active_configuration)
                prepared = await asyncio.to_thread(self._prepare, spec, requested)
                if prepared is None:
                    return
                key, provider = prepared
                model_id = str(spec["model_id"])
                artifact = str(spec.get("artifact_sha256") or "")
                result = await sweep_model_devices(model_id, only_providers={"cpu", provider})
                current, current_requested = await asyncio.to_thread(active_configuration)
                if (current.get("model_id"), current.get("artifact_sha256"), current_requested) != (
                    spec.get("model_id"),
                    spec.get("artifact_sha256"),
                    requested,
                ):
                    self._status.state = "superseded"
                    self._status.reason = "Model or provider changed while the check ran; no result was applied."
                elif provider not in result.get("eligible_providers", []):
                    self._status.state = "failed"
                    self._status.reason = "The accelerator did not pass validation. Review AI Models before retrying."
                else:
                    current_providers = validation.host_eligible_providers(model_id, artifact_sha256=artifact)
                    current_results = validation.host_provider_validation_results(model_id, artifact_sha256=artifact)
                    eligible = list(dict.fromkeys(current_providers + result["eligible_providers"]))
                    await asyncio.to_thread(
                        validation.write_eligibility_entry,
                        model_id,
                        eligible,
                        image_flavor=validation.get_image_flavor(),
                        provider_results=list(current_results.values()) + result.get("providers", []),
                        artifact_sha256=artifact,
                    )
                    if provider not in validation.host_eligible_providers(model_id, artifact_sha256=artifact):
                        raise RuntimeError("Could not persist accelerator validation")
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
