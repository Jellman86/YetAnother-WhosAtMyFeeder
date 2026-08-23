"""One rule for which name to show a person for a species.

Species are grouped by catalogue identity, so two names for one bird count as
one bird. The name shown for that group used to be `MAX(display_name)`, which
is whichever name happened to sort last. Correct grouping with an arbitrary
label is half a feature, because the label is the part anyone actually reads.

The rule lives here, once, and is applied at read time. A locale-dependent name
is a rendering rather than a fact about the bird, so nothing here is ever
written back into a detection's identity.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional

import structlog

log = structlog.get_logger()

DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class CatalogueNames:
    """What the catalogue knows about one species' names.

    `overrides` and `vernacular` are keyed by language tag; the empty tag in
    `overrides` is a rename the owner applied to every language at once.
    """

    overrides: Mapping[str, Optional[str]] = field(default_factory=dict)
    vernacular: Mapping[str, Optional[str]] = field(default_factory=dict)
    scientific: Optional[str] = None


def normalize_language(language: Optional[str]) -> str:
    """`  pt-BR ` and `PT` both mean the `pt` names the catalogue holds."""
    tag = str(language or "").strip().lower()
    if not tag:
        return DEFAULT_LANGUAGE
    return tag.split("-", 1)[0].split("_", 1)[0] or DEFAULT_LANGUAGE


def _clean(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def choose_display_name(names: CatalogueNames, *, language: Optional[str]) -> Optional[str]:
    """The name to show, or None to leave the caller's own name alone.

    In order: what the owner renamed it to for this language, what they renamed
    it to for every language, the catalogue's name in this language, the
    catalogue's English name, then the scientific name.

    English is the stand-in because coverage is uneven and measurable: IOC 14.2
    names all 11,276 species in English and 10,210 in Italian, so a species with
    no Italian name is an ordinary case rather than an error.
    """
    tag = normalize_language(language)

    for candidate in (
        names.overrides.get(tag),
        names.overrides.get(""),
        names.vernacular.get(tag),
        names.vernacular.get(DEFAULT_LANGUAGE),
        names.scientific,
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    return None


class SpeciesNameLookup:
    """Names for a handful of species, read on demand.

    Deliberately not loaded into memory the way the resolver's mappings are:
    the catalogue holds 98,932 names across nine languages, and a page shows
    one language and a few dozen species. One indexed query per read costs far
    less than holding all of it.

    Never raises into a read path. A catalogue that is absent or unreadable
    yields no names, and the caller keeps whatever name it already had.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path

    def _resolved_path(self) -> Path:
        if self._path is not None:
            return Path(self._path)
        from app.services.species_catalog_store import default_catalog_path

        return default_catalog_path()

    def display_names(self, species_ids: Iterable[int], *, language: Optional[str]) -> dict[int, str]:
        wanted = {int(value) for value in species_ids if value is not None}
        if not wanted:
            return {}

        tag = normalize_language(language)
        placeholders = ",".join(["?"] * len(wanted))
        ids = list(wanted)

        try:
            connection = sqlite3.connect(f"file:{self._resolved_path()}?mode=ro", uri=True)
        except sqlite3.Error as error:
            log.debug("Species catalogue unavailable for naming", error=str(error))
            return {}

        try:
            overrides: dict[int, dict[str, Optional[str]]] = {}
            for species_id, language_tag, name in connection.execute(
                f"SELECT species_id, language_tag, name FROM species_name_overrides"
                f" WHERE species_id IN ({placeholders})",
                ids,
            ):
                overrides.setdefault(int(species_id), {})[str(language_tag or "")] = name

            vernacular: dict[int, dict[str, Optional[str]]] = {}
            # Only the language asked for and English, which is the stand-in.
            for species_id, language_tag, name in connection.execute(
                f"SELECT species_id, language_tag, name FROM species_names"
                f" WHERE species_id IN ({placeholders}) AND language_tag IN (?, ?)",
                [*ids, tag, DEFAULT_LANGUAGE],
            ):
                vernacular.setdefault(int(species_id), {})[str(language_tag or "")] = name

            scientific: dict[int, str] = {}
            for species_id, name in connection.execute(
                f"SELECT species_id, scientific_name FROM species_concepts WHERE species_id IN ({placeholders})",
                ids,
            ):
                scientific.setdefault(int(species_id), str(name))
        except sqlite3.Error as error:
            log.debug("Species catalogue unreadable for naming", error=str(error))
            return {}
        finally:
            connection.close()

        resolved: dict[int, str] = {}
        for species_id in wanted:
            chosen = choose_display_name(
                CatalogueNames(
                    overrides=overrides.get(species_id, {}),
                    vernacular=vernacular.get(species_id, {}),
                    scientific=scientific.get(species_id),
                ),
                language=tag,
            )
            if chosen:
                resolved[species_id] = chosen
        return resolved


species_name_lookup = SpeciesNameLookup()
