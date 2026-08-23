"""A model's labels, read from the catalogue rather than its label file.

`labels.txt` is verified when a model is downloaded and never again, and every
inference since has trusted whatever is on disk. The catalogue holds a row per
output index carrying the model's own label, compiled from a file that was
proven at install time, so the labels can come from there instead.

Deliberately conservative. Labels are taken from the catalogue only when it
holds a complete, contiguous set matching the model's declared output width.
Anything short of that returns nothing and the caller keeps reading the file, so
a model the catalogue does not know behaves exactly as it does today.

The two failure modes this refuses are the ones that would be silent: a short
mapping would truncate a model's classes, and a gap in the indices would shift
every label after it onto the wrong class.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import structlog

from app.services.species_catalog_compatibility import LOCAL_REGISTRY_PREFIX

log = structlog.get_logger()


def published_model_sha256(model_id: str, region: Optional[str] = None) -> Optional[str]:
    """The checksum the registry publishes for a model's weights.

    Mirrors `label_integrity.published_labels_sha256`: region variants carry no
    id of their own, hanging off a parent under `region_variants`, so the caller
    has to say which one it means.
    """
    from app.services.model_manager import REMOTE_REGISTRY

    wanted = str(model_id or "").strip()
    if not wanted:
        return None
    region_key = str(region or "").strip().lower() or None

    def checksum(entry: object) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        value = str(entry.get("sha256") or "").strip().lower()
        return value or None

    for spec in REMOTE_REGISTRY:
        if not isinstance(spec, dict):
            continue
        if str(spec.get("id") or "") == wanted:
            if region_key:
                return checksum((spec.get("region_variants") or {}).get(region_key))
            return checksum(spec)
        for variant in spec.get("variants", []) or []:
            if isinstance(variant, dict) and str(variant.get("id") or "") == wanted:
                return checksum(variant)
    return None


def catalogue_labels_for_model(
    model_sha256: Optional[str],
    *,
    catalog_path: Optional[Path] = None,
) -> Optional[list[str]]:
    """Labels in output order, or None to fall back to the label file.

    Never raises: a catalogue that is absent, unreadable or incomplete simply
    yields nothing, and the caller reads the file as it always has.
    """
    checksum = str(model_sha256 or "").strip().lower()
    if not checksum:
        return None

    if catalog_path is None:
        from app.services.species_catalog_store import default_catalog_path

        catalog_path = default_catalog_path()

    try:
        connection = sqlite3.connect(f"file:{Path(catalog_path)}?mode=ro", uri=True)
    except sqlite3.Error:
        return None

    try:
        artifact = connection.execute(
            "SELECT id, output_width, registry_id FROM model_artifacts WHERE LOWER(model_sha256) = ?",
            (checksum,),
        ).fetchone()
        if artifact is None:
            return None
        artifact_id, output_width = int(artifact[0]), int(artifact[1] or 0)
        if output_width <= 0:
            return None
        # A locally derived mapping was read out of this model's own
        # `labels.txt`. Serving it back as catalogue labels would launder the
        # file this path exists to stop trusting, and would report a
        # verification that never happened.
        if str(artifact[2] or "").startswith(LOCAL_REGISTRY_PREFIX):
            return None

        rows = connection.execute(
            "SELECT output_index, source_label FROM model_output_taxa"
            " WHERE model_artifact_id = ? ORDER BY output_index",
            (artifact_id,),
        ).fetchall()
    except sqlite3.Error as error:
        log.debug("Species catalogue unreadable for labels", error=str(error))
        return None
    finally:
        connection.close()

    if len(rows) != output_width:
        return None
    labels: list[str] = []
    for expected_index, (index, label) in enumerate(rows):
        if int(index) != expected_index:
            return None
        text = str(label or "").strip()
        if not text:
            return None
        labels.append(text)
    return labels
