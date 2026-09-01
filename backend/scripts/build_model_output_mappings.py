"""Compile checksum-bound output mappings for every supported classifier.

Phase 2 of the catalogue design: a classifier's semantic output is an index,
and only a mapping gives that index a species meaning. This reads each
checksum-verified label file, resolves every line through the seed catalogue
by the artifact's declared grammar, and writes:

- `backend/app/assets/model_output_mappings.json` — the committed,
  machine-readable mapping record (the design's reproducibility intermediate)
  that the seed build folds into `model_artifacts` and `model_output_taxa`.
- a dated coverage report under `docs/reviews/`.

Resolution is deterministic and fails closed. A scientific label resolves
through catalogue concepts (or a resolved synonym alias); a common-name label
resolves through the English names, exactly first, then apostrophe- and
parenthetical-insensitively; `background` and `Unknown` are declared class
kinds; everything else is recorded as unresolved with the raw label kept.

Usage:
    python scripts/build_model_output_mappings.py --labels-dir /path/to/by_sha
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.model_registry_inventory import registry_artifacts  # noqa: E402
from app.services.model_taxon_map import normalize_common_name as _normalize_common  # noqa: E402
from app.services.model_taxon_map import paired_common_name  # noqa: E402
from app.services.model_taxon_map import corroborates, subspecies_candidates  # noqa: E402
from app.services.model_taxon_map import scientific_name_from_label  # noqa: E402

DEFAULT_OUTPUT = _BACKEND_DIR / "app" / "assets" / "model_output_mappings.json"
DEFAULT_REPORT = _BACKEND_DIR.parent / "docs" / "reviews" / "2026-08-20-model-output-mapping-coverage.md"

_AMBIGUOUS = object()
_HYBRID_SIGNS = str.maketrans("", "", "×")


@dataclass(frozen=True)
class OutputRow:
    index: int
    kind: str
    label: str
    provider: Optional[str] = None
    taxon: Optional[str] = None
    unresolved: Optional[str] = None


@dataclass
class LabelFileResult:
    """One label file's rows, kept with the grammar they were read under so a
    second pass can tell a paired label from a bare common name."""

    label_format: str
    rows: list[OutputRow]


def bridge_common_names(results: dict[str, LabelFileResult]) -> int:
    """Resolve bare common names through paired labels that already named them.

    A paired label like `Tyto alba (Barn Owl)` is the model author's own statement
    that this common name means this taxon, and it reached a concept through the
    reviewed scientific path. A second model writing only `Barn Owl` is asking the
    same question, and IOC's rename or split is why it fails on its own. Nothing is
    guessed: a name two paired labels disagree about is refused, and a name no
    paired label claims is left unresolved.
    """
    claims: dict[str, set[tuple[str, str]]] = {}
    for result in results.values():
        for row in result.rows:
            if row.kind != "species" or not row.provider or not row.taxon:
                continue
            common = paired_common_name(row.label)
            if not common:
                continue
            key = _normalize_common(common)
            if key:
                claims.setdefault(key, set()).add((row.provider, row.taxon))

    settled = {key: next(iter(values)) for key, values in claims.items() if len(values) == 1}

    recovered = 0
    for result in results.values():
        if result.label_format != "common_name":
            continue
        for position, row in enumerate(result.rows):
            if row.unresolved != "no catalogue identity":
                continue
            reference = settled.get(_normalize_common(row.label))
            if not reference:
                continue
            # OutputRow is frozen so a compiled row cannot be edited in place by
            # accident; the recovered one replaces it rather than mutating it.
            result.rows[position] = replace(row, provider=reference[0], taxon=reference[1], unresolved=None)
            recovered += 1
    return recovered


def resolve_subspecies(results: dict[str, LabelFileResult], resolver: "CatalogResolver") -> int:
    """Give a trinomial the identity IOC actually recognises.

    A subspecies is either a species in its own right now, or a form of its parent.
    The elevated binomial is tried first and taken only when the catalogue's common
    name for it corroborates the one the label carries, because genus plus a
    subspecies epithet can land on an unrelated bird. Otherwise the parent species
    is the honest identity: a Domestic Duck is an `Anas platyrhynchos`.
    """
    recovered = 0
    for result in results.values():
        for position, row in enumerate(result.rows):
            if row.unresolved is None or row.kind != "species":
                continue
            elevated, parent, common = subspecies_candidates(row.label)
            if not parent:
                continue

            reference = None
            if elevated:
                candidate, ambiguous = resolver.resolve_scientific(elevated)
                if candidate and not ambiguous:
                    if corroborates(resolver.common_name_for(candidate) or "", common):
                        reference = candidate
                    else:
                        # A distinct species exists under the subspecies epithet, so the
                        # parent is not safe to assume, and nothing corroborates the
                        # elevated reading either. Unresolved is the honest answer:
                        # collapsing here once filed a Northern Harrier as a Hen Harrier.
                        continue
            if reference is None:
                candidate, ambiguous = resolver.resolve_scientific(parent)
                if candidate and not ambiguous:
                    reference = candidate
            if reference is None:
                continue

            result.rows[position] = replace(row, provider=reference[0], taxon=reference[1], unresolved=None)
            recovered += 1
    return recovered


class CatalogResolver:
    """Lookup tables built once from a seed catalogue.

    A resolved value is a `(provider, provider_taxon_id)` concept reference —
    stable across seed rebuilds, unlike the build-local `species_id`. A key
    two species share resolves to nothing.
    """

    def __init__(self, seed_path: Path) -> None:
        connection = sqlite3.connect(f"file:{seed_path}?mode=ro", uri=True)
        try:
            concept_ref: dict[int, tuple[str, str]] = {}
            self._by_scientific: dict[str, object] = {}
            for species_id, provider, taxon_id, scientific in connection.execute(
                "SELECT species_id, provider, provider_taxon_id, scientific_name FROM species_concepts"
                " ORDER BY species_id, provider, provider_taxon_id"
            ):
                concept_ref.setdefault(species_id, (provider, taxon_id))
                self._put(self._by_scientific, scientific.casefold(), concept_ref[species_id])

            self._by_alias: dict[str, object] = {}
            for alias, species_id in connection.execute(
                "SELECT alias, species_id FROM species_aliases WHERE resolution = 'resolved' ORDER BY alias"
            ):
                reference = concept_ref.get(species_id)
                if reference:
                    self._put(self._by_alias, alias.casefold(), reference)

            self._common_by_reference: dict[tuple[str, str], str] = {}
            self._by_common_exact: dict[str, object] = {}
            self._by_common_normalized: dict[str, object] = {}
            for species_id, name in connection.execute(
                "SELECT species_id, name FROM species_names WHERE language_tag = 'en' ORDER BY species_id, name"
            ):
                reference = concept_ref.get(species_id)
                if not reference:
                    continue
                self._put(self._by_common_exact, name.casefold(), reference)
                self._put(self._by_common_normalized, _normalize_common(name), reference)
                # The reverse direction, so a resolved concept can state the name the
                # catalogue holds for it and corroborate a label's own reading.
                self._common_by_reference.setdefault(reference, name)
        finally:
            connection.close()

    def common_name_for(self, reference: Optional[tuple[str, str]]) -> Optional[str]:
        """The catalogue's English name for a resolved concept, if it has one."""
        return self._common_by_reference.get(reference) if reference else None

    @staticmethod
    def _put(table: dict[str, object], key: str, reference: tuple[str, str]) -> None:
        current = table.get(key)
        if current is None:
            table[key] = reference
        elif current != reference:
            table[key] = _AMBIGUOUS

    @staticmethod
    def _get(table: dict[str, object], key: str) -> tuple[Optional[tuple[str, str]], bool]:
        value = table.get(key)
        if value is None:
            return None, False
        if value is _AMBIGUOUS:
            return None, True
        assert isinstance(value, tuple)
        return value, False

    def resolve_scientific(self, scientific: str) -> tuple[Optional[tuple[str, str]], bool]:
        key = " ".join(scientific.translate(_HYBRID_SIGNS).casefold().split())
        reference, ambiguous = self._get(self._by_scientific, key)
        if reference or ambiguous:
            return reference, ambiguous
        return self._get(self._by_alias, key)

    def resolve_common(self, label: str) -> tuple[Optional[tuple[str, str]], bool]:
        reference, ambiguous = self._get(self._by_common_exact, label.casefold())
        if reference or ambiguous:
            return reference, ambiguous
        return self._get(self._by_common_normalized, _normalize_common(label))


