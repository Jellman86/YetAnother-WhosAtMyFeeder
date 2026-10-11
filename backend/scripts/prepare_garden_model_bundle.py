"""Prepare JSON taxonomy for already converted, locally verified SpeciesNet models.

This developer tool downloads nothing. Its input is Google's extracted 4.0.3a/b
releases plus the locally validated single-file ONNX classifier/detector exports.
Model execution and export agreement must be checked separately (#641).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def checksum(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load_taxonomy(path: Path) -> list[dict[str, Any]]:
    result = []
    identities = set()
    for line in path.read_text().splitlines():
        parts = line.split(";")
        if len(parts) != 7 or not parts[0] or parts[0] in identities:
            raise ValueError("Taxonomy requires unique identities and seven semicolon-separated fields")
        identities.add(parts[0])
        result.append({"id": parts[0], "name": parts[6], "ranks": parts[1:6]})
    if not result:
        raise ValueError("Taxonomy is empty")
    return result


def source_file(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Model metadata references a file outside its extracted release")
    return path


def prepare(source: Path, models: Path, countries: list[str]) -> dict[str, Any]:
    if not countries or any(len(code) != 3 or not code.isascii() or not code.isupper() for code in countries):
        raise ValueError("Supply an ISO-3 country registry as a JSON array")
    inputs = []
    for variant in ("4.0.3a", "4.0.3b"):
        root = source / variant
        info = json.loads((root / "info.json").read_text())
        expected_type = "always_crop" if variant == "4.0.3a" else "full_image"
        if info["version"] != variant or info["type"] != expected_type:
            raise ValueError("Unexpected SpeciesNet release or preprocessing type")
        inputs.append(
            {
                "outputs": load_taxonomy(source_file(root, info["classifier_labels"])),
                "taxonomy": load_taxonomy(source_file(root, info["taxonomy"])),
                "geofence": json.loads(source_file(root, info["geofence"]).read_text()),
            }
        )
    if inputs[0] != inputs[1] or len(inputs[0]["outputs"]) != 2498:
        raise ValueError("SpeciesNet variants must agree on taxonomy, order and geofence")
    return {
        "schema": 1,
        "version": "4.0.3",
        "license": "Apache-2.0",
        **inputs[0],
        "countries": sorted(set(countries)),
        "model_sha256": {v: checksum(models / (v + ".onnx")) for v in ("4.0.3a", "4.0.3b")},
        "detector_sha256": {str(s): checksum(models / f"mdv6-compact-{s}.onnx") for s in (640, 1280)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--countries", type=Path, required=True)
    args = parser.parse_args()
    bundle = prepare(args.source, args.models, json.loads(args.countries.read_text()))
    with (args.models / "speciesnet.json").open("x") as output:
        json.dump(bundle, output)


if __name__ == "__main__":
    main()
