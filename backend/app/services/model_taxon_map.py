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
#: `African crake`, so it is honoured only when the artifact declares that its
#: label file holds scientific names. Tested against the real label files, a
#: word-list of adjectives claimed 198 common names as scientific, and a
#: statistical discriminator separated the files by only a factor of two.
#: Neither is worth shipping when the alternative is to say so and resolve by
#: lookup instead.
_BINOMIAL = re.compile(r"^(?P<genus>[A-Z][a-z]+)\s+(?P<epithet>[a-z][a-z-]+)$")

#: Every label grammar an artifact may declare. The registry declares one per
#: artifact; the shape of a line is never trusted to reveal it. The NABirds
#: files are the proof: `Lesser Goldfinch (Female/juvenile)` matches the paired
#: shape exactly, and reading it that way records a common name as a
#: scientific one.
LABEL_FORMATS = frozenset(
    {
        "scientific_hierarchy",
        "scientific_binomial",
        "scientific_paired_common",
        "common_name",
        "detector_classes",
    }
)

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


def scientific_name_from_label(label: Optional[str], *, label_format: Optional[str] = None) -> Optional[str]:
    """Read the scientific name out of a model label, or None if it carries none.

    The declared `label_format` decides how a line is read. Without a
    declaration (a model outside the registry) only two shapes are read: the
    iNaturalist hierarchy, which a common name cannot take, and the paired
    form when its left half is binomial-shaped. The bare paired shape alone
    proves nothing — the NABirds files showed `Lesser Goldfinch
    (Female/juvenile)` wearing it, and `Lesser Goldfinch` is not a scientific
    name — but `Haemorhous cassinii (Cassin's Finch)` announces itself by its
    lowercase epithet, and sideloaded Coral-style models rely on it.

    None is the honest answer everywhere else — including an unknown declared
    format, where guessing would defeat the declaration — and the caller
    resolves that label against a taxonomy instead.
    """
    if not isinstance(label, str):
        return None
    text = label.strip()
    if not text:
        return None

    if label_format is None:
        if _HIERARCHY.match(text):
            return _hierarchy_scientific(text)
        paired = _PAIRED.match(text)
        if paired:
            left = paired.group("scientific").strip()
            if _BINOMIAL.match(left):
                return left
        return None

    if label_format == "scientific_hierarchy":
        if _HIERARCHY.match(text):
            return _hierarchy_scientific(text)
        return None

    if label_format == "scientific_paired_common":
        paired = _PAIRED.match(text)
        if paired:
            return paired.group("scientific").strip() or None
        return None

    if label_format == "scientific_binomial":
        binomial = _BINOMIAL.match(text)
        if binomial:
            return f"{binomial.group('genus')} {binomial.group('epithet')}"
        return None

    return None


def _hierarchy_scientific(text: str) -> Optional[str]:
    parts = text.split("_")
    if len(parts) < 3:
        return None
    genus, species = parts[-2], parts[-1]
    if not genus or not species:
        return None
    return f"{genus[:1].upper()}{genus[1:]} {species.lower()}"


#: A trailing `(…)` qualifier: the common half of a paired label, or the
#: plumage note the NABirds files append to one.
_TRAILING_PARENTHETICAL = re.compile(r"\s*\([^()]*\)\s*$")
_APOSTROPHES = str.maketrans("", "", "'\u2019")
_HYPHENS = re.compile(r"[-\u2010-\u2015]")
# American spellings the bird models are trained on, against the British ones IOC
# publishes. Whole words only: `Grayling` is a fish, not a grey anything.
_SPELLINGS = (
    (re.compile(r"\bgray\b"), "grey"),
    (re.compile(r"\bgrayish\b"), "greyish"),
    (re.compile(r"\bmustached\b"), "moustached"),
    (re.compile(r"\bcolored\b"), "coloured"),
)


def paired_common_name(label: Optional[str]) -> Optional[str]:
    """The bracketed half of a paired label, or None when there is no pair.

    Says nothing about whether that half is a common name: `Cassin's Finch`
    and `Female/juvenile` both live there. The caller decides by looking the
    text up, never by its shape.
    """
    if not isinstance(label, str):
        return None
    paired = _PAIRED.match(label.strip())
    if not paired:
        return None
    return paired.group("common").strip() or None


def normalize_common_name(name: str) -> str:
    """Fold a common name to the form two sources can be compared in.

    Drops a trailing qualifier, apostrophes, and case, and collapses runs of
    whitespace, so `Cassin\u2019s Finch` and `Cassins finch` meet. A hyphen counts
    as a space and the American spelling of a colour counts as the British one, so
    `Western Screech-Owl` meets IOC's `Western Screech Owl` and `Gray Catbird` meets
    its `Grey Catbird`. Deliberately conservative: it never reorders or drops words,
    because `Great Grey Owl` and `Grey Great Owl` are not the same claim, and it
    folds spellings only as whole words, because `Grayling` is a fish.
    """
    stripped = _TRAILING_PARENTHETICAL.sub("", name)
    folded = _HYPHENS.sub(" ", stripped.translate(_APOSTROPHES).casefold())
    for pattern, replacement in _SPELLINGS:
        folded = pattern.sub(replacement, folded)
    return " ".join(folded.split())


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
        label_format: Optional[str] = None,
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
            scientific = scientific_name_from_label(label, label_format=label_format)
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

    def add(self, model_key: str, entries: Sequence[tuple[int, str]], *, source: str = "label") -> int:
        """Add mappings for indices that have none, leaving existing ones alone.

        The label file is the better authority, so a row it supplied is never
        replaced by one resolved from a common name.
        """
        key = str(model_key or "").strip()
        if not key:
            return 0
        connection = self._connect()
        if connection is None:
            return 0

        rows = [
            (key, int(index), str(scientific).strip(), source)
            for index, scientific in entries
            if isinstance(index, int) and index >= 0 and str(scientific or "").strip()
        ]
        if not rows:
            return 0

        try:
            with self._access:
                connection.executemany(
                    "INSERT INTO model_taxon_map (model_key, output_index, scientific_name, source_label)"
                    " VALUES (?, ?, ?, ?) ON CONFLICT (model_key, output_index) DO NOTHING",
                    rows,
                )
                connection.execute(
                    "UPDATE model_taxon_coverage SET mapped ="
                    " (SELECT COUNT(*) FROM model_taxon_map WHERE model_key = ?) WHERE model_key = ?",
                    (key, key),
                )
                connection.commit()
        except sqlite3.Error as error:
            log.warning("Could not extend model taxon map", model_key=key, error=str(error))
            return 0
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
