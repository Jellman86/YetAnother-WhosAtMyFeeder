"""Bind a model's output index to a taxon.

Every iNaturalist-derived model already carries the scientific name in its own
label, so this mapping is derivable from the model's own file with no external
source and no licence question. That takes the flagship model from the 57.9% a
redistributable name list can cover to every one of its 10,000 outputs.

It is built once from the label file at install, in the same step that verifies
`labels_sha256`, rather than read from that file on every detection. A label file
altered after download can then no longer put wrong species into history.

Keyed on the label file's digest rather than a model name: a republished model
with corrected labels is a different artifact and gets its own mapping.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional, Sequence

import structlog

log = structlog.get_logger()

#: `04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus`
_HIERARCHY = re.compile(r"^\d+(?:_[A-Za-z\-]+)+$")
#: `Haemorhous cassinii (Cassin's Finch)`
_PAIRED = re.compile(r"^\s*(?P<scientific>[^()]+?)\s*\((?P<common>.+)\)\s*$")
#: `Genus species`. This shape cannot separate `Cyanistes caeruleus` from
#: `African crake`, so it is honoured only when the caller states that the label
#: file holds scientific names. Tested against the real label files, a word-list
#: of adjectives claimed 198 common names as scientific, and a statistical
#: discriminator separated the files by only a factor of two. Neither is worth
#: shipping when the alternative is to say so and resolve by lookup instead.
_BINOMIAL = re.compile(r"^(?P<genus>[A-Z][a-z]+)\s+(?P<epithet>[a-z][a-z-]+)$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_taxon_map (
    model_key       TEXT NOT NULL,
    output_index    INTEGER NOT NULL,
    scientific_name TEXT NOT NULL,
    source_label    TEXT NOT NULL,
    PRIMARY KEY (model_key, output_index)
);
CREATE TABLE IF NOT EXISTS model_taxon_coverage (
    model_key TEXT PRIMARY KEY,
    labels    INTEGER NOT NULL,
    mapped    INTEGER NOT NULL
);
"""


def scientific_name_from_label(label: Optional[str], *, assume_scientific: bool = False) -> Optional[str]:
    """Read the scientific name out of a model label, or None if it carries none.

    Only the two formats that *guarantee* a scientific name are read without
    being told: the iNaturalist hierarchy, whose last two parts are the genus and
    species, and the paired form, whose left half is the scientific name by
    construction. A bare `Genus species` is indistinguishable from a common name
    of the same shape, so it is read only when `assume_scientific` says the file
    holds scientific names.

    None is the honest answer everywhere else, and the caller resolves that label
    against a taxonomy instead of guessing at it.
    """
    if not isinstance(label, str):
        return None
    text = label.strip()
    if not text:
        return None

    if _HIERARCHY.match(text):
        parts = text.split("_")
        if len(parts) < 3:
            return None
        genus, species = parts[-2], parts[-1]
        if not genus or not species:
            return None
        return f"{genus[:1].upper()}{genus[1:]} {species.lower()}"

    paired = _PAIRED.match(text)
    if paired:
        scientific = paired.group("scientific").strip()
        return scientific or None

    if assume_scientific:
        binomial = _BINOMIAL.match(text)
        if binomial:
            return f"{binomial.group('genus')} {binomial.group('epithet')}"
    return None


def default_map_path() -> Path:
    configured = os.environ.get("DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve().parent / "model_taxon_map.db"
    return Path("/data/model_taxon_map.db")


class ModelTaxonMap:
    """Output index to taxon, per model artifact. Never raises into naming."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_map_path()
        self._connection: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._access = threading.Lock()
        self._disabled = False

    def _parent_is_writable(self) -> bool:
        parent = self._path.parent
        return parent.is_dir() and os.access(parent, os.W_OK | os.X_OK)

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
            if not self._path.exists() and not self._parent_is_writable():
                log.info("Model taxon map unavailable; naming will use label text", path=str(self._path))
                self._disabled = True
                return None
            try:
                connection = sqlite3.connect(self._path, check_same_thread=False)
                connection.row_factory = sqlite3.Row
                connection.executescript(SCHEMA)
                connection.commit()
            except sqlite3.Error as error:
                log.warning("Model taxon map unusable; naming will use label text", error=str(error))
                self._disabled = True
                return None
            self._connection = connection
            return connection

    def build(
        self,
        model_key: str,
        labels: Sequence[str] | Iterable[str],
        *,
        assume_scientific: bool = False,
    ) -> int:
        """Derive and store the mapping for one model artifact.

        The index is the label's position in the file, including labels that
        yield no scientific name, so a gap never shifts everything after it.
        """
        key = str(model_key or "").strip()
        if not key:
            return 0
        connection = self._connect()
        if connection is None:
            return 0

        ordered = list(labels)
        rows = []
        for index, label in enumerate(ordered):
            scientific = scientific_name_from_label(label, assume_scientific=assume_scientific)
            if scientific:
                rows.append((key, index, scientific, str(label).strip()))

        try:
            with self._access:
                connection.execute("DELETE FROM model_taxon_map WHERE model_key = ?", (key,))
                connection.executemany(
                    "INSERT INTO model_taxon_map (model_key, output_index, scientific_name, source_label)"
                    " VALUES (?, ?, ?, ?)",
                    rows,
                )
                connection.execute(
                    "INSERT INTO model_taxon_coverage (model_key, labels, mapped) VALUES (?, ?, ?)"
                    " ON CONFLICT (model_key) DO UPDATE SET labels = excluded.labels, mapped = excluded.mapped",
                    (key, len(ordered), len(rows)),
                )
                connection.commit()
        except sqlite3.Error as error:
            log.warning("Could not store model taxon map", model_key=key, error=str(error))
            return 0

        log.info("Model taxon map built", model_key=key, labels=len(ordered), mapped=len(rows))
        return len(rows)

    def lookup(self, model_key: str, output_index: int) -> Optional[str]:
        key = str(model_key or "").strip()
        if not key or not isinstance(output_index, int) or output_index < 0:
            return None
        connection = self._connect()
        if connection is None:
            return None
        try:
            with self._access:
                row = connection.execute(
                    "SELECT scientific_name FROM model_taxon_map WHERE model_key = ? AND output_index = ?",
                    (key, output_index),
                ).fetchone()
        except sqlite3.Error as error:
            log.warning("Model taxon map lookup failed", error=str(error))
            return None
        return row["scientific_name"] if row else None

    def has(self, model_key: str) -> bool:
        return self.coverage(model_key)["labels"] > 0

    def coverage(self, model_key: str) -> dict[str, object]:
        key = str(model_key or "").strip()
        connection = self._connect()
        if connection is None or not key:
            return {"labels": 0, "mapped": 0, "complete": False}
        try:
            with self._access:
                row = connection.execute(
                    "SELECT labels, mapped FROM model_taxon_coverage WHERE model_key = ?", (key,)
                ).fetchone()
        except sqlite3.Error:
            return {"labels": 0, "mapped": 0, "complete": False}
        if not row:
            return {"labels": 0, "mapped": 0, "complete": False}
        labels = int(row["labels"])
        mapped = int(row["mapped"])
        return {"labels": labels, "mapped": mapped, "complete": labels > 0 and mapped == labels}


model_taxon_map = ModelTaxonMap()
