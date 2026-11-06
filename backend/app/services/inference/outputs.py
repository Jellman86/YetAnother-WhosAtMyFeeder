"""Turn raw model outputs into ranked, labelled classifications.

Probability normalisation and softmax refuse non-finite output in strict mode, and
catalogue labels must match the model's output width exactly.
"""

import os
import math
from typing import Any, Optional

import numpy as np
import structlog

from app.config import settings
from app.utils.classifier_labels import (
    build_grouped_classifier_labels,
    normalize_classifier_label,
    normalize_classifier_labels,
)

log = structlog.get_logger()

LEGACY_CLASSIFIER_STRICT_NON_FINITE_OUTPUT = (
    os.getenv("CLASSIFIER_STRICT_NON_FINITE_OUTPUT", "true").strip().lower() != "false"
)


def strict_non_finite_output_enabled() -> bool:
    configured = getattr(getattr(settings, "classification", None), "strict_non_finite_output", None)
    if isinstance(configured, bool):
        return configured
    return LEGACY_CLASSIFIER_STRICT_NON_FINITE_OUTPUT


def normalize_probability_vector(values: np.ndarray, *, context: str) -> np.ndarray:
    probs = np.asarray(values, dtype=np.float32).reshape(-1)
    if probs.size == 0:
        return np.array([], dtype=np.float32)

    finite_mask = np.isfinite(probs)
    if not finite_mask.any():
        if not strict_non_finite_output_enabled():
            log.warning(
                "Classifier produced all non-finite probabilities; coercing in non-strict mode",
                context=context,
            )
            probs = np.nan_to_num(probs, nan=1.0, posinf=1.0, neginf=0.0).astype(np.float32, copy=False)
            total = float(np.sum(np.maximum(probs, 0.0)))
            if total > 0.0 and np.isfinite(total):
                return (np.maximum(probs, 0.0) / total).astype(np.float32, copy=False)
            return np.full((probs.size,), 1.0 / float(probs.size), dtype=np.float32)
        log.warning("Classifier produced all non-finite probabilities", context=context)
        return np.array([], dtype=np.float32)

    if not finite_mask.all():
        probs = probs.copy()
        bad_count = int((~finite_mask).sum())
        probs[~finite_mask] = 0.0
        log.warning(
            "Classifier produced non-finite probabilities; zeroing invalid entries",
            context=context,
            invalid_count=bad_count,
        )

    probs = np.maximum(probs, 0.0)
    total = float(np.sum(probs))
    if not np.isfinite(total) or total <= 0.0:
        log.warning("Classifier probability normalization failed", context=context, total=total)
        return np.array([], dtype=np.float32)

    normalized = probs / total
    if not np.isfinite(normalized).all():
        log.warning("Classifier normalization still produced non-finite probabilities", context=context)
        return np.array([], dtype=np.float32)
    return normalized.astype(np.float32, copy=False)


def safe_softmax(x: np.ndarray, *, context: str) -> np.ndarray:
    logits = np.asarray(x, dtype=np.float32).reshape(-1)
    if logits.size == 0:
        return np.array([], dtype=np.float32)

    finite_mask = np.isfinite(logits)
    if not finite_mask.any():
        nan_count = int(np.isnan(logits).sum())
        pos_inf_count = int((logits == np.inf).sum())
        neg_inf_count = int((logits == -np.inf).sum())
        log.warning(
            "Classifier produced ALL non-finite logits",
            context=context,
            nan_count=nan_count,
            pos_inf_count=pos_inf_count,
            neg_inf_count=neg_inf_count,
            total_elements=logits.size,
        )
        if not strict_non_finite_output_enabled():
            log.warning(
                "Classifier produced all non-finite logits; coercing in non-strict mode",
                context=context,
            )
            logits = np.nan_to_num(logits, nan=0.0, posinf=80.0, neginf=-80.0).astype(np.float32, copy=False)
            shifted = logits - float(np.max(logits))
            exp_logits = np.exp(np.clip(shifted, -80.0, 80.0)).astype(np.float32, copy=False)
            return normalize_probability_vector(exp_logits, context=context)
        log.warning("Classifier produced all non-finite logits", context=context)
        return np.array([], dtype=np.float32)

    if not finite_mask.all():
        logits = logits.copy()
        bad_count = int((~finite_mask).sum())
        logits[~finite_mask] = -np.inf
        log.warning(
            "Classifier produced non-finite logits; excluding invalid entries",
            context=context,
            invalid_count=bad_count,
        )

    max_logit = float(np.max(logits[finite_mask]))
    shifted = logits - max_logit
    exp_logits = np.zeros_like(logits, dtype=np.float32)
    exp_mask = np.isfinite(shifted)
    exp_logits[exp_mask] = np.exp(np.clip(shifted[exp_mask], -80.0, 80.0))
    return normalize_probability_vector(exp_logits, context=context)


