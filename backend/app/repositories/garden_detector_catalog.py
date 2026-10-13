"""Exact detector output semantics in the existing species catalogue."""

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.services.species_catalog_migrations import default_catalog_path
from app.services.species_provenance import load_source_manifest, require_build_source, SourceProvenanceError

PACKAGE_PATH = Path(__file__).parents[1] / "assets" / "garden_md1000_cedar.json"


def read_detector_package(path: Path = PACKAGE_PATH) -> dict[str, Any]:
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    try:
        source = require_build_source(load_source_manifest(), "megadetector-cedar", content_sha256=checksum)
    except SourceProvenanceError as error:
        raise ValueError("Garden detector mapping failed its checksum or licence gate") from error
    package = json.loads(raw)
    if (
        source.version != package["version"]
        or package["schema"] != 1
        or package["names"] != ["animal", "person", "vehicle"]
    ):
        raise ValueError("Garden detector mapping differs from its qualified contract")
    package["mapping_sha256"] = checksum
    return package


class GardenDetectorCatalog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_catalog_path()

    @staticmethod
    def _rows(db: sqlite3.Connection, package: dict[str, Any]) -> list[tuple]:
        identities = db.execute(
            "SELECT DISTINCT species_id FROM species_concepts WHERE scientific_name='Animalia'"
        ).fetchall()
        if len(identities) != 1:
            raise ValueError("Garden detector needs an unambiguous Animalia catalogue identity")
        return [
            (0, "aggregate", identities[0][0], "animal"),
            (1, "background", None, "person"),
            (2, "background", None, "vehicle"),
        ]

    @staticmethod
    def _artifact(db: sqlite3.Connection, package: dict[str, Any]) -> int:
        row = db.execute(
            "SELECT id,registry_id,mapping_set_sha256,output_width,runtime,model_version FROM model_artifacts WHERE model_sha256=?",
            (package["model_sha256"],),
        ).fetchone()
        expected = (package["registry_id"], package["mapping_sha256"], 3, "onnx", package["version"])
        if not row or row[1:] != expected:
            raise ValueError("Garden detector catalogue artifact or mapping is unavailable")
        return row[0]

    def initialize(self, source: Path = PACKAGE_PATH) -> None:
        package = read_detector_package(source)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM model_artifacts WHERE model_sha256=?", (package["model_sha256"],)
            ).fetchone():
                db.execute(
                    "INSERT INTO model_artifacts(registry_id,mapping_set_sha256,output_width,runtime,model_version,model_sha256) VALUES (?,?,3,'onnx',?,?)",
                    (package["registry_id"], package["mapping_sha256"], package["version"], package["model_sha256"]),
                )
            artifact = self._artifact(db, package)
            rows = self._rows(db, package)
            stored = db.execute(
                "SELECT output_index,class_kind,species_id,source_label FROM model_output_taxa WHERE model_artifact_id=? ORDER BY output_index",
                (artifact,),
            ).fetchall()
            if stored and stored != rows:
                raise ValueError("Existing garden detector output mapping differs")
            if not stored:
                db.executemany(
                    "INSERT INTO model_output_taxa(model_artifact_id,output_index,class_kind,species_id,source_label) VALUES (?,?,?,?,?)",
                    [(artifact, *row) for row in rows],
                )

    def load(self) -> dict[str, Any]:
        package = read_detector_package()
        with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True) as db:
            artifact = self._artifact(db, package)
            stored = db.execute(
                "SELECT output_index,class_kind,species_id,source_label FROM model_output_taxa WHERE model_artifact_id=? ORDER BY output_index",
                (artifact,),
            ).fetchall()
            if stored != self._rows(db, package):
                raise ValueError("Garden detector output mapping is missing or changed")
            package["names"] = [row[3] for row in stored]
        return package
