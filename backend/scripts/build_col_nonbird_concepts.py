"""Resolve the non-bird model classes against the pinned Catalogue of Life.

The 10,000-class iNat21 models emit 8,514 non-bird classes, which no bird list
covers. This reads their scientific names from the checksum-verified hierarchy
label file, matches them against the pinned COL26.7 ColDP export (admitted
through the provenance gate), and writes:

- `backend/app/assets/col_nonbird_concepts.json` — the committed identity
  artifact the seed builder folds into the catalogue: one Catalogue of Life
  concept per resolved class, plus the explicit unresolved list.
- a dated mapping report under `docs/reviews/` — the exact / synonym /
  ambiguous / unresolved evidence the catalogue design's Phase 0 requires.

Ambiguity fails closed: a name with several accepted candidates, an
`ambiguous synonym`, or a `misapplied` usage stays unresolved and listed,
never guessed.

Usage:
    python scripts/build_col_nonbird_concepts.py --col /path/to/col26.7-coldp.zip \
        --labels /path/to/rope_vit_b14_inat21_labels.txt
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.label_integrity import published_labels_sha256  # noqa: E402
from app.services.species_provenance import (  # noqa: E402
    SourceProvenanceError,
    load_source_manifest,
    require_build_source,
)

SOURCE_NAME = "catalogue-of-life"
HIERARCHY_MODEL_ID = "rope_vit_b14_inat21"
DEFAULT_OUTPUT = _BACKEND_DIR / "app" / "assets" / "col_nonbird_concepts.json"
DEFAULT_REPORT = _BACKEND_DIR.parent / "docs" / "reviews" / "2026-08-20-col-nonbird-mapping-report.md"

_ACCEPTED_STATUSES = frozenset({"accepted", "provisionally accepted"})


@dataclass(frozen=True)
class ColUsage:
    col_id: str
    parent_id: str
    status: str
    rank: str


@dataclass(frozen=True)
class ResolvedConcept:
    scientific_name: str
    kingdom: str
    label_class: str
    col_id: str
    col_status: str
    accepted_col_id: str
    accepted_scientific_name: str


@dataclass(frozen=True)
class UnresolvedClass:
    scientific_name: str
    kingdom: str
    label_class: str
    reason: str


@dataclass(frozen=True)
class Resolution:
    resolved: list[ResolvedConcept]
    unresolved: list[UnresolvedClass]


def resolve_needles(
    needles: dict[str, tuple[str, str, str]],
    usages_by_name: dict[str, list[ColUsage]],
    parents: dict[str, tuple[str, str, str]],
) -> Resolution:
    """Resolve each needle to at most one Catalogue of Life concept.

    `needles` maps a casefolded scientific name to (name, kingdom, class).
    `parents` maps a usage id to (scientific name, status, rank), needed only
    for synonym targets. Every branch that is not certain fails closed.
    """
    resolved: list[ResolvedConcept] = []
    unresolved: list[UnresolvedClass] = []

    for key in sorted(needles):
        name, kingdom, label_class = needles[key]
        usages = usages_by_name.get(key, [])
        accepted = [u for u in usages if u.status in _ACCEPTED_STATUSES and u.rank == "species"]
        synonyms = [u for u in usages if u.status == "synonym"]

        if len(accepted) == 1:
            usage = accepted[0]
            resolved.append(ResolvedConcept(name, kingdom, label_class, usage.col_id, usage.status, usage.col_id, name))
            continue
        if len(accepted) > 1:
            unresolved.append(UnresolvedClass(name, kingdom, label_class, "multiple accepted candidates"))
            continue

        if synonyms:
            targets = {u.parent_id for u in synonyms}
            if len(targets) > 1:
                unresolved.append(UnresolvedClass(name, kingdom, label_class, "synonym of multiple taxa"))
                continue
            parent = parents.get(next(iter(targets)))
            if parent is None or parent[1] not in _ACCEPTED_STATUSES or parent[2] != "species":
                unresolved.append(
                    UnresolvedClass(name, kingdom, label_class, "synonym parent is not an accepted species")
                )
                continue
            usage = synonyms[0]
            resolved.append(
                ResolvedConcept(name, kingdom, label_class, usage.col_id, "synonym", usage.parent_id, parent[0])
            )
            continue

        if usages:
            unresolved.append(UnresolvedClass(name, kingdom, label_class, "only ambiguous or misapplied usages"))
        else:
            unresolved.append(UnresolvedClass(name, kingdom, label_class, "not in the release"))

    return Resolution(resolved=resolved, unresolved=unresolved)


def _needles_from_labels(labels_path: Path) -> dict[str, tuple[str, str, str]]:
    needles: dict[str, tuple[str, str, str]] = {}
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split("_")
        if len(parts) < 8 or parts[3] == "Aves":
            continue
        name = f"{parts[-2]} {parts[-1]}"
        needles[name.casefold()] = (name, parts[1], parts[3])
    return needles


def _scan_export(
    col_zip: Path, needles: dict[str, tuple[str, str, str]]
) -> tuple[dict[str, list[ColUsage]], dict[str, tuple[str, str, str]]]:
    """Two streaming passes: matching usages, then the synonym parents."""
    usages_by_name: dict[str, list[ColUsage]] = {}
    with zipfile.ZipFile(col_zip) as archive:
        with archive.open("NameUsage.tsv") as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8")
            text.readline()
            for line in text:
                cols = line.rstrip("\n").split("\t")
                key = cols[4].casefold()
                if key in needles:
                    usages_by_name.setdefault(key, []).append(ColUsage(cols[0], cols[1], cols[2], cols[3]))

        wanted_parents = {
            usage.parent_id for usages in usages_by_name.values() for usage in usages if usage.status == "synonym"
        }
        parents: dict[str, tuple[str, str, str]] = {}
        if wanted_parents:
            with archive.open("NameUsage.tsv") as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8")
                text.readline()
                for line in text:
                    cols = line.rstrip("\n").split("\t")
                    if cols[0] in wanted_parents:
                        parents[cols[0]] = (cols[4], cols[2], cols[3])
    return usages_by_name, parents


def _write_artifact(output: Path, resolution: Resolution, provenance: dict[str, object]) -> None:
    payload = {
        "schema_version": 1,
        "source": provenance,
        "counts": {
            "classes": len(resolution.resolved) + len(resolution.unresolved),
            "resolved": len(resolution.resolved),
            "resolved_as_synonym": sum(1 for e in resolution.resolved if e.col_status == "synonym"),
            "unresolved": len(resolution.unresolved),
        },
        "concepts": [vars(entry) for entry in resolution.resolved],
        "unresolved": [vars(entry) for entry in resolution.unresolved],
    }
    output.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _write_report(report: Path, resolution: Resolution, provenance: dict[str, object]) -> None:
    reasons = Counter(entry.reason for entry in resolution.unresolved)
    kingdoms = Counter(entry.kingdom for entry in resolution.resolved)
    lines = [
        "# Non-bird model classes against Catalogue of Life COL26.7",
        "",
        "Generated by `backend/scripts/build_col_nonbird_concepts.py`; regenerate rather than edit.",
        "The mapping evidence the catalogue design's Phase 0 requires for the 8,514 non-bird",
        "classes: every class resolves to exactly one pinned Catalogue of Life concept, or is",
        "listed here as unresolved with its reason. Nothing is guessed.",
        "",
        f"Source: Catalogue of Life {provenance['version']} ({provenance['doi']}), export sha256",
        f"`{provenance['export_sha256']}`. Labels: `{HIERARCHY_MODEL_ID}` file `{provenance['labels_sha256']}`.",
        "",
        "## Outcome",
        "",
        "| | Count |",
        "| --- | ---: |",
        f"| Non-bird classes | {len(resolution.resolved) + len(resolution.unresolved)} |",
        f"| Resolved to an accepted concept | {sum(1 for e in resolution.resolved if e.col_status != 'synonym')} |",
        f"| Resolved through an unambiguous synonym | {sum(1 for e in resolution.resolved if e.col_status == 'synonym')} |",
        f"| Unresolved (fail closed) | {len(resolution.unresolved)} |",
        "",
        "Resolved by kingdom: " + ", ".join(f"{kingdom} {count}" for kingdom, count in sorted(kingdoms.items())) + ".",
        "",
        "## Unresolved, by reason",
        "",
    ]
    for reason, count in reasons.most_common():
        lines += [f"### {reason} ({count})", ""]
        names = [e.scientific_name for e in resolution.unresolved if e.reason == reason]
        lines += [", ".join(f"`{name}`" for name in names), ""]
    report.write_text("\n".join(lines), encoding="utf-8")


def build(
    col_zip: Path,
    labels_path: Path,
    output: Path,
    report: Path,
    *,
    manifest_path: Path | None = None,
) -> Resolution:
    export_digest = hashlib.sha256(col_zip.read_bytes()).hexdigest()
    try:
        source = require_build_source(load_source_manifest(manifest_path), SOURCE_NAME, content_sha256=export_digest)
    except SourceProvenanceError as error:
        raise SystemExit(f"Provenance gate refused the build: {error}") from error

    labels_digest = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    published = published_labels_sha256(HIERARCHY_MODEL_ID)
    if published and labels_digest != published:
        raise SystemExit(
            f"Label file does not match the registry checksum for {HIERARCHY_MODEL_ID}: "
            f"expected {published}, got {labels_digest}"
        )

    needles = _needles_from_labels(labels_path)
    if not needles:
        raise SystemExit(f"No non-bird hierarchy labels found in {labels_path}")

    usages_by_name, parents = _scan_export(col_zip, needles)
    resolution = resolve_needles(needles, usages_by_name, parents)

    provenance: dict[str, object] = {
        "id": source.id,
        "version": source.version,
        "doi": "10.48580/dgyhw",
        "export_sha256": export_digest,
        "licence": source.licence,
        "citation": source.citation,
        "labels_sha256": labels_digest,
    }
    _write_artifact(output, resolution, provenance)
    _write_report(report, resolution, provenance)
    return resolution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--col", required=True, type=Path, help="COL ColDP export zip")
    parser.add_argument("--labels", required=True, type=Path, help="iNat21 hierarchy label file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    resolution = build(args.col, args.labels, args.output, args.report)
    print(f"Resolved {len(resolution.resolved)} classes, {len(resolution.unresolved)} unresolved")
    print(f"Wrote {args.output} and {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
