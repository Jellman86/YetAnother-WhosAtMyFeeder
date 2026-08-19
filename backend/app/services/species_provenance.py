"""The frozen contract for where species data may come from.

`app/assets/species_sources.json` records every source the species catalogue
is allowed to touch: its pinned release, licence, citation, and an explicit
redistribution decision. Build tooling must pass through `require_build_source`
before consuming a source, so a build that names a source outside the manifest
— or an input file that is not the pinned release — fails instead of
proceeding. That is the Phase 0 provenance gate of
docs/plans/2026-08-12-versioned-species-catalogue-design.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: What may be done with a source's data. `bundled` ships inside the image,
#: `build-input` feeds the catalogue builder but is not redistributed verbatim,
#: `runtime-fetch` is fetched per installation under the owner's own key, and
#: `forbidden` records a deliberate decision not to redistribute at all.
REDISTRIBUTION_DECISIONS = frozenset({"bundled", "build-input", "runtime-fetch", "forbidden"})

#: Decisions that permit a source to feed a catalogue build.
_BUILD_DECISIONS = frozenset({"bundled", "build-input"})

_UNSPECIFIED_LICENCE = "unspecified"


class SourceProvenanceError(Exception):
    """A species-data source failed the provenance gate."""


@dataclass(frozen=True)
class SpeciesSource:
    id: str
    name: str
    role: str
    url: str
    licence: str
    citation: str
    redistribution: str
    version: Optional[str] = None
    content_sha256: Optional[str] = None
    notes: Optional[str] = None


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "species_sources.json"


def _required(raw: dict, key: str, source_id: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise SourceProvenanceError(f"Source '{source_id}' has no {key}")
    return value


def load_source_manifest(path: Optional[Path] = None) -> dict[str, SpeciesSource]:
    """Load and validate the manifest, or raise `SourceProvenanceError`.

    Validation is structural and deliberate: a duplicate id, a missing licence
    or citation, or an unknown redistribution decision is a broken contract,
    not a warning.
    """
    manifest_path = path or default_manifest_path()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SourceProvenanceError(f"Source manifest unreadable at {manifest_path}: {error}") from error

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SourceProvenanceError("Source manifest must declare schema_version 1")

    sources: dict[str, SpeciesSource] = {}
    for raw in payload.get("sources") or []:
        if not isinstance(raw, dict):
            raise SourceProvenanceError("Source entries must be objects")
        source_id = _required(raw, "id", str(raw.get("id") or "<missing id>"))
        if source_id in sources:
            raise SourceProvenanceError(f"Source manifest has a duplicate id: '{source_id}'")

        redistribution = _required(raw, "redistribution", source_id)
        if redistribution not in REDISTRIBUTION_DECISIONS:
            raise SourceProvenanceError(
                f"Source '{source_id}' has an unknown redistribution decision '{redistribution}'"
            )

        licence = _required(raw, "licence", source_id)
        if licence == _UNSPECIFIED_LICENCE and redistribution != "forbidden":
            raise SourceProvenanceError(
                f"Source '{source_id}' has no explicit licence; only a 'forbidden' source may record that"
            )

        version = str(raw.get("version") or "").strip() or None
        if redistribution in _BUILD_DECISIONS and not version:
            raise SourceProvenanceError(f"Source '{source_id}' is a build source and must pin a version")

        content_sha256 = str(raw.get("content_sha256") or "").strip().lower() or None
        if content_sha256 and len(content_sha256) != 64:
            raise SourceProvenanceError(f"Source '{source_id}' has a malformed content_sha256")

        sources[source_id] = SpeciesSource(
            id=source_id,
            name=_required(raw, "name", source_id),
            role=_required(raw, "role", source_id),
            url=_required(raw, "url", source_id),
            licence=licence,
            citation=_required(raw, "citation", source_id),
            redistribution=redistribution,
            version=version,
            content_sha256=content_sha256,
            notes=str(raw.get("notes") or "").strip() or None,
        )
    if not sources:
        raise SourceProvenanceError("Source manifest lists no sources")
    return sources


def require_build_source(
    sources: dict[str, SpeciesSource],
    source_id: str,
    *,
    content_sha256: Optional[str] = None,
) -> SpeciesSource:
    """Admit a source into a catalogue build, or raise `SourceProvenanceError`.

    An unknown source, a source whose redistribution decision does not permit
    building, or an input file that is not the pinned release all fail closed.
    A source pinned only by release identifier (no checksum yet, e.g. a DOI-
    pinned download that has not been fetched) passes the content check but
    still gates licence and redistribution.
    """
    source = sources.get(str(source_id or "").strip())
    if source is None:
        raise SourceProvenanceError(f"Source '{source_id}' is not in the source manifest; refusing to build from it")

    if source.redistribution not in _BUILD_DECISIONS:
        raise SourceProvenanceError(
            f"Source '{source.id}' has redistribution decision '{source.redistribution}' and may not feed a build"
        )

    supplied = str(content_sha256 or "").strip().lower() or None
    if source.content_sha256 and supplied and supplied != source.content_sha256:
        raise SourceProvenanceError(
            f"Input for source '{source.id}' does not match the pinned checksum: "
            f"expected {source.content_sha256}, got {supplied}. "
            "Update species_sources.json deliberately if this is a new release."
        )
    return source
