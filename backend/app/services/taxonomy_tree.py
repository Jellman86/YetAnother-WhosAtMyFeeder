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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Optional

import structlog

from app.services.species_names import DEFAULT_LANGUAGE, normalize_language, vernacular_case

log = structlog.get_logger()

#: The ranks a lineage normally shows. Intermediate ranks a source records (Catalogue of Life
#: puts subphylum, infraphylum, parvphylum and megaclass between Chordata and Aves) are kept and
#: returned, flagged so a view can collapse them.
PRINCIPAL_RANKS = ("kingdom", "phylum", "class", "order", "family", "genus", "species")

#: The ranks a person searches by: a species and the groups it is named in. Ranks above order
#: would match nearly everything seen here.
SEARCHABLE_RANKS = ("species", "genus", "family", "order")

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
    #: Species beneath this taxon (or this species itself) with a detection here, and how many detections.
    seen_species: Optional[int] = None
    seen_count: Optional[int] = None
    #: The accepted concept's authority and year exactly as the source publishes it; None when unrecorded.
    authorship: Optional[str] = None


@dataclass(frozen=True)
class OtherName:
    language: str
    name: str
    preferred: bool


@dataclass(frozen=True)
class OtherNames:
    """A taxon's common names outside the reader's language, preferred first within each language."""

    names: tuple[OtherName, ...]
    #: Languages among all of them, so a reader knows how many a bounded list stands for.
    languages: int
    truncated: bool


@dataclass(frozen=True)
class NamedTaxon:
    """A taxon with every name a reader might search it by."""

    taxon_id: int
    rank: str
    scientific_name: str
    #: The reader's language, else English, as a lineage names it.
    name: Optional[str]
    #: The reader's language, English, the owner's own name and the scientific name.
    names: tuple[str, ...]


def _display_name(name: Optional[str], scientific_name: str) -> Optional[str]:
    """A common name as a reader should see it.

    SpeciesNet calls a genus "<genus> species", a placeholder for an unidentified member
    rather than a name; the genus reads better as itself.
    """
    if not name:
        return None
    if scientific_name and name.casefold() == f"{scientific_name} species".casefold():
        return None
    return name


def _with_seen(taxon: "Taxon", seen: Optional[dict[int, tuple[int, int]]]) -> "Taxon":
    if seen is None:
        return taxon
    species, count = seen.get(taxon.taxon_id, (0, 0))
    return replace(taxon, seen_species=species, seen_count=count)


