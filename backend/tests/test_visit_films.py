import asyncio
import os
import json
import hashlib
from unittest.mock import AsyncMock

import cv2
import httpx
import numpy as np
import pytest

from app.config import settings
from app.main import app
from app.routers import about
from app.services import visit_film_service as films
from app.services.media_cache import media_cache


@pytest.mark.parametrize(
    ("box", "frame", "expected"),
    [
        # A bird in the middle of a 4K frame: 2.6x its width, 16:9.
        ([0.45, 0.45, 0.1, 0.1], (3840, 2160), (1421, 799, 998, 562)),
        # Against the left edge: the window slides inside the frame instead of running off it.
        ([0.0, 0.4, 0.05, 0.05], (1920, 1080), (0, 324, 480, 270)),
        # A box almost the size of the frame: never larger than the frame.
        ([0.05, 0.05, 0.9, 0.9], (1280, 720), (0, 0, 1280, 720)),
    ],
)
def test_the_film_window_frames_the_bird_inside_the_picture(box, frame, expected):
    x, y, width, height = films.film_window(box, *frame)
    assert (x, y, width, height) == expected
    assert abs(width / height - 16 / 9) < 0.01
    assert x >= 0 and y >= 0 and x + width <= frame[0] and y + height <= frame[1]


def _recording(path, seconds=6, fps=25, size=(1920, 1080)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for index in range(seconds * fps):
        frame = np.full((size[1], size[0], 3), 30, np.uint8)
        # The "bird": a bright square that moves a little, inside the box below.
        x = 900 + (index % 10)
        frame[500:580, x : x + 80] = (40, 200, 240)
        writer.write(frame)
    writer.release()


def test_a_film_is_a_short_card_sized_webm_cut_around_the_bird(tmp_path):
    source = tmp_path / "recording.mp4"
    _recording(source)
    destination = tmp_path / "film.webm"
    frames = films.render_film(source, [0.46, 0.45, 0.06, 0.08], 1.0, destination)
    assert frames == int(films.FILM_SECONDS * films.FILM_FPS)
    capture = cv2.VideoCapture(str(destination))
    assert (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))) == films.FILM_SIZE
    ok, frame = capture.read()
    capture.release()
    assert ok
    # The bright square is in the middle of the film, not cut off.
    centre = frame[150:210, 290:350]
    assert centre.mean() > 100


def test_a_recording_too_short_for_a_film_is_refused(tmp_path):
    source = tmp_path / "short.mp4"
    _recording(source, seconds=1)
    with pytest.raises(ValueError, match="recording_too_short"):
        films.render_film(source, [0.46, 0.45, 0.06, 0.08], 0.9, tmp_path / "film.webm")


@pytest.mark.asyncio
async def test_a_film_path_never_leaves_the_films_folder():
    with pytest.raises(ValueError):
        films.visit_film_service.path_for("../../etc/passwd")
    assert await films.visit_film_service.ready_path("../x") is None
    assert await films.visit_film_service.request("../x") == "unavailable"


@pytest.fixture
def film_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(about, "require_event_access", AsyncMock())
    return tmp_path


