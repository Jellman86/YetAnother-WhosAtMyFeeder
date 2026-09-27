"""Fixture provenance must survive retries without relabelling existing bytes."""

import hashlib
import io
import json
from pathlib import Path
import sys

import pytest
from PIL import Image

from scripts import download_test_fixtures as downloader


def photo(photo_id, license_code="cc-by"):
    return {
        "id": photo_id,
        "url": f"https://example.org/{photo_id}/square.jpg",
        "license_code": license_code,
        "attribution": "Test photographer",
    }


def test_selection_checks_photo_license_exclusions_and_independent_observations(monkeypatch):
    urls = []
    observations = [
        {"id": 1, "photos": [photo(1, None), photo(2, "cc-by-nc"), photo(3), photo(4)]},
        {"id": 2, "photos": [photo(3), photo(5, "cc0")]},
        {"id": 3, "photos": [photo(6)]},
    ]
    monkeypatch.setattr(downloader, "_fetch_json", lambda url: urls.append(url) or {"results": observations})
    records = downloader.fetch_observation_photos(42, count=3, exclude_photo_ids={6})
    assert [record["photo_id"] for record in records] == [3, 5]
    assert "photo_license=cc0,cc-by" in urls[0]
    assert "&license" not in urls[0]


@pytest.fixture
def downloaded(tmp_path):
    path = tmp_path / "robin" / "original.jpg"
    path.parent.mkdir()
    Image.new("RGB", (16, 16), "red").save(path)
    record = {
        "path": str(path),
        "photo_id": 8,
        "obs_id": 9,
        "license": "cc-by",
        "attribution": "Original photographer",
        "url": "https://example.org/8.jpg",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    (tmp_path / "downloaded.json").write_text(json.dumps({"cases": {"robin": [record]}}))
    return record


def test_existing_locked_photo_keeps_metadata_without_a_network_request(tmp_path, downloaded, monkeypatch):
    monkeypatch.setattr(downloader, "_fetch_json", lambda _: pytest.fail("locked fixture queried upstream"))
    assert downloader.download_case({"id": "robin", "inat_taxon_id": 42}, tmp_path, count=1) == [downloaded]


def test_changed_bytes_are_not_silently_relabelled(tmp_path, downloaded):
    Path(downloaded["path"]).write_bytes(b"different bytes")
    with pytest.raises(ValueError, match="checksum"):
        downloader.download_case({"id": "robin", "inat_taxon_id": 42}, tmp_path, count=1)


def test_partial_case_keeps_original_metadata_and_excludes_existing_observation(tmp_path, downloaded, monkeypatch):
    def fetch(*args, **kwargs):
        assert kwargs["count"] == 1
        assert kwargs["exclude_photo_ids"] == {8, 99}
        assert kwargs["exclude_observation_ids"] == {9}
        return []

    monkeypatch.setattr(downloader, "fetch_observation_photos", fetch)
    assert downloader.download_case(
        {"id": "robin", "inat_taxon_id": 42, "exclude_photo_ids": [99]}, tmp_path, count=2
    ) == [downloaded]


def test_invalid_media_response_is_not_accepted_as_an_image(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"<html>rate limited</html>"))
    assert downloader._download_file("https://example.org/image.jpg", tmp_path / "staging.jpg") is False


@pytest.mark.parametrize("case_id", ["../outside", "..", "/absolute"])
def test_case_cannot_write_outside_output_directory(tmp_path, case_id):
    with pytest.raises(ValueError, match="directory name"):
        downloader.download_case({"id": case_id, "inat_taxon_id": 42}, tmp_path)


def test_unattributed_legacy_photo_requires_explicit_refresh(tmp_path, downloaded):
    (tmp_path / "downloaded.json").write_text(json.dumps({"cases": {"robin": [{"path": downloaded["path"]}]}}))
    with pytest.raises(ValueError, match="provenance"):
        downloader.download_case({"id": "robin", "inat_taxon_id": 42}, tmp_path, count=1)


def test_refresh_uses_new_content_addressed_files_and_preserves_old_bytes(tmp_path, downloaded, monkeypatch):
    old_bytes = Path(downloaded["path"]).read_bytes()
    metadata = downloaded | {"photo_id": 17, "obs_id": 18}
    monkeypatch.setattr(downloader, "fetch_observation_photos", lambda *a, **kw: [metadata])

    def download(_url, destination):
        Image.new("RGB", (16, 16), "blue").save(destination, format="JPEG")
        return True

    monkeypatch.setattr(downloader, "_download_file", download)
    monkeypatch.setattr(downloader.time, "sleep", lambda _: None)
    records = downloader.download_case({"id": "robin", "inat_taxon_id": 42}, tmp_path, count=1, skip_existing=False)
    assert Path(downloaded["path"]).read_bytes() == old_bytes
    assert records[0]["path"] != downloaded["path"]
    assert records[0]["sha256"] == hashlib.sha256(Path(records[0]["path"]).read_bytes()).hexdigest()


@pytest.mark.parametrize("success", [True, False])
def test_single_case_refresh_preserves_other_cases_and_failure_keeps_original_manifest(
    tmp_path, downloaded, monkeypatch, success
):
    manifest = tmp_path / "cases.json"
    manifest.write_text(json.dumps({"test_cases": [{"id": "robin", "inat_taxon_id": 42}]}))
    saved = {"cases": {"robin": [downloaded], "sparrow": [{"path": "keep-this", "attribution": "Keep me"}]}}
    (tmp_path / "downloaded.json").write_text(json.dumps(saved))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "download",
            "--manifest",
            str(manifest),
            "--output_dir",
            str(tmp_path),
            "--case",
            "robin",
            "--count",
            "1",
            "--force",
        ],
    )
    replacement = downloaded | {"attribution": "New photographer"}
    monkeypatch.setattr(downloader, "download_case", lambda *a, **kw: [replacement] if success else [])
    assert downloader.main() == (0 if success else 1)
    result = json.loads((tmp_path / "downloaded.json").read_text())
    assert result["cases"]["sparrow"] == saved["cases"]["sparrow"]
    assert result["cases"]["robin"] == ([replacement] if success else [downloaded])
