"""Give synthetic model-mapping fixtures the same label checksums as real bundles."""

import hashlib
import json
from pathlib import Path


def rehash_mapping_fixture(path: Path) -> None:
    payload = json.loads(path.read_text())
    checksums = {}
    verified = {}
    for old, entry in payload["label_files"].items():
        checksum = hashlib.sha256("".join(row["label"] + "\n" for row in entry["outputs"]).encode()).hexdigest()
        checksums[old] = checksum
        verified[checksum] = entry
    payload["label_files"] = verified
    for artifact in payload["artifacts"]:
        artifact["labels_sha256"] = checksums[artifact["labels_sha256"]]
    path.write_text(json.dumps(payload))
