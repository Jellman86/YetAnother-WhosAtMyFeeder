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
import hashlib
import json
import sys
import tempfile
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
_PHOTO_LICENSES = {"cc0", "cc-by"}


def _checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _read_manifest(output_dir: Path) -> dict:
    path = output_dir / "downloaded.json"
    if not path.exists():
        return {"cases": {}}
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), dict):
        raise ValueError("Invalid downloaded fixture manifest; preserve it and inspect before retrying")
    return manifest


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _download_file(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        from PIL import Image

        with Image.open(dest) as image:
            image.convert("RGB").load()
        return True
    except Exception as e:
        print(f"    WARN: failed to download {url}: {e}")
        return False


def fetch_observation_photos(
    taxon_id: int,
    count: int = 3,
    *,
    quality_grade: str = "research",
    exclude_photo_ids: set[int] | None = None,
    exclude_observation_ids: set[int] | None = None,
) -> list[dict]:
    """Return up to `count` photo records for a taxon from iNaturalist."""
    url = (
        f"{_INAT_API}/observations"
        f"?taxon_id={taxon_id}"
        f"&quality_grade={quality_grade}"
        f"&photos=true"
        f"&photo_license=cc0,cc-by"
        f"&per_page={min(200, count * 3)}"
        f"&order_by=votes"
        f"&order=desc"
    )
    data = _fetch_json(url)
    photos = []
    seen_urls: set[str] = set()
    seen_ids = set(exclude_photo_ids or ())
    seen_observations = set(exclude_observation_ids or ())
    for obs in data.get("results", []):
        if not obs.get("id") or obs["id"] in seen_observations:
            continue
        for photo in obs.get("photos", []):
            # Observation and photo licences are independent. A mixed-licence
            # observation may pass the API filter while some of its photos do not.
            if (
                photo.get("license_code") not in _PHOTO_LICENSES
                or not photo.get("id")
                or photo["id"] in seen_ids
                or not photo.get("attribution")
            ):
                continue
            url_medium = (photo.get("url") or "").replace("square", "medium")
            if url_medium and url_medium not in seen_urls:
                photos.append(
                    {
                        "photo_id": photo.get("id"),
                        "url": url_medium,
                        "license": photo.get("license_code", "unknown"),
                        "attribution": photo.get("attribution", ""),
                        "obs_id": obs.get("id"),
                        "obs_url": f"https://www.inaturalist.org/observations/{obs.get('id')}",
                        "taxon": obs.get("taxon", {}).get("name", ""),
                    }
                )
                seen_urls.add(url_medium)
                seen_ids.add(photo["id"])
                seen_observations.add(obs["id"])
                # Adjacent frames of the same bird are not independent examples.
                break
        if len(photos) >= count:
            break
    return photos[:count]


def _existing_records(case: dict, output_dir: Path) -> list[dict]:
    records = _read_manifest(output_dir)["cases"].get(case["id"], [])
    excluded = set(case.get("exclude_photo_ids", []))
    result = []
    seen_photos, seen_observations = set(), set()
    for record in records:
        if record.get("photo_id") in excluded:
            continue
        if (
            not all(record.get(key) for key in ("path", "photo_id", "obs_id", "url", "attribution", "sha256"))
            or record.get("license") not in _PHOTO_LICENSES
        ):
            raise ValueError("Existing fixtures lack trusted provenance; use --force to explicitly refresh")
        path = Path(record["path"])
        if not path.resolve().is_relative_to((output_dir / case["id"]).resolve()):
            raise ValueError("Fixture path is outside its case directory")
        if not path.is_file() or _checksum(path) != record["sha256"]:
            raise ValueError("Fixture missing or checksum changed; use --force to explicitly refresh")
        if record["photo_id"] not in seen_photos and record["obs_id"] not in seen_observations:
            result.append(record)
            seen_photos.add(record["photo_id"])
            seen_observations.add(record["obs_id"])
    return result


def download_case(
    case: dict,
    output_dir: Path,
    count: int = 3,
    *,
    skip_existing: bool = True,
) -> list[dict]:
    case_id = case["id"]
    if not case_id or Path(case_id).name != case_id or case_id in {".", ".."}:
        raise ValueError("Case ID must be a single directory name")
    if count < 1:
        raise ValueError("Image count must be positive")
    taxon_id = case.get("inat_taxon_id")
    if not taxon_id:
        print(f"  SKIP {case_id}: no inat_taxon_id")
        return []

    case_dir = output_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    downloaded = _existing_records(case, output_dir) if skip_existing else []
    if len(downloaded) >= count:
        print(f"  SKIP {case_id}: verified {len(downloaded)} locked images")
        return downloaded

    print(f"  Fetching {count} images for {case_id} (taxon {taxon_id})...")
    try:
        photos = fetch_observation_photos(
            taxon_id,
            count=count - len(downloaded),
            exclude_photo_ids=set(case.get("exclude_photo_ids", [])) | {row["photo_id"] for row in downloaded},
            exclude_observation_ids={row["obs_id"] for row in downloaded},
        )
    except Exception as e:
        print(f"    ERROR fetching observations: {e}")
        return []

    with tempfile.TemporaryDirectory(prefix=".download-", dir=case_dir) as temporary:
        for i, photo in enumerate(photos):
            staging = Path(temporary) / "image.jpg"
            print(f"    [{i + 1}/{len(photos)}] {photo['url'][:70]}...")
            if _download_file(photo["url"], staging):
                checksum = _checksum(staging)
                dest = case_dir / f"{photo['photo_id']}-{checksum}.jpg"
                staging.replace(dest)
                downloaded.append({**photo, "path": str(dest.resolve()), "sha256": checksum})
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
    if args.count < 1:
        parser.error("--count must be positive")

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

    downloaded_manifest = _read_manifest(output_dir)
    results = downloaded_manifest["cases"]
    total_downloaded = 0
    complete = True

    for case in test_cases:
        try:
            photos = download_case(case, output_dir, count=args.count, skip_existing=not args.force)
        except ValueError as exc:
            print(f"ERROR {case['id']}: {exc}", file=sys.stderr)
            complete = False
            continue
        if len(photos) < args.count:
            print(f"ERROR {case['id']}: incomplete download; previous case manifest retained", file=sys.stderr)
            complete = False
            continue
        results[case["id"]] = photos
        total_downloaded += len(photos)

    # Write a downloaded manifest so tests can discover actual file paths
    downloaded_manifest["generated_by"] = "download_test_fixtures.py"
    out_manifest = output_dir / "downloaded.json"
    with tempfile.TemporaryDirectory(prefix=".manifest-", dir=output_dir) as temporary:
        staged = Path(temporary) / "downloaded.json"
        staged.write_text(json.dumps(downloaded_manifest, indent=2))
        staged.replace(out_manifest)
    print(f"\nTotal images: {total_downloaded}")
    print(f"Manifest written to {out_manifest}")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
