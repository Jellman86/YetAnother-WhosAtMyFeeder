"""Build the seed release of the species catalogue database.

The seed is the catalogue a fresh installation starts from: a fully migrated
`species_catalog.db` holding one *active* release built from the committed,
digest-verified `species_reference.db` (IOC World Bird List). The input is
admitted through the Phase 0 provenance gate — the reference's recorded source
digest must match the release `species_sources.json` pins — so the chain runs
manifest → reference → catalogue with no unpinned step.

The build is reproducible: rows are inserted in a deterministic order, the
release timestamp comes from the manifest's freeze date rather than the clock,
and the file is vacuumed, so the same input produces a byte-identical file and
the recorded digest can be checked rather than trusted.

Usage:
    python scripts/build_species_catalog_seed.py [--reference PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.species_catalog_migrations import upgrade_catalog  # noqa: E402
from app.services.species_catalog_release import release_content_digest  # noqa: E402
from app.services.species_provenance import (  # noqa: E402
    SourceProvenanceError,
    default_manifest_path,
    load_source_manifest,
    require_build_source,
)

SOURCE_NAME = "ioc-world-bird-list"
COL_SOURCE_NAME = "catalogue-of-life"
DEFAULT_REFERENCE = _BACKEND_DIR / "app" / "assets" / "species_reference.db"
DEFAULT_COL_CONCEPTS = _BACKEND_DIR / "app" / "assets" / "col_nonbird_concepts.json"
DEFAULT_BIRD_SYNONYMS = _BACKEND_DIR / "app" / "assets" / "col_bird_synonyms.json"
DEFAULT_MODEL_MAPPINGS = _BACKEND_DIR / "app" / "assets" / "model_output_mappings.json"
DEFAULT_OUTPUT = _BACKEND_DIR / "app" / "assets" / "species_catalog_seed.db"
_ENGLISH_TAG = "en"


def _reference_rows(reference_path: Path) -> tuple[dict[str, str], list[tuple[int, str, str | None]], dict[int, list]]:
    """The reference's provenance metadata, taxa, and localized names, in stable order."""
    connection = sqlite3.connect(f"file:{reference_path}?mode=ro", uri=True)
    try:
        meta = dict(connection.execute("SELECT key, value FROM reference_meta").fetchall())
        taxa = connection.execute("SELECT id, scientific_name, common_name FROM taxon ORDER BY id").fetchall()
        names: dict[int, list] = {}
        for taxon_id, locale, name in connection.execute(
            "SELECT taxon_id, locale, common_name FROM taxon_name ORDER BY taxon_id, locale"
        ):
            names.setdefault(taxon_id, []).append((locale, name))
    finally:
        connection.close()
    return meta, taxa, names


def _frozen_on(manifest_path: Path | None) -> str:
    payload = json.loads((manifest_path or default_manifest_path()).read_text(encoding="utf-8"))
    frozen = str(payload.get("frozen_on") or "").strip()
    if not frozen:
        raise SystemExit("The source manifest records no frozen_on date; the seed timestamp must be deterministic")
    return f"{frozen}T00:00:00Z"


def _source_record(source) -> dict[str, object]:
    return {
        "id": source.id,
        "version": source.version,
        "licence": source.licence,
        "citation": source.citation,
        "url": source.url,
        "redistribution": source.redistribution,
        "content_sha256": source.content_sha256,
    }


