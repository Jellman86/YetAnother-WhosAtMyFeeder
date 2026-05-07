"""Build the species panel for a model-evaluation run.

Combines a hand-curated shared-core list (50 common feeder birds) with a
region-aware list of species observed near the user's configured location,
sourced from iNaturalist's species_counts endpoint (which already returns
taxon IDs, sidestepping a separate species-code → taxa_id lookup).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

log = structlog.get_logger()

INAT_SPECIES_COUNTS_URL = "https://api.inaturalist.org/v1/observations/species_counts"
INAT_TAXA_URL = "https://api.inaturalist.org/v1/taxa"
INAT_BIRDS_TAXON_ID = 3  # iNat: Aves

SHARED_CORE_PATH = Path(__file__).parent / "shared_core_species.json"

DEFAULT_REGIONAL_COUNT = 150
DEFAULT_REGION_RADIUS_KM = 100


@dataclass
class SpeciesEntry:
    taxa_id: int
    scientific_name: str
    common_name: str
    panel: str  # "shared_core" | "regional"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_shared_core_seed() -> list[dict[str, Any]]:
    """Load the hand-curated species list from disk. taxa_id may be missing."""
    with open(SHARED_CORE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("species") or [])


async def _resolve_taxa_id_from_inat(
    client: httpx.AsyncClient, scientific_name: str
) -> Optional[int]:
    if not scientific_name:
        return None
    try:
        resp = await client.get(
            INAT_TAXA_URL,
            params={"q": scientific_name, "rank": "species", "per_page": 1},
            timeout=15.0,
        )
        resp.raise_for_status()
        results = (resp.json() or {}).get("results") or []
        if not results:
            return None
        candidate = results[0]
        # Prefer exact scientific-name match when available.
        candidate_name = (candidate.get("name") or "").strip().lower()
        if candidate_name and candidate_name != scientific_name.strip().lower():
            return None
        return int(candidate["id"]) if candidate.get("id") else None
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("eval_panel_taxa_lookup_failed", name=scientific_name, error=str(e))
        return None


async def resolve_shared_core(
    client: httpx.AsyncClient,
    seed: Optional[list[dict[str, Any]]] = None,
) -> list[SpeciesEntry]:
    """Take the hand-curated seed and ensure every entry has a taxa_id."""
    rows = seed if seed is not None else load_shared_core_seed()
    out: list[SpeciesEntry] = []
    for row in rows:
        sci = (row.get("scientific_name") or "").strip()
        common = (row.get("common_name") or "").strip()
        taxa_id = row.get("taxa_id")
        if not taxa_id:
            taxa_id = await _resolve_taxa_id_from_inat(client, sci)
        if not taxa_id:
            log.info("eval_panel_skipped_unresolved", scientific_name=sci)
            continue
        out.append(SpeciesEntry(
            taxa_id=int(taxa_id),
            scientific_name=sci,
            common_name=common,
            panel="shared_core",
        ))
    return out


async def fetch_regional_species(
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
    radius_km: int = DEFAULT_REGION_RADIUS_KM,
    count: int = DEFAULT_REGIONAL_COUNT,
) -> list[SpeciesEntry]:
    """Pull most-observed bird species near a coordinate from iNaturalist."""
    try:
        resp = await client.get(
            INAT_SPECIES_COUNTS_URL,
            params={
                "lat": latitude,
                "lng": longitude,
                "radius": radius_km,
                "taxon_id": INAT_BIRDS_TAXON_ID,
                "quality_grade": "research",
                "per_page": min(count, 500),
                "rank": "species",
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
    except httpx.HTTPError as e:
        log.warning("eval_panel_regional_fetch_failed", error=str(e))
        return []

    out: list[SpeciesEntry] = []
    for row in payload.get("results", []) or []:
        if len(out) >= count:
            break
        taxon = row.get("taxon") or {}
        tid = taxon.get("id")
        sci = taxon.get("name")
        common = taxon.get("preferred_common_name") or taxon.get("english_common_name") or ""
        if not tid or not sci:
            continue
        out.append(SpeciesEntry(
            taxa_id=int(tid),
            scientific_name=str(sci),
            common_name=str(common),
            panel="regional",
        ))
    return out


def merge_panel(
    shared_core: list[SpeciesEntry],
    regional: list[SpeciesEntry],
) -> list[SpeciesEntry]:
    """Concatenate shared core with regional, dropping regional duplicates of the core."""
    by_taxa: dict[int, SpeciesEntry] = {}
    for entry in shared_core:
        by_taxa[entry.taxa_id] = entry
    for entry in regional:
        if entry.taxa_id in by_taxa:
            continue
        by_taxa[entry.taxa_id] = entry
    return list(by_taxa.values())


async def build_panel(
    *,
    latitude: Optional[float],
    longitude: Optional[float],
    radius_km: int = DEFAULT_REGION_RADIUS_KM,
    regional_count: int = DEFAULT_REGIONAL_COUNT,
    client: Optional[httpx.AsyncClient] = None,
) -> list[SpeciesEntry]:
    """Build the full species panel: shared core + region extension.

    If lat/lng are unset, the panel falls back to the shared core only.
    """
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=30.0)
    try:
        core = await resolve_shared_core(client)
        regional: list[SpeciesEntry] = []
        if latitude is not None and longitude is not None:
            regional = await fetch_regional_species(
                client,
                latitude=float(latitude),
                longitude=float(longitude),
                radius_km=radius_km,
                count=regional_count,
            )
        return merge_panel(core, regional)
    finally:
        if owns_client:
            await client.aclose()
