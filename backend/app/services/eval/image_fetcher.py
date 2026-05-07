"""Fetch labeled bird images from iNaturalist (primary) and Wikimedia Commons (fallback).

Used by the model-evaluation harness. Images are taxonomy-verified by source:
- iNaturalist research-grade observations carry community-confirmed taxon IDs.
- Wikimedia Commons file pages are matched by scientific name from species infoboxes.

The caller controls concurrency and lifecycle. Files are written under
<dest_root>/<taxa_id>/<idx>.<ext>; cleanup is the caller's responsibility.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

log = structlog.get_logger()

INAT_OBSERVATIONS_URL = "https://api.inaturalist.org/v1/observations"
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"

# iNat photo URLs come back as <prefix>/square.jpg; "medium" is ~500px and good
# enough for classifier eval at typical 224-518px input sizes.
_INAT_PHOTO_SIZE = "medium"

DEFAULT_MAX_PER_SPECIES = 3
DEFAULT_TIMEOUT = 15.0


@dataclass
class FetchedImage:
    taxa_id: int
    scientific_name: str
    common_name: str
    source: str  # "inat" | "wikimedia"
    source_url: str
    local_path: str
    attribution: Optional[str] = None
    license_code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_basename(suffix: str, idx: int) -> str:
    return f"{idx:02d}{suffix}"


def _ext_from_url(url: str, fallback: str = ".jpg") -> str:
    path = url.split("?", 1)[0]
    for cand in (".jpg", ".jpeg", ".png", ".webp"):
        if path.lower().endswith(cand):
            return cand
    return fallback


def _inat_photo_url(raw_url: str) -> str:
    """Upgrade an iNat 'square' thumb URL to a medium-resolution version."""
    if not raw_url:
        return raw_url
    return raw_url.replace("/square.", f"/{_INAT_PHOTO_SIZE}.")


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
    try:
        resp = await client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        log.warning("eval_image_fetch_get_json_failed", url=url, error=str(e))
        return None


async def _download_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        resp = await client.get(url, timeout=DEFAULT_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as e:
        log.warning("eval_image_fetch_download_failed", url=url, error=str(e))
        return None


def _write_bytes(dest_dir: Path, idx: int, url: str, payload: bytes) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = _ext_from_url(url)
    dest_path = dest_dir / _safe_basename(suffix, idx)
    dest_path.write_bytes(payload)
    return dest_path


async def _fetch_inat(
    client: httpx.AsyncClient,
    *,
    taxa_id: int,
    scientific_name: str,
    common_name: str,
    max_count: int,
    dest_root: Path,
) -> list[FetchedImage]:
    payload = await _get_json(
        client,
        INAT_OBSERVATIONS_URL,
        {
            "taxon_id": taxa_id,
            "quality_grade": "research",
            "photos": "true",
            "per_page": max(max_count * 2, max_count),
            "order": "desc",
            "order_by": "votes",
            "locale": "en",
        },
    )
    if not payload:
        return []

    results = []
    species_dir = dest_root / str(taxa_id)
    seen_urls: set[str] = set()
    for obs in payload.get("results", []) or []:
        if len(results) >= max_count:
            break
        photos = obs.get("photos") or []
        if not photos:
            continue
        photo = photos[0]
        raw_url = photo.get("url")
        if not raw_url:
            continue
        url = _inat_photo_url(raw_url)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        data = await _download_bytes(client, url)
        if not data:
            continue
        local_path = _write_bytes(species_dir, len(results), url, data)
        results.append(
            FetchedImage(
                taxa_id=taxa_id,
                scientific_name=scientific_name,
                common_name=common_name,
                source="inat",
                source_url=url,
                local_path=str(local_path),
                attribution=photo.get("attribution"),
                license_code=photo.get("license_code"),
            )
        )
    return results


async def _fetch_wikimedia(
    client: httpx.AsyncClient,
    *,
    taxa_id: int,
    scientific_name: str,
    common_name: str,
    max_count: int,
    dest_root: Path,
) -> list[FetchedImage]:
    """Try Wikipedia REST summary first (single high-quality lead image), then
    Commons file search for additional candidates if more images are needed."""
    species_dir = dest_root / str(taxa_id)
    results: list[FetchedImage] = []
    seen_urls: set[str] = set()

    summary = await _get_json(
        client,
        f"{WIKIPEDIA_SUMMARY_URL}/{scientific_name.replace(' ', '_')}",
        {},
    )
    if summary:
        original = (summary.get("originalimage") or {}).get("source") or (summary.get("thumbnail") or {}).get("source")
        if original and original not in seen_urls:
            data = await _download_bytes(client, original)
            if data:
                seen_urls.add(original)
                local_path = _write_bytes(species_dir, len(results), original, data)
                results.append(
                    FetchedImage(
                        taxa_id=taxa_id,
                        scientific_name=scientific_name,
                        common_name=common_name,
                        source="wikimedia",
                        source_url=original,
                        local_path=str(local_path),
                        attribution="Wikipedia summary",
                        license_code=None,
                    )
                )
    if len(results) >= max_count:
        return results

    commons = await _get_json(
        client,
        WIKIMEDIA_API_URL,
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {scientific_name}",
            "gsrlimit": max(max_count * 2, max_count),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 800,
        },
    )
    if not commons:
        return results

    pages = ((commons.get("query") or {}).get("pages") or {}).values()
    for page in pages:
        if len(results) >= max_count:
            break
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        url = info.get("thumburl") or info.get("url")
        if not url or url in seen_urls:
            continue
        meta = info.get("extmetadata") or {}
        attribution = (meta.get("Artist") or {}).get("value") or (meta.get("Credit") or {}).get("value")
        license_code = (meta.get("LicenseShortName") or {}).get("value")
        data = await _download_bytes(client, url)
        if not data:
            continue
        seen_urls.add(url)
        local_path = _write_bytes(species_dir, len(results), url, data)
        results.append(
            FetchedImage(
                taxa_id=taxa_id,
                scientific_name=scientific_name,
                common_name=common_name,
                source="wikimedia",
                source_url=url,
                local_path=str(local_path),
                attribution=attribution,
                license_code=license_code,
            )
        )
    return results


async def fetch_images_for_species(
    *,
    client: httpx.AsyncClient,
    taxa_id: int,
    scientific_name: str,
    common_name: str,
    dest_root: Path | str,
    max_count: int = DEFAULT_MAX_PER_SPECIES,
) -> list[FetchedImage]:
    """Fetch up to ``max_count`` labeled images for a species.

    Tries iNaturalist first; falls back to Wikimedia Commons to top up if iNat
    returns fewer images than requested.
    """
    if max_count <= 0:
        return []
    dest_root_path = Path(dest_root)
    images = await _fetch_inat(
        client,
        taxa_id=taxa_id,
        scientific_name=scientific_name,
        common_name=common_name,
        max_count=max_count,
        dest_root=dest_root_path,
    )
    if len(images) < max_count:
        remainder = max_count - len(images)
        wiki = await _fetch_wikimedia(
            client,
            taxa_id=taxa_id,
            scientific_name=scientific_name,
            common_name=common_name,
            max_count=remainder,
            dest_root=dest_root_path,
        )
        images.extend(wiki)
    return images


async def fetch_panel_images(
    *,
    species: list[dict[str, Any]],
    dest_root: Path | str,
    max_per_species: int = DEFAULT_MAX_PER_SPECIES,
    concurrency: int = 5,
    progress_cb: Optional[Any] = None,
) -> dict[int, list[FetchedImage]]:
    """Fetch images for many species concurrently.

    ``species`` items must include ``taxa_id``, ``scientific_name``,
    ``common_name``. ``progress_cb(done, total)`` is called after each species
    completes if provided.
    """
    sem = asyncio.Semaphore(max(1, concurrency))
    out: dict[int, list[FetchedImage]] = {}
    total = len(species)
    done = 0

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        async def _one(entry: dict[str, Any]) -> None:
            nonlocal done
            taxa_id = entry.get("taxa_id")
            if not taxa_id:
                done += 1
                if progress_cb:
                    progress_cb(done, total)
                return
            async with sem:
                images = await fetch_images_for_species(
                    client=client,
                    taxa_id=int(taxa_id),
                    scientific_name=str(entry.get("scientific_name") or ""),
                    common_name=str(entry.get("common_name") or ""),
                    dest_root=dest_root,
                    max_count=max_per_species,
                )
            out[int(taxa_id)] = images
            done += 1
            if progress_cb:
                progress_cb(done, total)

        await asyncio.gather(*(_one(entry) for entry in species))
    return out


def cleanup_image_dir(dest_root: Path | str) -> None:
    """Remove the cached image tree. Safe to call on a missing path."""
    root = Path(dest_root)
    if not root.exists():
        return
    for sub in sorted(root.rglob("*"), reverse=True):
        try:
            if sub.is_file() or sub.is_symlink():
                sub.unlink()
            elif sub.is_dir():
                sub.rmdir()
        except OSError as e:
            log.warning("eval_image_cleanup_failed", path=str(sub), error=str(e))
    try:
        root.rmdir()
    except OSError:
        pass
