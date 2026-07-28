"""Per-host model validation record and the post-install selection gate.

A downloaded classifier is *installed* (files present) but not yet *validated*
(proven to load and produce finite output on this specific host). Selection is
gated on validation so a user cannot activate a model that has never been shown
to run here — the registry lists which providers a model *can* use, but only a
per-host check proves it actually does on this silicon.

Two records back the gate, both on the config volume under
``$YAWAMF_EVAL_RUNS_DIR`` (default ``/config/yawamf-eval``):

- ``device_eligibility.json`` — written by the shared provider sweep; keyed
  ``model_id -> [verified providers]`` with per-model image, runtime/hardware
  signature, artifact checksum, and provider metrics.
- ``model_validation.json`` — written by both the single-model endpoint and
  compatibility runs; keyed
  ``model_id -> {validated, provider, image_flavor, checked_at, reason}``.

Only current installation evidence clears the gate, keeping the flow honest
across CPU, CUDA and Intel images, runtime/driver upgrades, model replacements,
and config-volume moves. The currently-active model and bundled models are
grandfathered so an upgrade never blocks a working install.

Everything here is fail-soft: a missing or unreadable record yields "not
validated", never an exception.
"""

from __future__ import annotations

import asyncio
import hashlib
from importlib import metadata as importlib_metadata
import json
import math
import os
import platform
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

from app.utils.runtime_flavor import get_image_flavor, packaged_inference_providers

log = structlog.get_logger()

VALIDATION_FILENAME = "model_validation.json"
ELIGIBILITY_FILENAME = "device_eligibility.json"
ELIGIBILITY_SCHEMA_VERSION = 4
_EVIDENCE_WRITE_LOCK = threading.RLock()

_INFERENCE_RUNTIME_PACKAGES = (
    "numpy",
    "onnxruntime",
    "onnxruntime-gpu",
    "openvino",
    "tensorflow",
    "tflite-runtime",
)


