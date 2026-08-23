"""Derive a catalogue mapping for a model the owner installed themselves.

Every model in the registry ships a reviewed mapping in the release bundle, so
the catalogue can say what each of its outputs is. A model the owner supplied
has none: the resolver reports `unregistered`, no detection from it ever gains
a canonical identity, and its `labels.txt` stays the only thing that knows what
its classes are.

This closes that gap the only way that is honest without a reviewer: by
resolving the model's own labels against the live catalogue and recording what
resolves. An output that no source can name, or that two readings disagree
about, is written as `unknown` carrying the model's verbatim label — the same
row shape a published mapping uses for its own gaps — and returned in a report
rather than guessed at.

Three properties keep it safe to run unattended:

* it never touches an artifact the catalogue already holds, so a reviewed
  mapping cannot be overwritten by one derived from a file on disk;
* a label reaches an identity only through an exact catalogue match, and only
  when every reading that reaches one agrees, so a collision resolves to
  nothing rather than to the wrong bird;
* the artifact is recorded as locally derived, so the label reader refuses to
  serve these labels back as catalogue-verified.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import aiofiles
import structlog

from app.utils.classifier_labels import normalize_classifier_labels
from app.services.model_taxon_map import (
    normalize_common_name,
    paired_common_name,
    scientific_name_from_label,
)
from app.services.species_catalog_migrations import default_catalog_path

log = structlog.get_logger()

#: Marks an artifact whose mapping was derived here rather than reviewed and
#: published. No registry identifier contains a colon, so the namespace cannot
#: collide with one.
LOCAL_REGISTRY_PREFIX = "local:"

#: Enough unresolved outputs to see the shape of the problem without turning a
#: diagnostic payload into a copy of the label file.
_UNRESOLVED_SAMPLE = 20

_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_AMBIGUOUS = object()

#: `Malus \u00d7domestica` and `Malus domestica` are the same plant. Folded on the
#: way in to a lookup and never on the way into the table, so a catalogue
#: holding both spellings keeps them as the two entries it says they are.
_HYBRID_SIGNS = str.maketrans("", "", "\u00d7")

_BACKGROUND_LABELS = frozenset({"background", "none", "no bird"})
_UNKNOWN_LABELS = frozenset({"unknown", "unidentified"})


@dataclass(frozen=True)
class LocalMappingReport:
    """What the importer did, and everything it could not name.

    `verdict` is one of `imported`, `already_mapped`, `unavailable` or
    `refused`. The counts describe the outputs written; `unresolved_outputs`
    samples the ones with no identity so an owner can see which classes their
    model will never contribute to species history.
    """

    verdict: str
    model_sha256: str
    registry_id: Optional[str] = None
    output_width: int = 0
    resolved: int = 0
    unresolved: int = 0
    background: int = 0
    mapping_set_sha256: Optional[str] = None
    unresolved_outputs: list[dict[str, Any]] = field(default_factory=list)
    reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "model_sha256": self.model_sha256,
            "registry_id": self.registry_id,
            "output_width": self.output_width,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "background": self.background,
            "unresolved_outputs": list(self.unresolved_outputs),
            "reason": self.reason,
        }


class _LiveCatalogResolver:
    """Name lookups over one open catalogue, built for a single import.

    Deliberately not the long-lived resolver: this one carries English common
    names, which the detection path has no use for, and it is discarded as soon
    as the mapping is written.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._scientific: dict[str, Any] = {}
        self._common: dict[str, Any] = {}

        for scientific, species_id in connection.execute(
            "SELECT scientific_name, species_id FROM species_concepts ORDER BY species_id"
        ):
            self._put(self._scientific, str(scientific).casefold(), int(species_id))
        for alias, species_id in connection.execute(
            "SELECT alias, species_id FROM species_aliases"
            " WHERE resolution = 'resolved' AND species_id IS NOT NULL ORDER BY species_id"
        ):
            self._put(self._scientific, str(alias).casefold(), int(species_id))
        for name, species_id in connection.execute(
            "SELECT name, species_id FROM species_names WHERE language_tag = 'en' ORDER BY species_id"
        ):
            self._put(self._common, str(name).casefold(), int(species_id))
            self._put(self._common, normalize_common_name(str(name)), int(species_id))

    @staticmethod
    def _put(table: dict[str, Any], key: str, species_id: int) -> None:
        if not key:
            return
        current = table.get(key)
        if current is None:
            table[key] = species_id
        elif current != species_id:
            table[key] = _AMBIGUOUS

    def _lookup(self, table: dict[str, Any], *keys: Optional[str]) -> tuple[Optional[int], bool]:
        ambiguous = False
        for key in keys:
            if not key:
                continue
            value = table.get(key.casefold())
            if value is _AMBIGUOUS:
                ambiguous = True
                continue
            if value is not None:
                return int(value), ambiguous
        return None, ambiguous

    def scientific(self, text: Optional[str]) -> tuple[Optional[int], bool]:
        if not text:
            return None, False
        folded = " ".join(text.translate(_HYBRID_SIGNS).split())
        return self._lookup(self._scientific, text, folded)

    def common(self, text: Optional[str]) -> tuple[Optional[int], bool]:
        if not text:
            return None, False
        return self._lookup(self._common, text, normalize_common_name(text))


