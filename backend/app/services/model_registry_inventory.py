"""Every concrete model artifact the registry supports, as one flat inventory.

The species catalogue keys its output mappings on the exact artifact checksum,
so Phase 0 of the catalogue design requires an inventory covering 100% of
supported artifact checksums, each with its declared label grammar. This walks
the registry the same way installation does — a region variant is its own
artifact — and fails loudly when a concrete artifact is missing a declaration,
which is the freeze: a new registry entry cannot land half-described.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.model_manager import REMOTE_REGISTRY
from app.services.model_taxon_map import LABEL_FORMATS

_SHA256_LENGTH = 64


@dataclass(frozen=True)
class RegistryArtifact:
    artifact_id: str
    model_id: str
    region: Optional[str]
    name: str
    artifact_kind: str
    runtime: str
    status: str
    taxonomy_scope: str
    label_format: str
    sha256: str
    weights_sha256: Optional[str]
    labels_sha256: Optional[str]
    download_url: str
    labels_url: Optional[str]


def _checksum(entry: dict, key: str) -> Optional[str]:
    value = str(entry.get(key) or "").strip().lower()
    return value if len(value) == _SHA256_LENGTH else None


def _artifact(spec: dict, variant: Optional[dict] = None, region: Optional[str] = None) -> RegistryArtifact:
    entry = variant or spec

    def field(key: str, default: str = "") -> str:
        value = str(entry.get(key) or "").strip()
        if not value and variant is not None:
            value = str(spec.get(key) or "").strip()
        return value or default

    model_id = str(spec.get("id") or "").strip()
    artifact_id = f"{model_id}/{region}" if region else model_id
    sha256 = _checksum(entry, "sha256")
    if not sha256:
        raise ValueError(f"Registry artifact '{artifact_id}' has no usable sha256")

    label_format = field("label_format")
    if label_format not in LABEL_FORMATS:
        raise ValueError(
            f"Registry artifact '{artifact_id}' declares label_format '{label_format or '<missing>'}';"
            " every concrete artifact must declare a known label grammar"
        )

    return RegistryArtifact(
        artifact_id=artifact_id,
        model_id=model_id,
        region=region,
        name=field("name", model_id),
        artifact_kind=field("artifact_kind", "classifier"),
        runtime=field("runtime"),
        status=field("status"),
        taxonomy_scope=field("taxonomy_scope"),
        label_format=label_format,
        sha256=sha256,
        weights_sha256=_checksum(entry, "weights_sha256"),
        labels_sha256=_checksum(entry, "labels_sha256"),
        download_url=field("download_url"),
        labels_url=field("labels_url") or None,
    )


def registry_artifacts() -> list[RegistryArtifact]:
    """One row per concrete artifact: top-level models and region variants.

    A family parent with no artifact of its own (`download_url: "pending"`)
    contributes only its variants. Retired models are absent from the registry
    and therefore from the inventory.
    """
    artifacts: list[RegistryArtifact] = []
    for spec in REMOTE_REGISTRY:
        if not isinstance(spec, dict):
            continue
        variants = spec.get("region_variants") or {}
        for region, variant in sorted(variants.items()):
            if isinstance(variant, dict) and _checksum(variant, "sha256"):
                artifacts.append(_artifact(spec, variant, region))
        if _checksum(spec, "sha256"):
            artifacts.append(_artifact(spec))
    return artifacts