def _taxon(
    row: sqlite3.Row,
    names: Mapping[int, str],
    concepts: Mapping[int, tuple[str, str, Optional[str]]],
    counts: Mapping[int, int],
) -> "Taxon":
    taxon_id = int(row["species_id"])
    scientific_name, source, authorship = concepts.get(taxon_id, ("", None, None))
    return Taxon(
        taxon_id=taxon_id,
        rank=str(row["rank"]),
        scientific_name=scientific_name,
        name=_display_name(names.get(taxon_id), scientific_name),
        source=source,
        principal=str(row["rank"]) in PRINCIPAL_RANKS,
        parent_id=row["parent_species_id"],
        species_count=counts.get(taxon_id),
        authorship=authorship,
    )


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
            f"SELECT species_id, language_tag, name, provider FROM species_names"
            f" WHERE species_id IN ({placeholders}) AND language_tag IN (?, ?)",
            [*ids, language, DEFAULT_LANGUAGE],
        ):
            # SpeciesNet names its taxa in lowercase; other sources' casing is their own.
            name = vernacular_case(str(row["name"])) if row["provider"] == "google-speciesnet" else str(row["name"])
            found.setdefault(int(row["species_id"]), {})[str(row["language_tag"])] = name
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
    def _searchable_names(connection: sqlite3.Connection, ids: list[int], language: str) -> dict[int, list[str]]:
        """Every vernacular name a reader may type for each taxon: their language's, English and the owner's own."""
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        found: dict[int, list[str]] = {}
        for row in connection.execute(
            f"SELECT species_id, name, provider FROM species_names"
            f" WHERE species_id IN ({placeholders}) AND language_tag IN (?, ?)",
            [*ids, language, DEFAULT_LANGUAGE],
        ):
            name = vernacular_case(str(row["name"])) if row["provider"] == "google-speciesnet" else str(row["name"])
            found.setdefault(int(row["species_id"]), []).append(name)
        for row in connection.execute(
            f"SELECT species_id, language_tag, name FROM species_name_overrides WHERE species_id IN ({placeholders})",
            ids,
        ):
            if str(row["language_tag"] or "") in ("", language):
                found.setdefault(int(row["species_id"]), []).append(str(row["name"]))
        return found

    @staticmethod
    def _concepts(connection: sqlite3.Connection, ids: list[int]) -> dict[int, tuple[str, str, Optional[str]]]:
        """Each taxon's accepted concept: its scientific name, provider and authorship.

        The authorship is the one stored for that name, taken from another concept of the same
        name when the leading one has none, because an authority belongs to a name. It is used as
        the source wrote it, parentheses and all; nothing here adds or removes them.
        """
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        concepts: dict[int, tuple[str, str, Optional[str]]] = {}
        authorities: dict[tuple[int, str], str] = {}
        # IOC first where a taxon carries several concepts: it owns bird naming.
        for row in connection.execute(
            f"SELECT species_id, scientific_name, provider, authorship FROM species_concepts"
            f" WHERE species_id IN ({placeholders})"
            " ORDER BY species_id, CASE provider WHEN 'ioc-world-bird-list' THEN 0 ELSE 1 END,"
            " CASE status WHEN 'accepted' THEN 0 ELSE 1 END, provider",
            ids,
        ):
            taxon_id, scientific = int(row["species_id"]), str(row["scientific_name"])
            concepts.setdefault(taxon_id, (scientific, str(row["provider"]), None))
            authority = " ".join(str(row["authorship"] or "").split())
            if authority:
                authorities.setdefault((taxon_id, scientific.casefold()), authority)
        return {
            taxon_id: (scientific, provider, authorities.get((taxon_id, scientific.casefold())))
            for taxon_id, (scientific, provider, _none) in concepts.items()
        }

    @staticmethod
    def _chains(connection: sqlite3.Connection, taxon_ids: Iterable[int]) -> dict[int, list[int]]:
        """Each taxon and every taxon above it, nearest first, sharing one parent lookup across them."""
        parents: dict[int, Optional[int]] = {}

        def parent_of(taxon_id: int) -> Optional[int]:
            if taxon_id not in parents:
                row = connection.execute(
                    "SELECT parent_species_id FROM species WHERE species_id = ?", (taxon_id,)
                ).fetchone()
                parents[taxon_id] = row[0] if row else None
            return parents[taxon_id]

        chains: dict[int, list[int]] = {}
        for start in taxon_ids:
            chain: list[int] = []
            current: Optional[int] = int(start)
            while current is not None and current not in chain and len(chain) < _MAX_DEPTH:
                chain.append(current)
                current = parent_of(current)
            chains[int(start)] = chain
        return chains

    @classmethod
    def _seen_by_taxon(cls, connection: sqlite3.Connection, counts: Mapping[int, int]) -> dict[int, tuple[int, int]]:
        """Roll detection counts up the classification: each taxon gets its species seen and their detections.

        Walks up from each species seen here, a few dozen at most, rather than down from every taxon.
        """
        seen = {int(species_id): int(count) for species_id, count in counts.items() if count > 0}
        rolled: dict[int, list[int]] = {}
        for species_id, chain in cls._chains(connection, seen).items():
            for taxon_id in chain:
                entry = rolled.setdefault(taxon_id, [0, 0])
                entry[0] += 1
                entry[1] += seen[species_id]
        return {taxon_id: (species, total) for taxon_id, (species, total) in rolled.items()}

    @staticmethod
    def _species_beneath(connection: sqlite3.Connection, taxon_id: int) -> int:
        """Species at or below a taxon: a species counts itself."""
        return int(
            connection.execute(
                "WITH RECURSIVE below(id, rank, depth) AS ("
                "  SELECT species_id, rank, 0 FROM species WHERE species_id = ?"
                "  UNION ALL SELECT s.species_id, s.rank, below.depth + 1 FROM species s"
                "  JOIN below ON s.parent_species_id = below.id WHERE below.depth < ?"
                ") SELECT COUNT(*) FROM below WHERE rank = 'species'",
                (taxon_id, _MAX_DEPTH),
            ).fetchone()[0]
        )

    def seen_by_taxon(self, counts: Mapping[int, int]) -> dict[int, tuple[int, int]]:
        connection = self._connect()
        if connection is None:
            return {}
        try:
            return self._seen_by_taxon(connection, counts)
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return {}
        finally:
            connection.close()

    def seen_taxa(
        self, seen_ids: Iterable[int], *, language: Optional[str] = None, ranks: tuple[str, ...] = SEARCHABLE_RANKS
    ) -> list[NamedTaxon]:
        """The taxa of the given ranks at or above any species seen here, each with every name it answers to."""
        connection = self._connect()
        if connection is None:
            return []
        tag = normalize_language(language)
        try:
            chains = self._chains(connection, seen_ids)
            above = sorted({taxon_id for chain in chains.values() for taxon_id in chain})
            ranked: dict[int, str] = {}
            for start in range(0, len(above), 500):
                batch = above[start : start + 500]
                for row in connection.execute(
                    f"SELECT species_id, rank FROM species WHERE species_id IN ({','.join('?' * len(batch))})", batch
                ):
                    if str(row["rank"]) in ranks:
                        ranked[int(row["species_id"])] = str(row["rank"])
            ids = sorted(ranked)
            display = self._names(connection, ids, tag)
            searchable = self._searchable_names(connection, ids, tag)
            concepts = self._concepts(connection, ids)
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return []
        finally:
            connection.close()
        taxa: list[NamedTaxon] = []
        for taxon_id in ids:
            scientific_name = concepts.get(taxon_id, ("", "", None))[0]
            if not scientific_name:
                continue
            name = _display_name(display.get(taxon_id), scientific_name)
            spoken = [_display_name(value, scientific_name) for value in searchable.get(taxon_id, [])]
            names = tuple(dict.fromkeys(value for value in [name, *spoken, scientific_name] if value))
            taxa.append(NamedTaxon(taxon_id, ranked[taxon_id], scientific_name, name, names))
        return taxa

    def members_beneath(self, taxon_id: int, candidates: Iterable[int]) -> set[int]:
        """The candidates that are the taxon or sit anywhere beneath it."""
        if not 0 < taxon_id < 2**63:
            return set()
        connection = self._connect()
        if connection is None:
            return set()
        try:
            if connection.execute("SELECT 1 FROM species WHERE species_id = ?", (taxon_id,)).fetchone() is None:
                return set()
            chains = self._chains(connection, candidates)
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return set()
        finally:
            connection.close()
        return {species_id for species_id, chain in chains.items() if int(taxon_id) in chain}

    def ranks(self, taxon_ids: Iterable[int]) -> dict[int, str]:
        """The rank of each taxon the catalogue holds; an id it does not hold is left out."""
        ids = sorted({int(taxon_id) for taxon_id in taxon_ids if 0 < int(taxon_id) < 2**63})
        if not ids:
            return {}
        connection = self._connect()
        if connection is None:
            return {}
        try:
            found: dict[int, str] = {}
            for start in range(0, len(ids), 500):
                batch = ids[start : start + 500]
                for row in connection.execute(
                    f"SELECT species_id, rank FROM species WHERE species_id IN ({','.join('?' * len(batch))})", batch
                ):
                    found[int(row["species_id"])] = str(row["rank"])
            return found
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return {}
        finally:
            connection.close()

    def display_names(
        self, taxon_ids: Iterable[int], *, language: Optional[str] = None
    ) -> dict[int, tuple[str, Optional[str]]]:
        """Each taxon's scientific name and common name in the reader's language, as a lineage names it."""
        ids = sorted({int(taxon_id) for taxon_id in taxon_ids if 0 < int(taxon_id) < 2**63})
        if not ids:
            return {}
        connection = self._connect()
        if connection is None:
            return {}
        try:
            concepts = self._concepts(connection, ids)
            names = self._names(connection, ids, normalize_language(language))
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return {}
        finally:
            connection.close()
        return {
            taxon_id: (scientific, _display_name(names.get(taxon_id), scientific))
            for taxon_id, (scientific, _provider, _authorship) in concepts.items()
        }

    def members_by_taxon(self, species_ids: Iterable[int]) -> dict[int, list[int]]:
        """For every taxon at or above the given species, which of them sit beneath it.

        Walks up from each species, a few hundred at most, rather than down from every taxon.
        """
        connection = self._connect()
        if connection is None:
            return {}
        try:
            chains = self._chains(connection, species_ids)
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return {}
        finally:
            connection.close()
        members: dict[int, list[int]] = {}
        for species_id, chain in chains.items():
            for taxon_id in chain:
                members.setdefault(taxon_id, []).append(species_id)
        return members

    def other_names(self, taxon_id: int, *, language: Optional[str] = None, limit: int = 40) -> Optional[OtherNames]:
        """A taxon's common names in the catalogue's other languages. None when the catalogue lacks the taxon.

        The reader's own language is left out: its name is already the one they read. Repeats
        that differ only in case are one name; within a language the preferred name leads.
        """
        if not 0 < taxon_id < 2**63:
            return None
        connection = self._connect()
        if connection is None:
            return None
        tag = normalize_language(language)
        try:
            if connection.execute("SELECT 1 FROM species WHERE species_id = ?", (taxon_id,)).fetchone() is None:
                return None
            rows = connection.execute(
                "SELECT language_tag, name, preferred, provider FROM species_names"
                " WHERE species_id = ? AND language_tag != ? ORDER BY language_tag, preferred DESC, name, id",
                (taxon_id, tag),
            ).fetchall()
            scientific = self._concepts(connection, [taxon_id]).get(taxon_id, ("", "", None))[0]
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return None
        finally:
            connection.close()
        names: list[OtherName] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            raw = vernacular_case(str(row["name"])) if row["provider"] == "google-speciesnet" else str(row["name"])
            name = _display_name(raw.strip(), scientific)
            if not name:
                continue
            key = (str(row["language_tag"]), name.casefold())
            if key in seen:
                continue
            seen.add(key)
            names.append(OtherName(language=key[0], name=name, preferred=bool(row["preferred"])))
        bound = max(1, int(limit))
        return OtherNames(
            names=tuple(names[:bound]),
            languages=len({name.language for name in names}),
            truncated=len(names) > bound,
        )

    def lineage(
        self, taxon_id: int, *, language: Optional[str] = None, seen: Optional[Mapping[int, int]] = None
    ) -> list[Taxon]:
        """The taxon and every taxon above it, from the root down. Empty when the catalogue lacks it."""
        connection = self._connect()
        if connection is None:
            return []
        tag = normalize_language(language)
        try:
            chain: list[sqlite3.Row] = []
            walked: set[int] = set()
            current: Optional[int] = int(taxon_id)
            while current is not None and current not in walked and len(chain) < _MAX_DEPTH:
                row = connection.execute(
                    "SELECT species_id, rank, parent_species_id FROM species WHERE species_id = ?", (current,)
                ).fetchone()
                if row is None:
                    break
                walked.add(current)
                chain.append(row)
                current = row["parent_species_id"]
            ids = [int(row["species_id"]) for row in chain]
            names = self._names(connection, ids, tag)
            concepts = self._concepts(connection, ids)
            counts = {taxon: self._species_beneath(connection, taxon) for taxon in ids}
            rolled = self._seen_by_taxon(connection, seen) if seen is not None else None
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return []
        finally:
            connection.close()
        return [_with_seen(_taxon(row, names, concepts, counts), rolled) for row in reversed(chain)]

    def children(
        self,
        taxon_id: int,
        *,
        language: Optional[str] = None,
        limit: int = 500,
        seen: Optional[Mapping[int, int]] = None,
    ) -> list[Taxon]:
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
            counts = {child: self._species_beneath(connection, child) for child in ids}
            names = self._names(connection, ids, tag)
            concepts = self._concepts(connection, ids)
            rolled = self._seen_by_taxon(connection, seen) if seen is not None else None
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for the taxonomy", error=str(error))
            return []
        finally:
            connection.close()
        return [_with_seen(_taxon(row, names, concepts, counts), rolled) for row in rows]


taxonomy_tree = TaxonomyTree()
