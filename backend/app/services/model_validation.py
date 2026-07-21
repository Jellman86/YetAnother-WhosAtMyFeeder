"""Per-host model validation record and the post-install selection gate.

A downloaded classifier is *installed* (files present) but not yet *validated*
(proven to load and produce finite output on this specific host). Selection is
gated on validation so a user cannot activate a model that has never been shown
to run here — the registry lists which providers a model *can* use, but only a
per-host check proves it actually does on this silicon.

Two records back the gate, both on the config volume under
``$YAWAMF_EVAL_RUNS_DIR`` (default ``/config/yawamf-eval``):

- ``device_eligibility.json`` — written by the shared provider sweep; keyed
  ``model_id -> [verified providers]`` with an exact per-model image flavor.
- ``model_validation.json`` — written by both the single-model endpoint and
  compatibility runs; keyed
  ``model_id -> {validated, provider, image_flavor, checked_at, reason}``.

Either current-image record clearing the gate keeps the flow honest across CPU,
CUDA and Intel images. The currently-active model and bundled models are
grandfathered so an upgrade never blocks a working install.

Everything here is fail-soft: a missing or unreadable record yields "not
validated", never an exception.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from app.utils.runtime_flavor import get_image_flavor, packaged_inference_providers

log = structlog.get_logger()

VALIDATION_FILENAME = "model_validation.json"
ELIGIBILITY_FILENAME = "device_eligibility.json"

VALIDATION_PROVIDER_ORDER = ("cpu", "intel_cpu", "cuda", "intel_gpu", "intel_npu")


@dataclass(frozen=True)
class ValidationProviderCandidate:
    """One concrete inference runtime that is safe and meaningful to probe."""

    provider: str
    backend: str
    device: str


_VALIDATION_PROVIDER_TARGETS = {
    "cpu": ("onnxruntime", "CPUExecutionProvider"),
    "cuda": ("onnxruntime", "CUDAExecutionProvider"),
    "intel_cpu": ("openvino", "CPU"),
    "intel_gpu": ("openvino", "GPU"),
    "intel_npu": ("openvino", "NPU"),
}


def validation_provider_candidates(
    *,
    image_flavor: str,
    capabilities: dict[str, Any],
    supported_providers: list[str] | tuple[str, ...] | None,
    model_runtime: str,
) -> list[ValidationProviderCandidate]:
    """Return the provider sweep for one model on the running deployment.

    The contract is deliberately the intersection of what the image packages,
    what this host can actually expose, and what the model declares compatible.
    Unknown local-development images have no packaging restriction, but published
    images can never accidentally validate a runtime they do not own.
    """

    runtime = str(model_runtime or "onnx").strip().lower()
    supported = {
        str(provider or "").strip().lower() for provider in (supported_providers or []) if str(provider or "").strip()
    }
    packaged = set(packaged_inference_providers(image_flavor))

    if runtime in {"tflite", "tensorflow-lite", "tensorflow_lite"}:
        return [ValidationProviderCandidate("cpu", "tflite", "CPU")]

    host_available = {
        "cpu": bool(capabilities.get("ort_available")),
        "cuda": bool(capabilities.get("cuda_available")),
        "intel_cpu": bool(capabilities.get("openvino_available") and capabilities.get("intel_cpu_available")),
        "intel_gpu": bool(capabilities.get("openvino_available") and capabilities.get("intel_gpu_available")),
        "intel_npu": bool(capabilities.get("openvino_available") and capabilities.get("intel_npu_available")),
    }

    candidates: list[ValidationProviderCandidate] = []
    for provider in VALIDATION_PROVIDER_ORDER:
        if packaged and provider not in packaged:
            continue
        if supported and provider not in supported:
            continue
        if not host_available.get(provider):
            continue
        backend, device = _VALIDATION_PROVIDER_TARGETS[provider]
        candidates.append(ValidationProviderCandidate(provider, backend, device))
    return candidates


def _eval_root() -> Path:
    """Resolved at call time so tests (and re-configuration) see the current env."""
    return Path(os.environ.get("YAWAMF_EVAL_RUNS_DIR", "/config/yawamf-eval"))


def host_eligible_providers(model_id: str) -> list[str]:
    """Providers the unified sweep validated for ``model_id`` in this image."""
    if not model_id:
        return []
    try:
        path = _eval_root() / ELIGIBILITY_FILENAME
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        providers = [str(p).strip().lower() for p in (data.get("models") or {}).get(model_id) or [] if str(p).strip()]
        current_flavor = get_image_flavor()
        recorded_flavor = str((data.get("model_image_flavors") or {}).get(model_id) or "").strip().lower()
        # Published images require evidence from the exact runtime image tested.
        # Legacy records lacked this metadata and therefore require one revalidation;
        # the already-active and bundled models remain grandfathered by the gate.
        if current_flavor != "unknown" and recorded_flavor != current_flavor:
            return []
        packaged = set(packaged_inference_providers(current_flavor))
        return [provider for provider in providers if not packaged or provider in packaged]
    except Exception:
        return []


def read_validation_record(model_id: str) -> dict | None:
    """The raw persisted validation record for ``model_id``, or ``None``."""
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


def activation_provider_recommendation(model_id: str) -> str | None:
    """Return a current, eligible provider recommendation for activation.

    The two persisted records must agree: the single-model recommendation must
    belong to this image flavor and the provider sweep must still list it as
    eligible. This keeps activation atomic and fail-closed across image switches,
    interrupted sweeps, and hand-edited state files.
    """

    record = read_validation_record(model_id) or {}
    if record.get("validated") is not True:
        return None
    provider = str(record.get("provider") or "").strip().lower()
    if provider not in _VALIDATION_PROVIDER_TARGETS:
        return None
    current_flavor = get_image_flavor()
    recorded_flavor = str(record.get("image_flavor") or "").strip().lower()
    if current_flavor != "unknown" and recorded_flavor != current_flavor:
        return None
    return provider if provider in host_eligible_providers(model_id) else None


def write_validation_record(
    model_id: str, *, provider: str, ok: bool, reason: str, latency_ms: float | None = None
) -> None:
    """Record this image's validation outcome while preserving every other model.

    Fail-soft: a write error is logged, never raised.
    """
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
            "image_flavor": get_image_flavor(),
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


def write_eligibility_entry(
    model_id: str,
    providers: list[str],
    *,
    run_id: str | None = None,
    image_flavor: str | None = None,
) -> None:
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
        model_image_flavors: dict[str, str] = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                models = existing.get("models") or {}
                model_image_flavors = existing.get("model_image_flavors") or {}
                generated = {k: existing.get(k) for k in ("run_id", "image_flavor") if existing.get(k)}
            except Exception:
                models = {}
                model_image_flavors = {}
        models[model_id] = [str(p).strip().lower() for p in providers if str(p).strip()]
        if run_id:
            generated["run_id"] = run_id
        if image_flavor:
            generated["image_flavor"] = image_flavor
            model_image_flavors[model_id] = image_flavor
        payload = {
            "schema_version": 2,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": models,
            "model_image_flavors": model_image_flavors,
            **generated,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("model_eligibility_write_failed", model_id=model_id, error=str(e))


def _parse_probe_report(stdout: bytes) -> dict | None:
    """Extract the final JSON object while tolerating structured log lines."""

    text = stdout.decode("utf-8", "replace")
    for start in range(len(text) - 1, -1, -1):
        if text[start] != "{":
            continue
        try:
            value = json.loads(text[start:])
        except json.JSONDecodeError:
            continue
        return value if isinstance(value, dict) else None
    return None


async def _probe_one_provider(
    provider: str,
    *,
    model_id: str,
    timeout: float = 300.0,
    image_paths: list[str] | None = None,
) -> dict | None:
    """Compile and run the active model on one provider in a child process."""
    import sys as _sys

    try:
        import app as _app_pkg

        backend_root = str(Path(_app_pkg.__file__).resolve().parent.parent)
    except Exception:
        backend_root = None
    args = [
        _sys.executable,
        "-m",
        "scripts.probe_bird_model_provider",
        "--provider",
        provider,
        "--model-id",
        model_id,
    ]
    if image_paths:
        args += ["--images", ",".join(image_paths)]
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=backend_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            if proc is not None:
                proc.kill()
                await proc.communicate()
        except ProcessLookupError:
            pass
        return {
            "provider": provider,
            "compile": {"ok": False, "error": f"provider probe timed out after {timeout:.0f} seconds"},
        }
    except Exception as e:
        log.warning("model_validation_provider_probe_spawn_failed", provider=provider, error=str(e))
        return {"provider": provider, "compile": {"ok": False, "error": f"provider probe could not start: {e}"}}
    if proc.returncode != 0:
        return {
            "provider": provider,
            "compile": {"ok": False, "error": f"provider probe exited with status {proc.returncode}"},
        }
    report = _parse_probe_report(stdout)
    if report is None:
        return {
            "provider": provider,
            "compile": {"ok": False, "error": "provider probe returned no valid report"},
        }
    return report


def _device_report_ok(report: dict | None) -> tuple[bool, float | None, list[int]]:
    """Reduce a device probe report to (compiled-and-finite, latency_ms, top-indices)."""
    if not report:
        return (False, None, [])
    if not (report.get("compile") or {}).get("ok"):
        return (False, None, [])
    out = report.get("output_summary") or {}
    finite_count = int(out.get("finite_count") or 0)
    element_count = int(out.get("element_count") or 0)
    finite = bool(
        finite_count
        and finite_count == element_count
        and not (out.get("nan_count") or 0)
        and not (out.get("pos_inf_count") or 0)
        and not (out.get("neg_inf_count") or 0)
    )
    latency = report.get("inference_latency_ms")
    top = [int(i) for i in (report.get("output_top_indices") or [])]
    return (finite, latency, top)


async def sweep_model_devices(model_id: str, *, image_paths: list[str] | None = None) -> dict:
    """Validate every relevant provider for the active ``model_id``.

    The historical function name is retained for callers, but this is now a
    provider sweep: ONNX Runtime CPU/CUDA and OpenVINO CPU/GPU/NPU are all
    considered according to the running image, host probes, and model metadata.
    """

    from app.services.classifier_service import _detect_acceleration_capabilities
    from app.services.model_manager import model_manager

    spec = model_manager.get_active_model_spec()
    if str(spec.get("model_id") or "") != model_id:
        raise RuntimeError(
            f"active model changed before validation (expected {model_id}, found {spec.get('model_id')})"
        )
    image_flavor = get_image_flavor()
    capabilities = await asyncio.to_thread(_detect_acceleration_capabilities)
    candidates = validation_provider_candidates(
        image_flavor=image_flavor,
        capabilities=capabilities,
        supported_providers=spec.get("supported_inference_providers"),
        model_runtime=str(spec.get("runtime") or "onnx"),
    )
    baseline_provider = next(
        (candidate.provider for candidate in candidates if candidate.provider == "cpu"),
        next((candidate.provider for candidate in candidates if candidate.provider == "intel_cpu"), None),
    )

    reports: dict[str, dict | None] = {}
    for candidate in candidates:
        reports[candidate.provider] = await _probe_one_provider(
            candidate.provider,
            model_id=model_id,
            image_paths=image_paths,
        )

    baseline_report = reports.get(baseline_provider) if baseline_provider else None
    baseline_tops = (baseline_report or {}).get("per_image_top_indices") or []
    if not baseline_tops and (baseline_report or {}).get("output_top_indices"):
        baseline_tops = [(baseline_report or {}).get("output_top_indices")]

    per_provider: list[dict] = []
    eligible: list[str] = []
    best: dict | None = None
    for candidate in candidates:
        report = reports.get(candidate.provider)
        finite, latency, top = _device_report_ok(report)
        tops = (report or {}).get("per_image_top_indices") or ([top] if top else [])
        comparisons: list[tuple[list[int], list[int]]] = []
        if candidate.provider == baseline_provider:
            agrees = finite
        else:
            comparisons = [
                (baseline_top, provider_top)
                for baseline_top, provider_top in zip(baseline_tops, tops)
                if baseline_top and provider_top
            ]
            agrees = bool(finite and comparisons and all(base[0] == provider[0] for base, provider in comparisons))
        ok = bool(finite and agrees)
        entry = {
            "provider": candidate.provider,
            "backend": candidate.backend,
            "device": candidate.device,
            "ok": ok,
            "compiles": bool((report or {}).get("compile", {}).get("ok")),
            "finite": finite,
            "latency_ms": latency,
            "baseline": candidate.provider == baseline_provider,
            "images_evaluated": len([indices for indices in tops if indices]),
            "images_compared": len(
                [1 for baseline_top, provider_top in zip(baseline_tops, tops) if baseline_top and provider_top]
            )
            if candidate.provider != baseline_provider
            else 0,
            "matches_baseline": agrees if candidate.provider != baseline_provider else None,
            "matches_cpu": agrees if candidate.provider != baseline_provider else None,
            "top1_match_rate": (
                round(sum(1 for base, provider in comparisons if base[0] == provider[0]) / len(comparisons), 3)
                if comparisons
                else None
            ),
            "mean_top5_overlap": (
                round(sum(len(set(base) & set(provider)) for base, provider in comparisons) / len(comparisons), 2)
                if comparisons
                else None
            ),
            "error": (report or {}).get("runtime_error") or (report or {}).get("compile", {}).get("error"),
        }
        per_provider.append(entry)
        if ok:
            eligible.append(candidate.provider)
            if best is None or (
                latency is not None and (best.get("latency_ms") is None or latency < best["latency_ms"])
            ):
                best = {
                    "device": candidate.device,
                    "backend": candidate.backend,
                    "provider": candidate.provider,
                    "latency_ms": latency,
                }

    return {
        "image_flavor": image_flavor,
        "baseline_provider": baseline_provider,
        "providers": per_provider,
        # Backwards-compatible response field used by older API clients.
        "devices": per_provider,
        "eligible_providers": eligible,
        "best": best,
    }


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
        provider = str(record.get("provider") or "").strip().lower()
        current_flavor = get_image_flavor()
        recorded_flavor = str(record.get("image_flavor") or "").strip().lower()
        packaged = set(packaged_inference_providers(current_flavor))
        flavor_matches = current_flavor == "unknown" or recorded_flavor == current_flavor
        if flavor_matches and (not packaged or not provider or provider in packaged):
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
    """Validate ``model_id`` on this host and pick its fastest provider.

    Trial-activates the model, then:
    - Sweeps the CPU, CUDA and/or OpenVINO providers belonging to the current image,
      host and model contract. Each compile runs in an isolated subprocess.
    - Falls back to the live classifier only in an unknown development environment
      where no concrete packaged provider can be discovered.

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
            write_eligibility_entry(model_id, [], image_flavor=get_image_flavor())
            write_validation_record(model_id, provider=provider, ok=False, reason=reason)
            return {
                "model_id": model_id,
                "ok": False,
                "provider": provider,
                "reason": reason,
                "latency_ms": None,
                "devices": [],
                "providers": [],
                "image_flavor": get_image_flavor(),
                "best_provider": None,
            }

        # Preferred path: sweep every provider that belongs to this image and is
        # both present on the host and declared compatible with this model.
        sweep = await sweep_model_devices(model_id)
        if sweep.get("providers"):
            eligible = sweep["eligible_providers"]
            best = sweep["best"]
            if eligible:
                write_eligibility_entry(model_id, eligible, image_flavor=sweep["image_flavor"])
                best_provider = best["provider"] if best else eligible[0]
                latency_ms = best["latency_ms"] if best else None
                reason = "validated against this image's providers on this host"
                write_validation_record(model_id, provider=best_provider, ok=True, reason=reason, latency_ms=latency_ms)
                return {
                    "model_id": model_id,
                    "ok": True,
                    "provider": best_provider,
                    "reason": reason,
                    "latency_ms": latency_ms,
                    "devices": sweep["devices"],
                    "providers": sweep["providers"],
                    "image_flavor": sweep["image_flavor"],
                    "best_provider": best_provider,
                }
            reason = "model did not run correctly on any provider in this image"
            write_eligibility_entry(model_id, [], image_flavor=sweep["image_flavor"])
            write_validation_record(model_id, provider="cpu", ok=False, reason=reason)
            return {
                "model_id": model_id,
                "ok": False,
                "provider": "cpu",
                "reason": reason,
                "latency_ms": None,
                "devices": sweep["devices"],
                "providers": sweep["providers"],
                "image_flavor": sweep["image_flavor"],
                "best_provider": None,
            }

        # Published images have an explicit packaging contract. No candidate there
        # means the expected runtime is broken or absent, so never let a bundled/live
        # fallback accidentally validate a different model.
        if get_image_flavor() != "unknown":
            reason = "no compatible provider runtime is available in this image"
            write_eligibility_entry(model_id, [], image_flavor=get_image_flavor())
            write_validation_record(model_id, provider="cpu", ok=False, reason=reason)
            return {
                "model_id": model_id,
                "ok": False,
                "provider": "cpu",
                "reason": reason,
                "latency_ms": None,
                "devices": [],
                "providers": [],
                "image_flavor": get_image_flavor(),
                "best_provider": None,
            }

        # Last-resort compatibility path for unknown development environments
        # whose runtime probe exposed no concrete provider target.
        write_eligibility_entry(model_id, [], image_flavor=get_image_flavor())
        await classifier.reload_bird_model()
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
            "providers": [],
            "image_flavor": get_image_flavor(),
            "best_provider": None,
        }
    except Exception as e:
        reason = f"validation errored: {e}"
        log.warning("model_validation_probe_failed", model_id=model_id, error=str(e))
        write_eligibility_entry(model_id, [], image_flavor=get_image_flavor())
        write_validation_record(model_id, provider=provider, ok=False, reason=reason)
        return {
            "model_id": model_id,
            "ok": False,
            "provider": provider,
            "reason": reason,
            "latency_ms": None,
            "devices": [],
            "providers": [],
            "image_flavor": get_image_flavor(),
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
