"""A visit's own video kept outside Frigate and the media cache can still make photos and be rescored (#481).

The player plays a favourite's archived clip, and an uploaded video, long after Frigate and the media
cache have let go of them. Generating new photo options and "Score again" only looked in Frigate and
the cache, so for those visits they found nothing and silently did nothing.
"""

from unittest.mock import AsyncMock

import pytest

from app.services import archive_service as archive_module
from app.services import auto_video_classifier_service as video_module
from app.services import high_quality_snapshot_service as hq_module
from app.services import retained_visit_video as retained_module

CLIP = b"\x00\x00\x00\x18ftypmp42" + b"\x02" * 512
RECORDING = b"\x00\x00\x00\x18ftypmp42" + b"\x03" * 512


@pytest.fixture
def archive(tmp_path, monkeypatch):
    service = archive_module.ArchiveService(base_dir=tmp_path / "archive")
    monkeypatch.setattr(retained_module, "archive_service", service)

    def keep(event_id: str, *, clip: bool = True, recording: bool = False) -> None:
        event_dir = service.event_dir(event_id)
        event_dir.mkdir(parents=True)
        if clip:
            (event_dir / archive_module.CLIP_NAME).write_bytes(CLIP)
        if recording:
            (event_dir / archive_module.RECORDING_NAME).write_bytes(RECORDING)
        (event_dir / archive_module.MANIFEST_NAME).write_text("{}")

    return keep


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    videos: dict[str, object] = {}

    async def video_path_for_event(event_id: str):
        return videos.get(event_id)

    monkeypatch.setattr(retained_module.manual_observation_service, "video_path_for_event", video_path_for_event)

    def upload(event_id: str) -> None:
        path = tmp_path / f"{event_id}.mp4"
        path.write_bytes(CLIP)
        videos[event_id] = path

    return upload


@pytest.mark.asyncio
async def test_a_favourites_archived_clip_and_full_visit_are_found(archive, uploads):
    archive("evt-starred", clip=True, recording=True)

    assert (await retained_module.retained_event_clip("evt-starred")).read_bytes() == CLIP
    assert (await retained_module.retained_recording_clip("evt-starred")).read_bytes() == RECORDING
    assert await retained_module.retained_event_clip("evt-never-starred") is None


@pytest.mark.asyncio
async def test_an_uploaded_video_is_its_visits_event_clip(archive, uploads):
    uploads("manual_abc")

    assert (await retained_module.retained_event_clip("manual_abc")).read_bytes() == CLIP
    assert await retained_module.retained_recording_clip("manual_abc") is None


@pytest.mark.asyncio
async def test_new_photo_options_for_an_old_favourite_use_its_archived_clip(archive, uploads, monkeypatch):
    archive("evt-old-favourite")
    service = hq_module.high_quality_snapshot_service
    monkeypatch.setattr(service, "_read_cached_event_clip", AsyncMock(return_value=None))
    frigate = AsyncMock(return_value=(None, "clip_not_found"))
    monkeypatch.setattr(service, "_wait_for_clip", frigate)

    # Asked for by a person: the kept clip, without waiting on Frigate.
    assert await service._load_event_clip("evt-old-favourite", prefer_cached=True) == (CLIP, None)
    frigate.assert_not_awaited()
    # The automatic pass still asks Frigate first, then falls back to the kept clip.
    assert await service._load_event_clip("evt-old-favourite", prefer_cached=False) == (CLIP, None)
    frigate.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_photo_options_for_an_upload_never_ask_frigate(archive, uploads, monkeypatch):
    uploads("manual_upload")
    service = hq_module.high_quality_snapshot_service
    monkeypatch.setattr(service, "_read_cached_event_clip", AsyncMock(return_value=None))
    frigate = AsyncMock(return_value=(None, "clip_not_found"))
    monkeypatch.setattr(service, "_wait_for_clip", frigate)

    assert await service._load_event_clip("manual_upload", prefer_cached=False) == (CLIP, None)
    assert await service._load_event_clip("manual_photo_only", prefer_cached=False) == (None, "clip_unavailable")
    frigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_archived_full_visit_is_the_recording_fallback_for_photos(archive, uploads, monkeypatch):
    archive("evt-full-visit", clip=False, recording=True)
    monkeypatch.setattr(hq_module.settings.frigate, "recording_clip_enabled", False)

    assert await hq_module.high_quality_snapshot_service._load_recording_clip_bytes("evt-full-visit") == RECORDING


@pytest.mark.asyncio
async def test_score_again_uses_a_kept_video_when_frigate_and_the_cache_have_none(
    archive, uploads, monkeypatch, tmp_path
):
    archive("evt-rescore", clip=True, recording=True)
    uploads("manual_rescore")
    service = video_module.AutoVideoClassifierService()
    monkeypatch.setattr(
        video_module, "_get_valid_cached_recording_clip_path", AsyncMock(return_value=(None, None, None, None))
    )
    monkeypatch.setattr(video_module.media_cache, "get_recording_clip_path", lambda _event: None)
    monkeypatch.setattr(video_module.media_cache, "get_clip_path", lambda _event: None)
    monkeypatch.setattr(service, "_clip_file_valid", AsyncMock(return_value=True))
    frigate = AsyncMock(return_value=(False, "clip_not_found"))
    monkeypatch.setattr(service, "_wait_for_clip", frigate)

    dest = tmp_path / "clip.mp4"
    loaded, error, variant, _start = await service._load_preferred_clip("evt-rescore", str(dest))
    assert (loaded, error, variant) == (True, None, "recording")
    assert dest.read_bytes() == RECORDING

    loaded, error, variant, _start = await service._load_preferred_clip("manual_rescore", str(dest))
    assert (loaded, error, variant) == (True, None, "event")
    assert dest.read_bytes() == CLIP

    loaded, error, _variant, _start = await service._load_preferred_clip("manual_gone", str(dest))
    assert (loaded, error) == (False, "clip_unavailable")
    frigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_kept_video_counts_as_present_when_frigate_has_forgotten_the_event(archive, uploads):
    archive("evt-forgotten")

    assert await retained_module.has_retained_video("evt-forgotten") is True
    assert await retained_module.has_retained_video("evt-unknown") is False
