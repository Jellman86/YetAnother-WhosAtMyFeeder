"""Local species names, without a network round trip.

A bundled read-only SQLite file maps the label formats our models emit to a
scientific name and an English common name. It sits between the taxonomy cache
and iNaturalist: a hit costs one indexed local read, a miss is silent so the
caller falls through unchanged.

The source is the IOC World Bird List, licensed CC BY 3.0 and therefore
redistributable, carrying 11,276 species with one curated name per language.
That covers 95.2% of the birds the flagship model can emit and eight languages
besides English, so naming works with no API key and no network at all.

Nothing here writes. A reference hit is deliberately not persisted into
`taxonomy_cache`: the reference carries no iNaturalist taxon id, and caching a
row without one would stop enrichment ever resolving it.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

import structlog

from app.utils.classifier_labels import normalize_classifier_label

log = structlog.get_logger()

DEFAULT_REFERENCE_PATH = Path(__file__).resolve().parent.parent / "assets" / "species_reference.db"

#: Read in 1MB chunks so verification never holds the whole file in memory.
_DIGEST_CHUNK_BYTES = 1024 * 1024


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
        # sqlite3 connections are not safe for concurrent use, and this one is
        # shared by every caller resolving a name.
        self._access = threading.Lock()
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
            if not self._verify_digest():
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

    def _verify_digest(self) -> bool:
        """Check the file against the digest recorded beside it, when there is one.

        A shipped asset that no longer matches what was generated is refused
        rather than trusted: a silently altered reference would write wrong
        species names into detection history, which is worse than no names at
        all. A locally regenerated file has no sidecar, and that is not a
        corruption signal.
        """
        sidecar = self._path.with_suffix(self._path.suffix + ".sha256")
        if not sidecar.is_file():
            return True
        try:
            expected = sidecar.read_text(encoding="utf-8").split()[0].strip().lower()
        except (OSError, IndexError):
            log.warning("Species reference digest unreadable; using the file as found", path=str(sidecar))
            return True
        if len(expected) != 64:
            log.warning("Species reference digest malformed; using the file as found", path=str(sidecar))
            return True

        digest = hashlib.sha256()
        try:
            with open(self._path, "rb") as handle:
                for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
                    digest.update(chunk)
        except OSError as error:
            log.warning("Species reference unreadable; naming will use the network", error=str(error))
            return False

        actual = digest.hexdigest()
        if actual != expected:
            log.error(
                "Species reference does not match its recorded digest; refusing it",
                path=str(self._path),
                expected=expected,
                actual=actual,
            )
            return False
        return True

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

    def localized_name(self, scientific_name: Optional[str], locale: Optional[str]) -> Optional[str]:
        """The bundled name for a species in a language, if the list carries one."""
        scientific = str(scientific_name or "").strip()
        language = str(locale or "").strip().split("-")[0].split("_")[0].lower()
        if not scientific or not language or language == "en":
            return None
        connection = self._connect()
        if connection is None:
            return None
        try:
            with self._access:
                row = connection.execute(
                    "SELECT n.common_name FROM taxon_name n"
                    " JOIN taxon t ON t.id = n.taxon_id"
                    " WHERE t.scientific_name = ? COLLATE NOCASE AND n.locale = ? LIMIT 1",
                    (scientific, language),
                ).fetchone()
        except sqlite3.Error as error:
            log.warning("Species reference localized lookup failed", error=str(error))
            return None
        return row["common_name"] if row else None

    def lookup(self, query_name: Optional[str], locale: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Resolve a model label to names, or None to fall through.

        A locale returns the bundled name in that language when the list has one,
        so an offline install names the bird in the owner's language rather than
        only in English.
        """
        if not isinstance(query_name, str) or not query_name.strip():
            return None
        connection = self._connect()
        if connection is None:
            return None

        try:
            for candidate in self._candidates(query_name):
                with self._access:
                    row = connection.execute(
                        "SELECT scientific_name, common_name FROM taxon"
                        " WHERE scientific_name = ? COLLATE NOCASE"
                        " OR common_name = ? COLLATE NOCASE LIMIT 1",
                        (candidate, candidate),
                    ).fetchone()
                if row:
                    localized = self.localized_name(row["scientific_name"], locale) if locale else None
                    return {
                        "scientific_name": row["scientific_name"],
                        "common_name": localized or row["common_name"],
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
            with self._access:
                meta = {
                    row["key"]: row["value"]
                    for row in connection.execute("SELECT key, value FROM reference_meta").fetchall()
                }
        except sqlite3.Error:
            meta = {}

        def number(key: str) -> int:
            try:
                return int(meta.get(key, "0"))
            except (TypeError, ValueError):
                return 0

        return {
            "available": True,
            "taxon_count": number("taxon_count"),
            "localized_name_count": number("localized_name_count"),
            "schema_version": meta.get("schema_version"),
            "source": meta.get("source"),
            "source_licence": meta.get("source_licence"),
        }


species_reference = SpeciesReference()
