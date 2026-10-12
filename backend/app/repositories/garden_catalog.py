"""Checksum-bound garden outputs and geofences live in the species catalogue.

These synchronous SQLite operations run only in worker threads/processes.
Existing catalogue names, parents, releases and owner overrides are never rewritten.
"""

import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.services.species_catalog_migrations import default_catalog_path
from app.services.species_provenance import load_source_manifest, require_build_source, SourceProvenanceError

PACKAGE_PATH = Path(__file__).parents[1] / "assets" / "garden_speciesnet_4.0.3.json.gz"


def read_shipped_package(path: Path = PACKAGE_PATH) -> tuple[bytes, str]:
    raw = gzip.decompress(path.read_bytes())
    checksum = hashlib.sha256(raw).hexdigest()
    try:
        source = require_build_source(load_source_manifest(), "google-speciesnet", content_sha256=checksum)
    except SourceProvenanceError as error:
        raise ValueError("Garden package failed its source checksum or licence gate") from error
    if source.version != "4.0.3":
        raise ValueError("Unsupported garden package version")
    return raw, checksum


def taxon_identity(value: dict[str, Any]) -> tuple[str, str] | None:
    ranks = value["ranks"]
    if value["name"] == "animal":
        return "Animalia", "kingdom"
    if not ranks[0] or ranks[0] == "no cv result":
        return None
    for index, rank in reversed(list(enumerate(("class", "order", "family", "genus", "species")))):
        if ranks[index]:
            scientific = f"{ranks[3].capitalize()} {ranks[4]}" if index == 4 else ranks[index].capitalize()
            return scientific, rank
    return None


class GardenCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_catalog_path()

    def initialize(self, source: Path = PACKAGE_PATH) -> None:
        raw, checksum = read_shipped_package(source)
        package = json.loads(raw)
        if package["schema"] != 1 or len(package["outputs"]) != 2498:
            raise ValueError("Unexpected garden package output mapping")
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM garden_model_packages WHERE sha256=?", (checksum,)).fetchone():
                return
            db.execute("INSERT INTO garden_model_packages(sha256,payload) VALUES (?,?)", (checksum, raw.decode()))
            bindings: dict[str, int | None] = {}
            created: set[int] = set()
            # Three upstream output UUIDs differ from the taxonomy UUID for the
            # same full lineage. Preserve both source identities and resolve
            # their canonical identity by the same exact-name/rank rule.
            taxa = {taxon["id"]: taxon for taxon in [*package["taxonomy"], *package["outputs"]]}
            for taxon in taxa.values():
                identity = taxon_identity(taxon)
                species_id = None
                if identity:
                    scientific, rank = identity
                    source_identity = db.execute(
                        "SELECT c.species_id,c.scientific_name,s.rank,s.status FROM species_concepts c "
                        "JOIN species s USING(species_id) WHERE c.provider='google-speciesnet' "
                        "AND c.source_release='4.0.3' AND c.provider_taxon_id=?",
                        (taxon["id"],),
                    ).fetchone()
                    if source_identity:
                        if source_identity[1].casefold() != scientific.casefold() or source_identity[2:] != (
                            rank,
                            "accepted",
                        ):
                            raise ValueError("Existing garden source identity differs from its pinned taxonomy")
                        known = [(source_identity[0],)]
                    else:
                        known = db.execute(
                            "SELECT DISTINCT c.species_id FROM species_concepts c JOIN species s USING(species_id) "
                            "WHERE c.scientific_name=? COLLATE NOCASE AND s.rank=? AND s.status='accepted'",
                            (scientific, rank),
                        ).fetchall()
                    if len(known) == 1:
                        species_id = known[0][0]
                    elif not known:
                        species_id = db.execute(
                            "INSERT INTO species(rank,status) VALUES (?,'accepted')", (rank,)
                        ).lastrowid
                        created.add(species_id)
                    if species_id is not None:
                        db.execute(
                            "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) "
                            "VALUES (?,'google-speciesnet',?,'4.0.3',?) "
                            "ON CONFLICT(provider,source_release,provider_taxon_id) DO NOTHING",
                            (species_id, taxon["id"], scientific),
                        )
                        db.execute(
                            "INSERT OR IGNORE INTO species_names(species_id,language_tag,name,name_kind,preferred,provider,source_release) "
                            "SELECT ?,'en',?,'vernacular',0,'google-speciesnet','4.0.3' WHERE NOT EXISTS "
                            "(SELECT 1 FROM species_names WHERE species_id=? AND language_tag='en')",
                            (species_id, taxon["name"], species_id),
                        )
                bindings[taxon["id"]] = species_id
                db.execute(
                    "INSERT INTO garden_taxon_bindings(package_sha256,taxon_id,species_id) VALUES (?,?,?)",
                    (checksum, taxon["id"], species_id),
                )
            by_key = {tuple(taxon["ranks"]): bindings[taxon["id"]] for taxon in taxa.values() if taxon_identity(taxon)}
            for taxon in taxa.values():
                species_id = bindings[taxon["id"]]
                ranks = taxon["ranks"]
                if species_id not in created or not any(ranks):
                    continue
                depth = max(index for index, value in enumerate(ranks) if value)
                parent = next(
                    (
                        by_key[key]
                        for size in range(depth, -1, -1)
                        if (key := tuple(ranks[:size] + [""] * (5 - size))) in by_key and by_key[key] is not None
                    ),
                    None,
                )
                db.execute("UPDATE species SET parent_species_id=? WHERE species_id=?", (parent, species_id))
            mapping_hash = hashlib.sha256(json.dumps(package["outputs"], sort_keys=True).encode()).hexdigest()
            for variant, model_hash in package["model_sha256"].items():
                existing = db.execute(
                    "SELECT id,registry_id,mapping_set_sha256,output_width,runtime,model_version "
                    "FROM model_artifacts WHERE model_sha256=?",
                    (model_hash,),
                ).fetchone()
                expected_header = (f"garden/speciesnet-{variant}", mapping_hash, 2498, "onnx", variant)
                if existing and existing[1:] != expected_header:
                    raise ValueError("Existing garden artifact differs from its pinned mapping")
                artifact_id = (
                    existing[0]
                    if existing
                    else db.execute(
                        "INSERT INTO model_artifacts(registry_id,mapping_set_sha256,output_width,runtime,model_version,model_sha256) "
                        "VALUES (?,?,?,?,?,?)",
                        (*expected_header, model_hash),
                    ).lastrowid
                )
                rows = []
                for index, taxon in enumerate(package["outputs"]):
                    species_id = bindings[taxon["id"]]
                    identity = taxon_identity(taxon)
                    kind = ("species" if identity[1] == "species" else "aggregate") if identity else "background"
                    if identity and species_id is None:
                        kind = "unknown"
                    rows.append((index, kind, species_id, taxon["name"]))
                if existing:
                    stored = db.execute(
                        "SELECT output_index,class_kind,species_id,source_label FROM model_output_taxa "
                        "WHERE model_artifact_id=? ORDER BY output_index",
                        (artifact_id,),
                    ).fetchall()
                    if stored != rows:
                        raise ValueError("Existing garden output identities differ from their pinned mapping")
                else:
                    db.executemany(
                        "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,species_id,source_label) "
                        "VALUES (?,?,?,?,?)",
                        [(artifact_id, *row) for row in rows],
                    )

    def load(self) -> dict[str, Any]:
        expected = load_source_manifest()["google-speciesnet"].content_sha256
        with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as db:
            row = db.execute("SELECT payload FROM garden_model_packages WHERE sha256=?", (expected,)).fetchone()
            if row is None or hashlib.sha256(row[0].encode()).hexdigest() != expected:
                raise ValueError("Garden catalogue package is missing or changed")
            bundle = json.loads(row[0])
            bundle["package_sha256"] = expected
            bundle["bindings"] = dict(
                db.execute("SELECT taxon_id,species_id FROM garden_taxon_bindings WHERE package_sha256=?", (expected,))
            )
            expected_ids = {v["id"] for v in [*bundle["taxonomy"], *bundle["outputs"]]}
            if set(bundle["bindings"]) != expected_ids:
                raise ValueError("Garden catalogue bindings are incomplete")
            return bundle
