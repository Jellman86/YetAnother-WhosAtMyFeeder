"""An uploaded video's photo shows the species the record names, not whatever the first frame shows (#481).

A video can hold several species. Analysis already knows each species' best frame and bird box,
so the photo follows the species a person confirms, and follows it again when they correct it.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import httpx
import numpy as np
import pytest
import pytest_asyncio
from PIL import Image
from starlette.requests import Request

from app.auth import session_cookie_allowed
from app.config import settings
from app.database import close_db, init_db
from app.main import app
from app.services.manual_observation_service import _result_for_species, manual_observation_service

GREY = (128, 128, 128)
TITMOUSE_BOX = [8, 16, 40, 48]
DOWNY_BOX = [56, 16, 88, 48]
NAMES = {
    "Baeolophus bicolor": {"scientific_name": "Baeolophus bicolor", "common_name": "Tufted Titmouse", "taxa_id": 1},
    "Tufted Titmouse": {"scientific_name": "Baeolophus bicolor", "common_name": "Tufted Titmouse", "taxa_id": 1},
    "Dryobates pubescens": {"scientific_name": "Dryobates pubescens", "common_name": "Downy Woodpecker", "taxa_id": 2},
    "Downy Woodpecker": {"scientific_name": "Dryobates pubescens", "common_name": "Downy Woodpecker", "taxa_id": 2},
    "Cardinalis cardinalis": {"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal"},
    "Northern Cardinal": {"scientific_name": "Cardinalis cardinalis", "common_name": "Northern Cardinal"},
    "Carolina Wren": {"scientific_name": "Thryothorus ludovicianus", "common_name": "Carolina Wren"},
}


async def _names(label: str, *_args, **_kwargs) -> dict:
    return dict(NAMES.get(label, {}))


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def initialized_db():
    await init_db()
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled
    settings.auth.enabled = False
    settings.public_access.enabled = False
    try:
        yield
    finally:
        settings.auth.enabled = original_auth
        settings.public_access.enabled = original_public
        await close_db()


def _two_bird_video(path) -> bytes:
    """Frame 0 shows no bird; frame 1 a red titmouse on the left; frame 2 a blue woodpecker on the right."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5, (96, 64))
    assert writer.isOpened(), "The test runtime must provide the existing OpenCV MPEG4 encoder"
    try:
        for bird in (None, ("titmouse", TITMOUSE_BOX, (0, 0, 255)), ("downy", DOWNY_BOX, (255, 0, 0)), None):
            frame = np.full((64, 96, 3), GREY, dtype=np.uint8)
            if bird:
                left, top, right, bottom = bird[1]
                frame[top:bottom, left:right] = bird[2]
            writer.write(frame)
    finally:
        writer.release()
    return path.read_bytes()


def _evidence(frame_index: int, box: list[int]) -> dict:
    return {
        "frame_index": frame_index,
        "frame_offset_seconds": frame_index / 5,
        "frame_width": 96,
        "frame_height": 64,
        "crop_box": box,
        "input_source": "model_crop",
        "input_is_cropped": True,
        "score": 0.9,
        "presence_source": "bird_crop_detector",
        "bird_box": box,
        "detector_confidence": 0.9,
    }


def _classifier() -> MagicMock:
    classifier = MagicMock()
    classifier.get_status.return_value = {}
    classifier.classify_video_async = AsyncMock(
        return_value=[
            {"label": "Baeolophus bicolor", "score": 0.82, "index": 1, "input_source": "model_crop",
             "_video_snapshot_evidence": _evidence(1, TITMOUSE_BOX)},
            {"label": "Dryobates pubescens", "score": 0.11, "index": 2, "input_source": "model_crop",
             "_video_snapshot_evidence": _evidence(2, DOWNY_BOX)},
            {"label": "Cardinalis cardinalis", "score": 0.03, "index": 3, "input_source": "model_crop",
             "_video_snapshot_evidence": None},
        ]
    )  # fmt: skip
    return classifier