def map_labels(labels: list[str], label_format: str, resolver: CatalogResolver) -> list[OutputRow]:
    rows: list[OutputRow] = []
    for index, label in enumerate(labels):
        text = label.strip()
        folded = text.casefold()
        if folded == "background":
            rows.append(OutputRow(index, "background", text))
            continue
        if folded == "unknown":
            rows.append(OutputRow(index, "unknown", text))
            continue

        if label_format == "common_name":
            reference, ambiguous = resolver.resolve_common(text)
        else:
            scientific = scientific_name_from_label(text, label_format=label_format)
            reference, ambiguous = resolver.resolve_scientific(scientific or text)

        if reference:
            rows.append(OutputRow(index, "species", text, provider=reference[0], taxon=reference[1]))
        elif ambiguous:
            rows.append(OutputRow(index, "species", text, unresolved="ambiguous after normalization"))
        else:
            rows.append(OutputRow(index, "species", text, unresolved="no catalogue identity"))
    return rows


def _read_labels(labels_dir: Path, labels_sha256: str) -> list[str]:
    path = labels_dir / f"{labels_sha256}.txt"
    if not path.is_file():
        raise SystemExit(f"Label file {labels_sha256}.txt not found in {labels_dir}")
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != labels_sha256:
        raise SystemExit(f"{path} does not match its own name: digest is {actual}")
    return [line.strip() for line in content.decode("utf-8", errors="replace").splitlines() if line.strip()]


