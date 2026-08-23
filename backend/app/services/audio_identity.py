"""Catalogue identity for an audio detection.

BirdNET-Go reports a scientific name, and a scientific name moves. Measured on
a live install of 56,027 audio detections, 84 of 85 species it reports resolve
to a catalogue identity. The one that does not is `Corvus monedula`, which
IOC 14.2 calls `Coloeus monedula` after the jackdaw genus split: two sources on
opposite sides of one rename, with nothing recording that they are the same
bird.

The rule is the one the detection backfill already follows. A name the
catalogue holds for exactly one species gains that identity; anything
ambiguous, unknown, or unavailable gains nothing and keeps behaving as it does
today. Nothing here guesses.
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

log = structlog.get_logger()


def resolve_audio_identity(scientific_name: Optional[str], *, resolver: Any = None) -> Optional[int]:
    """The catalogue identity for this name, or None to record nothing.

    Never raises. Audio ingest continues whatever the catalogue is doing, since
    a detection without an identity is still a detection worth keeping.
    """
    name = str(scientific_name or "").strip()
    if not name:
        return None

    if resolver is None:
        from app.services.species_catalog_resolver import species_catalog_resolver

        resolver = species_catalog_resolver

    try:
        species_id, _reason = resolver.resolve_scientific_name(name)
    except Exception as error:  # pragma: no cover - defensive
        log.debug("Species catalogue unavailable for audio identity", error=str(error))
        return None
    return int(species_id) if species_id is not None else None
