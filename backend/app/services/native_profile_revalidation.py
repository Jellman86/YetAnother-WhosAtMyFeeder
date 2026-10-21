"""Explicit owner diagnostics; normal work never bypasses native quarantine."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import os
import sys
import time
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel
import structlog

from app.services.native_crash_quarantine import (
    NativeCrashQuarantine,
    NativeCrashQuarantinedError,
    NativeCrashEvidenceUnavailableError,
)

logger = structlog.get_logger()
_BUSY = {"uploading", "checking", "running", "restoring"}
_CLEANUP_REQUIRED = "Diagnostic cleanup is incomplete. Restart through your deployment manager before retrying."


class RevalidationStatus(BaseModel):
    state: Literal[
        "idle", "uploading", "checking", "running", "restoring", "succeeded", "failed", "cancelled", "superseded"
    ] = "idle"
    attempt_id: str | None = None
    profile_fingerprint: str | None = None
    model_id: str | None = None
    provider: str | None = None
    message: str = "No owner revalidation has run in this process."
    started_at: str | None = None
    finished_at: str | None = None
    approval_scope: Literal["process"] = "process"


class RevalidationProfile(BaseModel):
    fingerprint: str
    model_id: str | None = None
    provider: str | None = None
    blocked: bool
    eligible: bool
    reason: str | None = None


class RevalidationView(BaseModel):
    profile: RevalidationProfile | None = None
    attempt: RevalidationStatus


@dataclass
class RevalidationContext:
    profile: dict[str, Any]
    policy: NativeCrashQuarantine
    restore: Callable[[], Awaitable[None]]
    cleanup: Callable[[], Awaitable[None]]
    execution_mode: str
    pressure: Callable[[], str | None] = lambda: None


def current_context() -> RevalidationContext:
    from app.config import settings
    from app.services.classifier_service import get_classifier

    classifier = get_classifier()

    async def cleanup() -> None:
        supervisors = {
            id(s): s for s in (classifier._classifier_supervisor, classifier._video_supervisor) if s is not None
        }
        for supervisor in supervisors.values():
            await supervisor.wait_for_cleanup(timeout_seconds=30)

    def pressure() -> str | None:
        metrics = classifier._classification_admission.get_metrics()
        if any(metrics[lane].get(k, 0) for lane in ("live", "background") for k in ("queued", "running")):
            return "Bird classification needs the hardware. Retry when it is idle."
        if any(
            supervisor.has_native_work()
            for supervisor in (classifier._classifier_supervisor, classifier._video_supervisor)
            if supervisor is not None
        ):
            return "Native workers are still active. Retry when classification is idle."
        from app.services.provider_revalidation import provider_revalidation

        if provider_revalidation.status().get("state") in {"running", "checking"}:
            return "Provider compatibility validation is active. Retry after it finishes."
        from app.services.mqtt_service import mqtt_service

        if mqtt_service.get_status().get("pressure_level") in {"elevated", "high", "critical"}:
            return "MQTT ingest is under pressure. Retry when it is idle."
        return None

    return RevalidationContext(
        classifier._native_launch_profile(),
        classifier._native_crash_quarantine,
        classifier.reload_bird_model,
        cleanup,
        settings.classification.image_execution_mode,
        pressure,
    )


def _profile_reason(context: RevalidationContext) -> str | None:
    if sys.platform != "linux":
        return "This diagnostic requires Linux process and memory monitoring."
    if context.execution_mode != "subprocess":
        return "Select subprocess image execution before testing a quarantined profile."
    if context.profile.get("provider") not in {"cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"}:
        return "Select a concrete provider instead of Auto before revalidation."
    if not context.profile.get("model_sha256"):
        return "The installed model artifact identity is unavailable."
    return None


def auxiliary_components(profile: dict[str, Any]) -> list[str]:
    artifacts = profile.get("auxiliary_artifacts") or {}
    components = [f"crop:{tier}" for tier, value in (artifacts.get("crop") or {}).items() if value.get("weights")]
    if (artifacts.get("wildlife") or {}).get("weights"):
        components.append("wildlife")
    return sorted(components)


def _report_valid(profile: dict[str, Any], report: dict[str, Any]) -> bool:
    return (
        report.get("profile_fingerprint") == NativeCrashQuarantine._key(profile)
        and report.get("active_provider") == profile.get("provider")
        and report.get("model_sha256") == profile.get("model_sha256")
        and report.get("auxiliary_checked", []) == auxiliary_components(profile)
        and report.get("images_checked") == 3
        and isinstance(report.get("video_frames_checked"), int)
        and report["video_frames_checked"] >= 3
        and all(report.get(key) is True for key in ("finite", "nondegenerate", "pipeline_checked"))
    )


async def _probe(context: RevalidationContext, images: list[bytes], video: bytes) -> dict[str, Any]:
    from app.services.native_profile_probe import run_profile_probe

    return await run_profile_probe(context.profile, images, video, context.pressure)


class NativeProfileRevalidation:
    def __init__(
        self,
        *,
        context_getter: Callable[[], RevalidationContext] = current_context,
        probe: Callable[..., Awaitable[dict[str, Any]]] = _probe,
        audit_root: Path | None = None,
    ) -> None:
        self._context_getter = context_getter
        self._probe = probe
        self._audit_root = audit_root or Path(os.environ.get("CONFIG_DIR", "/config")) / "native-revalidation-audit"
        self._status = RevalidationStatus()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._cleanup_failed = False
        self._prepared_context: RevalidationContext | None = None
        self._prepared_token: dict[str, Any] | None = None
        self._upload_deadline: float | None = None
        self._upload_claimed = False

    def status(self) -> RevalidationStatus:
        return self._status.model_copy(deep=True)

    async def inspect(self) -> RevalidationView:
        async with self._lock:
            return await self._inspect_locked()

    async def _inspect_locked(self) -> RevalidationView:
        self._expire_upload()
        context = await asyncio.to_thread(self._context_getter)
        blocked = False
        evidence_reason = None
        try:
            await asyncio.to_thread(context.policy.guard, context.profile)
        except NativeCrashEvidenceUnavailableError as error:
            blocked = True
            evidence_reason = str(error)
        except NativeCrashQuarantinedError:
            blocked = True
        reason = evidence_reason or (_profile_reason(context) if blocked else "This profile is not quarantined.")
        if (
            evidence_reason is None
            and await asyncio.to_thread(context.policy.worker_approval, context.profile) is not None
        ):
            reason = "This exact profile is approved in this process. Restart requires another explicit check."
        if self._status.state == "succeeded" and (
            blocked or self._status.profile_fingerprint != context.policy._key(context.profile)
        ):
            self._terminal(
                "superseded", "The previous approval no longer applies. The current profile must be checked separately."
            )
        if self._cleanup_failed:
            reason = _CLEANUP_REQUIRED
        return RevalidationView(
            profile=RevalidationProfile(
                fingerprint=context.policy._key(context.profile),
                model_id=context.profile.get("model_id"),
                provider=context.profile.get("provider"),
                blocked=blocked,
                eligible=blocked and reason is None,
                reason=reason,
            ),
            attempt=self.status(),
        )

    def _expire_upload(self) -> None:
        if (
            self._status.state == "uploading"
            and self._upload_deadline is not None
            and time.monotonic() >= self._upload_deadline
        ):
            self._terminal("failed", "The diagnostic upload expired. Prepare a new check.")
            self._prepared_context = self._prepared_token = None
            self._upload_deadline = None

    async def prepare(self, fingerprint: str, *, attempt_id: str | None = None) -> RevalidationStatus:
        async with self._lock:
            self._expire_upload()
            if self._cleanup_failed:
                raise ValueError(_CLEANUP_REQUIRED)
            if attempt_id is not None and attempt_id == self._status.attempt_id:
                return self.status()
            if self._status.state in _BUSY:
                if attempt_id is None and fingerprint == self._status.profile_fingerprint:
                    return self.status()
                raise ValueError("Another diagnostic is active. Finish or cancel it first.")
            context = await asyncio.to_thread(self._context_getter)
            context = replace(context, profile=deepcopy(context.profile))
            if fingerprint != context.policy._key(context.profile):
                raise ValueError("The selected profile changed. Refresh before retrying.")
            if reason := _profile_reason(context):
                raise ValueError(reason)
            token = await asyncio.to_thread(context.policy.capture_revalidation, context.profile)
            self._prepared_context, self._prepared_token = context, token
            self._upload_claimed = False
            self._upload_deadline = time.monotonic() + 300
            self._task = None
            self._status = RevalidationStatus(
                state="uploading",
                attempt_id=attempt_id or str(uuid4()),
                profile_fingerprint=fingerprint,
                model_id=context.profile.get("model_id"),
                provider=context.profile.get("provider"),
                message="Waiting for representative diagnostic uploads. No native work has started.",
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            return self.status()

    def check_upload(self, attempt_id: str) -> None:
        self._expire_upload()
        if attempt_id != self._status.attempt_id or self._status.state != "uploading":
            raise ValueError("This diagnostic upload is no longer current.")

    def claim_upload(self, attempt_id: str) -> None:
        self.check_upload(attempt_id)
        if self._upload_claimed:
            raise ValueError("This diagnostic already has an upload in progress.")
        self._upload_claimed = True

    async def abandon_upload(self, attempt_id: str) -> None:
        async with self._lock:
            if self._status.attempt_id == attempt_id and self._status.state == "uploading":
                self._prepared_context = self._prepared_token = None
                self._upload_deadline = None
                self._terminal("cancelled", "Diagnostic upload did not complete. No native work was started.")

    async def start_prepared(self, attempt_id: str, images: list[bytes], video: bytes) -> RevalidationStatus:
        from app.services.native_profile_probe import MAX_VIDEO_BYTES
        from app.utils.image_io import MAX_IMAGE_BYTES

        async with self._lock:
            self.check_upload(attempt_id)
            if (
                len(images) != 3
                or len(set(images)) != 3
                or any(not image or len(image) > MAX_IMAGE_BYTES for image in images)
                or not video
                or len(video) > MAX_VIDEO_BYTES
            ):
                raise ValueError(
                    "Choose three distinct representative bird photos and one short bird clip within the upload limits."
                )
            context, token = self._prepared_context, self._prepared_token
            if context is None or token is None:
                raise ValueError("This diagnostic upload is no longer current.")
            current = await asyncio.to_thread(self._context_getter)
            if not self._same_context(context, current):
                raise ValueError("The selected profile changed while uploading. Prepare a new check.")
            fresh = await asyncio.to_thread(current.policy.capture_revalidation, current.profile)
            if fresh != token:
                raise ValueError("The saved incidents changed while uploading. Prepare a new check.")
            self._prepared_context = self._prepared_token = None
            self._upload_deadline = None
            self._status.state = "checking"
            self._status.message = "Checking cleanup and diagnostic resources."
            self._task = asyncio.create_task(self._run(context, token, images, video))
            return self.status()

    async def start(self, fingerprint: str, images: list[bytes], video: bytes) -> RevalidationStatus:
        prepared = await self.prepare(fingerprint)
        if prepared.state != "uploading":
            return prepared
        return await self.start_prepared(prepared.attempt_id, images, video)

    async def wait(self) -> None:
        if self._task is not None:
            await asyncio.shield(self._task)

    async def cancel(self, attempt_id: str) -> RevalidationStatus:
        async with self._lock:
            if attempt_id != self._status.attempt_id:
                raise ValueError("This diagnostic attempt is no longer current.")
            if self._status.state == "uploading":
                self._prepared_context = self._prepared_token = None
                self._upload_deadline = None
                self._terminal("cancelled", "Diagnostic upload cancelled. No native work was started.")
                try:
                    await self._audit()
                except OSError:
                    logger.error("native_profile_revalidation_audit_failed", attempt_id=attempt_id)
            if self._task is not None and not self._task.done() and self._status.state in _BUSY:
                self._task.cancel()
                disconnected = False
                while not self._task.done():
                    try:
                        await asyncio.shield(self._task)
                    except asyncio.CancelledError:
                        disconnected |= bool(asyncio.current_task().cancelling())
                if self._task.cancelled() and self._status.state in _BUSY:
                    self._terminal("cancelled", "Check cancelled before launch. The profile remains blocked.")
                    await self._audit()
                if disconnected:
                    raise asyncio.CancelledError
            return self.status()

    async def shutdown(self) -> None:
        if self._status.state in _BUSY and self._status.attempt_id is not None:
            await self.cancel(self._status.attempt_id)

    def _terminal(self, state: str, message: str) -> None:
        self._status.state = state
        self._status.message = message
        self._status.finished_at = datetime.now(timezone.utc).isoformat()

    def _same_context(self, before: RevalidationContext, after: RevalidationContext) -> bool:
        return before.policy is after.policy and before.policy._key(before.profile) == after.policy._key(after.profile)

    async def _run(
        self, context: RevalidationContext, token: dict[str, Any], images: list[bytes], video: bytes
    ) -> None:
        try:
            await self._audit()
            await context.cleanup()
            if reason := context.pressure():
                raise ValueError(reason)
            self._status.state = "running"
            self._status.message = "Checking representative image, crop and video inference in an isolated process."
            report = await self._probe(context, images, video)
            if not _report_valid(context.profile, report):
                raise ValueError("The diagnostic did not establish exact-provider, finite and nondegenerate inference.")
            current = await asyncio.to_thread(self._context_getter)
            if not self._same_context(context, current):
                self._terminal("superseded", "The model or provider changed. No profile was released.")
            else:
                self._status.state = "restoring"
                self._status.message = (
                    "The probe passed. Restoring isolated worker state while the profile stays blocked."
                )
                await asyncio.wait_for(context.restore(), timeout=30)
                # Audit the completed diagnostic before granting process-local authority.
                # If persistence/cancellation fails here, normal work is still blocked.
                await self._audit("probe_passed")
                current = await asyncio.to_thread(self._context_getter)
                if not self._same_context(context, current) or not context.policy.release_after_revalidation(
                    current.profile, token
                ):
                    self._terminal("superseded", "The profile or saved incidents changed. No profile was released.")
                else:
                    self._terminal(
                        "succeeded",
                        "This exact profile passed and is available in this process. Saved crash evidence remains; restart requires another explicit check.",
                    )
                    return
        except asyncio.CancelledError:
            self._terminal("cancelled", "Check cancelled after diagnostic cleanup. The profile remains blocked.")
        except Exception as error:
            from app.services.native_profile_probe import ProbeCleanupFailed

            if isinstance(error, ProbeCleanupFailed):
                self._cleanup_failed = True
                self._terminal(
                    "failed",
                    "Diagnostic cleanup is incomplete. The profile remains blocked; restart through your deployment manager before retrying.",
                )
            else:
                message = (
                    str(error)
                    if isinstance(error, ValueError)
                    else "The diagnostic could not finish. Review the incident before retrying."
                )
                self._terminal("failed", message)
        try:
            await self._audit()
        except OSError:
            logger.error("native_profile_revalidation_audit_failed", attempt_id=self._status.attempt_id)

    async def _audit(self, outcome: str | None = None) -> None:
        record = self._status.model_dump()
        record["diagnostic_outcome"] = outcome or self._status.state
        await asyncio.to_thread(self._write_audit, record)

    def _write_audit(self, record: dict[str, Any]) -> None:
        from app.services.model_validation import _write_json_atomic

        self._audit_root.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(self._audit_root / f"{record['attempt_id']}.json", record)


native_profile_revalidation = NativeProfileRevalidation()