def current_inference_runtime_signature() -> str:
    """Stable identity for inference binaries and accelerator hardware.

    Provider compatibility evidence must not survive a runtime/driver-facing
    image change or a config-volume move to different accelerator silicon.
    The optional override lets image builders add a driver/image ABI marker
    without coupling validity to every application-only commit.
    """
    return _inference_runtime_signature_for(
        get_image_flavor(),
        str(os.environ.get("YAWAMF_INFERENCE_RUNTIME_ID") or "").strip(),
    )


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Replace an evidence document atomically so readers never see torn JSON."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@lru_cache(maxsize=16)
def _inference_runtime_signature_for(image_flavor: str, runtime_abi: str) -> str:
    packages: dict[str, str] = {}
    for package in _INFERENCE_RUNTIME_PACKAGES:
        try:
            packages[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            continue

    hardware: dict[str, str] = {}
    marker_paths: list[Path] = []
    for pattern in (
        "/sys/class/drm/card*/device/vendor",
        "/sys/class/drm/card*/device/device",
        "/sys/class/drm/card*/device/revision",
        "/sys/class/accel/accel*/device/vendor",
        "/sys/class/accel/accel*/device/device",
    ):
        marker_paths.extend(sorted(Path("/").glob(pattern.lstrip("/"))))
    marker_paths.extend(sorted(Path("/proc/driver/nvidia/gpus").glob("*/information")))
    for marker in (
        Path("/proc/driver/nvidia/version"),
        Path("/sys/module/i915/version"),
        Path("/sys/module/xe/version"),
    ):
        if marker.is_file():
            marker_paths.append(marker)
    for path in marker_paths:
        try:
            hardware[str(path)] = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue

    identity = {
        "image_flavor": image_flavor,
        "runtime_abi": runtime_abi,
        "machine": platform.machine().lower(),
        "kernel": platform.release(),
        "packages": packages,
        "hardware": hardware,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    discover_providers: bool = False,
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
        if not discover_providers and supported and provider not in supported:
            continue
        if not host_available.get(provider):
            continue
        backend, device = _VALIDATION_PROVIDER_TARGETS[provider]
        candidates.append(ValidationProviderCandidate(provider, backend, device))
    return candidates


def _eval_root() -> Path:
    """Resolved at call time so tests (and re-configuration) see the current env."""
    return Path(os.environ.get("YAWAMF_EVAL_RUNS_DIR", "/config/yawamf-eval"))


def _read_current_eligibility_payload() -> dict[str, Any]:
    """Read eligibility evidence only when it belongs to this exact image.

    A single helper keeps provider selection, the Settings UI, and activation
    recommendations from applying different flavor rules.
    """
    try:
        path = _eval_root() / ELIGIBILITY_FILENAME
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _model_eligibility_is_current(
    data: dict[str, Any],
    model_id: str,
    *,
    artifact_sha256: str | None = None,
) -> bool:
    current_flavor = get_image_flavor()
    recorded_flavor = str((data.get("model_image_flavors") or {}).get(model_id) or "").strip().lower()
    if current_flavor != "unknown" and recorded_flavor != current_flavor:
        return False
    if int(data.get("schema_version") or 0) < ELIGIBILITY_SCHEMA_VERSION:
        return False
    recorded_runtime = str((data.get("model_runtime_signatures") or {}).get(model_id) or "").strip().lower()
    if not recorded_runtime or recorded_runtime != current_inference_runtime_signature():
        return False
    expected_artifact = str(artifact_sha256 or "").strip().lower()
    if expected_artifact:
        recorded_artifact = str((data.get("model_artifact_sha256") or {}).get(model_id) or "").strip().lower()
        if recorded_artifact != expected_artifact:
            return False
    return True


def host_eligible_providers(
    model_id: str,
    *,
    artifact_sha256: str | None = None,
) -> list[str]:
    """Providers validated for this model artifact, runtime stack, and host."""
    if not model_id:
        return []
    try:
        data = _read_current_eligibility_payload()
        if not data or not _model_eligibility_is_current(
            data,
            model_id,
            artifact_sha256=artifact_sha256,
        ):
            return []
        providers = [str(p).strip().lower() for p in (data.get("models") or {}).get(model_id) or [] if str(p).strip()]
        current_flavor = get_image_flavor()
        packaged = set(packaged_inference_providers(current_flavor))
        return [provider for provider in providers if not packaged or provider in packaged]
    except Exception:
        return []


def host_eligibility_summary() -> dict[str, Any]:
    """Summarize current evidence with one bounded evidence-file read."""
    empty = {
        "verified_providers": [],
        "generated_at": None,
        "run_id": None,
        "model_count": 0,
    }
    try:
        data = _read_current_eligibility_payload()
        models = data.get("models") or {}
        if not isinstance(models, dict):
            return empty
        verified: set[str] = set()
        model_count = 0
        for raw_model_id, raw_providers in models.items():
            model_id = str(raw_model_id or "").strip()
            if not model_id or not _model_eligibility_is_current(data, model_id):
                continue
            providers = [
                str(provider or "").strip().lower() for provider in (raw_providers or []) if str(provider or "").strip()
            ]
            if not providers:
                continue
            model_count += 1
            verified.update(providers)
        return {
            "verified_providers": sorted(verified),
            "generated_at": data.get("generated_at"),
            "run_id": data.get("run_id"),
            "model_count": model_count,
        }
    except Exception:
        return empty


def host_provider_validation_results(
    model_id: str,
    *,
    artifact_sha256: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-provider passing evidence for a model in the current image.

    Older evidence did not retain enough runtime/artifact identity and is
    deliberately rejected by ``host_eligible_providers`` until revalidation.
    A schema-4 entry may still omit metrics when written by a narrow probe.
    """
    if not model_id:
        return {}
    data = _read_current_eligibility_payload()
    if not data or not _model_eligibility_is_current(
        data,
        model_id,
        artifact_sha256=artifact_sha256,
    ):
        return {}
    eligible = set(host_eligible_providers(model_id, artifact_sha256=artifact_sha256))
    raw = (data.get("model_provider_results") or {}).get(model_id) or {}
    if not isinstance(raw, dict):
        return {}
    results: dict[str, dict[str, Any]] = {}
    for raw_provider, raw_result in raw.items():
        provider = str(raw_provider or "").strip().lower()
        if provider not in eligible or not isinstance(raw_result, dict):
            continue
        result = dict(raw_result)
        if result.get("ok") is not True:
            continue
        results[provider] = result
    return results


def host_provider_preference_order(
    model_id: str,
    *,
    artifact_sha256: str | None = None,
) -> list[str]:
    """Return this installation's validated provider order for ``model_id``.

    Schema-4 metrics order passing providers by measured latency with a
    deterministic tie-break. A narrow schema-4 probe without metrics falls
    back to its recorded activation recommendation.
    """
    eligible = host_eligible_providers(model_id, artifact_sha256=artifact_sha256)
    if not eligible:
        return []

    preferred = str((read_validation_record(model_id) or {}).get("provider") or "").strip().lower()
    results = host_provider_validation_results(model_id, artifact_sha256=artifact_sha256)
    stable_rank = {provider: index for index, provider in enumerate(VALIDATION_PROVIDER_ORDER)}

    def _latency_key(provider: str) -> tuple[float, int, str]:
        value = (results.get(provider) or {}).get("latency_ms")
        try:
            latency = float(value)
        except (TypeError, ValueError):
            latency = float("inf")
        if not math.isfinite(latency) or latency < 0:
            latency = float("inf")
        return (latency, stable_rank.get(provider, len(stable_rank)), provider)

    measured = [provider for provider in eligible if provider in results]
    unmeasured = [provider for provider in eligible if provider not in results]
    ordered: list[str] = sorted(measured, key=_latency_key)
    # Narrow validation records may have no per-provider metrics. Preserve their
    # recommendation, but never let it override newer measured evidence if the
    # process stopped between the two persistence writes.
    if not measured and preferred in unmeasured:
        ordered.append(preferred)
    for provider in sorted(unmeasured, key=_latency_key):
        if provider not in ordered:
            ordered.append(provider)
    return ordered


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


def activation_provider_recommendation(
    model_id: str,
    *,
    artifact_sha256: str | None = None,
) -> str | None:
    """Return a current, eligible provider recommendation for activation.

    The two persisted records must be current: the model record must belong to
    this runtime/image/artifact and the provider sweep must still list a passing
    route. This stays fail-closed across image or hardware switches, interrupted
    sweeps, replaced artifacts, and hand-edited state files.
    """

    record = read_validation_record(model_id) or {}
    if record.get("validated") is not True:
        return None
    current_flavor = get_image_flavor()
    recorded_flavor = str(record.get("image_flavor") or "").strip().lower()
    if current_flavor != "unknown" and recorded_flavor != current_flavor:
        return None
    if str(record.get("runtime_signature") or "").strip().lower() != current_inference_runtime_signature():
        return None
    expected_artifact = str(artifact_sha256 or "").strip().lower()
    if expected_artifact and str(record.get("artifact_sha256") or "").strip().lower() != expected_artifact:
        return None
    # Schema-v3 compatibility evidence contains the full measured order. It is
    # stronger than the single-provider record, which may be stale if a process
    # stopped between the two persistence writes. Legacy evidence still places
    # that recorded provider first in host_provider_preference_order().
    preference = host_provider_preference_order(model_id, artifact_sha256=artifact_sha256)
    return preference[0] if preference else None


def write_validation_record(
    model_id: str,
    *,
    provider: str,
    ok: bool,
    reason: str,
    latency_ms: float | None = None,
    artifact_sha256: str | None = None,
) -> None:
    """Record this image's validation outcome while preserving every other model.

    Fail-soft: a write error is logged, never raised.
    """
    if not model_id:
        return
    root = _eval_root()
    path = root / VALIDATION_FILENAME
    _EVIDENCE_WRITE_LOCK.acquire()
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
            "runtime_signature": current_inference_runtime_signature(),
            "artifact_sha256": str(artifact_sha256 or "").strip().lower() or None,
            "reason": reason,
            "latency_ms": latency_ms,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        with _EVIDENCE_WRITE_LOCK:
            _write_json_atomic(path, {"models": models})
    except OSError as e:
        log.warning("model_validation_write_failed", model_id=model_id, error=str(e))
    finally:
        _EVIDENCE_WRITE_LOCK.release()


def write_eligibility_entry(
    model_id: str,
    providers: list[str],
    *,
    run_id: str | None = None,
    image_flavor: str | None = None,
    provider_results: list[dict[str, Any]] | None = None,
    artifact_sha256: str | None = None,
) -> None:
    """Record which inference providers this host validated for ``model_id`` in
    ``device_eligibility.json``, preserving every other model's entry. Fail-soft."""
    if not model_id:
        return
    root = _eval_root()
    path = root / ELIGIBILITY_FILENAME
    _EVIDENCE_WRITE_LOCK.acquire()
    try:
        root.mkdir(parents=True, exist_ok=True)
        models: dict = {}
        generated: dict = {}
        model_image_flavors: dict[str, str] = {}
        model_runtime_signatures: dict[str, str] = {}
        model_artifact_sha256: dict[str, str] = {}
        model_provider_results: dict[str, dict[str, dict[str, Any]]] = {}
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                models = existing.get("models") or {}
                model_image_flavors = existing.get("model_image_flavors") or {}
                model_runtime_signatures = existing.get("model_runtime_signatures") or {}
                model_artifact_sha256 = existing.get("model_artifact_sha256") or {}
                model_provider_results = existing.get("model_provider_results") or {}
                generated = {k: existing.get(k) for k in ("run_id", "image_flavor") if existing.get(k)}
            except Exception:
                models = {}
                model_image_flavors = {}
                model_runtime_signatures = {}
                model_artifact_sha256 = {}
                model_provider_results = {}
        models[model_id] = [str(p).strip().lower() for p in providers if str(p).strip()]
        eligible = set(models[model_id])
        normalized_results: dict[str, dict[str, Any]] = {}
        for result in provider_results or []:
            if not isinstance(result, dict):
                continue
            provider = str(result.get("provider") or "").strip().lower()
            if provider not in eligible or result.get("ok") is not True:
                continue
            normalized_results[provider] = {
                key: result.get(key)
                for key in (
                    "provider",
                    "backend",
                    "device",
                    "ok",
                    "compiles",
                    "finite",
                    "latency_ms",
                    "images_evaluated",
                    "images_compared",
                    "matches_baseline",
                    "top1_match_rate",
                    "mean_top5_overlap",
                )
                if key in result
            }
            normalized_results[provider]["provider"] = provider
        if provider_results is not None:
            model_provider_results[model_id] = normalized_results
        if run_id:
            generated["run_id"] = run_id
        if image_flavor:
            generated["image_flavor"] = image_flavor
            model_image_flavors[model_id] = image_flavor
        model_runtime_signatures[model_id] = current_inference_runtime_signature()
        normalized_artifact = str(artifact_sha256 or "").strip().lower()
        if normalized_artifact:
            model_artifact_sha256[model_id] = normalized_artifact
        else:
            model_artifact_sha256.pop(model_id, None)
        payload = {
            "schema_version": ELIGIBILITY_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": models,
            "model_image_flavors": model_image_flavors,
            "model_runtime_signatures": model_runtime_signatures,
            "model_artifact_sha256": model_artifact_sha256,
            "model_provider_results": model_provider_results,
            **generated,
        }
        with _EVIDENCE_WRITE_LOCK:
            _write_json_atomic(path, payload)
    except OSError as e:
        log.warning("model_eligibility_write_failed", model_id=model_id, error=str(e))
    finally:
        _EVIDENCE_WRITE_LOCK.release()


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


async def _probe_one_crop_provider(
    provider: str,
    *,
    model_id: str,
    timeout: float = 300.0,
    image_paths: list[str] | None = None,
) -> dict | None:
    """Compile and run one exact crop detector in a disposable child process."""
    import sys as _sys

    try:
        import app as _app_pkg

        backend_root = str(Path(_app_pkg.__file__).resolve().parent.parent)
    except Exception:
        backend_root = None
    args = [
        _sys.executable,
        "-m",
        "scripts.probe_crop_model_provider",
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
            "compile": {"ok": False, "error": f"crop provider probe timed out after {timeout:.0f} seconds"},
        }
    except Exception as exc:
        log.warning("crop_validation_provider_probe_spawn_failed", provider=provider, error=str(exc))
        return {"provider": provider, "compile": {"ok": False, "error": f"crop probe could not start: {exc}"}}
    if proc.returncode != 0:
        return {
            "provider": provider,
            "compile": {"ok": False, "error": f"crop provider probe exited with status {proc.returncode}"},
        }
    report = _parse_probe_report(stdout)
    if report is None:
        return {
            "provider": provider,
            "compile": {"ok": False, "error": "crop provider probe returned no valid report"},
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


def _normalized_box_iou(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return 0.0
    inter_left = max(float(left[0]), float(right[0]))
    inter_top = max(float(left[1]), float(right[1]))
    inter_right = min(float(left[2]), float(right[2]))
    inter_bottom = min(float(left[3]), float(right[3]))
    intersection = max(0.0, inter_right - inter_left) * max(0.0, inter_bottom - inter_top)
    left_area = max(0.0, float(left[2]) - float(left[0])) * max(0.0, float(left[3]) - float(left[1]))
    right_area = max(0.0, float(right[2]) - float(right[0])) * max(0.0, float(right[3]) - float(right[1]))
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _crop_report_ok(report: dict | None) -> tuple[bool, float | None, list[dict[str, Any]]]:
    if not report or not (report.get("compile") or {}).get("ok") or report.get("runtime_error"):
        return (False, None, [])
    summary = report.get("output_summary") or {}
    element_count = int(summary.get("element_count") or 0)
    finite_count = int(summary.get("finite_count") or 0)
    finite = bool(
        element_count
        and element_count == finite_count
        and not int(summary.get("nan_count") or 0)
        and not int(summary.get("pos_inf_count") or 0)
        and not int(summary.get("neg_inf_count") or 0)
    )
    rows = [row for row in (report.get("per_image_detections") or []) if isinstance(row, dict)]
    return (finite, report.get("inference_latency_ms"), rows)


def _compare_crop_detections(
    baseline_rows: list[dict[str, Any]],
    provider_rows: list[dict[str, Any]],
    *,
    min_iou: float = 0.90,
    max_confidence_delta: float = 0.03,
) -> dict[str, Any]:
    baseline_keys = [str(row.get("image") or "") for row in baseline_rows]
    provider_keys = [str(row.get("image") or "") for row in provider_rows]
    duplicate_keys = (len(baseline_keys) != len(set(baseline_keys))) or (len(provider_keys) != len(set(provider_keys)))
    baseline_key_set = set(baseline_keys)
    provider_key_set = set(provider_keys)
    coverage_complete = bool(
        baseline_keys
        and not duplicate_keys
        and len(baseline_keys) == len(provider_keys)
        and baseline_key_set == provider_key_set
    )
    provider_by_image = {str(row.get("image") or ""): row for row in provider_rows}
    comparisons = matches = 0
    ious: list[float] = []
    confidence_deltas: list[float] = []
    for baseline in baseline_rows:
        image_key = str(baseline.get("image") or "")
        provider = provider_by_image.get(image_key)
        if provider is None:
            continue
        comparisons += 1
        baseline_detection = baseline.get("top_detection")
        provider_detection = provider.get("top_detection")
        if baseline_detection is None and provider_detection is None:
            matches += 1
            continue
        if not isinstance(baseline_detection, dict) or not isinstance(provider_detection, dict):
            continue
        iou = _normalized_box_iou(
            list(baseline_detection.get("normalized_box") or []),
            list(provider_detection.get("normalized_box") or []),
        )
        confidence_delta = abs(
            float(baseline_detection.get("confidence") or 0.0) - float(provider_detection.get("confidence") or 0.0)
        )
        ious.append(iou)
        confidence_deltas.append(confidence_delta)
        if iou >= min_iou and confidence_delta <= max_confidence_delta:
            matches += 1
    return {
        "images_expected": len(baseline_rows),
        "images_compared": comparisons,
        "matches": matches,
        "match_rate": (matches / comparisons) if comparisons else None,
        "mean_box_iou": (sum(ious) / len(ious)) if ious else None,
        "mean_confidence_delta": (sum(confidence_deltas) / len(confidence_deltas)) if confidence_deltas else None,
        "coverage_complete": coverage_complete,
        "duplicate_image_keys": duplicate_keys,
        "missing_images": len(baseline_key_set - provider_key_set),
        "unexpected_images": len(provider_key_set - baseline_key_set),
        "agrees": bool(coverage_complete and comparisons and matches == comparisons),
    }


async def sweep_model_devices(
    model_id: str,
    *,
    image_paths: list[str] | None = None,
    discover_providers: bool = False,
) -> dict:
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
        supported_providers=(spec.get("candidate_inference_providers") or spec.get("supported_inference_providers")),
        model_runtime=str(spec.get("runtime") or "onnx"),
        discover_providers=discover_providers,
    )
    declared_providers = {
        str(provider or "").strip().lower()
        for provider in (spec.get("candidate_inference_providers") or spec.get("supported_inference_providers") or [])
        if str(provider or "").strip()
    }
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
    discovered: list[str] = []
    best: dict | None = None
    best_discovered: dict | None = None
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
        declared = not declared_providers or candidate.provider in declared_providers
        entry = {
            "provider": candidate.provider,
            "backend": candidate.backend,
            "device": candidate.device,
            "ok": ok,
            "declared": declared,
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
            candidate_summary = {
                "device": candidate.device,
                "backend": candidate.backend,
                "provider": candidate.provider,
                "latency_ms": latency,
            }
            if declared:
                eligible.append(candidate.provider)
                if best is None or (
                    latency is not None and (best.get("latency_ms") is None or latency < best["latency_ms"])
                ):
                    best = candidate_summary
            else:
                discovered.append(candidate.provider)
                if best_discovered is None or (
                    latency is not None
                    and (best_discovered.get("latency_ms") is None or latency < best_discovered["latency_ms"])
                ):
                    best_discovered = candidate_summary

    return {
        "image_flavor": image_flavor,
        "artifact_sha256": str(spec.get("artifact_sha256") or "").strip().lower() or None,
        "baseline_provider": baseline_provider,
        "providers": per_provider,
        # Backwards-compatible response field used by older API clients.
        "devices": per_provider,
        "eligible_providers": eligible,
        "discovered_providers": discovered,
        "best": best,
        "best_discovered": best_discovered,
    }


async def sweep_crop_model_devices(
    model_id: str,
    *,
    image_paths: list[str] | None = None,
    discover_providers: bool = False,
) -> dict[str, Any]:
    """Validate an exact crop detector across CPU/GPU/NPU providers.

    Raw output must be finite and every top detection must agree with the CPU
    baseline in presence, geometry, and confidence. Three deterministic hard
    negatives are added by the child probe to catch provider-specific false
    positives alongside the varied real bird images supplied by the eval run.
    """
    from app.services.classifier_service import _detect_acceleration_capabilities
    from app.services.model_manager import model_manager

    spec = model_manager.get_crop_detector_spec_by_model_id(model_id)
    if not spec.get("healthy"):
        raise RuntimeError(f"crop detector {model_id} is not installed and ready: {spec.get('reason')}")
    metadata = dict(spec.get("metadata") or {})
    image_flavor = get_image_flavor()
    capabilities = await asyncio.to_thread(_detect_acceleration_capabilities)
    candidates = validation_provider_candidates(
        image_flavor=image_flavor,
        capabilities=capabilities,
        supported_providers=(
            metadata.get("candidate_inference_providers") or metadata.get("supported_inference_providers")
        ),
        model_runtime=str(metadata.get("runtime") or "onnx"),
        discover_providers=discover_providers,
    )
    declared_providers = {
        str(provider or "").strip().lower()
        for provider in (
            metadata.get("candidate_inference_providers") or metadata.get("supported_inference_providers") or []
        )
        if str(provider or "").strip()
    }
    baseline_provider = next(
        (candidate.provider for candidate in candidates if candidate.provider == "cpu"),
        next((candidate.provider for candidate in candidates if candidate.provider == "intel_cpu"), None),
    )

    reports: dict[str, dict | None] = {}
    for candidate in candidates:
        reports[candidate.provider] = await _probe_one_crop_provider(
            candidate.provider,
            model_id=model_id,
            image_paths=image_paths,
        )

    baseline_report = reports.get(baseline_provider) if baseline_provider else None
    baseline_finite, _baseline_latency, baseline_rows = _crop_report_ok(baseline_report)
    baseline_real_detections = sum(
        1 for row in baseline_rows if row.get("kind") == "real" and row.get("top_detection") is not None
    )
    baseline_usable = bool(baseline_finite and baseline_rows and baseline_real_detections)

    per_provider: list[dict[str, Any]] = []
    eligible: list[str] = []
    discovered: list[str] = []
    best: dict[str, Any] | None = None
    best_discovered: dict[str, Any] | None = None
    for candidate in candidates:
        report = reports.get(candidate.provider)
        finite, latency, rows = _crop_report_ok(report)
        comparison = (
            _compare_crop_detections(baseline_rows, rows)
            if baseline_rows and rows
            else {
                "images_expected": len(baseline_rows),
                "images_compared": 0,
                "matches": 0,
                "match_rate": None,
                "mean_box_iou": None,
                "mean_confidence_delta": None,
                "coverage_complete": False,
                "duplicate_image_keys": False,
                "missing_images": len(baseline_rows),
                "unexpected_images": len(rows),
                "agrees": False,
            }
        )
        if candidate.provider == baseline_provider:
            agrees = baseline_usable
            comparison = {
                "images_expected": len(baseline_rows),
                "images_compared": 0,
                "matches": 0,
                "match_rate": None,
                "mean_box_iou": None,
                "mean_confidence_delta": None,
                "coverage_complete": True,
                "duplicate_image_keys": False,
                "missing_images": 0,
                "unexpected_images": 0,
                "agrees": agrees,
            }
        else:
            agrees = bool(finite and baseline_usable and comparison["agrees"])
        ok = bool(finite and agrees)
        declared = not declared_providers or candidate.provider in declared_providers
        entry = {
            "provider": candidate.provider,
            "backend": candidate.backend,
            "device": candidate.device,
            "comparison_kind": "crop_box",
            "ok": ok,
            "declared": declared,
            "compiles": bool((report or {}).get("compile", {}).get("ok")),
            "finite": finite,
            "latency_ms": latency,
            "baseline": candidate.provider == baseline_provider,
            "images_evaluated": len(rows),
            "real_images_evaluated": sum(1 for row in rows if row.get("kind") == "real"),
            "negative_images_evaluated": sum(1 for row in rows if row.get("kind") == "negative"),
            "real_detections": sum(
                1 for row in rows if row.get("kind") == "real" and row.get("top_detection") is not None
            ),
            "images_compared": comparison["images_compared"],
            "image_set_complete": comparison["coverage_complete"],
            "duplicate_image_keys": comparison["duplicate_image_keys"],
            "missing_images": comparison["missing_images"],
            "unexpected_images": comparison["unexpected_images"],
            "matches_baseline": agrees if candidate.provider != baseline_provider else None,
            "matches_cpu": agrees if candidate.provider != baseline_provider else None,
            "detection_match_rate": (
                round(float(comparison["match_rate"]), 3) if comparison["match_rate"] is not None else None
            ),
            "mean_box_iou": (
                round(float(comparison["mean_box_iou"]), 3) if comparison["mean_box_iou"] is not None else None
            ),
            "mean_confidence_delta": (
                round(float(comparison["mean_confidence_delta"]), 4)
                if comparison["mean_confidence_delta"] is not None
                else None
            ),
            "error": (report or {}).get("runtime_error") or (report or {}).get("compile", {}).get("error"),
        }
        per_provider.append(entry)
        if not ok:
            continue
        candidate_summary = {
            "device": candidate.device,
            "backend": candidate.backend,
            "provider": candidate.provider,
            "latency_ms": latency,
        }
        target_list = eligible if declared else discovered
        target_list.append(candidate.provider)
        if declared:
            if best is None or (
                latency is not None and (best.get("latency_ms") is None or latency < best["latency_ms"])
            ):
                best = candidate_summary
        elif best_discovered is None or (
            latency is not None
            and (best_discovered.get("latency_ms") is None or latency < best_discovered["latency_ms"])
        ):
            best_discovered = candidate_summary

    return {
        "image_flavor": image_flavor,
        "artifact_sha256": str(metadata.get("sha256") or "").strip().lower() or None,
        "comparison_kind": "crop_box",
        "baseline_provider": baseline_provider,
        "providers": per_provider,
        "devices": per_provider,
        "eligible_providers": eligible,
        "discovered_providers": discovered,
        "best": best,
        "best_discovered": best_discovered,
    }


def is_model_validated(
    model_id: str,
    *,
    active_model_id: str | None,
    bundled_ids: set[str],
    artifact_sha256: str | None = None,
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
    if host_eligible_providers(model_id, artifact_sha256=artifact_sha256):
        return (True, "device_sweep")
    record = read_validation_record(model_id)
    if record and record.get("validated") is True:
        provider = str(record.get("provider") or "").strip().lower()
        current_flavor = get_image_flavor()
        recorded_flavor = str(record.get("image_flavor") or "").strip().lower()
        packaged = set(packaged_inference_providers(current_flavor))
        flavor_matches = current_flavor == "unknown" or recorded_flavor == current_flavor
        runtime_matches = (
            str(record.get("runtime_signature") or "").strip().lower() == current_inference_runtime_signature()
        )
        expected_artifact = str(artifact_sha256 or "").strip().lower()
        artifact_matches = (
            not expected_artifact or str(record.get("artifact_sha256") or "").strip().lower() == expected_artifact
        )
        if (
            flavor_matches
            and runtime_matches
            and artifact_matches
            and (not packaged or not provider or provider in packaged)
        ):
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
    registry_lookup = getattr(model_manager, "_get_registry_model_meta", None)
    registry_meta = registry_lookup(model_id) if callable(registry_lookup) else {}
    registry_meta = registry_meta or {}
    artifact_sha256 = str(registry_meta.get("sha256") or "").strip().lower() or None
    try:
        activated = await model_manager.activate_model(model_id)
        if not activated:
            reason = "model files are missing or incomplete"
            write_eligibility_entry(
                model_id,
                [],
                image_flavor=get_image_flavor(),
                artifact_sha256=artifact_sha256,
            )
            write_validation_record(
                model_id,
                provider=provider,
                ok=False,
                reason=reason,
                artifact_sha256=artifact_sha256,
            )
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
                write_eligibility_entry(
                    model_id,
                    eligible,
                    image_flavor=sweep["image_flavor"],
                    provider_results=sweep["providers"],
                    artifact_sha256=sweep.get("artifact_sha256") or artifact_sha256,
                )
                best_provider = best["provider"] if best else eligible[0]
                latency_ms = best["latency_ms"] if best else None
                reason = "validated against this image's providers on this host"
                write_validation_record(
                    model_id,
                    provider=best_provider,
                    ok=True,
                    reason=reason,
                    latency_ms=latency_ms,
                    artifact_sha256=sweep.get("artifact_sha256") or artifact_sha256,
                )
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
            write_eligibility_entry(
                model_id,
                [],
                image_flavor=sweep["image_flavor"],
                provider_results=sweep["providers"],
                artifact_sha256=sweep.get("artifact_sha256") or artifact_sha256,
            )
            write_validation_record(
                model_id,
                provider="cpu",
                ok=False,
                reason=reason,
                artifact_sha256=sweep.get("artifact_sha256") or artifact_sha256,
            )
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
            write_eligibility_entry(
                model_id,
                [],
                image_flavor=get_image_flavor(),
                artifact_sha256=artifact_sha256,
            )
            write_validation_record(
                model_id,
                provider="cpu",
                ok=False,
                reason=reason,
                artifact_sha256=artifact_sha256,
            )
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
        write_eligibility_entry(
            model_id,
            [],
            image_flavor=get_image_flavor(),
            artifact_sha256=artifact_sha256,
        )
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
        write_validation_record(
            model_id,
            provider=provider,
            ok=ok,
            reason=reason,
            latency_ms=latency_ms,
            artifact_sha256=artifact_sha256,
        )
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
        write_eligibility_entry(
            model_id,
            [],
            image_flavor=get_image_flavor(),
            artifact_sha256=artifact_sha256,
        )
        write_validation_record(
            model_id,
            provider=provider,
            ok=False,
            reason=reason,
            artifact_sha256=artifact_sha256,
        )
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
