"""Map the models whose labels are common names only.

`flexivit_il_all` and the European models carry no scientific name in their
labels, so nothing can be derived from the file alone and they map at zero. A
common name resolves to a scientific one against sources already present: the
bundled reference first, which needs no network, then eBird.

Done once per label file rather than per detection. Resolving 700 names on the
event path against a free community service is the load the original design
rejected, and that reasoning has not changed.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from app.services.label_integrity import LabelCheck, LabelVerdict
from app.services.model_taxon_map import ModelTaxonMap, model_taxon_map
from app.services.species_reference import species_reference

log = structlog.get_logger()


async def _ebird_common_name_index() -> dict[str, str]:
    """Common name to scientific name, for real species only.

    `get_taxonomy` also returns subspecies, `spuh` and `slash` forms for its own
    callers. A classifier cannot emit `Mallard/Black Duck`, and offering it as a
    species would put a pair label into history as an identity.
    """
    from app.services.ebird_service import ebird_service

    try:
        items = await ebird_service.get_taxonomy("en")
    except Exception as error:
        log.warning("Could not fetch eBird taxonomy for label enrichment", error=str(error))
        return {}

    index: dict[str, str] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("category") or "species") != "species":
            continue
        common = str(item.get("comName") or "").strip()
        scientific = str(item.get("sciName") or "").strip()
        if common and scientific:
            index.setdefault(common.casefold(), scientific)
    return index


async def resolve_common_name(
    common_name: Optional[str],
    *,
    ebird_index: Optional[dict[str, str]] = None,
) -> Optional[str]:
    """Turn a common name into a scientific one, or None if no source knows it."""
    name = str(common_name or "").strip()
    if not name:
        return None

    hit = await asyncio.to_thread(species_reference.lookup, name)
    if hit and hit.get("scientific_name"):
        return str(hit["scientific_name"])

    index = ebird_index if ebird_index is not None else await _ebird_common_name_index()
    return index.get(name.casefold())


async def enrich_unmapped_labels(
    check: LabelCheck,
    *,
    mapping: Optional[ModelTaxonMap] = None,
) -> int:
    """Fill the indices the label file could not supply, returning how many.

    The label file is the better authority, so an index it already mapped is
    never overwritten. A file reported as changed is not enriched at all: adding
    names to an altered file's mapping would make it more authoritative, not less.
    """
    if check.verdict in (LabelVerdict.CHANGED, LabelVerdict.MISSING):
        return 0
    if not check.actual_sha256 or not check.labels:
        return 0

    target = mapping or model_taxon_map
    key = check.actual_sha256

    def unmapped() -> list[tuple[int, str]]:
        return [(index, label) for index, label in enumerate(check.labels) if target.lookup(key, index) is None]

    gaps = await asyncio.to_thread(unmapped)
    if not gaps:
        return 0

    ebird_index = await _ebird_common_name_index()
    filled: list[tuple[int, str]] = []
    for index, label in gaps:
        scientific = await resolve_common_name(label, ebird_index=ebird_index)
        if scientific:
            filled.append((index, scientific))

    if not filled:
        log.info("No common-name labels could be resolved", model_id=check.model_id, gaps=len(gaps))
        return 0

    stored = await asyncio.to_thread(target.add, key, filled, source="common_name_lookup")
    log.info(
        "Filled label gaps by resolving common names",
        model_id=check.model_id,
        gaps=len(gaps),
        filled=stored,
    )
    return stored


async def refresh_model_maps() -> dict[str, int]:
    """Verify, map and enrich every installed model's labels.

    One eBird request covers all of them: the taxonomy is fetched once and every
    label is then a dictionary lookup, so the cost does not grow with the number
    of models installed.

    Never raises. A model that cannot be read is skipped and reported, because a
    naming improvement must not be able to stop the app starting.
    """
    from pathlib import Path

    from app.services.label_integrity import build_map_for_verified_labels, verify_model_labels
    from app.services.model_manager import _resolve_models_dir

    def discover() -> list[tuple[str, Path, Optional[str]]]:
        """Every installed label file, with the region a variant belongs to."""
        try:
            root = Path(_resolve_models_dir())
        except Exception as error:
            log.warning("Could not resolve the models directory", error=str(error))
            return []
        if not root.is_dir():
            return []

        found: list[tuple[str, Path, Optional[str]]] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            # A region variant installs as `<parent>/<region>` and has no labels
            # of its own at the parent level.
            candidates: list[tuple[str, Path, Optional[str]]] = [(entry.name, entry, None)]
            for region in ("eu", "na"):
                if (entry / region).is_dir():
                    candidates.append((entry.name, entry / region, region))
            found.extend(c for c in candidates if (c[1] / "labels.txt").is_file())
        return found

    def verify_and_build(model_id: str, directory: Path, region: Optional[str]):
        check = verify_model_labels(model_id, directory, region=region)
        build_map_for_verified_labels(check)
        return check

    results: dict[str, int] = {}
    for model_id, directory, region in await asyncio.to_thread(discover):
        try:
            check = await asyncio.to_thread(verify_and_build, model_id, directory, region)
            filled = await enrich_unmapped_labels(check)
        except Exception as error:
            log.warning("Could not refresh model map", model_id=model_id, error=str(error))
            continue
        results[f"{model_id}/{region}" if region else model_id] = filled
    return results


async def start_background_map_refresh() -> None:
    """Schedule the map refresh without holding up startup."""

    async def run() -> None:
        try:
            await refresh_model_maps()
        except Exception as error:  # pragma: no cover - guarded by the caller's phase
            log.warning("Model map refresh failed", error=str(error))

    asyncio.get_running_loop().create_task(run())