def _readings(text: str, label_format: Optional[str]) -> list[tuple[str, Optional[str]]]:
    """Every way this label may honestly be read, given what the caller knows.

    A declared format is obeyed exactly, because the declaration exists to stop
    the shape of a line being trusted. Without one — the owner-supplied case,
    where nobody has declared anything — the label is read every way at once
    and the readings have to agree before an identity is recorded.
    """
    if label_format == "common_name":
        return [("common", text)]
    if label_format == "detector_classes":
        return []
    if label_format is not None:
        return [("scientific", scientific_name_from_label(text, label_format=label_format))]
    return [
        ("common", text),
        ("scientific", text),
        ("scientific", scientific_name_from_label(text)),
        ("common", paired_common_name(text)),
    ]


def _identify(text: str, label_format: Optional[str], resolver: _LiveCatalogResolver) -> tuple[Optional[int], str]:
    confident: set[int] = set()
    saw_ambiguous = False
    for kind, candidate in _readings(text, label_format):
        lookup = resolver.scientific if kind == "scientific" else resolver.common
        species_id, ambiguous = lookup(candidate)
        saw_ambiguous = saw_ambiguous or ambiguous
        if species_id is not None:
            confident.add(species_id)

    if len(confident) == 1:
        return confident.pop(), "resolved"
    if len(confident) > 1:
        return None, "conflicting identities"
    if saw_ambiguous:
        return None, "ambiguous"
    return None, "no catalogue identity"


def _mapping_digest(rows: Sequence[tuple[int, str, Optional[int], str]]) -> str:
    digest = hashlib.sha256()
    for index, kind, species_id, label in rows:
        digest.update(f"{index}\t{kind}\t{'' if species_id is None else species_id}\t{label}\n".encode("utf-8"))
    return digest.hexdigest()


def _open_catalog(catalog_path: Optional[Path]) -> Optional[sqlite3.Connection]:
    path = Path(catalog_path or default_catalog_path())
    if not path.is_file():
        return None
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("SELECT 1 FROM model_artifacts LIMIT 1").fetchone()
    except sqlite3.Error:
        connection.close()
        return None
    return connection


def import_local_model_mapping(
    *,
    model_id: str,
    model_sha256: str,
    labels: Sequence[str],
    runtime: str,
    label_format: Optional[str] = None,
    catalog_path: Optional[Path] = None,
) -> LocalMappingReport:
    """Give an unregistered model a catalogue mapping built from its labels."""
    checksum = str(model_sha256 or "").strip().lower()
    cleaned = [str(label).strip() for label in labels]

    if not _CHECKSUM.match(checksum):
        return LocalMappingReport(verdict="refused", model_sha256=checksum, reason="model checksum is not a sha256")
    if not cleaned or not all(cleaned):
        return LocalMappingReport(verdict="refused", model_sha256=checksum, reason="label set is empty or has a blank")
    if not str(model_id or "").strip():
        return LocalMappingReport(verdict="refused", model_sha256=checksum, reason="model identifier is empty")

    connection = _open_catalog(catalog_path)
    if connection is None:
        return LocalMappingReport(verdict="unavailable", model_sha256=checksum, reason="no readable species catalogue")

    registry_id = f"{LOCAL_REGISTRY_PREFIX}{str(model_id).strip()}"
    try:
        existing = connection.execute(
            "SELECT registry_id FROM model_artifacts WHERE LOWER(model_sha256) = ?", (checksum,)
        ).fetchone()
        if existing is not None:
            return LocalMappingReport(
                verdict="already_mapped",
                model_sha256=checksum,
                registry_id=str(existing[0]),
                reason="the catalogue already holds this artifact",
            )

        resolver = _LiveCatalogResolver(connection)
        rows: list[tuple[int, str, Optional[int], str]] = []
        unresolved_outputs: list[dict[str, Any]] = []
        resolved = background = unresolved = 0

        for index, label in enumerate(cleaned):
            folded = label.casefold()
            if folded in _BACKGROUND_LABELS:
                rows.append((index, "background", None, label))
                background += 1
                continue
            if folded in _UNKNOWN_LABELS:
                rows.append((index, "unknown", None, label))
                continue

            species_id, reason = _identify(label, label_format, resolver)
            if species_id is not None:
                rows.append((index, "species", species_id, label))
                resolved += 1
                continue

            rows.append((index, "unknown", None, label))
            unresolved += 1
            if len(unresolved_outputs) < _UNRESOLVED_SAMPLE:
                unresolved_outputs.append({"index": index, "label": label, "reason": reason})

        digest = _mapping_digest(rows)
        with connection:
            cursor = connection.execute(
                "INSERT INTO model_artifacts"
                " (registry_id, model_sha256, mapping_set_sha256, output_width, runtime, state)"
                " VALUES (?, ?, ?, ?, ?, 'installed')",
                (registry_id, checksum, digest, len(rows), str(runtime or "unknown")),
            )
            connection.executemany(
                "INSERT INTO model_output_taxa (model_artifact_id, output_index, class_kind, species_id, source_label)"
                " VALUES (?, ?, ?, ?, ?)",
                [(cursor.lastrowid, index, kind, species_id, label) for index, kind, species_id, label in rows],
            )
    except sqlite3.Error as error:
        log.warning("Local model mapping not imported", model_id=model_id, error=str(error))
        return LocalMappingReport(verdict="refused", model_sha256=checksum, reason=str(error))
    finally:
        connection.close()

    report = LocalMappingReport(
        verdict="imported",
        model_sha256=checksum,
        registry_id=registry_id,
        output_width=len(rows),
        resolved=resolved,
        unresolved=unresolved,
        background=background,
        mapping_set_sha256=digest,
        unresolved_outputs=unresolved_outputs,
    )
    log.info(
        "Derived a catalogue mapping for a locally installed model",
        registry_id=registry_id,
        outputs=report.output_width,
        resolved=resolved,
        unresolved=unresolved,
    )
    return report


