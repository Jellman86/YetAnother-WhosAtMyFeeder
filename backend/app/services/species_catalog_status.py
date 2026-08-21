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
from pathlib import Path
from typing import Any, Optional

import structlog

from app.services.species_catalog_migrations import default_catalog_path

log = structlog.get_logger()


class SpeciesCatalogStatus:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path

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
        """The catalogue's active release, size, and per-artifact coverage."""
        connection = self._connect()
        if connection is None:
            return {"available": False, "species_count": 0, "active_release": None, "artifacts": []}
        try:
            release_row = connection.execute(
                "SELECT source_manifest, generated_at FROM catalogue_releases WHERE state = 'active'"
            ).fetchone()
            active_release: Optional[dict[str, Any]] = None
            if release_row:
                try:
                    sources = json.loads(release_row["source_manifest"]).get("sources") or []
                except ValueError:
                    sources = []
                active_release = {
                    "generated_at": release_row["generated_at"],
                    "sources": [{"id": source.get("id"), "version": source.get("version")} for source in sources],
                }

            species_count = connection.execute("SELECT COUNT(*) FROM species").fetchone()[0]

            artifacts: list[dict[str, Any]] = []
            for row in connection.execute(
                "SELECT a.registry_id, a.model_sha256, a.output_width,"
                " (SELECT COUNT(*) FROM model_output_taxa t WHERE t.model_artifact_id = a.id) AS mapped"
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
            return {"available": False, "species_count": 0, "active_release": None, "artifacts": []}
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
                " (SELECT COUNT(*) FROM model_output_taxa t WHERE t.model_artifact_id = a.id) AS mapped"
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