def _build_temp_seed() -> Path:
    import build_species_catalog_seed as seed_builder

    staging = Path(tempfile.mkdtemp(prefix="yawamf_mapping_seed_"))
    seed_path = staging / "seed.db"
    col = seed_builder.DEFAULT_COL_CONCEPTS if seed_builder.DEFAULT_COL_CONCEPTS.is_file() else None
    # The synonyms have to be in the seed the mappings are compiled against, or
    # every label still using a superseded name resolves to nothing here while
    # resolving perfectly well at runtime. That is how `Accipiter gentilis`
    # came to be an unmapped output of a model that names it on the tin.
    synonyms = seed_builder.DEFAULT_BIRD_SYNONYMS if seed_builder.DEFAULT_BIRD_SYNONYMS.is_file() else None
    seed_builder.build(
        seed_builder.DEFAULT_REFERENCE,
        seed_path,
        col_concepts_path=col,
        bird_synonyms_path=synonyms,
    )
    return seed_path


def compile_mappings(labels_dir: Path, seed_path: Path) -> dict[str, object]:
    resolver = CatalogResolver(seed_path)
    classifiers = [a for a in registry_artifacts() if a.artifact_kind == "classifier"]

    label_files: dict[str, dict[str, object]] = {}
    compiled: dict[str, LabelFileResult] = {}
    widths: dict[str, int] = {}
    for artifact in classifiers:
        if not artifact.labels_sha256:
            raise SystemExit(f"Classifier artifact '{artifact.artifact_id}' publishes no labels checksum")
        existing = compiled.get(artifact.labels_sha256)
        if existing is not None:
            # A shared label file is compiled once; every artifact sharing it
            # must declare the same grammar or the second one would silently
            # inherit the first's resolution.
            if existing.label_format != artifact.label_format:
                raise SystemExit(
                    f"Artifact '{artifact.artifact_id}' declares label_format '{artifact.label_format}'"
                    f" but label file {artifact.labels_sha256} was compiled as '{existing['label_format']}'"
                )
            continue
        labels = _read_labels(labels_dir, artifact.labels_sha256)
        rows = map_labels(labels, artifact.label_format, resolver)
        widths[artifact.labels_sha256] = len(labels)
        compiled[artifact.labels_sha256] = LabelFileResult(label_format=artifact.label_format, rows=rows)

    # A common name IOC has since renamed or split resolves to nothing on its own,
    # but another model's paired label may already have named the same bird through
    # the scientific path. That is a second pass because it needs every file first.
    bridged = bridge_common_names(compiled)
    # A trinomial is last: the two passes above may already have named it, and this
    # one deliberately settles for the parent species when nothing better fits.
    subspecies = resolve_subspecies(compiled, resolver)

    for labels_sha256, result in compiled.items():
        label_files[labels_sha256] = {
            "label_format": result.label_format,
            "output_width": widths[labels_sha256],
            "outputs": [{key: value for key, value in vars(row).items() if value is not None} for row in result.rows],
        }

    return {
        "bridged_common_names": bridged,
        "resolved_subspecies": subspecies,
        "schema_version": 1,
        "label_files": label_files,
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "model_sha256": artifact.sha256,
                "labels_sha256": artifact.labels_sha256,
                "runtime": artifact.runtime,
            }
            for artifact in classifiers
        ],
    }


