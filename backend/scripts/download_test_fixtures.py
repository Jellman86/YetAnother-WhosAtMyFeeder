"""Download labeled bird test images from iNaturalist for use in model evaluation.

Downloads CC-BY/CC0 research-grade observation photos by taxon ID and saves them
to tests/fixtures/bird_images/<case_id>/ alongside a manifest of what was fetched.

Usage:
    python scripts/download_test_fixtures.py
    python scripts/download_test_fixtures.py --count 3 --output_dir tests/fixtures/bird_images
    python scripts/download_test_fixtures.py --case house_sparrow --count 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

_INAT_API = "https://api.inaturalist.org/v1"
_HEADERS = {"User-Agent": "YA-WAMF-test-fixture-downloader/1.0"}

_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_DEFAULT_MANIFEST = _BACKEND_DIR / "tests" / "fixtures" / "bird_image_manifest.json"
_DEFAULT_OUTPUT = _BACKEND_DIR / "tests" / "fixtures" / "bird_images"


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _download_file(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:
        print(f"    WARN: failed to download {url}: {e}")
        return False


def fetch_observation_photos(
    taxon_id: int,
    count: int = 3,
    *,
    quality_grade: str = "research",
) -> list[dict]:
    """Return up to `count` photo records for a taxon from iNaturalist."""
    url = (
        f"{_INAT_API}/observations"
        f"?taxon_id={taxon_id}"
        f"&quality_grade={quality_grade}"
        f"&photos=true"
        f"&license=cc0,cc-by,cc-by-nc"
        f"&per_page={count * 3}"
        f"&order_by=votes"
        f"&order=desc"
    )
    data = _fetch_json(url)
    photos = []
    seen_urls: set[str] = set()
    for obs in data.get("results", []):
        for photo in obs.get("photos", []):
            url_medium = (photo.get("url") or "").replace("square", "medium")
            if url_medium and url_medium not in seen_urls:
                photos.append({
                    "photo_id": photo.get("id"),
                    "url": url_medium,
                    "license": photo.get("license_code", "unknown"),
                    "attribution": photo.get("attribution", ""),
                    "obs_id": obs.get("id"),
                    "obs_url": f"https://www.inaturalist.org/observations/{obs.get('id')}",
                    "taxon": obs.get("taxon", {}).get("name", ""),
                })
                seen_urls.add(url_medium)
            if len(photos) >= count:
                break
        if len(photos) >= count:
            break
    return photos[:count]


def download_case(
    case: dict,
    output_dir: Path,
    count: int = 3,
    *,
    skip_existing: bool = True,
) -> list[dict]:
    case_id = case["id"]
    taxon_id = case.get("inat_taxon_id")
    if not taxon_id:
        print(f"  SKIP {case_id}: no inat_taxon_id")
        return []

    case_dir = output_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    # Check existing
    existing = sorted(case_dir.glob("*.jpg"))
    if skip_existing and len(existing) >= count:
        print(f"  SKIP {case_id}: already have {len(existing)} images")
        return [{"path": str(p)} for p in existing]

    print(f"  Fetching {count} images for {case_id} (taxon {taxon_id})...")
    try:
        photos = fetch_observation_photos(taxon_id, count=count)
    except Exception as e:
        print(f"    ERROR fetching observations: {e}")
        return []

    downloaded = []
    for i, photo in enumerate(photos):
        dest = case_dir / f"{case_id}_{i+1:02d}.jpg"
        if dest.exists() and skip_existing:
            downloaded.append({"path": str(dest), **photo})
            continue
        print(f"    [{i+1}/{len(photos)}] {photo['url'][:70]}...")
        if _download_file(photo["url"], dest):
            downloaded.append({"path": str(dest), **photo})
        time.sleep(0.3)  # be polite to iNat API

    print(f"    Downloaded {len(downloaded)}/{count} images to {case_dir}")
    return downloaded


def main() -> int:
    parser = argparse.ArgumentParser(description="Download iNaturalist test fixture images")
    parser.add_argument("--manifest", default=str(_DEFAULT_MANIFEST), help="Path to bird_image_manifest.json")
    parser.add_argument("--output_dir", default=str(_DEFAULT_OUTPUT), help="Output directory for images")
    parser.add_argument("--count", type=int, default=3, help="Images per species (default: 3)")
    parser.add_argument("--case", help="Download only this specific case ID")
    parser.add_argument("--force", action="store_true", help="Re-download even if images exist")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    test_cases = manifest.get("test_cases", [])
    if args.case:
        test_cases = [c for c in test_cases if c["id"] == args.case]
        if not test_cases:
            print(f"ERROR: case '{args.case}' not found in manifest", file=sys.stderr)
            return 1

    print(f"Downloading fixtures for {len(test_cases)} species ({args.count} images each)...")
    print(f"Output: {output_dir}\n")

    results: dict[str, list[dict]] = {}
    total_downloaded = 0

    for case in test_cases:
        photos = download_case(case, output_dir, count=args.count, skip_existing=not args.force)
        results[case["id"]] = photos
        total_downloaded += len(photos)

    # Write a downloaded manifest so tests can discover actual file paths
    downloaded_manifest = {
        "generated_by": "download_test_fixtures.py",
        "cases": results,
    }
    out_manifest = output_dir / "downloaded.json"
    out_manifest.write_text(json.dumps(downloaded_manifest, indent=2))
    print(f"\nTotal images: {total_downloaded}")
    print(f"Manifest written to {out_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
