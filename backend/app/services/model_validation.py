"""Per-host model validation record and the post-install selection gate.

A downloaded classifier is *installed* (files present) but not yet *validated*
(proven to load and produce finite output on this specific host). Selection is
gated on validation so a user cannot activate a model that has never been shown
to run here — the registry lists which providers a model *can* use, but only a
per-host check proves it actually does on this silicon.

Two records back the gate, both on the config volume under
``$YAWAMF_EVAL_RUNS_DIR`` (default ``/config/yawamf-eval``):

- ``device_eligibility.json`` — written by the OpenVINO device sweep
  (``model_eval_service``). Present only on Intel/OpenVINO hosts; keyed
  ``model_id -> [intel_cpu|intel_gpu|intel_npu]``.
- ``model_validation.json`` — written by the host-agnostic validate probe
  (``/api/models/{id}/validate``). Works on every host (CPU-only, CUDA,
  OpenVINO); keyed ``model_id -> {validated, provider, checked_at, reason}``.

Either record clearing the gate keeps the flow honest without stranding the
non-Intel hosts the device sweep cannot cover. The currently-active model and
bundled models are grandfathered so an upgrade never blocks a working install.

Everything here is fail-soft: a missing or unreadable record yields "not
validated", never an exception.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

VALIDATION_FILENAME = "model_validation.json"
ELIGIBILITY_FILENAME = "device_eligibility.json"


def _eval_root() -> Path:
    """Resolved at call time so tests (and re-configuration) see the current env."""
    return Path(os.environ.get("YAWAMF_EVAL_RUNS_DIR", "/config/yawamf-eval"))


def host_eligible_providers(model_id: str) -> list[str]:
    """Inference providers the OpenVINO device sweep validated for ``model_id`` on
    this host. Empty on hosts without an Intel/OpenVINO sweep record."""
    if not model_id:
        return []
    try:
        path = _eval_root() / ELIGIBILITY_FILENAME
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        providers = (data.get("models") or {}).get(model_id) or []
        return [str(p).strip().lower() for p in providers if str(p).strip()]
    except Exception:
        return []


def read_validation_record(model_id: str) -> dict | None:
    """The host-agnostic validate-probe record for ``model_id``, or ``None``."""
    if not model_id:
        return None
    try:
        path = _eval_root() / VALIDATION_FILENAME
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        record = (data.get("models") or {}).get(model_id)
        return record if isinstance(record, dict) else None
    except Exception:
        return None


def write_validation_record(model_id: str, *, provider: str, ok: bool, reason: str) -> None:
    """Record the outcome of a host-agnostic validate probe, preserving every other
    model's record. Fail-soft: a write error is logged, never raised."""
    if not model_id:
        return
    root = _eval_root()
    path = root / VALIDATION_FILENAME
    try:
        root.mkdir(parents=True, exist_ok=True)
        models: dict = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                models = existing.get("models") or {}
            except Exception:
                models = {}
        models[model_id] = {
            "validated": bool(ok),
            "provider": str(provider or "").strip().lower(),
            "reason": reason,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(
            json.dumps({"models": models}, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("model_validation_write_failed", model_id=model_id, error=str(e))


def is_model_validated(
    model_id: str,
    *,
    active_model_id: str | None,
    bundled_ids: set[str],
) -> tuple[bool, str]:
    """Whether ``model_id`` may be selected on this host, and why.

    Returns ``(True, reason)`` when selectable — reason in
    ``{"bundled", "active", "device_sweep", "probe"}`` — or ``(False,
    "unvalidated")`` when it must be validated first.
    """
    if not model_id:
        return (False, "unvalidated")
    if model_id in bundled_ids:
        return (True, "bundled")
    if active_model_id and model_id == active_model_id:
        # Grandfather the running model: an upgrade must never deactivate a model
        # that is already live and working.
        return (True, "active")
    if host_eligible_providers(model_id):
        return (True, "device_sweep")
    record = read_validation_record(model_id)
    if record and record.get("validated") is True:
        return (True, "probe")
    return (False, "unvalidated")


def _synthetic_probe_image() -> Any:
    """A cheap, deterministic RGB image to push one frame through the model. We only
    care that inference *runs and returns finite scores here*, not what it predicts."""
    from PIL import Image

    size = 224
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = (x % 256, y % 256, (x + y) % 256)
    return img


def _judge_predictions(results: Any) -> tuple[bool, str]:
    """A model passes when it returns at least one prediction with a finite, positive
    score — the signature of a runtime that loaded and produced usable output here."""
    if not results:
        return (False, "model returned no predictions")
    try:
        scores = [float(r.get("score", 0.0)) for r in results]
    except (TypeError, ValueError, AttributeError):
        return (False, "model returned malformed predictions")
    if not all(math.isfinite(s) for s in scores):
        return (False, "model produced non-finite scores (NaN/inf) on this hardware")
    if max(scores, default=0.0) <= 0.0:
        return (False, "model produced no positive score")
    return (True, "model produced finite predictions on this hardware")


async def run_validation_probe(model_id: str) -> dict:
    """Host-agnostic validation: trial-activate ``model_id``, run one frame through the
    live classifier, judge the output, record the result, and restore the previously
    active model. Works on any host (CPU-only, CUDA, OpenVINO) because it exercises the
    real classifier on whatever provider this machine resolves.

    Never raises: a failure is captured as a failed record and returned.
    """
    # Lazy imports keep this module importable by ``model_manager`` (which uses the
    # sync gate helpers above) without a circular import at module load.
    from app.services.classifier_service import get_classifier
    from app.services.model_manager import model_manager

    original_active = model_manager.active_model_id
    classifier = get_classifier()
    provider = "cpu"
    try:
        activated = await model_manager.activate_model(model_id)
        if not activated:
            reason = "model files are missing or incomplete"
            write_validation_record(model_id, provider=provider, ok=False, reason=reason)
            return {"model_id": model_id, "ok": False, "provider": provider, "reason": reason}

        await classifier.reload_bird_model()
        try:
            status = classifier.get_status()
            provider = str(status.get("active_provider") or status.get("selected_provider") or "cpu")
        except Exception:
            provider = "cpu"

        image = await asyncio.to_thread(_synthetic_probe_image)
        results = await asyncio.to_thread(classifier.classify, image, input_context={"is_cropped": False})
        ok, reason = _judge_predictions(results)
        write_validation_record(model_id, provider=provider, ok=ok, reason=reason)
        return {"model_id": model_id, "ok": ok, "provider": provider, "reason": reason}
    except Exception as e:
        reason = f"validation errored: {e}"
        log.warning("model_validation_probe_failed", model_id=model_id, error=str(e))
        write_validation_record(model_id, provider=provider, ok=False, reason=reason)
        return {"model_id": model_id, "ok": False, "provider": provider, "reason": reason}
    finally:
        # Restore the model that was active before the trial so a validation run never
        # silently changes what the user is running.
        if original_active and original_active != model_manager.active_model_id:
            try:
                await model_manager.activate_model(original_active)
                await classifier.reload_bird_model()
            except Exception as e:
                log.warning("model_validation_restore_failed", model_id=original_active, error=str(e))
