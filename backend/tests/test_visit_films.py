import asyncio
import os
from unittest.mock import AsyncMock

import cv2
import httpx
import numpy as np
import pytest

from app.config import settings
from app.main import app
from app.routers import about
from app.services import visit_film_service as films


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


def test_a_film_path_never_leaves_the_films_folder():
    with pytest.raises(ValueError):
        films.visit_film_service.path_for("../../etc/passwd")
    assert films.visit_film_service.ready_path("../x") is None
    assert films.visit_film_service.request("../x") == "unavailable"


@pytest.fixture
def film_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(films, "FILMS_DIR", tmp_path)
    monkeypatch.setattr(about, "require_event_access", AsyncMock())
    return tmp_path


@pytest.mark.asyncio
async def test_a_film_not_made_yet_is_asked_for_and_the_card_keeps_its_photograph(film_dir, monkeypatch):
    requested = []
    monkeypatch.setattr(films.visit_film_service, "request", lambda event_id: requested.append(event_id) or "pending")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/about/showcase/1790957361.937179-wfjaqa.webm")
    assert response.status_code == 404
    assert response.headers["x-film-status"] == "pending"
    assert requested == ["1790957361.937179-wfjaqa"]


@pytest.mark.asyncio
async def test_a_made_film_is_served_as_webm_under_the_clip_rules(film_dir):
    (film_dir / "1790957361.937179-wfjaqa.webm").write_bytes(b"\x1a\x45\xdf\xa3webm")
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
    assert films.visit_film_service.request("1790957361.937179-wfjaqa") == "unavailable"


@pytest.mark.asyncio
async def test_a_film_answers_byte_ranges_so_safari_plays_it(film_dir):
    (film_dir / "1790957361.937179-wfjaqa.webm").write_bytes(b"\x1a\x45\xdf\xa3webm-film")
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
    assert service.request("1790957361.937179-wfjaqa") == "pending"
    await asyncio.gather(*service._tasks)
    now[0] = 10.0**9
    assert service.request("1790957361.937179-wfjaqa") == "unavailable"
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
    assert service.request("1790957361.937179-wfjaqa") == "pending"
    await asyncio.gather(*service._tasks)
    assert service.request("1790957361.937179-wfjaqa") == "unavailable"
    now[0] = films.FAILED_RETRY_SECONDS + 1.0
    assert service.request("1790957361.937179-wfjaqa") == "pending"
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