@pytest.mark.asyncio
async def test_a_film_not_made_yet_is_asked_for_and_the_card_keeps_its_photograph(film_dir, monkeypatch):
    requested = []
    monkeypatch.setattr(
        films.visit_film_service,
        "request",
        AsyncMock(side_effect=lambda event_id: requested.append(event_id) or "pending"),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/about/showcase/1790957361.937179-wfjaqa.webm")
    assert response.status_code == 404
    assert response.headers["x-film-status"] == "pending"
    assert requested == ["1790957361.937179-wfjaqa"]


@pytest.mark.asyncio
async def test_a_made_film_is_served_as_webm_under_the_clip_rules(film_dir, photo):
    (film_dir / "1790957361.937179-wfjaqa.webm").write_bytes(b"\x1a\x45\xdf\xa3webm")
    await _bind_film(films.visit_film_service, "1790957361.937179-wfjaqa")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/about/showcase/1790957361.937179-wfjaqa.webm")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/webm"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    about.require_event_access.assert_awaited_once()
    assert about.require_event_access.await_args.kwargs["media"] == "clip"


@pytest.mark.asyncio
async def test_no_film_is_made_without_the_media_cache(monkeypatch):
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    assert await films.visit_film_service.request("1790957361.937179-wfjaqa") == "unavailable"


@pytest.mark.asyncio
async def test_a_film_answers_byte_ranges_so_safari_plays_it(film_dir, photo):
    (film_dir / "1790957361.937179-wfjaqa.webm").write_bytes(b"\x1a\x45\xdf\xa3webm-film")
    await _bind_film(films.visit_film_service, "1790957361.937179-wfjaqa")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/about/showcase/1790957361.937179-wfjaqa.webm", headers={"Range": "bytes=0-1"})
    assert response.status_code == 206
    assert response.content == b"\x1a\x45"


@pytest.mark.asyncio
async def test_a_visit_whose_recording_is_gone_is_never_asked_for_again(tmp_path, monkeypatch):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    now = [0.0]
    service = films.VisitFilmService(clock=lambda: now[0])
    event = {"camera": "cam", "start_time": 100.0, "data": {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101.0}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    recording = AsyncMock(return_value=(None, "clip_not_retained"))
    monkeypatch.setattr(films.frigate_client, "get_recording_clip_with_error", recording)
    assert await service.request("1790957361.937179-wfjaqa") == "pending"
    await asyncio.gather(*service._tasks)
    now[0] = 10.0**9
    assert await service.request("1790957361.937179-wfjaqa") == "unavailable"
    assert recording.await_count == 1


@pytest.mark.asyncio
async def test_a_passing_failure_is_tried_again_later(tmp_path, monkeypatch):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    now = [0.0]
    service = films.VisitFilmService(clock=lambda: now[0])
    monkeypatch.setattr(
        films.frigate_client, "get_event_with_error", AsyncMock(return_value=(None, "event_request_error"))
    )
    assert await service.request("1790957361.937179-wfjaqa") == "pending"
    await asyncio.gather(*service._tasks)
    assert await service.request("1790957361.937179-wfjaqa") == "unavailable"
    now[0] = films.FAILED_RETRY_SECONDS + 1.0
    assert await service.request("1790957361.937179-wfjaqa") == "pending"
    await asyncio.gather(*service._tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("event_state", ["live", "recent", "old"])
@pytest.mark.parametrize("failure", ["clip_not_retained", "recording_too_short"])
async def test_a_recording_still_arriving_can_recover_without_retrying_old_absence(
    tmp_path, monkeypatch, event_state, failure, photo
):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    elapsed = [0.0]
    service = films.VisitFilmService(clock=lambda: elapsed[0])
    event = {
        "camera": "cam",
        "start_time": 100,
        "end_time": None if event_state == "live" else 102,
        "data": {
            "box": [0.4, 0.4, 0.1, 0.1],
            "snapshot_frame_time": films.time.time() if event_state == "recent" else 101,
        },
    }
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    photo[0]["snapshot_photo_hints"]["event_hints"]["snapshot"]["frame_time"] = event["data"]["snapshot_frame_time"]
    recording = AsyncMock(
        side_effect=[(None, failure), (b"later-recording", None)]
        if failure == "clip_not_retained"
        else [(b"partial-recording", None), (b"later-recording", None)]
    )
    monkeypatch.setattr(films.frigate_client, "get_recording_clip_with_error", recording)
    writes = []

    def write_film(clip, box, start, destination):
        writes.append(clip)
        if clip == b"partial-recording":
            raise ValueError("recording_too_short")
        destination.write_bytes(b"finished-film")
        return 48

    monkeypatch.setattr(films, "write_film", write_film)
    assert await service.request("arriving-recording") == "pending"
    await asyncio.gather(*service._tasks)
    assert await service.request("arriving-recording") == "unavailable"
    elapsed[0] = 60
    if event_state == "old":
        elapsed[0] = films.FAILED_RETRY_SECONDS * 100
        assert await service.request("arriving-recording") == "unavailable"
        assert recording.await_count == 1
    else:
        assert await service.request("arriving-recording") == "pending"
        await asyncio.gather(*service._tasks)
        assert await service.request("arriving-recording") == "ready"
        assert recording.await_count == 2


@pytest.mark.asyncio
async def test_film_admission_is_bounded_and_deferred_requests_can_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(films, "FILMS_PENDING_LIMIT", 3, raising=False)
    service = films.VisitFilmService()
    started = asyncio.Event()
    release = asyncio.Event()

    async def render(_event_id, _fingerprint):
        started.set()
        await release.wait()

    monkeypatch.setattr(service, "_render", render)
    try:
        for index in range(10):
            assert await service.request(f"admitted-{index}") == "pending"
        await started.wait()
        assert len(service._tasks) == len(service._pending) == 3
        assert "admitted-9" not in service._pending
        assert await service.request("admitted-0") == "pending"
        assert len(service._tasks) == 3
        (tmp_path / "already-made.webm").write_bytes(b"film")
        await _bind_film(service, "already-made")
        assert await service.request("already-made") == "ready"
        release.set()
        await asyncio.gather(*service._tasks)
        assert await service.request("admitted-9") == "pending"
        await asyncio.gather(*service._tasks)
    finally:
        release.set()
        await asyncio.gather(*service._tasks)


@pytest.mark.asyncio
async def test_failed_film_memory_is_bounded_and_recent_failures_remain_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(films, "FILM_FAILURES_KEPT", 3, raising=False)
    service = films.VisitFilmService()
    monkeypatch.setattr(service, "_render", AsyncMock(side_effect=ValueError("clip_not_retained")))
    for index in range(5):
        assert await service.request(f"unavailable-{index}") == "pending"
        await asyncio.gather(*service._tasks)
    assert len(service._failed) == 3
    assert await service.request("unavailable-4") == "unavailable"
    assert await service.request("unavailable-0") == "pending"
    await asyncio.gather(*service._tasks)


def test_only_the_newest_films_are_kept(tmp_path):
    for index in range(5):
        path = tmp_path / f"event-{index}.webm"
        path.write_bytes(b"film")
        os.utime(path, (1_000 + index, 1_000 + index))
    (tmp_path / "scratch").mkdir()
    assert films.prune_films(tmp_path, keep=3) == 2
    assert sorted(path.name for path in tmp_path.glob("*.webm")) == ["event-2.webm", "event-3.webm", "event-4.webm"]
    assert (tmp_path / "scratch").is_dir()


def test_a_film_is_written_whole_and_leaves_no_scratch_behind(tmp_path):
    source = tmp_path / "recording.mp4"
    _recording(source)
    films_dir = tmp_path / "films"
    destination = films_dir / "1790957361.937179-wfjaqa.webm"
    frames = films.write_film(source.read_bytes(), [0.46, 0.45, 0.06, 0.08], 1.0, destination)
    assert frames == int(films.FILM_SECONDS * films.FILM_FPS)
    assert [path.name for path in films_dir.iterdir()] == [destination.name]


@pytest.fixture(autouse=True)
def photo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    path = tmp_path / "current.jpg"
    path.write_bytes(b"original-frigate-crop")
    metadata = {
        "source": "frigate_snapshot_cropped",
        "updated_at": "revision-1",
        "snapshot_photo_hints": {
            "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "event_hints": {"snapshot": {"frame_time": 101}, "data": {"box": [0.4, 0.4, 0.1, 0.1]}},
        },
    }
    monkeypatch.setattr(media_cache, "get_snapshot_metadata", AsyncMock(side_effect=lambda _: dict(metadata)))
    monkeypatch.setattr(media_cache, "get_snapshot_path", AsyncMock(return_value=path))
    return metadata, path


async def _bind_film(service, event_id):
    fingerprint, _metadata = await service._photo_revision(event_id)
    path = service.path_for(event_id, fingerprint)
    legacy = service.path_for(event_id)
    if legacy.is_file():
        legacy.rename(path)
    path.with_suffix(".json").write_text(json.dumps({"photo_fingerprint": fingerprint}))
    return path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,manual",
    [
        ("hq_candidate_model_crop", False),
        ("video_evidence_bird_crop", False),
        ("unknown", False),
        ("frigate_snapshot_cropped", True),
    ],
)
async def test_only_the_original_frigate_crop_can_admit_a_film(photo, monkeypatch, source, manual):
    metadata, _ = photo
    metadata.update(source=source, manual_selection=manual)
    service = films.VisitFilmService()
    render = AsyncMock()
    monkeypatch.setattr(service, "_render", render)
    assert await service.request("other-frame") == "unavailable"
    assert not service._tasks and not service._failed
    metadata.update(source="frigate_snapshot_cropped", manual_selection=False)
    assert await service.request("other-frame") == "pending"
    await asyncio.gather(*service._tasks)
    render.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["bytes", "metadata", "manual", "missing", "legacy"])
async def test_cached_film_is_withdrawn_when_its_photo_changes(film_dir, photo, change):
    metadata, image = photo
    service = films.VisitFilmService()
    path = service.path_for("same-event")
    path.write_bytes(b"film")
    if change != "legacy":
        path = await _bind_film(service, "same-event")
        assert await service.ready_path("same-event") == path
    if change == "bytes":
        image.write_bytes(b"other-bird")
    elif change == "metadata":
        metadata["updated_at"] = "revision-2"
    elif change == "manual":
        metadata["manual_selection"] = True
    elif change == "missing":
        image.unlink()
    assert await service.ready_path("same-event") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["moment", "box", "no_moment"])
