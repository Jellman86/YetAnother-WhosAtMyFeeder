"""Check an installed label file against the checksum it was published with.

`labels_sha256` is verified while a model is downloaded and never again. A label
file altered afterwards is read as authoritative, and every detection classified
against it is written to history under the wrong species. That is a data
integrity problem, not a naming one, so it is checked here rather than assumed.

The same pass builds the output-index mapping, because the moment a file has been
proven is the right moment to derive something durable from it. A file that does
not match is not mapped: making an altered file's names authoritative is exactly
what this exists to prevent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import structlog

from app.services.model_taxon_map import ModelTaxonMap, model_taxon_map

log = structlog.get_logger()

LABELS_FILENAME = "labels.txt"
_DIGEST_CHUNK_BYTES = 1024 * 1024


class LabelVerdict(str, Enum):
    VERIFIED = "verified"
    CHANGED = "changed"
    UNVERIFIABLE = "unverifiable"
    MISSING = "missing"


@dataclass(frozen=True)
class LabelCheck:
    model_id: str
    verdict: LabelVerdict
    expected_sha256: Optional[str]
    actual_sha256: Optional[str]
    label_count: int
    labels: tuple[str, ...] = ()
    label_format: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "verdict": self.verdict.value,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "label_count": self.label_count,
        }


def published_labels_sha256(model_id: str, region: Optional[str] = None) -> Optional[str]:
    """The checksum the registry publishes for a model's label file.

    Region variants carry no id of their own; they hang off a parent under
    `region_variants` and install into `<parent>/<region>`, so the caller has to
    say which one it means.
    """
    from app.services.model_manager import REMOTE_REGISTRY

    wanted = str(model_id or "").strip()
    if not wanted:
        return None
    region_key = str(region or "").strip().lower() or None

    def checksum(entry: object) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        value = str(entry.get("labels_sha256") or "").strip().lower()
        return value or None

    for spec in REMOTE_REGISTRY:
        if not isinstance(spec, dict):
            continue
        if str(spec.get("id") or "") == wanted:
            if region_key:
                variant = (spec.get("region_variants") or {}).get(region_key)
                return checksum(variant)
            return checksum(spec)
        for variant in spec.get("variants", []) or []:
            if isinstance(variant, dict) and str(variant.get("id") or "") == wanted:
                return checksum(variant)
    return None


def published_label_format(model_id: str, region: Optional[str] = None) -> Optional[str]:
    """The label grammar the registry declares for a model's label file.

    Declared per artifact rather than inferred from the file: the NABirds
    plumage labels wear the Coral paired shape, and shape-guessing them recorded
    common names as scientific names.
    """
    from app.services.model_manager import REMOTE_REGISTRY

    wanted = str(model_id or "").strip()
    if not wanted:
        return None
    region_key = str(region or "").strip().lower() or None

    def declared(entry: object, parent: Optional[dict] = None) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        value = str(entry.get("label_format") or "").strip()
        if not value and parent is not None:
            value = str(parent.get("label_format") or "").strip()
        return value or None

    for spec in REMOTE_REGISTRY:
        if not isinstance(spec, dict):
            continue
        if str(spec.get("id") or "") == wanted:
            if region_key:
                variant = (spec.get("region_variants") or {}).get(region_key)
                return declared(variant, spec)
            return declared(spec)
        for variant in spec.get("variants", []) or []:
            if isinstance(variant, dict) and str(variant.get("id") or "") == wanted:
                return declared(variant, spec)
    return None


def _digest_file(path: Path) -> Optional[str]:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError as error:
        log.warning("Could not read label file", path=str(path), error=str(error))
        return None
    return digest.hexdigest()


def verify_model_labels(
    model_id: str,
    model_dir: Path,
    *,
    expected_sha256: Optional[str] = None,
    region: Optional[str] = None,
) -> LabelCheck:
    """Compare an installed label file against its published checksum.

    An absent checksum yields `unverifiable`, never `changed`: plenty of models
    ship without one, and reporting that as tampering would be a false alarm.
    """
    labels_path = Path(model_dir) / LABELS_FILENAME
    expected = (expected_sha256 or published_labels_sha256(model_id, region) or "").strip().lower() or None
    declared_format = published_label_format(model_id, region)

    if not labels_path.is_file():
        return LabelCheck(model_id, LabelVerdict.MISSING, expected, None, 0, label_format=declared_format)

    actual = _digest_file(labels_path)
    if actual is None:
        return LabelCheck(model_id, LabelVerdict.MISSING, expected, None, 0, label_format=declared_format)

    try:
        labels = tuple(
            line.strip()
            for line in labels_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        )
    except OSError as error:
        log.warning("Could not read label file", path=str(labels_path), error=str(error))
        return LabelCheck(model_id, LabelVerdict.MISSING, expected, actual, 0, label_format=declared_format)

    if expected is None:
        verdict = LabelVerdict.UNVERIFIABLE
    elif actual == expected:
        verdict = LabelVerdict.VERIFIED
    else:
        verdict = LabelVerdict.CHANGED
        log.error(
            "Model label file does not match its published checksum; species names from it are not trustworthy",
            model_id=model_id,
            path=str(labels_path),
            expected=expected,
            actual=actual,
        )

    return LabelCheck(model_id, verdict, expected, actual, len(labels), labels, label_format=declared_format)


def build_map_for_verified_labels(
    check: LabelCheck,
    *,
    mapping: Optional[ModelTaxonMap] = None,
) -> int:
    """Derive the output-index mapping from a label file that has been checked.

    A file reported as `changed` is deliberately not mapped. Everything else is:
    a model with no published checksum is ordinary, and withholding its names
    would punish the user for the registry's omission. Crop-detector classes are
    not taxa, so a detector file never enters the species mapping at all.
    """
    if check.verdict in (LabelVerdict.CHANGED, LabelVerdict.MISSING):
        return 0
    if not check.actual_sha256 or not check.labels:
        return 0
    if check.label_format == "detector_classes":
        return 0

    target = mapping or model_taxon_map
    return target.build(
        check.actual_sha256,
        check.labels,
        label_format=check.label_format,
    )
