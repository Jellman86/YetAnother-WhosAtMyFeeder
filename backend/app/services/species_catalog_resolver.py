"""Shadow-resolve inference through the catalogue beside the label path.

Phase 3 of the catalogue design runs both identity paths on every new
detection: the label path keeps writing the name snapshots it always has,
and the catalogue path resolves the winning `(model checksum, output index)`
to a canonical `species_id`. The identity is persisted only when the two
paths agree — a catalogue concept or recorded synonym matching the label
path's scientific name — and every disagreement is counted and surfaced in
diagnostics rather than written into history.

Read-only and fail-soft like its naming-layer siblings: a missing catalogue,
an unregistered model, or an unresolved index degrades to a detection with
whatever provenance is known and no canonical identity, exactly the
pre-catalogue behaviour.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import structlog

from app.services.species_catalog_migrations import default_catalog_path

log = structlog.get_logger()


@dataclass(frozen=True)
class ShadowResolution:
    verdict: str
    species_id: Optional[int] = None
    model_artifact_id: Optional[int] = None
    model_output_index: Optional[int] = None


@dataclass(frozen=True)
class _OutputEntry:
    artifact_row_id: int
    class_kind: str
    species_id: Optional[int]


class SpeciesCatalogResolver:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._cache_key: Optional[tuple[int, int]] = None
        # model_sha256 -> {output_index -> _OutputEntry}; artifact ids for
        # models with no mapped outputs are still recorded so gaps resolve to
        # the artifact rather than to nothing.
        self._outputs: dict[str, dict[int, _OutputEntry]] = {}
        self._artifact_ids: dict[str, int] = {}
        # species_id -> casefolded names the catalogue accepts for it: every
        # concept's scientific name plus every resolved alias, so a label
        # still using a recorded synonym counts as the same bird.
        self._accepted_names: dict[int, set[str]] = {}
        # The inverse, for the historical backfill: a casefolded name held by
        # exactly one species resolves; one held by several is ambiguous and
        # resolves nothing.
        self._name_to_species: dict[str, Optional[int]] = {}
        self._stats_lock = threading.Lock()
        self._agreements = 0
        self._mismatches = 0
        self._unverified = 0
        self._last_mismatch: Optional[dict[str, Any]] = None

    def _resolved_path(self) -> Path:
        return Path(self._path or default_catalog_path())

    def _ensure_loaded(self) -> bool:
        try:
            stat = self._resolved_path().stat()
            cache_key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return False

        with self._lock:
            if cache_key == self._cache_key:
                return True
            try:
                self._load()
            except sqlite3.Error as error:
                log.warning("Species catalogue unreadable for resolution", error=str(error))
                return False
            self._cache_key = cache_key
            return True

    def _load(self) -> None:
        connection = sqlite3.connect(f"file:{self._resolved_path()}?mode=ro", uri=True)
        try:
            artifact_ids: dict[str, int] = {}
            artifact_sha_by_id: dict[int, str] = {}
            for row_id, model_sha256 in connection.execute("SELECT id, model_sha256 FROM model_artifacts"):
                artifact_ids[str(model_sha256)] = int(row_id)
                artifact_sha_by_id[int(row_id)] = str(model_sha256)

            outputs: dict[str, dict[int, _OutputEntry]] = {sha: {} for sha in artifact_ids}
            for artifact_row_id, output_index, class_kind, species_id in connection.execute(
                "SELECT model_artifact_id, output_index, class_kind, species_id FROM model_output_taxa"
            ):
                sha = artifact_sha_by_id.get(int(artifact_row_id))
                if sha is None:
                    continue
                outputs[sha][int(output_index)] = _OutputEntry(
                    artifact_row_id=int(artifact_row_id),
                    class_kind=str(class_kind),
                    species_id=int(species_id) if species_id is not None else None,
                )

            accepted: dict[int, set[str]] = {}
            for species_id, scientific in connection.execute(
                "SELECT species_id, scientific_name FROM species_concepts"
            ):
                accepted.setdefault(int(species_id), set()).add(str(scientific).casefold())
            for species_id, alias in connection.execute(
                "SELECT species_id, alias FROM species_aliases WHERE resolution = 'resolved' AND species_id IS NOT NULL"
            ):
                accepted.setdefault(int(species_id), set()).add(str(alias).casefold())
        finally:
            connection.close()

        name_to_species: dict[str, Optional[int]] = {}
        for species_id, names in accepted.items():
            for name in names:
                if name not in name_to_species:
                    name_to_species[name] = species_id
                elif name_to_species[name] != species_id:
                    name_to_species[name] = None

        self._artifact_ids = artifact_ids
        self._outputs = outputs
        self._accepted_names = accepted
        self._name_to_species = name_to_species

    def shadow_resolve(
        self,
        model_sha256: Optional[str],
        output_index: int,
        label_scientific_name: Optional[str],
        event_id: Optional[str] = None,
    ) -> ShadowResolution:
        checksum = str(model_sha256 or "").strip().lower()
        if not checksum or not isinstance(output_index, int) or output_index < 0:
            return ShadowResolution(verdict="unavailable")
        if not self._ensure_loaded():
            return ShadowResolution(verdict="unavailable")

        artifact_row_id = self._artifact_ids.get(checksum)
        if artifact_row_id is None:
            return ShadowResolution(verdict="unregistered")

        entry = self._outputs.get(checksum, {}).get(output_index)
        if entry is None:
            return ShadowResolution(
                verdict="unresolved_index",
                model_artifact_id=artifact_row_id,
                model_output_index=output_index,
            )

        if entry.class_kind != "species" or entry.species_id is None:
            return ShadowResolution(
                verdict="non_species",
                model_artifact_id=entry.artifact_row_id,
                model_output_index=output_index,
            )

        label = str(label_scientific_name or "").strip()
        if not label:
            with self._stats_lock:
                self._unverified += 1
            return ShadowResolution(
                verdict="unverified",
                model_artifact_id=entry.artifact_row_id,
                model_output_index=output_index,
            )

        if label.casefold() in self._accepted_names.get(entry.species_id, set()):
            with self._stats_lock:
                self._agreements += 1
            return ShadowResolution(
                verdict="agree",
                species_id=entry.species_id,
                model_artifact_id=entry.artifact_row_id,
                model_output_index=output_index,
            )

        with self._stats_lock:
            self._mismatches += 1
            self._last_mismatch = {
                "event_id": event_id,
                "label_scientific": label,
                "catalog_species_id": entry.species_id,
                "output_index": output_index,
            }
        log.warning(
            "Catalogue and label path disagree on species identity; identity withheld",
            event_id=event_id,
            label_scientific=label,
            catalog_species_id=entry.species_id,
            output_index=output_index,
        )
        return ShadowResolution(
            verdict="mismatch",
            model_artifact_id=entry.artifact_row_id,
            model_output_index=output_index,
        )

    def resolve_scientific_name(self, scientific_name: Optional[str]) -> tuple[Optional[int], str]:
        """Resolve a bare scientific name to one catalogue identity, or say why not.

        Returns `(species_id, "resolved")`, `(None, "ambiguous")` when the
        catalogue holds the name for more than one species, `(None, "unknown")`
        when no source holds it, or `(None, "unavailable")` without a
        catalogue. Used by the historical backfill, which never guesses.
        """
        name = str(scientific_name or "").strip()
        if not name:
            return None, "unknown"
        if not self._ensure_loaded():
            return None, "unavailable"
        key = name.casefold()
        if key not in self._name_to_species:
            return None, "unknown"
        species_id = self._name_to_species[key]
        if species_id is None:
            return None, "ambiguous"
        return species_id, "resolved"

    def stats(self) -> dict[str, Any]:
        with self._stats_lock:
            return {
                "agreements": self._agreements,
                "mismatches": self._mismatches,
                "unverified": self._unverified,
                "last_mismatch": dict(self._last_mismatch) if self._last_mismatch else None,
            }


species_catalog_resolver = SpeciesCatalogResolver()