def _write_report(report: Path, payload: dict[str, object]) -> None:
    label_files = payload["label_files"]
    assert isinstance(label_files, dict)
    artifacts_by_labels: dict[str, list[str]] = defaultdict(list)
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, list)
    for artifact in artifacts:
        artifacts_by_labels[artifact["labels_sha256"]].append(artifact["artifact_id"])

    lines = [
        "# Model output mapping coverage",
        "",
        "Generated by `backend/scripts/build_model_output_mappings.py`; regenerate rather than edit.",
        "Every supported classifier artifact's output indices, resolved through the seed catalogue",
        "by the artifact's declared label grammar. An index resolves to a canonical species",
        "identity, is a declared non-species class, or is listed here as unresolved. Nothing is",
        "guessed, and an artifact with unresolved species classes is not activatable from the",
        "catalogue until they are resolved or explicitly declared.",
        "",
        "| Label file | Used by | Width | Species mapped | Non-species | Unresolved |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    unresolved_sections: list[str] = []
    for labels_sha256, entry in sorted(label_files.items()):
        outputs = entry["outputs"]
        mapped = sum(1 for row in outputs if row["kind"] == "species" and "taxon" in row)
        declared = sum(1 for row in outputs if row["kind"] != "species")
        unresolved = [row for row in outputs if "unresolved" in row]
        users = ", ".join(f"`{a}`" for a in artifacts_by_labels[labels_sha256])
        lines.append(
            f"| `{labels_sha256[:12]}…` | {users} | {entry['output_width']} | {mapped} | {declared} | {len(unresolved)} |"
        )
        if unresolved:
            names = ", ".join(f"`{row['label']}`" for row in unresolved)
            unresolved_sections += [
                "",
                f"### Unresolved in {users} ({len(unresolved)})",
                "",
                names,
            ]
    lines += unresolved_sections
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", required=True, type=Path, help="directory of <labels_sha256>.txt files")
    parser.add_argument("--seed", type=Path, default=None, help="built seed catalogue; defaults to a fresh build")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    seed_path = args.seed if args.seed else _build_temp_seed()
    payload = compile_mappings(args.labels_dir, seed_path)
    args.output.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _write_report(args.report, payload)

    label_files = payload["label_files"]
    assert isinstance(label_files, dict)
    total = sum(entry["output_width"] for entry in label_files.values())
    unresolved = sum(1 for entry in label_files.values() for row in entry["outputs"] if "unresolved" in row)
    print(f"Mapped {total - unresolved} of {total} outputs across {len(label_files)} label files")
    print(f"Wrote {args.output} and {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
