"""Tests for backend/app/services/eval/image_fetcher.py.

Mocks the two private HTTP helpers (_get_json, _download_bytes) rather than
the underlying httpx.AsyncClient, keeping tests stable across httpx versions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.eval import image_fetcher
from app.services.eval.image_fetcher import (
    FetchedImage,
    _inat_photo_url,
    cleanup_image_dir,
    fetch_images_for_species,
)


def test_inat_photo_url_upgrades_size():
    raw = "https://inaturalist-open-data.s3.amazonaws.com/photos/123/square.jpg"
    assert _inat_photo_url(raw).endswith("/medium.jpg")


def test_inat_photo_url_passthrough_when_no_square():
    raw = "https://example.com/foo.jpg"
    assert _inat_photo_url(raw) == raw


@pytest.mark.asyncio
async def test_inat_path_writes_files(tmp_path: Path):
    inat_payload = {
        "results": [
            {
                "photos": [
                    {
                        "url": "https://x/photos/1/square.jpg",
                        "attribution": "(c) someone",
                        "license_code": "cc-by",
                    }
                ]
            },
            {"photos": [{"url": "https://x/photos/2/square.jpg"}]},
            {"photos": [{"url": "https://x/photos/3/square.jpg"}]},
        ]
    }
    fake_bytes = b"\xff\xd8fakejpg"
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(return_value=inat_payload)),
        patch.object(image_fetcher, "_download_bytes", AsyncMock(return_value=fake_bytes)),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=12345,
                scientific_name="Passer domesticus",
                common_name="House Sparrow",
                dest_root=tmp_path,
                max_count=2,
            )
    assert len(images) == 2
    for img in images:
        assert img.source == "inat"
        assert img.taxa_id == 12345
        assert Path(img.local_path).is_file()
        assert Path(img.local_path).read_bytes() == fake_bytes
    assert images[0].license_code == "cc-by"


@pytest.mark.asyncio
async def test_inat_dedupes_identical_urls(tmp_path: Path):
    payload = {
        "results": [
            {"photos": [{"url": "https://x/photos/1/square.jpg"}]},
            {"photos": [{"url": "https://x/photos/1/square.jpg"}]},
        ]
    }
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(return_value=payload)),
        patch.object(image_fetcher, "_download_bytes", AsyncMock(return_value=b"x")),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=99,
                scientific_name="Foo bar",
                common_name="Foo",
                dest_root=tmp_path,
                max_count=5,
            )
    assert len(images) == 1


@pytest.mark.asyncio
async def test_falls_back_to_wikimedia_when_inat_short(tmp_path: Path):
    inat_payload = {
        "results": [
            {"photos": [{"url": "https://x/photos/1/square.jpg"}]},
        ]
    }
    wiki_summary = {"originalimage": {"source": "https://wiki/lead.jpg"}}
    wiki_commons = {
        "query": {
            "pages": {
                "1": {
                    "imageinfo": [
                        {
                            "thumburl": "https://wiki/file1.jpg",
                            "extmetadata": {
                                "Artist": {"value": "Photographer A"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            },
                        }
                    ]
                },
                "2": {
                    "imageinfo": [
                        {
                            "url": "https://wiki/file2.jpg",
                            "extmetadata": {},
                        }
                    ]
                },
            }
        }
    }
    json_responses = iter([inat_payload, wiki_summary, wiki_commons])
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(side_effect=lambda *a, **k: next(json_responses))),
        patch.object(image_fetcher, "_download_bytes", AsyncMock(return_value=b"img")),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=42,
                scientific_name="Foo bar",
                common_name="Foo",
                dest_root=tmp_path,
                max_count=3,
            )
    assert len(images) == 3
    assert images[0].source == "inat"
    assert images[1].source == "wikimedia"
    assert images[2].source == "wikimedia"
    assert images[1].source_url == "https://wiki/lead.jpg"


@pytest.mark.asyncio
async def test_returns_empty_when_inat_returns_none(tmp_path: Path):
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(return_value=None)),
        patch.object(image_fetcher, "_download_bytes", AsyncMock()),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=1,
                scientific_name="Nothing here",
                common_name="",
                dest_root=tmp_path,
                max_count=3,
            )
    assert images == []


@pytest.mark.asyncio
async def test_max_count_zero_short_circuits(tmp_path: Path):
    with patch.object(image_fetcher, "_get_json", AsyncMock()) as get_json:
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=1,
                scientific_name="X y",
                common_name="",
                dest_root=tmp_path,
                max_count=0,
            )
    assert images == []
    get_json.assert_not_called()


def test_cleanup_image_dir_removes_tree(tmp_path: Path):
    sub = tmp_path / "images" / "100"
    sub.mkdir(parents=True)
    (sub / "00.jpg").write_bytes(b"x")
    (sub / "01.jpg").write_bytes(b"y")
    cleanup_image_dir(tmp_path / "images")
    assert not (tmp_path / "images").exists()


def test_cleanup_image_dir_missing_path_is_ok(tmp_path: Path):
    cleanup_image_dir(tmp_path / "does_not_exist")  # no error


def test_fetched_image_to_dict_round_trip():
    img = FetchedImage(
        taxa_id=1,
        scientific_name="A b",
        common_name="A",
        source="inat",
        source_url="u",
        local_path="/p",
    )
    assert img.to_dict()["taxa_id"] == 1
    assert img.to_dict()["source"] == "inat"


def _jpeg(size: tuple[int, int]) -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 90, 60)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_a_full_size_photo_is_stored_at_feeder_scale(tmp_path: Path):
    """Wikipedia's lead image is the full upload. On 2026-10-06, 40 of 299 test photos were 3840 px
    wide and each took 2 to 2.5 s for every model, against about 0.3 s for a 800 px photo, so the
    p95 latency measured the photo, not the model."""
    from PIL import Image

    summary = {"originalimage": {"source": "https://upload.wikimedia.org/a/Northern_Lapwing.jpg"}}
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(side_effect=[None, summary, None])),
        patch.object(image_fetcher, "_download_bytes", AsyncMock(return_value=_jpeg((3840, 2560)))),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=4857,
                scientific_name="Vanellus vanellus",
                common_name="Northern Lapwing",
                dest_root=tmp_path,
                max_count=1,
            )

    with Image.open(images[0].local_path) as stored:
        assert stored.size == (
            image_fetcher.MAX_EVAL_IMAGE_SIDE,
            round(image_fetcher.MAX_EVAL_IMAGE_SIDE * 2560 / 3840),
        )


@pytest.mark.asyncio
async def test_a_photo_already_at_feeder_scale_is_stored_unchanged(tmp_path: Path):
    payload = {"results": [{"photos": [{"url": "https://x/photos/1/square.jpg"}]}]}
    small = _jpeg((600, 800))
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(return_value=payload)),
        patch.object(image_fetcher, "_download_bytes", AsyncMock(return_value=small)),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=1,
                scientific_name="Passer domesticus",
                common_name="House Sparrow",
                dest_root=tmp_path,
                max_count=1,
            )

    assert Path(images[0].local_path).read_bytes() == small


@pytest.mark.asyncio
async def test_a_photo_pillow_refuses_as_too_large_is_skipped_later_not_fatal_now(tmp_path: Path, monkeypatch):
    """Pillow raises DecompressionBombError (not OSError) past its pixel limit. Before the downscale step
    that happened at evaluation time, where one bad photo is skipped; it must not abort the whole fetch."""
    from PIL import Image

    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    payload = {"results": [{"photos": [{"url": "https://x/photos/1/square.jpg"}]}]}
    huge = _jpeg((200, 200))
    with (
        patch.object(image_fetcher, "_get_json", AsyncMock(return_value=payload)),
        patch.object(image_fetcher, "_download_bytes", AsyncMock(return_value=huge)),
    ):
        async with __import__("httpx").AsyncClient() as client:
            images = await fetch_images_for_species(
                client=client,
                taxa_id=1,
                scientific_name="Passer domesticus",
                common_name="House Sparrow",
                dest_root=tmp_path,
                max_count=1,
            )

    assert Path(images[0].local_path).read_bytes() == huge
