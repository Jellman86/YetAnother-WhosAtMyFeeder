"""Compile coarse taxonomy independently of canonical species identity.

Only checksum-verified model label mappings provide evidence. Missing or
conflicting evidence stays unknown; the output order of another model is never
borrowed. This compiler performs no file, database or network access.
"""

from collections import defaultdict
import hashlib
import re
from typing import Literal

from app.services.model_taxon_map import scientific_name_from_label

OutputGroup = Literal["bird", "nonbird", "unknown"]
_CHECKSUM = re.compile(r"[a-f0-9]{64}")
_OTHER_KINGDOMS = {"Plantae", "Fungi", "Chromista", "Protozoa", "Bacteria", "Archaea"}
_UNKNOWN_CLASSES = {"", "unknown", "unidentified", "incertae sedis", "incertae_sedis"}


def _verified_file(checksum: str, value: dict) -> list[dict]:
    width, rows = value.get("output_width"), value.get("outputs")
    if (
        not isinstance(checksum, str)
        or not _CHECKSUM.fullmatch(checksum)
        or type(width) is not int
        or not 0 < width <= 100_000
        or not isinstance(rows, list)
        or len(rows) != width
        or any(
            not isinstance(row, dict)
            or type(row.get("index")) is not int
            or row["index"] != index
            or not isinstance(row.get("label"), str)
            or not row["label"]
            or "\n" in row["label"]
            or "\r" in row["label"]
            for index, row in enumerate(rows)
        )
    ):
        raise ValueError("Output groups require complete, ordered and unique label rows")
    encoded = "".join(row["label"] + "\n" for row in rows).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != checksum:
        raise ValueError("Output group label source failed its checksum")
    return rows


def _hierarchy_group(label: str, index: int) -> OutputGroup:
    parts = label.split("_")
    if len(parts) != 8 or parts[0] != f"{index:05d}":
        return "unknown"
    kingdom, taxon_class = parts[1], parts[3]
    if taxon_class.casefold() in _UNKNOWN_CLASSES:
        return "unknown"
    if kingdom == "Animalia":
        return "bird" if taxon_class == "Aves" else "nonbird"
    if kingdom in _OTHER_KINGDOMS and taxon_class != "Aves":
        return "nonbird"
    return "unknown"


def compile_output_groups(value: dict) -> dict[str, dict[int, OutputGroup]]:
    """Return model SHA → output index → positively evidenced coarse group."""
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Unsupported output mapping schema")
    files, artifacts = value.get("label_files"), value.get("artifacts")
    if not isinstance(files, dict) or not isinstance(artifacts, list):
        raise ValueError("Output groups require label files and artifact identities")
    verified = {checksum: _verified_file(checksum, entry) for checksum, entry in files.items()}
    direct: dict[tuple[str, int], set[str]] = defaultdict(set)
    names: dict[str, set[str]] = defaultdict(set)
    row_names: dict[tuple[str, int], set[str]] = defaultdict(set)
    for checksum, rows in verified.items():
        grammar = files[checksum].get("label_format")
        for row in rows:
            if row.get("kind") in {"background", "unknown"}:
                continue
            key = checksum, row["index"]
            scientific = scientific_name_from_label(row["label"], label_format=grammar)
            if scientific:
                row_names[key].add(scientific.casefold())
            if grammar == "scientific_hierarchy":
                group = _hierarchy_group(row["label"], row["index"])
                if group != "unknown":
                    direct[key].add(group)
            if row.get("provider") == "ioc-world-bird-list" and row.get("kind") == "species":
                direct[key].add("bird")
                taxon = scientific_name_from_label(row.get("taxon"), label_format="scientific_binomial")
                if taxon:
                    row_names[key].add(taxon.casefold())
            for name in row_names[key]:
                names[name].update(direct[key])
    compiled = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("Invalid model output artifact")
        model, checksum = artifact.get("model_sha256"), artifact.get("labels_sha256")
        if not isinstance(model, str) or not _CHECKSUM.fullmatch(model) or checksum not in verified:
            raise ValueError("Artifact does not bind a verified label source")
        groups: dict[int, OutputGroup] = {}
        for row in verified[checksum]:
            if row.get("kind") in {"background", "unknown"}:
                groups[row["index"]] = "unknown"
                continue
            key = checksum, row["index"]
            evidence = set(direct[key])
            for name in row_names[key]:
                evidence.update(names[name])
            groups[row["index"]] = next(iter(evidence)) if len(evidence) == 1 else "unknown"
        if model in compiled and compiled[model] != groups:
            raise ValueError("One model checksum cannot bind conflicting output groups")
        compiled[model] = groups
    return compiled