def _dominant(image_bytes: bytes) -> tuple[tuple[int, int], tuple[int, int, int]]:
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        return rgb.size, rgb.getpixel((rgb.width // 2, rgb.height // 2))


async def _analysed_video_draft(client: httpx.AsyncClient, tmp_path) -> dict:
    content = _two_bird_video(tmp_path / "two-birds.mp4")
    with patch.object(manual_observation_service, "_run_analysis", new=AsyncMock()):
        created = await client.post(
            "/api/manual-observations", files={"media": ("two-birds.mp4", content, "video/mp4")}
        )
    assert created.status_code == 202, created.text
    draft_id = created.json()["id"]
    with (
        patch("app.services.manual_observation_service.get_classifier", return_value=_classifier()),
        patch("app.services.manual_observation_service.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)),
    ):
        await manual_observation_service._run_analysis(draft_id)
    status = await client.get(f"/api/manual-observations/{draft_id}")
    assert status.json()["status"] == "ready", status.text
    return status.json()


def test_a_species_is_found_by_any_of_its_names() -> None:
    results = [
        {"label": "Baeolophus bicolor", "common_name": "Tufted Titmouse"},
        {"label": "Dryobates_pubescens", "scientific_name": "Dryobates pubescens", "common_name": "Downy Woodpecker"},
    ]

    assert _result_for_species(results, ["downy  woodpecker"]) == (1, results[1])
    assert _result_for_species(results, [None, "Dryobates pubescens"]) == (1, results[1])
    assert _result_for_species(results, ["Baeolophus bicolor"]) == (0, results[0])
    assert _result_for_species(results, ["Carolina Wren", ""]) is None


def test_species_photos_are_cookie_readable_like_the_preview() -> None:
    def allowed(path: str) -> bool:
        return session_cookie_allowed(Request({"type": "http", "method": "GET", "path": path, "headers": []}))

    draft = "a" * 32
    assert allowed(f"/api/manual-observations/{draft}/species/0/photo")
    assert allowed(f"/api/manual-observations/{draft}/species/4/scene")
    assert not allowed(f"/api/manual-observations/{draft}/species/0/other")
    assert not allowed(f"/api/manual-observations/{draft}/species/12/photo")


@pytest.mark.asyncio
async def test_each_suggested_species_gets_its_own_best_frame(client: httpx.AsyncClient, tmp_path):
    draft = await _analysed_video_draft(client, tmp_path)
    try:
        titmouse, downy, cardinal = draft["predictions"]
        assert titmouse["photo_url"].endswith("/species/0/photo")
        assert titmouse["scene_url"].endswith("/species/0/scene")
        assert downy["frame_offset_seconds"] == pytest.approx(0.4)
        # No frame localised the cardinal, so the page must not pretend one did.
        assert cardinal["photo_url"] is None and cardinal["scene_url"] is None

        size, colour = _dominant((await client.get(titmouse["photo_url"])).content)
        assert size == (32, 32) and colour[0] > 200 and colour[2] < 60
        size, colour = _dominant((await client.get(downy["photo_url"])).content)
        assert size == (32, 32) and colour[2] > 200 and colour[0] < 60
        scene = await client.get(downy["scene_url"])
        assert scene.status_code == 200 and _dominant(scene.content)[0] == (96, 64)

        assert (await client.get(f"/api/manual-observations/{draft['id']}/species/2/photo")).status_code == 404
        assert (await client.get(f"/api/manual-observations/{draft['id']}/species/9/photo")).status_code == 404
        # The stored analysis keeps a plain description of the photo, not the classifier's internals.
        stored = await manual_observation_service.get(draft["id"])
        assert all("_video_snapshot_evidence" not in item for item in stored.results)
    finally:
        await client.delete(f"/api/manual-observations/{draft['id']}")


@pytest.mark.asyncio
async def test_saved_photo_follows_the_confirmed_species_and_later_corrections(client: httpx.AsyncClient, tmp_path):
    draft = await _analysed_video_draft(client, tmp_path)
    with patch("app.services.manual_observation_service.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)):
        # The person names the less obvious bird, by its common name.
        saved = await client.post(f"/api/manual-observations/{draft['id']}/confirm", json={"label": "Downy Woodpecker"})
    assert saved.status_code == 200, saved.text
    event_id = saved.json()["event_id"]

    async def photo() -> tuple[tuple[int, int], tuple[int, int, int]]:
        response = await client.get(f"/api/frigate/{event_id}/snapshot.jpg")
        assert response.status_code == 200
        thumbnail = await client.get(f"/api/frigate/{event_id}/thumbnail.jpg")
        assert thumbnail.content == response.content
        return _dominant(response.content)

    async def retag(name: str) -> dict:
        with (
            patch("app.routers.events.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)),
            patch(
                "app.routers.events.audio_service.correlate_species", new=AsyncMock(return_value=(False, None, None))
            ),
            patch("app.routers.events.broadcaster.broadcast", new=AsyncMock()),
        ):
            response = await client.patch(f"/api/events/{event_id}", json={"display_name": name})
        assert response.status_code == 200, response.text
        return response.json()

    try:
        size, colour = await photo()
        assert size == (32, 32) and colour[2] > 200, "the photo should show the woodpecker the person confirmed"

        assert (await retag("Tufted Titmouse"))["photo_changed"] is True
        size, colour = await photo()
        assert size == (32, 32) and colour[0] > 200 and colour[2] < 60

        # A species no frame localised falls back to the upload's own preview rather than another bird.
        assert (await retag("Carolina Wren"))["photo_changed"] is True
        size, colour = await photo()
        assert size == (96, 64) and abs(colour[0] - 128) < 20

        assert (await retag("Northern Cardinal"))["photo_changed"] is False
    finally:
        assert (await client.delete(f"/api/events/{event_id}")).status_code == 200


@pytest.mark.asyncio
async def test_upload_analysed_before_species_photos_still_gets_the_confirmed_bird(client: httpx.AsyncClient, tmp_path):
    """Older analyses kept the classifier's evidence with each suggestion but saved no photos."""
    import json

    from app.database import get_db

    draft = await _analysed_video_draft(client, tmp_path)
    draft_dir = manual_observation_service.directory(draft["id"])
    for photo_file in draft_dir.glob("species-*.jpg"):
        photo_file.unlink()
    older_results = [
        {"label": "Baeolophus bicolor", "score": 0.82, "_video_snapshot_evidence": _evidence(1, TITMOUSE_BOX)},
        {"label": "Dryobates pubescens", "score": 0.11, "_video_snapshot_evidence": _evidence(2, DOWNY_BOX)},
    ]
    async with get_db() as db:
        await db.execute(
            "UPDATE manual_observation_drafts SET results_json = ? WHERE id = ?",
            (json.dumps(older_results), draft["id"]),
        )
        await db.commit()

    with patch("app.services.manual_observation_service.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)):
        saved = await client.post(f"/api/manual-observations/{draft['id']}/confirm", json={"label": "Downy Woodpecker"})
    assert saved.status_code == 200, saved.text
    event_id = saved.json()["event_id"]
    try:
        size, colour = _dominant((await client.get(f"/api/frigate/{event_id}/snapshot.jpg")).content)
        assert size == (32, 32) and colour[2] > 200 and colour[0] < 60
    finally:
        assert (await client.delete(f"/api/events/{event_id}")).status_code == 200


@pytest.mark.asyncio
async def test_photo_follows_a_correction_without_holding_a_database_connection(client: httpx.AsyncClient, tmp_path):
    """Following the species can decode a frame from the upload; no pooled connection may wait on that."""
    from app.database import get_db_pool_status

    draft = await _analysed_video_draft(client, tmp_path)
    with patch("app.services.manual_observation_service.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)):
        saved = await client.post(f"/api/manual-observations/{draft['id']}/confirm", json={"label": "Downy Woodpecker"})
    event_id = saved.json()["event_id"]
    real_follow = manual_observation_service.follow_species
    seen_free: list[bool] = []

    async def follow(*args, **kwargs):
        status = get_db_pool_status()
        seen_free.append(status["available_connections"] == status["pool_size"])
        return await real_follow(*args, **kwargs)

    try:
        for species in ("Tufted Titmouse", "Downy Woodpecker"):
            with (
                patch.object(manual_observation_service, "follow_species", side_effect=follow),
                patch("app.routers.events.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)),
                patch(
                    "app.routers.events.audio_service.correlate_species",
                    new=AsyncMock(return_value=(False, None, None)),
                ),
                patch("app.routers.events.broadcaster.broadcast", new=AsyncMock()),
            ):
                if species == "Tufted Titmouse":
                    response = await client.patch(f"/api/events/{event_id}", json={"display_name": species})
                    assert response.json()["photo_changed"] is True
                else:
                    response = await client.patch(
                        "/api/events/bulk/manual-tag", json={"event_ids": [event_id], "display_name": species}
                    )
                    assert response.json()["updated_event_ids"] == [event_id]
        assert seen_free == [True, True]
        _size, colour = _dominant((await client.get(f"/api/frigate/{event_id}/snapshot.jpg")).content)
        assert colour[2] > 200, "the bulk correction should also have moved the photo back to the woodpecker"
    finally:
        assert (await client.delete(f"/api/events/{event_id}")).status_code == 200


def _jpeg(colour: tuple[int, int, int], size: tuple[int, int] = (20, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_a_frame_chosen_for_an_upload_becomes_its_photo_and_reverting_restores_the_species_photo(
    client: httpx.AsyncClient, tmp_path
):
    """An upload's photo is its own file, served ahead of the media cache, so a frame applied only to the
    cache never showed; and its "original" is the species photo, not a Frigate snapshot it never had."""
    from app.repositories.detection_repository import DetectionRepository
    from app.services.media_cache import media_cache

    draft = await _analysed_video_draft(client, tmp_path)
    with patch("app.services.manual_observation_service.taxonomy_service.get_names", new=AsyncMock(side_effect=_names)):
        saved = await client.post(f"/api/manual-observations/{draft['id']}/confirm", json={"label": "Downy Woodpecker"})
    event_id = saved.json()["event_id"]
    chosen = _jpeg((220, 30, 30))
    candidate = {
        "candidate_id": "frame-1",
        "frame_index": 3,
        "frame_offset_seconds": 0.1,
        "source_mode": "model_crop",
        "clip_variant": "manual_upload",
        "crop_box": [4, 4, 16, 16],
        "selected": False,
        "image_ref": f"{event_id}__frame-1__image",
        "snapshot_source": "hq_candidate_model_crop",
    }

    async def cached(key):
        return chosen if key == candidate["image_ref"] else None

    async def photo_colour() -> tuple[int, int, int]:
        response = await client.get(f"/api/frigate/{event_id}/snapshot.jpg")
        assert response.status_code == 200
        return _dominant(response.content)[1]

    try:
        assert (await photo_colour())[2] > 200, "starts on the woodpecker"
        with (
            patch.object(DetectionRepository, "list_snapshot_candidates", new=AsyncMock(return_value=[candidate])),
            patch.object(DetectionRepository, "mark_selected_snapshot_candidate", new=AsyncMock()),
            patch.object(media_cache, "get_snapshot", new=AsyncMock(side_effect=cached)),
            patch.object(media_cache, "get_snapshot_metadata", new=AsyncMock(return_value={})),
            patch.object(media_cache, "replace_snapshot", new=AsyncMock(return_value=True)),
            patch("app.services.archive_service.archive_service.refresh_photograph", new=AsyncMock()),
        ):
            applied = await client.post(
                f"/api/frigate/{event_id}/snapshot/apply", json={"mode": "candidate", "candidate_id": "frame-1"}
            )
            assert applied.status_code == 200, applied.text
            colour = await photo_colour()
            assert colour[0] > 200 and colour[2] < 60, "the chosen frame is the photo now"

            reverted = await client.post(f"/api/frigate/{event_id}/snapshot/apply", json={"mode": "revert_original"})
            assert reverted.status_code == 200, reverted.text
        assert (await photo_colour())[2] > 200, "back on the species photo"
    finally:
        assert (await client.delete(f"/api/events/{event_id}")).status_code == 200


@pytest.mark.asyncio
async def test_an_upload_keeps_its_common_name_when_the_lookup_returns_none(client: httpx.AsyncClient, tmp_path):
    """The list filled a missing common name from the taxon id, but live updates sent the stored empty one,
    so an uploaded bird dropped back to its scientific name after a while."""
    from app.database import get_db
    from app.repositories.detection_repository import DetectionRepository

    draft = await _analysed_video_draft(client, tmp_path)

    async def names_without_common(label: str, *_args, **_kwargs) -> dict:
        return {"scientific_name": "Archilochus colubris", "common_name": None, "taxa_id": 6432}

    with (
        patch(
            "app.services.manual_observation_service.taxonomy_service.get_names",
            new=AsyncMock(side_effect=names_without_common),
        ),
        patch(
            "app.services.manual_observation_service.taxonomy_service.get_canonical_english_name",
            new=AsyncMock(return_value="Ruby-throated Hummingbird"),
        ),
    ):
        saved = await client.post(
            f"/api/manual-observations/{draft['id']}/confirm", json={"label": "Archilochus colubris"}
        )
    assert saved.status_code == 200, saved.text
    event_id = saved.json()["event_id"]
    try:
        async with get_db() as db:
            detection = await DetectionRepository(db).get_by_frigate_event(event_id)
        assert detection.common_name == "Ruby-throated Hummingbird"
        assert detection.display_name == "Ruby-throated Hummingbird"
    finally:
        assert (await client.delete(f"/api/events/{event_id}")).status_code == 200
