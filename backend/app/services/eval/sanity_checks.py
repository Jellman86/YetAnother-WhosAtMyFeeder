"""Pure functions that turn per-model eval results into actionable warnings.

Kept separate from the service so the rules can be unit-tested without any
classifier or HTTP dependencies.
"""
from __future__ import annotations

from typing import Any


# Thresholds. Centralized so they can be tuned in one place.
LATENCY_DRIFT_FACTOR = 5.0          # measured mean / startup benchmark
HIGH_ABSTENTION_RATE = 0.10
LOW_SHARED_CORE_TOP1 = 0.50


def latency_drift(model: dict[str, Any]) -> dict[str, Any] | None:
    benchmark = model.get("startup_benchmark_ms")
    measured = model.get("mean_latency_ms")
    if not benchmark or not measured:
        return None
    if measured <= benchmark * LATENCY_DRIFT_FACTOR:
        return None
    return {
        "code": "latency_drift_high",
        "message": (
            f"measured mean {measured:.0f} ms is {measured / benchmark:.1f}× "
            f"the startup benchmark ({benchmark:.0f} ms)"
        ),
        "severity": "critical",
    }


def high_abstention(model: dict[str, Any]) -> dict[str, Any] | None:
    rate = model.get("abstention_rate")
    if rate is None or rate <= HIGH_ABSTENTION_RATE:
        return None
    return {
        "code": "high_abstention",
        "message": f"abstained on {rate:.1%} of images (threshold {HIGH_ABSTENTION_RATE:.0%})",
        "severity": "warning",
    }


def low_shared_core(model: dict[str, Any]) -> dict[str, Any] | None:
    score = model.get("shared_core_top1")
    if score is None or score >= LOW_SHARED_CORE_TOP1:
        return None
    return {
        "code": "low_shared_core",
        "message": (
            f"shared-core top-1 {score:.1%} below {LOW_SHARED_CORE_TOP1:.0%} — "
            "likely vocab mismatch, broken install, or incorrect labels"
        ),
        "severity": "critical",
    }


def provider_fallback(model: dict[str, Any]) -> dict[str, Any] | None:
    requested = (model.get("requested_provider") or "").lower()
    active = (model.get("active_provider") or "").lower()
    if not requested or requested == active:
        return None
    if "cpu" in active and "cpu" not in requested:
        return {
            "code": "provider_fallback_active",
            "message": f"requested {requested!r} but running on {active!r}",
            "severity": "warning",
        }
    return None


def incomplete_install(model: dict[str, Any]) -> dict[str, Any] | None:
    if model.get("ready") is False:
        reason = model.get("ready_reason") or "unknown"
        return {
            "code": "incomplete_install",
            "message": f"model not ready: {reason}",
            "severity": "critical",
        }
    if not model.get("labels_file_present", True):
        return {"code": "incomplete_install", "message": "labels.txt missing", "severity": "critical"}
    if not model.get("model_config_present", True):
        return {"code": "incomplete_install", "message": "model_config.json missing", "severity": "warning"}
    return None


def inference_health_unhealthy(model: dict[str, Any]) -> dict[str, Any] | None:
    verdict = (model.get("inference_health_verdict") or "").lower()
    if verdict != "unhealthy":
        return None
    return {
        "code": "inference_health_unhealthy",
        "message": "InferenceHealth verdict is 'unhealthy' at run end",
        "severity": "critical",
    }


def region_mismatch(model: dict[str, Any], region_label: str | None) -> dict[str, Any] | None:
    if not region_label:
        return None
    region_short = region_label.split("-", 1)[0].lower()  # "US" / "GB" / etc
    family = (model.get("model_id") or "").lower()
    is_eu = "/eu" in family or family.endswith("_eu") or "_eu_" in family or "focalnet" in family
    is_na = "/na" in family or family.endswith("_na") or "_na_" in family
    eu_regions = {"gb", "ie", "fr", "de", "es", "it", "nl", "be", "se", "no", "dk", "fi", "ch", "at", "pt"}
    na_regions = {"us", "ca", "mx"}
    if is_eu and region_short in na_regions:
        return {
            "code": "region_mismatch",
            "message": f"EU-tuned model evaluated against region {region_label}",
            "severity": "info",
        }
    if is_na and region_short in eu_regions:
        return {
            "code": "region_mismatch",
            "message": f"NA-tuned model evaluated against region {region_label}",
            "severity": "info",
        }
    return None


_RULES = (
    incomplete_install,
    inference_health_unhealthy,
    latency_drift,
    low_shared_core,
    high_abstention,
    provider_fallback,
)


def collect(model: dict[str, Any], *, region_label: str | None = None) -> list[dict[str, Any]]:
    """Run every rule against a model summary and return the warnings list."""
    warnings: list[dict[str, Any]] = []
    for rule in _RULES:
        result = rule(model)
        if result:
            warnings.append(result)
    rm = region_mismatch(model, region_label)
    if rm:
        warnings.append(rm)
    return warnings
