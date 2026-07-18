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
import time
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


def write_validation_record(
    model_id: str, *, provider: str, ok: bool, reason: str, latency_ms: float | None = None
) -> None:
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
            "latency_ms": latency_ms,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(
            json.dumps({"models": models}, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("model_validation_write_failed", model_id=model_id, error=str(e))


def write_eligibility_entry(model_id: str, providers: list[str]) -> None:
    """Record which inference providers this host validated for ``model_id`` in
    ``device_eligibility.json``, preserving every other model's entry. Fail-soft."""
    if not model_id:
        return
    root = _eval_root()
    path = root / ELIGIBILITY_FILENAME
    try:
        root.mkdir(parents=True, exist_ok=True)
        models: dict = {}
        generated: dict = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                models = existing.get("models") or {}
                generated = {k: existing.get(k) for k in ("run_id",) if existing.get(k)}
            except Exception:
                models = {}
        models[model_id] = [str(p).strip().lower() for p in providers if str(p).strip()]
        payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "models": models, **generated}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("model_eligibility_write_failed", model_id=model_id, error=str(e))


# OpenVINO sweep devices map to the inference-provider setting values.
_DEVICE_TO_PROVIDER = {"CPU": "intel_cpu", "GPU": "intel_gpu", "NPU": "intel_npu"}


def _openvino_devices() -> list[str]:
    """CPU / GPU / NPU available to OpenVINO on this host, or ``[]`` when OpenVINO
    is not installed (CPU-only / CUDA hosts). Enumerating devices is safe; only
    compiling a model on one can crash, and that runs in an isolated subprocess."""
    try:
        import openvino as _ov

        avail = list(_ov.Core().available_devices)
    except Exception:
        return []
    devices: list[str] = ["CPU"] if any(str(d).split(".")[0] == "CPU" for d in avail) else []
    for d in avail:
        base = str(d).split(".")[0]
        if base in ("GPU", "NPU") and base not in devices:
            devices.append(base)
    return devices


async def _probe_one_device(device: str, *, timeout: float = 240.0) -> dict | None:
    """Compile + run the *active* model on ``device`` in a child process so a GPU/NPU
    driver fault cannot take down the app. Returns the parsed JSON report, or ``None``
    on crash / timeout / parse failure."""
    import sys as _sys

    try:
        import app as _app_pkg

        backend_root = str(Path(_app_pkg.__file__).resolve().parent.parent)
    except Exception:
        backend_root = None
    args = [_sys.executable, "-m", "scripts.probe_openvino_bird_model", "--device", device]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=backend_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    except Exception as e:
        log.warning("model_validation_device_probe_spawn_failed", device=device, error=str(e))
        return None
    if proc.returncode != 0:
        return None
    try:
        text = stdout.decode("utf-8", "replace")
        start = text.find("{")
        return json.loads(text[start:]) if start >= 0 else None
    except Exception:
        return None


def _device_report_ok(report: dict | None) -> tuple[bool, float | None, list[int]]:
    """Reduce a device probe report to (compiled-and-finite, latency_ms, top-indices)."""
    if not report:
        return (False, None, [])
    if not (report.get("compile") or {}).get("ok"):
        return (False, None, [])
    out = report.get("output_summary") or {}
    finite = bool(out.get("finite_count")) and not (out.get("nan_count") or 0)
    latency = report.get("inference_latency_ms")
    top = [int(i) for i in (report.get("output_top_indices") or [])]
    return (finite, latency, top)


async def sweep_model_devices(model_id: str) -> dict | None:
    """Probe ``model_id`` (which must already be the active model) on every OpenVINO
    device, and choose the fastest that compiled, produced finite output, and agreed
    with the CPU baseline on the probe image. Returns a summary, or ``None`` when this
    host has no OpenVINO devices (so the caller falls back to the generic probe).
    """
    devices = await asyncio.to_thread(_openvino_devices)
    if not devices:
        return None

    per_device: list[dict] = []
    eligible: list[str] = []
    cpu_top: list[int] = []
    best: dict | None = None
    for dev in devices:
        report = await _probe_one_device(dev)
        finite, latency, top = _device_report_ok(report)
        provider = _DEVICE_TO_PROVIDER.get(dev, dev.lower())
        if dev == "CPU":
            cpu_top = top
            agrees = finite
        else:
            # An accelerator must match the CPU top-1 or it is silently wrong (the
            # NaN / precision-divergence failure mode) even when it "runs".
            agrees = finite and bool(cpu_top) and bool(top) and top[0] == cpu_top[0]
        ok = bool(finite and agrees)
        per_device.append({"device": dev, "provider": provider, "ok": ok, "latency_ms": latency})
        if ok:
            eligible.append(provider)
            if latency is not None and (best is None or latency < best["latency_ms"]):
                best = {"device": dev, "provider": provider, "latency_ms": latency}

    return {"devices": per_device, "eligible_providers": eligible, "best": best}


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
    """Validate ``model_id`` on this host and pick its fastest inference device.

    Trial-activates the model, then:
    - On an OpenVINO host, sweeps CPU / Intel GPU / NPU (each compile isolated in a
      subprocess), records which providers passed, and returns the fastest one as
      ``best_provider`` so the caller can set it.
    - On a CPU-only / CUDA host (no OpenVINO), runs one frame through the live
      classifier on whatever provider it resolves.

    Restores the previously active model afterwards. Never raises: a failure is
    captured as a failed record and returned.
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
            return {
                "model_id": model_id,
                "ok": False,
                "provider": provider,
                "reason": reason,
                "latency_ms": None,
                "devices": [],
                "best_provider": None,
            }

        await classifier.reload_bird_model()

        # Preferred path: sweep this model's OpenVINO devices and pick the fastest.
        sweep = await sweep_model_devices(model_id)
        if sweep is not None:
            eligible = sweep["eligible_providers"]
            best = sweep["best"]
            if eligible:
                write_eligibility_entry(model_id, eligible)
                best_provider = best["provider"] if best else eligible[0]
                latency_ms = best["latency_ms"] if best else None
                reason = "validated on this host's devices"
                write_validation_record(model_id, provider=best_provider, ok=True, reason=reason, latency_ms=latency_ms)
                return {
                    "model_id": model_id,
                    "ok": True,
                    "provider": best_provider,
                    "reason": reason,
                    "latency_ms": latency_ms,
                    "devices": sweep["devices"],
                    "best_provider": best_provider,
                }
            reason = "model did not run correctly on any of this host's devices"
            write_validation_record(model_id, provider="cpu", ok=False, reason=reason)
            return {
                "model_id": model_id,
                "ok": False,
                "provider": "cpu",
                "reason": reason,
                "latency_ms": None,
                "devices": sweep["devices"],
                "best_provider": None,
            }

        # Fallback (no OpenVINO): run a few frames on the resolved provider.
        try:
            status = classifier.get_status()
            provider = str(status.get("active_provider") or status.get("selected_provider") or "cpu")
        except Exception:
            provider = "cpu"

        image = await asyncio.to_thread(_synthetic_probe_image)
        results = None
        samples: list[float] = []
        for _ in range(3):
            t0 = time.perf_counter()
            results = await asyncio.to_thread(classifier.classify, image, input_context={"is_cropped": False})
            samples.append((time.perf_counter() - t0) * 1000.0)
        latency_ms = round(sorted(samples)[len(samples) // 2], 1) if samples else None

        ok, reason = _judge_predictions(results)
        write_validation_record(model_id, provider=provider, ok=ok, reason=reason, latency_ms=latency_ms)
        return {
            "model_id": model_id,
            "ok": ok,
            "provider": provider,
            "reason": reason,
            "latency_ms": latency_ms,
            "devices": [],
            "best_provider": None,
        }
    except Exception as e:
        reason = f"validation errored: {e}"
        log.warning("model_validation_probe_failed", model_id=model_id, error=str(e))
        write_validation_record(model_id, provider=provider, ok=False, reason=reason)
        return {
            "model_id": model_id,
            "ok": False,
            "provider": provider,
            "reason": reason,
            "latency_ms": None,
            "devices": [],
            "best_provider": None,
        }
    finally:
        # Restore the model that was active before the trial so a validation run never
        # silently changes what the user is running.
        if original_active and original_active != model_manager.active_model_id:
            try:
                await model_manager.activate_model(original_active)
                await classifier.reload_bird_model()
            except Exception as e:
                log.warning("model_validation_restore_failed", model_id=original_active, error=str(e))
