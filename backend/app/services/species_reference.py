"""Local species names, without a network round trip.

A bundled read-only SQLite file maps the label formats our models emit to a
scientific name and an English common name. It sits between the taxonomy cache
and iNaturalist: a hit costs one indexed local read, a miss is silent so the
caller falls through unchanged.

Coverage is partial on purpose. The source is the Google Coral MobileNet bird
labels, which are Apache-2.0 and therefore redistributable; the iNaturalist
export is not. Measured against `rope_vit_b14_inat21`, this covers 860 of the
1,486 birds that model emits, with eBird and iNaturalist filling the rest at
runtime. See docs/plans/2026-08-19-species-reference-source-decision.md.

Nothing here writes. A reference hit is deliberately not persisted into
`taxonomy_cache`: the reference carries no iNaturalist taxon id, and caching a
row without one would stop enrichment ever resolving it.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

import structlog

from app.utils.classifier_labels import normalize_classifier_label

log = structlog.get_logger()

DEFAULT_REFERENCE_PATH = Path(__file__).resolve().parent.parent / "assets" / "species_reference.db"


def _parenthetical_halves(value: str) -> tuple[Optional[str], Optional[str]]:
    """Split `Scientific name (Common Name)` into its two halves."""
    if "(" not in value or not value.rstrip().endswith(")"):
        return None, None
    head, _, tail = value.partition("(")
    left = head.strip() or None
    right = tail.rsplit(")", 1)[0].strip() or None
    return left, right


class SpeciesReference:
    """Read-only access to the bundled reference.

    Opened lazily and kept open. If the file is absent or unreadable the layer
    disables itself: naming must degrade to the network path, never fail.
    """

    def __init__(self, path: Path = DEFAULT_REFERENCE_PATH) -> None:
        self._path = path
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._disabled = False

    @property
    def available(self) -> bool:
        return self._connect() is not None

    def _connect(self) -> Optional[sqlite3.Connection]:
        if self._disabled:
            return None
        if self._connection is not None:
            return self._connection
        with self._lock:
            if self._disabled:
                return None
            if self._connection is not None:
                return self._connection
            if not self._path.is_file():
                log.info("Species reference not bundled; naming will use the network", path=str(self._path))
                self._disabled = True
                return None
            try:
                connection = sqlite3.connect(f"file:{self._path}?mode=ro", uri=True, check_same_thread=False)
                connection.row_factory = sqlite3.Row
                # Prove the file is usable now rather than on the first lookup.
                connection.execute("SELECT 1 FROM taxon LIMIT 1").fetchone()
            except sqlite3.Error as error:
                log.warning("Species reference unreadable; naming will use the network", error=str(error))
                self._disabled = True
                return None
            self._connection = connection
            return connection

    def _candidates(self, query: str) -> list[str]:
        """Every form of the query worth matching, in order of preference."""
        candidates: list[str] = []

        def add(value: Optional[str]) -> None:
            if value:
                cleaned = value.strip()
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

        add(query)
        # `04815_Animalia_..._Genus_species` reduces to `Genus species`.
        add(normalize_classifier_label(query))
        left, right = _parenthetical_halves(query)
        add(left)
        add(right)
        return candidates

    def lookup(self, query_name: Optional[str]) -> Optional[dict[str, Any]]:
        """Resolve a model label to names, or None to fall through."""
        if not isinstance(query_name, str) or not query_name.strip():
            return None
        connection = self._connect()
        if connection is None:
            return None

        try:
            for candidate in self._candidates(query_name):
                row = connection.execute(
                    "SELECT scientific_name, common_name FROM taxon"
                    " WHERE scientific_name = ? COLLATE NOCASE"
                    " OR common_name = ? COLLATE NOCASE LIMIT 1",
                    (candidate, candidate),
                ).fetchone()
                if row:
                    return {
                        "scientific_name": row["scientific_name"],
                        "common_name": row["common_name"],
                        # The source carries no iNaturalist id, and inventing one
                        # would corrupt identity downstream.
                        "taxa_id": None,
                        "source": "species_reference",
                    }
        except sqlite3.Error as error:
            log.warning("Species reference lookup failed", error=str(error))
            return None
        return None

    def status(self) -> dict[str, Any]:
        connection = self._connect()
        if connection is None:
            return {"available": False, "taxon_count": 0, "schema_version": None, "source": None}
        try:
            meta = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM reference_meta").fetchall()
            }
        except sqlite3.Error:
            meta = {}
        try:
            count = int(meta.get("taxon_count", "0"))
        except (TypeError, ValueError):
            count = 0
        return {
            "available": True,
            "taxon_count": count,
            "schema_version": meta.get("schema_version"),
            "source": meta.get("source"),
        }


species_reference = SpeciesReference()