_report_lock = threading.Lock()
_last_report: Optional[LocalMappingReport] = None


def last_local_mapping_report() -> Optional[dict[str, Any]]:
    """The most recent local import, for diagnostics, or None if none ran."""
    with _report_lock:
        return _last_report.as_dict() if _last_report else None


def _record_report(report: LocalMappingReport) -> None:
    global _last_report
    with _report_lock:
        _last_report = report


async def _read_label_file(labels_path: str) -> list[str]:
    """The model's labels, parsed exactly as the loader parses them.

    Sharing `normalize_classifier_labels` is the point: a mapping whose width
    disagreed with the tensor the model actually produces would bind every
    output after the disagreement to the wrong class.
    """
    if not labels_path:
        return []
    # A missing file raises here rather than being probed for first: the probe
    # is blocking I/O, and the open has to handle the race anyway.
    try:
        async with aiofiles.open(labels_path, "r", encoding="utf-8", errors="replace") as handle:
            content = await handle.read()
    except OSError as error:
        log.debug("Label file unreadable for local mapping", path=labels_path, error=str(error))
        return []
    return normalize_classifier_labels(line.strip() for line in content.splitlines() if line.strip())


#: A model that is still loading has nothing to map yet. Startup does not wait
#: for it, so the import waits instead, and gives up rather than polling for
#: the life of the process.
_MODEL_WAIT_ATTEMPTS = 20
_MODEL_WAIT_SECONDS = 6.0

_NO_MODEL_LOADED = "no model is loaded"


def _skipped(reason: str) -> LocalMappingReport:
    return LocalMappingReport(verdict="skipped", model_sha256="", reason=reason)


async def import_mapping_for_installed_model(
    catalog_path: Optional[Path] = None,
) -> LocalMappingReport:
    """Map the loaded model's outputs when the registry publishes none for it.

    A registry model is skipped outright. Its mapping is reviewed and arrives
    in the release bundle, and one derived from a file on disk must never stand
    in for one that was checked — not even while the reviewed one is missing.
    """
    from app.services.catalogue_labels import published_model_sha256
    from app.services.classifier_service import get_classifier
    from app.services.model_manager import model_manager

    spec = dict(model_manager.get_active_model_spec() or {})
    model_id = str(spec.get("model_id") or "").strip()
    if not model_id:
        return _skipped("no model is selected")
    if published_model_sha256(model_id, spec.get("resolved_region")):
        return _skipped("the registry publishes a mapping for this model")

    checksum = str(get_classifier().active_model_sha256() or "")
    if not checksum:
        return _skipped(_NO_MODEL_LOADED)

    labels = await _read_label_file(str(spec.get("labels_path") or ""))
    if not labels:
        return _skipped("the model has no readable label file")

    return await asyncio.to_thread(
        import_local_model_mapping,
        model_id=model_id,
        model_sha256=checksum,
        labels=labels,
        runtime=str(spec.get("runtime") or "unknown"),
        catalog_path=catalog_path,
    )


async def start_background_local_mapping_import() -> None:
    """Run the compatibility import detached from startup; never fatal.

    Waits for the classifier to finish loading rather than racing it, because
    the checksum this keys on only exists once the model file has been read.
    """
    report = _skipped(_NO_MODEL_LOADED)
    try:
        for attempt in range(_MODEL_WAIT_ATTEMPTS):
            report = await import_mapping_for_installed_model()
            if report.reason != _NO_MODEL_LOADED:
                break
            if attempt + 1 < _MODEL_WAIT_ATTEMPTS:
                await asyncio.sleep(_MODEL_WAIT_SECONDS)
    except Exception as error:  # pragma: no cover - defensive
        report = LocalMappingReport(verdict="refused", model_sha256="", reason=str(error))
        log.warning("Local model mapping import failed", error=str(error))

    _record_report(report)
    if report.verdict == "imported" and report.unresolved:
        log.info(
            "Some outputs of the installed model have no catalogue identity",
            registry_id=report.registry_id,
            unresolved=report.unresolved,
            of=report.output_width,
        )
