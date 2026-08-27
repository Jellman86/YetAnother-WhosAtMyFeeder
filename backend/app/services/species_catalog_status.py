"""Report the species catalogue's state, coverage, and activation readiness.

Phase 2 diagnostics for the versioned species catalogue: which release is
active, how many species it holds, and how far each registered model
artifact's outputs are mapped. `activation_check` resolves a model checksum
directly against SQLite and verifies the output tensor width — the machinery
that gates model selection once label-file authority is retired before 3.0.
Until then its verdicts are advisory: they are reported on the Health surface
rather than enforced, because several supported artifacts still carry
honestly-unresolved output classes.

Read-only and fail-soft, like the other naming-layer services: a missing or
unreadable catalogue reports itself as unavailable and never raises into a
health check.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

import structlog

from app.services.species_catalog_migrations import default_catalog_path

log = structlog.get_logger()


def _manifest_sources(source_manifest: object) -> list[dict[str, Any]]:
    """Pinned sources from a release's manifest, defensively.

    Carries the citation and licence as well as the version, because the
    catalogue redistributes work under CC BY terms and an owner cannot
    attribute what they are never shown. Every field is optional: the column
    is free text copied from bundles, and anything that is not the expected
    object shape yields an empty list rather than an exception on the health
    path.
    """
    try:
        payload = json.loads(str(source_manifest or ""))
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return []
    return [
        {
            "id": source.get("id"),
            "version": source.get("version"),
            "licence": source.get("licence"),
            "citation": source.get("citation"),
            "url": source.get("url"),
        }
        for source in sources
        if isinstance(source, dict)
    ]


_UNAVAILABLE_STATUS: dict[str, Any] = {
    "available": False,
    "species_count": 0,
    "active_release": None,
    "artifacts": [],
}


class SpeciesCatalogStatus:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path
        # The status answer changes only when a release is imported or the
        # file is replaced, while the health surface polls it every few
        # seconds; cache it keyed on the file's identity so a poll costs one
        # stat() rather than a connection and COUNT scans.
        self._lock = threading.Lock()
        self._cache_key: Optional[tuple[int, int]] = None
        self._cache_value: Optional[dict[str, Any]] = None

    def _resolved_path(self) -> Path:
        return Path(self._path or default_catalog_path())

    def _connect(self) -> Optional[sqlite3.Connection]:
        path = self._resolved_path()
        if not path.is_file():
            return None
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("SELECT 1 FROM catalogue_releases LIMIT 1").fetchone()
        except sqlite3.Error as error:
            log.warning("Species catalogue unreadable for status", path=str(path), error=str(error))
            return None
        return connection

    def status(self) -> dict[str, Any]:
        """The catalogue's active release, size, and per-artifact coverage.

        Cached on the file's (mtime, size): a poll pays one stat() until an
        import or replacement changes the file.
        """
        try:
            stat = self._resolved_path().stat()
            cache_key = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return dict(_UNAVAILABLE_STATUS)

        with self._lock:
            if cache_key == self._cache_key and self._cache_value is not None:
                return dict(self._cache_value)
            value = self._compute_status()
            self._cache_key = cache_key
            self._cache_value = value
            return dict(value)

    def _compute_status(self) -> dict[str, Any]:
        connection = self._connect()
        if connection is None:
            return dict(_UNAVAILABLE_STATUS)
        try:
            release_row = connection.execute(
                "SELECT source_manifest, generated_at FROM catalogue_releases WHERE state = 'active'"
            ).fetchone()
            active_release: Optional[dict[str, Any]] = None
            if release_row:
                active_release = {
                    "generated_at": release_row["generated_at"],
                    "sources": _manifest_sources(release_row["source_manifest"]),
                }

            species_count = connection.execute("SELECT COUNT(*) FROM species").fetchone()[0]

            artifacts: list[dict[str, Any]] = []
            for row in connection.execute(
                # Counts identified outputs, not rows. Every output index now
                # has a row, including ones nothing could resolve, so counting
                # rows would report a model as fully mapped while hundreds of
                # its outputs still had no identity.
                "SELECT a.registry_id, a.model_sha256, a.output_width,"
                " (SELECT COUNT(*) FROM model_output_taxa t"
                "  WHERE t.model_artifact_id = a.id AND t.class_kind != 'unknown') AS mapped"
                " FROM model_artifacts a ORDER BY a.registry_id"
            ):
                unresolved = int(row["output_width"]) - int(row["mapped"])
                artifacts.append(
                    {
                        "registry_id": row["registry_id"],
                        "model_sha256": row["model_sha256"],
                        "output_width": int(row["output_width"]),
                        "mapped_outputs": int(row["mapped"]),
                        "unresolved_outputs": unresolved,
                        "complete": unresolved == 0,
                    }
                )

            return {
                "available": True,
                "species_count": int(species_count),
                "active_release": active_release,
                "artifacts": artifacts,
            }
        except sqlite3.Error as error:
            log.warning("Species catalogue status query failed", error=str(error))
            return dict(_UNAVAILABLE_STATUS)
        finally:
            connection.close()

    def activation_check(self, model_sha256: str, tensor_width: Optional[int] = None) -> dict[str, Any]:
        """Resolve a model checksum against the catalogue mapping.

        Verdicts: `ready` (registered, complete, width matches when given),
        `incomplete_mapping`, `width_mismatch`, `unregistered`, `unavailable`.
        """
        checksum = str(model_sha256 or "").strip().lower()
        connection = self._connect()
        if connection is None:
            return {"verdict": "unavailable", "model_sha256": checksum}
        try:
            row = connection.execute(
                "SELECT a.id, a.registry_id, a.output_width, a.mapping_set_sha256,"
                " (SELECT COUNT(*) FROM model_output_taxa t"
                "  WHERE t.model_artifact_id = a.id AND t.class_kind != 'unknown') AS mapped"
                " FROM model_artifacts a WHERE a.model_sha256 = ?",
                (checksum,),
            ).fetchone()
        except sqlite3.Error as error:
            log.warning("Species catalogue activation check failed", error=str(error))
            return {"verdict": "unavailable", "model_sha256": checksum}
        finally:
            connection.close()

        if row is None:
            return {"verdict": "unregistered", "model_sha256": checksum}

        result: dict[str, Any] = {
            "model_sha256": checksum,
            "registry_id": row["registry_id"],
            "output_width": int(row["output_width"]),
            "mapped_outputs": int(row["mapped"]),
            # Same rule as the artifact listing: an `unknown` output is not
            # mapped, whether it is present as a row or absent entirely.
            "unresolved_outputs": int(row["output_width"]) - int(row["mapped"]),
            "mapping_set_sha256": row["mapping_set_sha256"],
        }
        if tensor_width is not None and int(tensor_width) != int(row["output_width"]):
            result["verdict"] = "width_mismatch"
            result["tensor_width"] = int(tensor_width)
        elif result["unresolved_outputs"] > 0:
            result["verdict"] = "incomplete_mapping"
        else:
            result["verdict"] = "ready"
        return result


species_catalog_status = SpeciesCatalogStatus()
