"""Generate GitHub Release model sidecars from the application registry.

The current registry is the reviewed source of truth for preprocessing, crop
policy, and provider compatibility. Publishing sidecars from the same source
prevents an older release asset from hiding a newly validated provider or
re-enabling a provider that the application has since withdrawn. Retired
pre-3.0 assets are intentionally outside this generator and remain untouched
until their documented 3.0 removal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.model_manager import REMOTE_REGISTRY, model_manager  # noqa: E402


def _release_filename(model_config_url: Any) -> str:
    url = str(model_config_url or "").strip()
    filename = Path(urlparse(url).path).name
    if not filename.endswith("_model_config.json"):
        raise ValueError(f"registry model_config_url does not name a release sidecar: {url or '<missing>'}")
    return filename


def _release_payload(model_meta: dict[str, Any]) -> dict[str, Any]:
    payload = model_manager._build_model_config_payload(model_meta)
    artifact_kind = str(model_meta.get("artifact_kind") or "classifier").strip().lower()
    payload["artifact_kind"] = artifact_kind
    taxonomy_scope = str(model_meta.get("taxonomy_scope") or "").strip()
    if taxonomy_scope:
        payload["taxonomy_scope"] = taxonomy_scope
    if artifact_kind != "classifier":
        payload.pop("crop_generator", None)
        payload.pop("label_grouping", None)
    return payload


def build_release_model_configs(
    registry: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ``release filename -> canonical sidecar`` for every registry asset."""

    configs: dict[str, dict[str, Any]] = {}
    for registry_entry in registry or REMOTE_REGISTRY:
        variants = registry_entry.get("region_variants") or {}
        model_metas = (
            [model_manager._merge_family_variant_meta(registry_entry, region=region) for region in sorted(variants)]
            if variants
            else [dict(registry_entry)]
        )
        for model_meta in model_metas:
            filename = _release_filename(model_meta.get("model_config_url"))
            if filename in configs:
                raise ValueError(f"duplicate release sidecar filename in registry: {filename}")
            configs[filename] = _release_payload(model_meta)
    return dict(sorted(configs.items()))


def write_release_model_configs(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, payload in build_release_model_configs().items():
        path = output_dir / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="Directory that will receive release-ready JSON sidecars")
    args = parser.parse_args()
    written = write_release_model_configs(args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "files": [path.name for path in written]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
