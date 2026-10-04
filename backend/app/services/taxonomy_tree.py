"""A taxon's place in the classification, read from the species catalogue.

Every catalogue taxon points at the next higher one, so a lineage is a walk up
`parent_species_id` and a branch is the taxa that point at one parent. Birds take
genus, family and order from IOC and the ranks above Aves from Catalogue of Life;
`source` on each taxon says which. It is a ranked classification as those sources
publish it, not an evolutionary tree: nothing here has dates or branch lengths,
and a taxon with no recorded parent is shown as the gap it is.

Never raises into a read path: an absent or unreadable catalogue yields nothing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from app.services.species_names import DEFAULT_LANGUAGE, normalize_language

log = structlog.get_logger()

#: The ranks a lineage normally shows. Intermediate ranks a source records (Catalogue of Life
#: puts subphylum, infraphylum, parvphylum and megaclass between Chordata and Aves) are kept and
#: returned, flagged so a view can collapse them.
PRINCIPAL_RANKS = ("kingdom", "phylum", "class", "order", "family", "genus", "species")

#: A guard against a cycle in the parent links: no real lineage is this deep.
_MAX_DEPTH = 40


@dataclass(frozen=True)
class Taxon:
    taxon_id: int
    rank: str
    scientific_name: str
    name: Optional[str]
    source: Optional[str]
    principal: bool
    parent_id: Optional[int] = None
    species_count: Optional[int] = None


class TaxonomyTree:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path

    def _connect(self) -> Optional[sqlite3.Connection]:
        path = self._path
        if path is None:
            from app.services.species_catalog_store import default_catalog_path

            path = default_catalog_path()
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as error:
            log.debug("Species catalogue unavailable for the taxonomy", error=str(error))
            return None
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _names(connection: sqlite3.Connection, ids: list[int], language: str) -> dict[int, str]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        found: dict[int, dict[str, str]] = {}
        for row in connection.execute(
            f"SELECT species_id, language_tag, name FROM species_names"
            f" WHERE species_id IN ({placeholders}) AND language_tag IN (?, ?)",
            [*ids, language, DEFAULT_LANGUAGE],
        ):
            found.setdefault(int(row["species_id"]), {})[str(row["language_tag"])] = str(row["name"])
        for row in connection.execute(
            f"SELECT species_id, language_tag, name FROM species_name_overrides WHERE species_id IN ({placeholders})",
            ids,
        ):
            tag = str(row["language_tag"] or "")
            if tag in ("", language):
                found.setdefault(int(row["species_id"]), {})["override"] = str(row["name"])
        return {
            taxon_id: names.get("override") or names.get(language) or names.get(DEFAULT_LANGUAGE)
            for taxon_id, names in found.items()
            if names.get("override") or names.get(language) or names.get(DEFAULT_LANGUAGE)
        }

    @staticmethod
    def _concepts(connection: sqlite3.Connection, ids: list[int]) -> dict[int, tuple[str, str]]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        concepts: dict[int, tuple[str, str]] = {}
        # IOC first where a taxon carries several concepts: it owns bird naming.
        for row in connection.execute(
            f"SELECT species_id, scientific_name, provider FROM species_concepts WHERE species_id IN ({placeholders})"
            " ORDER BY species_id, CASE provider WHEN 'ioc-world-bird-list' THEN 0 ELSE 1 END, provider",
            ids,
        ):
            concepts.setdefault(int(row["species_id"]), (str(row["scientific_name"]), str(row["provider"])))
        return concepts

    def lineage(self, taxon_id: int, *, language: Optional[str] = None) -> list[Taxon]:
        """The taxon and every taxon above it, from the root down. Empty when the catalogue lacks it."""
        connection = self._connect()
        if connection is None:
            return []
        tag = normalize_language(language)
        try:
            chain: list[sqlite3.Row] = []
            seen: set[int] = set()
            current: Optional[int] = int(taxon_id)
            while current is not None and current not in seen and len(chain) < _MAX_DEPTH:
                row = connection.execute(
                    "SELECT species_id, rank, parent_species_id FROM species WHERE species_id = ?", (current,)
                ).fetchone()
                if row is None:
                    break
                seen.add(current)
                chain.append(row)
                current = row["parent_species_id"]
            ids = [int(row["species_id"]) for row in chain]
            names = self._names(connection, ids, tag)
            concepts = self._concepts(connection, ids)
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return []
        finally:
            connection.close()
        return [
            Taxon(
                taxon_id=int(row["species_id"]),
                rank=str(row["rank"]),
                scientific_name=concepts.get(int(row["species_id"]), ("", ""))[0],
                name=names.get(int(row["species_id"])),
                source=concepts.get(int(row["species_id"]), ("", None))[1],
                principal=str(row["rank"]) in PRINCIPAL_RANKS,
                parent_id=row["parent_species_id"],
            )
            for row in reversed(chain)
        ]

    def children(self, taxon_id: int, *, language: Optional[str] = None, limit: int = 500) -> list[Taxon]:
        """The taxa directly beneath one, in the source's order, each with how many species it holds."""
        connection = self._connect()
        if connection is None:
            return []
        tag = normalize_language(language)
        try:
            rows = connection.execute(
                "SELECT species_id, rank, parent_species_id FROM species WHERE parent_species_id = ?"
                " ORDER BY sequence IS NULL, sequence, species_id LIMIT ?",
                (int(taxon_id), max(1, min(int(limit), 5000))),
            ).fetchall()
            ids = [int(row["species_id"]) for row in rows]
            counts: dict[int, int] = {}
            for child in ids:
                counts[child] = int(
                    connection.execute(
                        "WITH RECURSIVE below(id, rank, depth) AS ("
                        "  SELECT species_id, rank, 0 FROM species WHERE species_id = ?"
                        "  UNION ALL SELECT s.species_id, s.rank, below.depth + 1 FROM species s"
                        "  JOIN below ON s.parent_species_id = below.id WHERE below.depth < ?"
                        ") SELECT COUNT(*) FROM below WHERE rank = 'species'",
                        (child, _MAX_DEPTH),
                    ).fetchone()[0]
                )
            names = self._names(connection, ids, tag)
            concepts = self._concepts(connection, ids)
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return []
        finally:
            connection.close()
        return [
            Taxon(
                taxon_id=int(row["species_id"]),
                rank=str(row["rank"]),
                scientific_name=concepts.get(int(row["species_id"]), ("", ""))[0],
                name=names.get(int(row["species_id"])),
                source=concepts.get(int(row["species_id"]), ("", None))[1],
                principal=str(row["rank"]) in PRINCIPAL_RANKS,
                parent_id=row["parent_species_id"],
                species_count=counts.get(int(row["species_id"])),
            )
            for row in rows
        ]


taxonomy_tree = TaxonomyTree()