async def test_retained_photo_hints_must_match_the_actual_snapshot(film_dir, photo, monkeypatch, mismatch):
    metadata, _ = photo
    metadata["snapshot_photo_hints"]["event_hints"] = {
        "snapshot": {"frame_time": 101},
        "data": {"box": [0.4, 0.4, 0.1, 0.1]},
    }
    data = {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101}
    if mismatch == "moment":
        data["snapshot_frame_time"] = 103
    elif mismatch == "box":
        data["box"] = [0.1, 0.1, 0.1, 0.1]
    else:
        del data["snapshot_frame_time"]
    monkeypatch.setattr(
        films.frigate_client,
        "get_event_with_error",
        AsyncMock(return_value=({"camera": "cam", "start_time": 100, "data": data}, None)),
    )
    recording = AsyncMock()
    monkeypatch.setattr(films.frigate_client, "get_recording_clip_with_error", recording)
    service = films.VisitFilmService()
    assert await service.request("mismatch") == "pending"
    await asyncio.gather(*service._tasks)
    recording.assert_not_awaited()
    assert not service._failed


@pytest.mark.asyncio
async def test_photo_change_during_render_never_publishes_the_other_bird(film_dir, photo, monkeypatch):
    metadata, image = photo
    event = {"camera": "cam", "data": {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    monkeypatch.setattr(
        films.frigate_client, "get_recording_clip_with_error", AsyncMock(return_value=(b"recording", None))
    )

    def render(_clip, _box, _start, destination):
        destination.write_bytes(b"film-of-original-bird")
        image.write_bytes(b"owner-selected-other-bird")
        return 48

    monkeypatch.setattr(films, "write_film", render)
    service = films.VisitFilmService()
    assert await service.request("changed") == "pending"
    await asyncio.gather(*service._tasks)
    assert not list(film_dir.glob("changed*.webm"))
    assert not service._failed
    assert not list(film_dir.glob("tmp*"))


@pytest.mark.asyncio
async def test_an_original_crop_publishes_a_fingerprint_bound_film(film_dir, photo, monkeypatch):
    event = {"camera": "cam", "data": {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    monkeypatch.setattr(
        films.frigate_client, "get_recording_clip_with_error", AsyncMock(return_value=(b"recording", None))
    )

    def render(_clip, _box, _start, destination):
        destination.write_bytes(b"film")
        return 48

    monkeypatch.setattr(films, "write_film", render)
    service = films.VisitFilmService()
    assert await service.request("original") == "pending"
    await asyncio.gather(*service._tasks)
    fingerprint, _ = await service._photo_revision("original")
    path = service.path_for("original", fingerprint)
    assert await service.ready_path("original") == path
    assert json.loads(path.with_suffix(".json").read_text())["photo_fingerprint"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source,manual", [("hq_candidate_model_crop", False), ("hq_candidate_model_crop", True)])
async def test_known_snapshot_alignment_renders_the_exact_selected_bird(film_dir, photo, monkeypatch, source, manual):
    metadata, image = photo
    aligned_box = [0.1, 0.2, 0.05, 0.08]
    metadata.update(
        source=source,
        manual_selection=manual,
        film_alignment={
            "frame_time": 101,
            "box": aligned_box,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        },
    )
    # Frigate's box is a different bird; its current best moment has also moved.
    event = {"camera": "cam", "data": {"box": [0.7, 0.4, 0.1, 0.1], "snapshot_frame_time": 110}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    recording = AsyncMock(return_value=(b"recording", None))
    monkeypatch.setattr(films.frigate_client, "get_recording_clip_with_error", recording)
    calls = []

    def render(_clip, box, start, destination):
        calls.append((box, start))
        destination.write_bytes(b"film-of-selected-bird")
        return 48

    monkeypatch.setattr(films, "write_film", render)
    service = films.VisitFilmService()
    assert await service.request("aligned") == "pending"
    await asyncio.gather(*service._tasks)
    assert await service.request("aligned") == "ready"
    recording.assert_awaited_once_with("cam", 99, 106)
    assert calls == [(aligned_box, 1.5)]


@pytest.mark.asyncio
async def test_mutable_event_hints_cannot_prove_an_old_photo_matches_a_new_snapshot(photo):
    metadata, _ = photo
    metadata.pop("snapshot_photo_hints")
    metadata["event_hints"] = {"snapshot": {"frame_time": 101}}
    service = films.VisitFilmService()
    assert await service.request("unproven") == "unavailable"
    assert not service._tasks and not service._failed


@pytest.mark.asyncio
async def test_invalid_alignment_cannot_override_valid_original_proof(film_dir, photo, monkeypatch):
    metadata, _ = photo
    metadata["film_alignment"] = {"frame_time": 999, "box": [0.7, 0.7, 0.1, 0.1], "image_sha256": "wrong"}
    event = {"camera": "cam", "data": {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    recording = AsyncMock(return_value=(None, "clip_not_retained"))
    monkeypatch.setattr(films.frigate_client, "get_recording_clip_with_error", recording)
    service = films.VisitFilmService()
    assert await service.request("original") == "pending"
    await asyncio.gather(*service._tasks)
    recording.assert_awaited_once_with("cam", 99, 106)


def test_pruning_a_film_removes_its_fingerprint_sidecar(tmp_path):
    for index in range(3):
        path = tmp_path / f"event-{index}.webm"
        path.write_bytes(b"film")
        path.with_suffix(".json").write_text("{}")
        os.utime(path, (1000 + index, 1000 + index))
    assert films.prune_films(tmp_path, keep=1) == 2
    assert sorted(path.name for path in tmp_path.glob("*.json")) == ["event-2.json"]


@pytest.mark.asyncio
async def test_cancelled_render_finishes_its_private_writer_without_publishing(film_dir, photo, monkeypatch):
    import threading

    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    event = {"camera": "cam", "data": {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    monkeypatch.setattr(
        films.frigate_client, "get_recording_clip_with_error", AsyncMock(return_value=(b"recording", None))
    )

    def render(_clip, _box, _start, destination):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5)
        destination.write_bytes(b"film")
        return 48

    monkeypatch.setattr(films, "write_film", render)
    service = films.VisitFilmService()
    assert await service.request("cancelled") == "pending"
    await asyncio.wait_for(started.wait(), timeout=5)
    task = next(iter(service._tasks))
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    await asyncio.gather(task, return_exceptions=True)
    assert not list(film_dir.glob("cancelled*.webm"))
    assert not service._pending and not service._failed
    assert not list(film_dir.glob("tmp*"))


@pytest.mark.asyncio
async def test_stale_films_are_withdrawn_from_the_route_and_leaderboard(film_dir, photo):
    from app.routers.species import _portrait_responses

    event_id = "1790957361.937179-wfjaqa"
    service = films.visit_film_service
    service.path_for(event_id).write_bytes(b"film")
    await _bind_film(service, event_id)
    portrait = {"species": "Robin", "frigate_event": event_id, "image_url": f"/api/about/showcase/{event_id}.jpg"}
    assert (await _portrait_responses([portrait], films_allowed=True))[0].film_url is not None
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(f"/api/about/showcase/{event_id}.webm")).status_code == 200
        photo[0]["manual_selection"] = True
        response = await client.get(f"/api/about/showcase/{event_id}.webm")
    assert response.status_code == 404 and response.headers["x-film-status"] == "unavailable"
    assert (await _portrait_responses([portrait], films_allowed=True))[0].film_url is None
    assert not service._pending


@pytest.mark.parametrize(
    "hints",
    [
        {"snapshot": {"frame_time": 101}},
        {"snapshot": {"frame_time": 101}, "data": {"snapshot_frame_time": 102, "box": [0.4, 0.4, 0.1, 0.1]}},
        {"snapshot": {"frame_time": 0}, "data": {"snapshot_frame_time": 101, "box": [0.4, 0.4, 0.1, 0.1]}},
        {"snapshot": {"frame_time": 101, "box": [400, 400, 500, 500]}},
        {"snapshot": {"frame_time": 101, "box": [0.1, 0.1, 0.1, 0.1]}, "data": {"box": [0.4, 0.4, 0.1, 0.1]}},
    ],
)
def test_original_photo_proof_requires_a_box_and_all_retained_fields_to_agree(hints):
    metadata = {"snapshot_photo_hints": {"event_hints": hints}}
    assert not films.snapshot_matches_photo(metadata, [0.4, 0.4, 0.1, 0.1], 101)


@pytest.mark.parametrize(
    "hints",
    [
        {"snapshot": {"frame_time": 101, "box": [0.4, 0.4, 0.1, 0.1]}},
        {"data": {"snapshot_frame_time": 101, "box": [0.4, 0.4, 0.1, 0.1]}},
        {
            "snapshot": {"frame_time": 101, "box": [0.4, 0.4, 0.1, 0.1]},
            "data": {"snapshot_frame_time": 101, "box": [0.4, 0.4, 0.1, 0.1]},
        },
    ],
)
def test_original_photo_proof_accepts_matching_normalized_localization(hints):
    metadata = {"snapshot_photo_hints": {"event_hints": hints}}
    assert films.snapshot_matches_photo(metadata, [0.4, 0.4, 0.1, 0.1], 101)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_proof", ["no_box", "conflicting_moment", "pixel_box"])
async def test_cached_original_films_require_consistent_photo_localization(film_dir, photo, bad_proof):
    metadata, _ = photo
    service = films.VisitFilmService()
    path = service.path_for("proof-changed")
    path.write_bytes(b"film")
    hints = metadata["snapshot_photo_hints"]["event_hints"]
    if bad_proof == "no_box":
        hints["data"].pop("box")
    elif bad_proof == "conflicting_moment":
        hints["data"]["snapshot_frame_time"] = 102
    else:
        hints["snapshot"]["box"] = [400, 400, 500, 500]
    # Even a sidecar matching the current raw metadata cannot make invalid proof usable.
    digest = hashlib.sha256(photo[1].read_bytes())
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
    versioned = service.path_for("proof-changed", digest.hexdigest())
    path.rename(versioned)
    versioned.with_suffix(".json").write_text(json.dumps({"photo_fingerprint": digest.hexdigest()}))
    assert await service.ready_path("proof-changed") is None
    assert await service.request("proof-changed") == "unavailable"
    assert not service._tasks and not service._failed


@pytest.mark.asyncio
async def test_a_delayed_response_path_keeps_its_photo_revision_after_another_is_published(
    film_dir, photo, monkeypatch
):
    metadata, image = photo
    service = films.VisitFilmService()
    event_id = "delayed-open"
    service.path_for(event_id).write_bytes(b"film-A")
    await _bind_film(service, event_id)
    delayed_response_path = await service.ready_path(event_id)
    assert delayed_response_path.read_bytes() == b"film-A"
    image.write_bytes(b"photo-B")
    metadata["updated_at"] = "revision-B"
    metadata["snapshot_photo_hints"]["image_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
    fingerprint_b, _ = await service._photo_revision(event_id)
    event = {"camera": "cam", "data": {"box": [0.4, 0.4, 0.1, 0.1], "snapshot_frame_time": 101}}
    monkeypatch.setattr(films.frigate_client, "get_event_with_error", AsyncMock(return_value=(event, None)))
    monkeypatch.setattr(
        films.frigate_client, "get_recording_clip_with_error", AsyncMock(return_value=(b"recording", None))
    )

    def render(_clip, _box, _start, destination):
        destination.write_bytes(b"film-B")
        return 48

    monkeypatch.setattr(films, "write_film", render)
    await service._render(event_id, fingerprint_b)
    current_path = await service.ready_path(event_id)
    assert current_path.read_bytes() == b"film-B"
    # FileResponse may open its path only after this newer film was published.
    assert delayed_response_path.read_bytes() == b"film-A"
    assert current_path != delayed_response_path


@pytest.mark.parametrize("fingerprint", ["../outside", "short", "g" * 64, "A" * 64])
def test_versioned_film_paths_accept_only_sha256_fingerprints(fingerprint):
    with pytest.raises(ValueError, match="invalid_photo_fingerprint"):
        films.VisitFilmService().path_for("event", fingerprint)


def test_publishing_an_already_authorized_revision_preserves_its_immutable_file(tmp_path):
    service = films.VisitFilmService()
    fingerprint = "a" * 64
    destination = tmp_path / service.path_for("event", fingerprint).name
    destination.write_bytes(b"original-authorized-film")
    destination.with_suffix(".json").write_text(json.dumps({"photo_fingerprint": fingerprint}))
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    draft = scratch / "film.webm"
    draft.write_bytes(b"re-rendered-film")
    films._publish_film(draft, destination, fingerprint)
    assert destination.read_bytes() == b"original-authorized-film"


@pytest.mark.asyncio
async def test_a_legacy_mutable_film_is_refused_even_with_a_matching_sidecar(film_dir, photo):
    service = films.VisitFilmService()
    fingerprint, _ = await service._photo_revision("legacy")
    legacy = service.path_for("legacy")
    legacy.write_bytes(b"old-mutable-film")
    legacy.with_suffix(".json").write_text(json.dumps({"photo_fingerprint": fingerprint}))
    assert await service.ready_path("legacy") is None


def test_versioned_films_and_sidecars_share_the_forty_file_cap(film_dir):
    service = films.VisitFilmService()
    for index in range(films.FILMS_KEPT + 2):
        path = service.path_for("one-event", f"{index:064x}")
        path.write_bytes(b"film")
        path.with_suffix(".json").write_text("{}")
        os.utime(path, (1000 + index, 1000 + index))
    assert films.prune_films(film_dir) == 2
    assert len(list(film_dir.glob("*.webm"))) == films.FILMS_KEPT
    assert len(list(film_dir.glob("*.json"))) == films.FILMS_KEPT
    assert not service.path_for("one-event", f"{0:064x}").exists()
    assert not service.path_for("one-event", f"{1:064x}").with_suffix(".json").exists()
