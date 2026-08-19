"""Build the bundled species reference database.

The reference answers "what is this label called" without a network round trip.
It is generated from the Google Coral MobileNet bird labels, which are
Apache-2.0 licensed (see `backend/app/assets/mobilenet-v2-inat-bird.NOTICE.md`)
and therefore redistributable, unlike the iNaturalist taxonomy export.

Coverage is deliberately partial. Measured against `rope_vit_b14_inat21`, which
emits 1,486 birds, this source covers 860 of them. eBird fills the rest at
runtime under each installation's own key, and iNaturalist remains the final
fallback. See docs/plans/2026-08-19-species-reference-source-decision.md.

Usage:
    python scripts/build_species_reference.py --labels /path/to/labels.txt
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

SCHEMA_VERSION = "1"
SOURCE_NAME = "coral-mobilenet-v2-inat-bird"

#: `Haemorhous cassinii (Cassin's Finch)`
_PAIRED_LABEL = re.compile(r"^\s*(?P<scientific>[^()]+?)\s*\((?P<common>.+)\)\s*$")

SCHEMA = """
CREATE TABLE reference_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE taxon (
    id              INTEGER PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    common_name     TEXT,
    source          TEXT NOT NULL
);

-- Lookups are case-insensitive on both names, so the indexes are too.
CREATE UNIQUE INDEX idx_taxon_scientific ON taxon (scientific_name COLLATE NOCASE);
CREATE INDEX idx_taxon_common ON taxon (common_name COLLATE NOCASE);

-- Localized names, populated at runtime from eBird rather than shipped.
CREATE TABLE taxon_name (
    taxon_id    INTEGER NOT NULL REFERENCES taxon (id) ON DELETE CASCADE,
    locale      TEXT NOT NULL,
    common_name TEXT NOT NULL,
    source      TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
);
"""


def parse_labels(lines: list[str]) -> list[tuple[str, str | None]]:
    """Read `Scientific name (Common Name)` pairs, skipping anything else.

    Returns pairs in first-seen order. A duplicate scientific name keeps the
    first entry rather than the last, so regeneration is deterministic.
    """
    seen: set[str] = set()
    pairs: list[tuple[str, str | None]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        match = _PAIRED_LABEL.match(line)
        if not match:
            continue
        scientific = match.group("scientific").strip()
        common = match.group("common").strip() or None
        key = scientific.casefold()
        if not scientific or key in seen:
            continue
        seen.add(key)
        pairs.append((scientific, common))
    return pairs


def build(labels_path: Path, output_path: Path) -> tuple[int, str]:
    lines = labels_path.read_text(encoding="utf-8").splitlines()
    pairs = parse_labels(lines)
    if not pairs:
        raise SystemExit(f"No usable 'Scientific (Common)' labels found in {labels_path}")

    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(output_path)
    try:
        connection.executescript(SCHEMA)
        connection.executemany(
            "INSERT INTO taxon (scientific_name, common_name, source) VALUES (?, ?, ?)",
            [(scientific, common, SOURCE_NAME) for scientific, common in pairs],
        )
        connection.executemany(
            "INSERT INTO reference_meta (key, value) VALUES (?, ?)",
            [
                ("schema_version", SCHEMA_VERSION),
                ("source", SOURCE_NAME),
                ("source_licence", "Apache-2.0"),
                ("taxon_count", str(len(pairs))),
                # Deliberately no build timestamp: the output must be
                # reproducible, so a reviewer can regenerate and compare digests.
                # The input is identified by its own checksum instead.
                ("labels_sha256", hashlib.sha256(labels_path.read_bytes()).hexdigest()),
            ],
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    # Recorded beside the asset so the runtime can refuse a file that no longer
    # matches what was generated. Committed, and diffable, unlike the database.
    sidecar = output_path.with_suffix(output_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")
    return len(pairs), digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path, help="Coral MobileNet labels.txt")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "app" / "assets" / "species_reference.db",
    )
    args = parser.parse_args()

    count, digest = build(args.labels, args.output)
    print(f"Wrote {args.output} with {count} taxa")
    print(f"sha256 {digest}")
    print(f"Wrote {args.output.with_suffix(args.output.suffix + '.sha256')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
