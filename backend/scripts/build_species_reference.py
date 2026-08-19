"""Build the bundled species reference database.

The source is the IOC World Bird List multilingual file, which is licensed
CC BY 3.0 and may therefore be redistributed with attribution. It carries one
curated name per species per language, which matters: aggregated sources return
several candidates per language with no way to choose, and for Cyanistes
caeruleus that includes the Italian name for a different species entirely.

Bundling it removes the need for an eBird API key to name birds locally, and
covers the two languages eBird effectively could not: Italian and Chinese. See
docs/plans/2026-08-19-species-reference-source-decision.md for the measurements.

The build is reproducible: no timestamp is written, so regenerating from the
same source produces a byte-identical file and the recorded digest can be
checked rather than trusted.

Usage:
    python scripts/build_species_reference.py --ioc /path/to/Multiling_IOC_14.2.xlsx
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA_VERSION = "2"
SOURCE_NAME = "ioc-world-bird-list"
SOURCE_LICENCE = "CC-BY-3.0"

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: The application's locales, mapped to the IOC column that carries them.
LOCALE_COLUMNS = {
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "ja": "Japanese",
    "pt": "Portuguese (Lusophone)",
    "ru": "Russian",
    "zh": "Chinese",
}
_ENGLISH_COLUMN = "English"

SCHEMA = """
CREATE TABLE reference_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE taxon (
    id              INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    common_name     TEXT
);

CREATE UNIQUE INDEX idx_taxon_scientific ON taxon (scientific_name COLLATE NOCASE);
CREATE INDEX idx_taxon_common ON taxon (common_name COLLATE NOCASE);

-- Read as "the name for this taxon in this language", so the primary key is the
-- whole access path. A reverse index on (locale, common_name) would add 2.4MB
-- to the shipped file and nothing looks names up that way.
CREATE TABLE taxon_name (
    taxon_id    INTEGER NOT NULL,
    locale      TEXT NOT NULL,
    common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""


def _read_sheet(path: Path) -> list[dict[str, str]]:
    """Read the first worksheet as dictionaries keyed by column heading.

    Parsed straight from the workbook XML so the build needs no spreadsheet
    dependency in the runtime image.
    """
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [
                "".join(node.text or "" for node in item.iter(f"{_NS}t"))
                for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(f"{_NS}si")
            ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows = sheet.find(f"{_NS}sheetData").findall(f"{_NS}row")
    if not rows:
        return []

    def cells(row: ET.Element) -> dict[str, str]:
        values: dict[str, str] = {}
        for cell in row.findall(f"{_NS}c"):
            column = "".join(char for char in (cell.get("r") or "") if char.isalpha())
            kind = cell.get("t")
            if kind == "inlineStr":
                # Exporters differ: some write strings in place rather than into
                # the shared table, and reading nothing from those is silent.
                inline = cell.find(f"{_NS}is")
                values[column] = (
                    "".join(node.text or "" for node in inline.iter(f"{_NS}t")) if inline is not None else ""
                )
                continue
            value = cell.find(f"{_NS}v")
            if value is None:
                values[column] = ""
                continue
            if kind == "s":
                try:
                    values[column] = shared[int(value.text)]
                except (ValueError, IndexError):
                    values[column] = ""
            else:
                values[column] = value.text or ""
        return values

    headings = {name: column for column, name in cells(rows[0]).items() if name}
    return [{name: (cells(row).get(column) or "").strip() for name, column in headings.items()} for row in rows[1:]]


def parse_ioc(records: list[dict[str, str]]) -> list[dict[str, object]]:
    """Keep species with a binomial, first entry wins, so the build is stable."""
    scientific_column = next((name for name in records[0] if name.startswith("IOC")), None) if records else None
    if not scientific_column:
        raise SystemExit("No IOC scientific-name column found in the workbook")

    seen: set[str] = set()
    taxa: list[dict[str, object]] = []
    for record in records:
        scientific = (record.get(scientific_column) or "").strip()
        # Genus and species only: the file also carries order and family rows.
        if not scientific or " " not in scientific:
            continue
        key = scientific.casefold()
        if key in seen:
            continue
        seen.add(key)
        taxa.append(
            {
                "scientific_name": scientific,
                "common_name": (record.get(_ENGLISH_COLUMN) or "").strip() or None,
                "names": {
                    locale: record[column].strip()
                    for locale, column in LOCALE_COLUMNS.items()
                    if (record.get(column) or "").strip()
                },
            }
        )
    return taxa


def build(source_path: Path, output_path: Path) -> tuple[int, int, str]:
    taxa = parse_ioc(_read_sheet(source_path))
    if not taxa:
        raise SystemExit(f"No usable species rows found in {source_path}")

    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(output_path)
    localized = 0
    try:
        connection.executescript(SCHEMA)
        for index, taxon in enumerate(taxa, start=1):
            connection.execute(
                "INSERT INTO taxon (id, scientific_name, common_name) VALUES (?, ?, ?)",
                (index, taxon["scientific_name"], taxon["common_name"]),
            )
            names = [(index, locale, name) for locale, name in sorted(taxon["names"].items())]
            connection.executemany("INSERT INTO taxon_name VALUES (?, ?, ?)", names)
            localized += len(names)

        connection.executemany(
            "INSERT INTO reference_meta (key, value) VALUES (?, ?)",
            [
                ("schema_version", SCHEMA_VERSION),
                ("source", SOURCE_NAME),
                ("source_licence", SOURCE_LICENCE),
                ("taxon_count", str(len(taxa))),
                ("localized_name_count", str(localized)),
                ("source_sha256", hashlib.sha256(source_path.read_bytes()).hexdigest()),
            ],
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    sidecar = output_path.with_suffix(output_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")
    return len(taxa), localized, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ioc", required=True, type=Path, help="IOC multilingual .xlsx")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "app" / "assets" / "species_reference.db",
    )
    args = parser.parse_args()

    taxa, localized, digest = build(args.ioc, args.output)
    size_mb = args.output.stat().st_size / 1024 / 1024
    print(f"Wrote {args.output}: {taxa} taxa, {localized} localized names, {size_mb:.2f} MB")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
