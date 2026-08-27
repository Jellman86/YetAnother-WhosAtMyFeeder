#!/usr/bin/env python3
"""Extract bird synonyms from the pinned Catalogue of Life release.

The catalogue takes bird names from the IOC World Bird List and taxonomy for
everything else from Catalogue of Life. IOC's multilingual export carries one
curated name per species per language and no taxonomic history, so nothing
recorded that a species had been called something else. Catalogue of Life does
carry that history, but the existing extractor skips `Aves` because IOC owns
bird names.

The result was visible: BirdNET-Go reports `Corvus monedula`, IOC 14.2 calls
that bird `Coloeus monedula` after the jackdaw genus split, and with no synonym
recorded they counted as two birds.

This reads the same pinned release, anchored on the IOC names the catalogue
already ships, and writes only the synonym relationships. It never walks the
Catalogue of Life hierarchy: every synonym here points at a name the catalogue
already holds, so a name IOC does not recognise cannot enter through this door.

Usage:
    python scripts/build_col_bird_synonyms.py --col /path/to/col-coldp.zip
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = _BACKEND_DIR / "app" / "assets" / "species_reference.db"
DEFAULT_OUTPUT = _BACKEND_DIR / "app" / "assets" / "col_bird_synonyms.json"

# Parsed by position, so the layout is proven before anything is read from it.
_EXPECTED_COLUMNS = ("col:ID", "col:parentID", "col:status", "col:rank", "col:scientificName")
_ACCEPTED_STATUSES = frozenset({"accepted", "provisionally accepted"})


def _open_name_usage(archive: zipfile.ZipFile) -> io.TextIOWrapper:
    text = io.TextIOWrapper(archive.open("NameUsage.tsv"), encoding="utf-8")
    header = tuple(text.readline().rstrip("\n").split("\t")[: len(_EXPECTED_COLUMNS)])
    if header != _EXPECTED_COLUMNS:
        raise SystemExit(
            f"NameUsage.tsv columns changed: expected {_EXPECTED_COLUMNS} first, found {header};"
            " update the parser against the new export layout"
        )
    return text


def _ioc_species(reference_path: Path) -> dict[str, str]:
    """The accepted bird names the catalogue ships, casefolded to their original."""
    connection = sqlite3.connect(f"file:{reference_path}?mode=ro", uri=True)
    try:
        return {
            str(name).casefold(): str(name)
            for (name,) in connection.execute("SELECT scientific_name FROM taxon")
            if str(name or "").strip()
        }
    finally:
        connection.close()


def _accepted_usage_ids(col_zip: Path, wanted: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Map each IOC name to the one Catalogue of Life concept that accepts it.

    A name with more than one accepted concept is dropped and reported: two
    concepts mean the release disagrees with itself about what the name is, and
    a synonym hung off the wrong one would merge two real birds.
    """
    candidates: dict[str, list[str]] = defaultdict(list)
    with zipfile.ZipFile(col_zip) as archive, _open_name_usage(archive) as text:
        for line in text:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < len(_EXPECTED_COLUMNS):
                if line.strip():
                    raise SystemExit(f"Truncated NameUsage.tsv row: {line!r}")
                continue
            if cols[3] != "species" or cols[2] not in _ACCEPTED_STATUSES:
                continue
            key = cols[4].casefold()
            if key in wanted:
                candidates[key].append(cols[0])

    resolved = {key: ids[0] for key, ids in candidates.items() if len(ids) == 1}
    ambiguous = sorted(wanted[key] for key, ids in candidates.items() if len(ids) > 1)
    return resolved, ambiguous


def _synonyms_for(col_zip: Path, accepted_ids: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Species-rank synonyms pointing at those concepts, keyed by synonym name.

    Subspecies are skipped: a subspecies name is not another name for the
    species, and treating it as one would fold real distinctions away.
    """
    by_id = {usage_id: key for key, usage_id in accepted_ids.items()}
    found: dict[str, set[str]] = defaultdict(set)
    original_case: dict[str, str] = {}
    with zipfile.ZipFile(col_zip) as archive, _open_name_usage(archive) as text:
        for line in text:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < len(_EXPECTED_COLUMNS):
                continue
            if cols[2] != "synonym" or cols[3] != "species":
                continue
            accepted_key = by_id.get(cols[1])
            if accepted_key is None:
                continue
            alias = cols[4].strip()
            if alias:
                found[alias.casefold()].add(accepted_key)
                # Keep the name as the release writes it. The resolver
                # casefolds anyway, but a stored name that reads oddly is
                # harder to check against the source by eye.
                original_case.setdefault(alias.casefold(), alias)
    return found, original_case


def build(col_zip: Path, reference_path: Path) -> dict[str, object]:
    ioc = _ioc_species(reference_path)
    accepted_ids, ambiguous_accepted = _accepted_usage_ids(col_zip, ioc)
    raw, alias_case = _synonyms_for(col_zip, accepted_ids)

    synonyms: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    for alias_key in sorted(raw):
        targets = raw[alias_key]
        alias = alias_case.get(alias_key, alias_key)
        if len(targets) > 1:
            rejected.append({"alias": alias, "reason": "synonym of more than one accepted species"})
            continue
        accepted_key = next(iter(targets))
        if alias_key == accepted_key:
            continue
        # A synonym that IOC itself accepts as a species is not a synonym here.
        # Recording it would alias one real bird onto another, which is the
        # opposite of what this exists to do.
        if alias_key in ioc:
            rejected.append({"alias": ioc[alias_key], "reason": "IOC accepts this name as its own species"})
            continue
        synonyms.append({"alias": alias, "accepted": ioc[accepted_key]})

    return {
        "note": "Generated by backend/scripts/build_col_bird_synonyms.py; regenerate rather than edit.",
        "source": {
            "id": "catalogue-of-life",
            "role": "bird-synonyms",
            "usage": "Synonym relationships only. Bird names remain IOC's.",
        },
        "counts": {
            "ioc_species": len(ioc),
            "matched_in_col": len(accepted_ids),
            "synonyms": len(synonyms),
            "rejected": len(rejected),
            "ambiguous_accepted": len(ambiguous_accepted),
        },
        "synonyms": synonyms,
        "rejected": rejected,
        "ambiguous_accepted": ambiguous_accepted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--col", required=True, type=Path, help="Catalogue of Life ColDP export")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    payload = build(args.col, args.reference)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    counts = payload["counts"]
    print(f"Wrote {args.output} ({counts['synonyms']} synonyms from {counts['matched_in_col']} matched species)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
