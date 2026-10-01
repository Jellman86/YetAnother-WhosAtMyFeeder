"""Candidate metadata must not promise missing images or reload unchanged files."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routers import proxy
from app.services import media_cache as cache
from test_media_cache import _make_service
from test_proxy import client as client


@pytest.fixture
def candidate_media(tmp_path, monkeypatch):
    media, _ = _make_service(tmp_path, monkeypatch)
    monkeypatch.setattr(cache, "media_cache", media)
    rows = [
        {
            "candidate_id": "candidate-1",
            "source_mode": "model_crop",
            "selected": True,
            "snapshot_source": "hq_candidate_model_crop",
            "image_ref": "candidate-1__image",
            "thumbnail_ref": "candidate-1__thumb",
        }
    ]
    monkeypatch.setattr(proxy, "_list_snapshot_candidates", AsyncMock(return_value=rows))
    monkeypatch.setattr(
        proxy, "_build_snapshot_status", AsyncMock(return_value=SimpleNamespace(source="hq_candidate_model_crop"))
    )
    return media


@pytest.mark.asyncio
@pytest.mark.parametrize("image_exists,thumbnail_exists", [(False, False), (False, True), (True, False), (True, True)])
async def test_candidate_urls_only_advertise_retained_files(client, candidate_media, image_exists, thumbnail_exists):
    if image_exists:
        await candidate_media.cache_snapshot("candidate-1__image", b"retained image")
    if thumbnail_exists:
        await candidate_media.cache_thumbnail("candidate-1__thumb", b"retained thumbnail")
    response = await client.get("/api/frigate/test_event_id/snapshot/candidates")
    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert bool(candidate["image_url"]) is image_exists
    assert bool(candidate["thumbnail_url"]) is thumbnail_exists
    assert candidate["candidate_id"] == "candidate-1"
    assert candidate["selected"] is True


@pytest.mark.asyncio
async def test_candidate_media_urls_are_stable_across_unchanged_reads(client, candidate_media):
    await candidate_media.cache_snapshot("candidate-1__image", b"retained image")
    await candidate_media.cache_thumbnail("candidate-1__thumb", b"retained thumbnail")
    with patch("time.time", return_value=1_700_000_000):
        first = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()
    with patch("time.time", return_value=1_700_000_100):
        second = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()
    assert first["candidates"] == second["candidates"]


@pytest.mark.asyncio
async def test_candidate_image_replacement_changes_only_its_own_version(client, candidate_media):
    await candidate_media.cache_snapshot("candidate-1__image", b"old image")
    await candidate_media.cache_thumbnail("candidate-1__thumb", b"retained thumbnail")
    first = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()["candidates"][0]
    await candidate_media.replace_snapshot("candidate-1__image", b"new image")
    second = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()["candidates"][0]
    assert first["image_url"] != second["image_url"]
    assert first["thumbnail_url"] == second["thumbnail_url"]


@pytest.mark.asyncio
async def test_empty_candidate_files_are_not_advertised(client, candidate_media):
    candidate_media._snapshot_path("candidate-1__image").touch()
    candidate_media._thumbnail_path("candidate-1__thumb").touch()
    candidate = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()["candidates"][0]
    assert candidate["image_url"] is None
    assert candidate["thumbnail_url"] is None


@pytest.mark.asyncio
async def test_reading_candidate_images_does_not_change_their_urls(client, candidate_media):
    await candidate_media.cache_snapshot("candidate-1__image", b"retained image")
    await candidate_media.cache_thumbnail("candidate-1__thumb", b"retained thumbnail")
    first = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()["candidates"][0]
    image = await client.get(first["image_url"])
    thumbnail = await client.get(first["thumbnail_url"])
    assert image.status_code == thumbnail.status_code == 200
    second = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()["candidates"][0]
    assert first == second


@pytest.mark.asyncio
async def test_missing_media_keeps_reviewed_bird_metadata(client, candidate_media, monkeypatch):
    bird = {
        "id": 7,
        "frigate_event": "test_event_id",
        "bird_index": 0,
        "candidate_id": "candidate-1",
        "clip_variant": "event",
        "frame_index": -1,
        "crop_box": [10, 10, 20, 20],
        "detector_confidence": 0.9,
        "species": "Robin",
        "classifier_label": "Blue Tit",
        "classifier_score": 0.6,
        "manual_species": True,
        "is_hidden": True,
    }
    monkeypatch.setattr(proxy.BirdObservationRepository, "list_for_event", AsyncMock(return_value=[bird]))
    response = (await client.get("/api/frigate/test_event_id/snapshot/candidates")).json()
    assert response["current_candidate_id"] == "candidate-1"
    assert response["birds"][0]["id"] == 7
    assert response["birds"][0]["manual_species"] is True
    assert response["birds"][0]["is_hidden"] is True
    assert response["birds"][0]["species"] == "Robin"
    assert response["candidates"][0]["image_url"] is None
