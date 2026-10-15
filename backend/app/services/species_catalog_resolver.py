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

import re
from contextlib import closing
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional

import structlog

from app.services.species_catalog_migrations import default_catalog_path
from app.services.model_output_groups import OutputGroup
from app.services.model_taxon_map import scientific_name_from_label
from app.utils.classifier_labels import normalize_classifier_label

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
    source_label: Optional[str] = None
    taxonomic_group: OutputGroup = "unknown"


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
        self._group_snapshot: Mapping[str, Mapping[int, _OutputEntry]] = MappingProxyType({})

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
            widths = {}
            for row_id, model_sha256, width in connection.execute(
                "SELECT id, model_sha256, output_width FROM model_artifacts"
            ):
                artifact_ids[str(model_sha256)] = int(row_id)
                artifact_sha_by_id[int(row_id)] = str(model_sha256)
                widths[str(model_sha256)] = int(width)

            outputs: dict[str, dict[int, _OutputEntry]] = {sha: {} for sha in artifact_ids}
            columns = {row[1] for row in connection.execute("PRAGMA table_info(model_output_taxa)")}
            group_column = "taxonomic_group" if "taxonomic_group" in columns else "'unknown'"
            for artifact_row_id, output_index, class_kind, species_id, source_label, group in connection.execute(
                "SELECT model_artifact_id, output_index, class_kind, species_id, source_label, "
                + group_column
                + " FROM model_output_taxa"
            ):
                sha = artifact_sha_by_id.get(int(artifact_row_id))
                if sha is None:
                    continue
                outputs[sha][int(output_index)] = _OutputEntry(
                    artifact_row_id=int(artifact_row_id),
                    class_kind=str(class_kind),
                    species_id=int(species_id) if species_id is not None else None,
                    source_label=str(source_label) if source_label is not None else None,
                    taxonomic_group=group if group in {"bird", "nonbird", "unknown"} else "unknown",
                )

            accepted: dict[int, set[str]] = {}
            # Species only. The genera, families and orders above them are catalogue taxa too, but a
            # name resolving to one of those would be a new kind of identity for history rows; that
            # change is made deliberately, not as a side effect of adding a classification.
            for species_id, scientific in connection.execute(
                "SELECT c.species_id, c.scientific_name FROM species_concepts c"
                " JOIN species s ON s.species_id = c.species_id WHERE s.rank = 'species'"
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
        self._group_snapshot = MappingProxyType(
            {
                sha: MappingProxyType(
                    {
                        index: entry
                        for index, entry in entries.items()
                        if 0 <= index < widths[sha] and entry.taxonomic_group != "unknown"
                    }
                )
                for sha, entries in outputs.items()
            }
        )

    def invalidate_output_groups(self) -> None:
        """Discard cached admission evidence after an app-owned catalogue write."""
        with self._lock:
            self._group_snapshot = MappingProxyType({})
            self._cache_key = None

    def warm_output_groups(self) -> bool:
        """Publish a complete fresh snapshot; callers run this off the event loop."""
        self.invalidate_output_groups()
        with self._lock:
            try:
                stat = self._resolved_path().stat()
                self._load()
                self._cache_key = (stat.st_mtime_ns, stat.st_size)
                return True
            except (OSError, ValueError, sqlite3.Error) as error:
                log.warning("Catalogue output groups unavailable", error_type=type(error).__name__)
                return False

    def refresh_output_groups_for(self, path: Path) -> bool:
        """Refresh only the singleton's own catalogue after a committed write."""
        if Path(path).absolute() != self._resolved_path().absolute():
            return False
        return self.warm_output_groups()

    @staticmethod
    def _group_request(model_sha256: Optional[str], output_index: int, label: str) -> tuple[str, str] | None:
        if (
            not isinstance(model_sha256, str)
            or not re.fullmatch(r"[a-f0-9]{64}", model_sha256.strip().lower())
            or type(output_index) is not int
            or output_index < 0
            or not isinstance(label, str)
            or not label.strip()
        ):
            return None
        return model_sha256.strip().lower(), label.strip().casefold()

    @staticmethod
    def _bound_group(source_label: str | None, group: str, label: str) -> OutputGroup:
        if group not in {"bird", "nonbird"} or not isinstance(source_label, str) or not source_label.strip():
            return "unknown"
        expected = {source_label.strip().casefold(), normalize_classifier_label(source_label).casefold()}
        if scientific := scientific_name_from_label(source_label):
            expected.add(scientific.casefold())
        return group if label in expected else "unknown"

    def cached_output_group(self, model_sha256: Optional[str], output_index: int, label: str) -> OutputGroup:
        """Pure lookup for synchronous classification selection, with no I/O."""
        request = self._group_request(model_sha256, output_index, label)
        if request is None:
            return "unknown"
        checksum, normalized_label = request
        entry = self._group_snapshot.get(checksum, {}).get(output_index)
        return self._bound_group(entry.source_label, entry.taxonomic_group, normalized_label) if entry else "unknown"

    def fresh_output_group(self, model_sha256: Optional[str], output_index: int, label: str) -> OutputGroup:
        """Recheck durable evidence immediately before writes, without the cache."""
        request = self._group_request(model_sha256, output_index, label)
        if request is None:
            return "unknown"
        checksum, normalized_label = request
        try:
            with closing(sqlite3.connect(f"file:{self._resolved_path()}?mode=ro", uri=True)) as connection:
                row = connection.execute(
                    "SELECT t.source_label,t.taxonomic_group FROM model_output_taxa t "
                    "JOIN model_artifacts a ON a.id=t.model_artifact_id "
                    "WHERE a.model_sha256=? AND t.output_index=? AND t.output_index<a.output_width",
                    (checksum, output_index),
                ).fetchone()
            return self._bound_group(row[0], row[1], normalized_label) if row else "unknown"
        except (OSError, sqlite3.Error):
            return "unknown"

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
        # An index the catalogue cannot identify now carries a row holding the
        # model's own label, so the label text does not depend on `labels.txt`.
        # That row says `unknown`, which means exactly what an absent row meant:
        # nothing here knows what this output is. Reporting it as `non_species`
        # would claim knowledge that it is not a species, which is a different
        # and unearned statement.
        if entry is None or entry.class_kind == "unknown":
            return ShadowResolution(
                verdict="unresolved_index",
                model_artifact_id=(entry.artifact_row_id if entry is not None else artifact_row_id),
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

    def species_outputs(self, model_sha256: Optional[str]) -> Optional[dict[int, int]]:
        """Every output of a registered model that names a species, as `{output_index: species_id}`.

        This is the set of birds the model can name at all. Returns None when the
        catalogue is missing or the model is not registered, so a caller can tell
        "names none of these" apart from "not known".
        """
        checksum = str(model_sha256 or "").strip().lower()
        if not checksum or not self._ensure_loaded() or checksum not in self._artifact_ids:
            return None
        return {
            output_index: entry.species_id
            for output_index, entry in self._outputs.get(checksum, {}).items()
            if entry.class_kind == "species" and entry.species_id is not None
        }

    def unresolved_output_labels(self, model_sha256: Optional[str]) -> Optional[tuple[str, ...]]:
        """The model's own labels for outputs the catalogue cannot identify, or None for an unknown model.

        Such an output may still be a bird the catalogue knows under another name (the European
        models' "Feral pigeon" is the Rock Pigeon), so ``species_outputs`` alone does not prove a
        model cannot name a species.
        """
        checksum = str(model_sha256 or "").strip().lower()
        if not checksum or not self._ensure_loaded() or checksum not in self._artifact_ids:
            return None
        return tuple(
            entry.source_label
            for _index, entry in sorted(self._outputs.get(checksum, {}).items())
            if entry.class_kind == "unknown" and entry.source_label
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