def build(
    reference_path: Path,
    output_path: Path,
    *,
    manifest_path: Path | None = None,
    col_concepts_path: Path | None = None,
    bird_synonyms_path: Path | None = None,
    model_mappings_path: Path | None = None,
) -> str:
    meta, taxa, names = _reference_rows(reference_path)
    if not taxa:
        raise SystemExit(f"No taxa found in {reference_path}")

    manifest = load_source_manifest(manifest_path)
    try:
        source = require_build_source(manifest, SOURCE_NAME, content_sha256=str(meta.get("source_sha256") or ""))
    except SourceProvenanceError as error:
        raise SystemExit(f"Provenance gate refused the build: {error}") from error

    col_source = None
    col_concepts: dict[str, object] = {}
    if col_concepts_path is not None:
        col_concepts = json.loads(Path(col_concepts_path).read_text(encoding="utf-8"))
        recorded = str((col_concepts.get("source") or {}).get("export_sha256") or "")
        try:
            col_source = require_build_source(manifest, COL_SOURCE_NAME, content_sha256=recorded)
        except SourceProvenanceError as error:
            raise SystemExit(f"Provenance gate refused the build: {error}") from error

    generated_at = _frozen_on(manifest_path)
    sources = [_source_record(source)] + ([_source_record(col_source)] if col_source else [])
    source_manifest = json.dumps({"sources": sources}, sort_keys=True)

    if output_path.exists():
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    upgrade_catalog(output_path)

    connection = sqlite3.connect(output_path)
    concept_species: dict[tuple[str, str], int] = {}
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for species_id, (_, scientific, english) in enumerate(taxa, start=1):
            connection.execute(
                "INSERT INTO species (species_id, rank, status) VALUES (?, 'species', 'accepted')", (species_id,)
            )
            connection.execute(
                "INSERT INTO species_concepts"
                " (species_id, provider, provider_taxon_id, source_release, scientific_name)"
                " VALUES (?, ?, ?, ?, ?)",
                (species_id, source.id, scientific, source.version, scientific),
            )
            concept_species[(source.id, scientific)] = species_id

            localized = names.get(taxa[species_id - 1][0], [])
            rows = ([(_ENGLISH_TAG, english)] if english else []) + localized
            for language_tag, name in rows:
                connection.execute(
                    "INSERT INTO species_names"
                    " (species_id, language_tag, name, name_kind, preferred, provider, source_release)"
                    " VALUES (?, ?, ?, 'vernacular', 1, ?, ?)",
                    (species_id, language_tag, name, source.id, source.version),
                )

        # Bird synonyms, from the same pinned Catalogue of Life release that
        # supplies non-bird taxonomy. IOC keeps ownership of bird names; this
        # records only that a species has been called something else, which
        # IOC's multilingual export does not carry. Without it a renamed taxon
        # counts twice: BirdNET reports `Corvus monedula` where IOC 14.2 says
        # `Coloeus monedula`, and nothing joined them.
        if bird_synonyms_path is not None:
            synonyms = json.loads(Path(bird_synonyms_path).read_text(encoding="utf-8"))
            # Reuse the mapping the IOC pass already built rather than
            # reconstructing it, so the two cannot drift apart.
            by_accepted = {
                scientific.casefold(): species_id
                for (provider, scientific), species_id in concept_species.items()
                if provider == source.id
            }
            written = 0
            for entry in synonyms.get("synonyms") or []:
                alias = str(entry.get("alias") or "").strip()
                accepted = str(entry.get("accepted") or "").strip()
                species_id = by_accepted.get(accepted.casefold())
                # Fail closed: an alias naming a species this build does not
                # hold is dropped rather than attached to a guess.
                if not alias or species_id is None:
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO species_aliases (alias, alias_kind, species_id, resolution, source)"
                    " VALUES (?, 'synonym', ?, 'resolved', ?)",
                    (alias, species_id, "catalogue-of-life"),
                )
                written += 1
            print(f"  bird synonyms recorded: {written}", file=sys.stderr)

        if col_source is not None:
            next_species_id = len(taxa) + 1
            # Several model classes can resolve to one accepted taxon when the
            # taxonomy has lumped them since the model was trained; they share
            # one species identity, exactly as the design's mapping policy says.
            species_by_accepted_id: dict[str, int] = {}
            for entry in col_concepts.get("concepts") or []:
                species_id = species_by_accepted_id.get(entry["accepted_col_id"])
                if species_id is None:
                    species_id = next_species_id
                    next_species_id += 1
                    species_by_accepted_id[entry["accepted_col_id"]] = species_id
                    connection.execute(
                        "INSERT INTO species (species_id, rank, status) VALUES (?, 'species', 'accepted')",
                        (species_id,),
                    )
                    connection.execute(
                        "INSERT INTO species_concepts"
                        " (species_id, provider, provider_taxon_id, source_release, scientific_name, status)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            species_id,
                            col_source.id,
                            entry["accepted_col_id"],
                            col_source.version,
                            entry["accepted_scientific_name"],
                            "accepted",
                        ),
                    )
                    concept_species[(col_source.id, entry["accepted_col_id"])] = species_id
                # A class resolved through a synonym keeps its label text
                # reachable: the alias records that Catalogue of Life reads
                # the label's name as this accepted taxon.
                if entry["col_status"] == "synonym":
                    connection.execute(
                        "INSERT INTO species_aliases (alias, alias_kind, species_id, resolution, source)"
                        " VALUES (?, 'synonym', ?, 'resolved', ?)",
                        (entry["scientific_name"], species_id, col_source.id),
                    )
            for entry in col_concepts.get("unresolved") or []:
                connection.execute(
                    "INSERT INTO species_aliases (alias, alias_kind, species_id, resolution, source)"
                    " VALUES (?, 'model_label', NULL, 'unresolved', ?)",
                    (entry["scientific_name"], col_source.id),
                )

        if model_mappings_path is not None:
            mappings = json.loads(Path(model_mappings_path).read_text(encoding="utf-8"))
            label_files = mappings.get("label_files") or {}
            for artifact in sorted(mappings.get("artifacts") or [], key=lambda a: str(a["artifact_id"])):
                entry = label_files.get(artifact["labels_sha256"])
                if entry is None:
                    raise SystemExit(
                        f"Mapping artifact '{artifact['artifact_id']}' references label file"
                        f" {artifact['labels_sha256']} which the mappings record does not carry"
                    )
                mapping_digest = hashlib.sha256()
                for row in entry["outputs"]:
                    mapping_digest.update(
                        f"{row['index']}|{row['kind']}|{row.get('provider', '')}"
                        f"|{row.get('taxon', '')}|{row['label']}\n".encode()
                    )
                cursor = connection.execute(
                    "INSERT INTO model_artifacts"
                    " (registry_id, model_sha256, mapping_set_sha256, output_width, runtime)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        artifact["artifact_id"],
                        artifact["model_sha256"],
                        mapping_digest.hexdigest(),
                        entry["output_width"],
                        artifact["runtime"],
                    ),
                )
                artifact_row_id = cursor.lastrowid
                for row in entry["outputs"]:
                    if "unresolved" in row:
                        # An output nothing could resolve still gets a row, so
                        # the catalogue knows what the model calls it even when
                        # it cannot say what it is. Without that the label text
                        # existed only in `labels.txt`, which is what stopped
                        # that file being retired.
                        #
                        # It is recorded as `unknown`, and coverage counts
                        # identified outputs rather than rows, so the artifact
                        # stays incomplete and unactivatable exactly as before.
                        connection.execute(
                            "INSERT INTO model_output_taxa"
                            " (model_artifact_id, output_index, class_kind, species_id, source_label)"
                            " VALUES (?, ?, 'unknown', NULL, ?)",
                            (artifact_row_id, row["index"], row["label"]),
                        )
                        continue
                    species_id = None
                    if row["kind"] == "species":
                        species_id = concept_species.get((row["provider"], row["taxon"]))
                        if species_id is None:
                            raise SystemExit(
                                f"Mapping for '{artifact['artifact_id']}' references concept"
                                f" ({row['provider']}, {row['taxon']}) which this catalogue does not hold;"
                                " regenerate model_output_mappings.json against the current sources"
                            )
                    connection.execute(
                        "INSERT INTO model_output_taxa"
                        " (model_artifact_id, output_index, class_kind, species_id, source_label)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (artifact_row_id, row["index"], row["kind"], species_id, row["label"]),
                    )

        connection.execute(
            "INSERT INTO catalogue_releases"
            " (schema_version, source_manifest, content_sha256, generated_at, state)"
            " VALUES (1, ?, ?, ?, 'active')",
            (
                source_manifest,
                release_content_digest(
                    connection, schema_version=1, source_manifest=source_manifest, generated_at=generated_at
                ),
                generated_at,
            ),
        )
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    sidecar = output_path.with_suffix(output_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {output_path.name}\n", encoding="utf-8")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--col-concepts", type=Path, default=DEFAULT_COL_CONCEPTS)
    parser.add_argument("--bird-synonyms", type=Path, default=DEFAULT_BIRD_SYNONYMS)
    parser.add_argument("--model-mappings", type=Path, default=DEFAULT_MODEL_MAPPINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    col_concepts = args.col_concepts if args.col_concepts.is_file() else None
    bird_synonyms = args.bird_synonyms if args.bird_synonyms.is_file() else None
    model_mappings = args.model_mappings if args.model_mappings.is_file() else None
    digest = build(
        args.reference,
        args.output,
        col_concepts_path=col_concepts,
        bird_synonyms_path=bird_synonyms,
        model_mappings_path=model_mappings,
    )
    size_mb = args.output.stat().st_size / 1024 / 1024
    print(f"Wrote {args.output} ({size_mb:.2f} MB)")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