def build_classification_results(
    probs: np.ndarray,
    labels: list[str],
    *,
    top_k: int,
    grouped_labels: Optional[list[str]] = None,
    model_sha256: Optional[str] = None,
) -> list[dict]:
    probabilities = np.asarray(probs, dtype=np.float32).reshape(-1)
    if probabilities.size == 0:
        return []

    evidence = _classification_group_evidence(probabilities, labels, model_sha256=model_sha256)

    if grouped_labels and len(grouped_labels) == probabilities.size:
        aggregated: dict[str, dict[str, Any]] = {}
        for i, score in enumerate(probabilities):
            label = grouped_labels[i] or (labels[i] if i < len(labels) else f"Class {i}")
            entry = aggregated.get(label)
            score_value = float(score)
            if entry is None:
                aggregated[label] = {
                    "index": int(i),
                    "label": label,
                    "score": score_value,
                    "_best_member_score": score_value,
                }
                continue
            entry["score"] += score_value
            if score_value > float(entry["_best_member_score"]):
                entry["index"] = int(i)
                entry["_best_member_score"] = score_value

        ranked = sorted(aggregated.values(), key=lambda item: float(item["score"]), reverse=True)
        for item in ranked:
            item.pop("_best_member_score", None)
        results = ranked[:top_k]
    else:
        top_indices = np.argsort(probabilities)[::-1][:top_k]
        results = [
            {
                "index": int(i),
                "score": float(probabilities[i]),
                "label": normalize_classifier_label(labels[i]) if i < len(labels) else f"Class {i}",
            }
            for i in top_indices
        ]
    if evidence is not None:
        for result in results:
            result["taxonomic_evidence"] = dict(evidence)
    return results


def _classification_group_evidence(
    probabilities: np.ndarray, labels: list[str], *, model_sha256: Optional[str]
) -> dict[str, Any] | None:
    """Summarise the original posterior, never a top-k or bird-only distribution."""
    if not model_sha256 or not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)):
        return None
    if not math.isclose(float(np.sum(probabilities, dtype=np.float64)), 1.0, abs_tol=1e-5):
        return None
    from app.services.species_catalog_resolver import species_catalog_resolver

    bound = species_catalog_resolver.cached_output_groups(model_sha256, labels)
    if bound is None or len(bound.groups) != probabilities.size:
        return None
    groups = np.asarray(bound.groups)
    birds, nonbirds = groups == "bird", groups == "nonbird"
    if not birds.any() or not nonbirds.any():
        return None
    return {
        "model_sha256": bound.model_sha256,
        "mapping_sha256": bound.mapping_sha256,
        "output_width": int(probabilities.size),
        "bird_outputs": int(birds.sum()),
        "nonbird_outputs": int(nonbirds.sum()),
        "bird_mass": float(np.sum(probabilities[birds], dtype=np.float64)),
        "nonbird_mass": float(np.sum(probabilities[nonbirds], dtype=np.float64)),
        "unknown_mass": float(np.sum(probabilities[~(birds | nonbirds)], dtype=np.float64)),
        "top_group": bound.groups[int(np.argmax(probabilities))],
    }


def check_catalogue_output_width(labels: list[str], output_width: int, source: str) -> None:
    if source == "catalogue" and len(labels) != output_width:
        raise ValueError(f"Catalogue output width {len(labels)} differs from model output width {output_width}")


def resolve_model_labels(
    labels_path: str,
    label_grouping: dict,
    *,
    model_sha256: Optional[str] = None,
    context: str = "model",
) -> tuple[list[str], list[str], str]:
    """Labels and their grouping, preferring the catalogue over the label file.

    `labels.txt` is verified when a model is downloaded and never again, so every
    inference since has trusted whatever is on disk. The catalogue holds the same
    labels compiled from a file that was proven at install time.

    The catalogue is used only when it holds a complete, contiguous set matching
    the model's declared output width; anything short of that falls back to the
    file, so a model it does not know behaves exactly as it does today.

    Returns the labels, the grouped labels, and which source supplied them.
    """
    labels: list[str] = []
    source = "none"

    if model_sha256:
        try:
            from app.services.catalogue_labels import catalogue_labels_for_model

            from_catalogue = catalogue_labels_for_model(model_sha256)
        except Exception as error:  # pragma: no cover - defensive
            log.debug("Catalogue labels unavailable", context=context, error=str(error))
            from_catalogue = None
        if from_catalogue:
            labels = normalize_classifier_labels(from_catalogue)
            source = "catalogue"
        try:
            from app.services.species_catalog_resolver import species_catalog_resolver

            # Model loading already runs off-thread. Classification only reads
            # the immutable snapshot, including inside isolated native workers.
            species_catalog_resolver.ensure_loaded()
        except Exception as error:
            log.debug("Catalogue group snapshot unavailable", context=context, error_type=type(error).__name__)

    if not labels and os.path.exists(labels_path):
        try:
            with open(labels_path, "r", encoding="utf-8", errors="replace") as handle:
                labels = normalize_classifier_labels(line.strip() for line in handle.readlines() if line.strip())
            source = "label_file"
        except Exception as error:
            log.error("Failed to load labels", context=context, error=str(error))
            return [], [], "none"

    grouped: list[str] = []
    strategy = str((label_grouping or {}).get("strategy") or "").strip()
    if strategy and labels:
        grouped = build_grouped_classifier_labels(labels, strategy=strategy)
    return labels, grouped, source


def resolve_grouped_labels(
    labels: list[str],
    *,
    label_grouping: Optional[dict[str, Any]] = None,
    existing_grouped_labels: Optional[list[str]] = None,
) -> list[str]:
    if existing_grouped_labels:
        return list(existing_grouped_labels)
    strategy = str((label_grouping or {}).get("strategy") or "").strip()
    if not strategy:
        return []
    return build_grouped_classifier_labels(labels, strategy=strategy)
