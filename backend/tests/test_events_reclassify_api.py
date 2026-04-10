from datetime import datetime, timezone
import io
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from PIL import Image

from app.auth import AuthContext, AuthLevel, require_owner
from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers import classifier as classifier_router


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_hq_enabled = settings.media_cache.high_quality_event_snapshots
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.media_cache.high_quality_event_snapshots = original_hq_enabled


async def _insert_detection(event_id: str, species_name: str, camera_name: str) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.77,
                species_name,
                species_name,
                event_id,
                camera_name,
            ),
        )
        await db.commit()


async def _delete_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


class _GoodVideoCapture:
    def __init__(self, *_args, **_kwargs):
        self._opened = True

    def isOpened(self):
        return self._opened

    def read(self):
        return True, object()

    def release(self):
        return None


class _ContentAwareVideoCapture:
    def __init__(self, path, *_args, **_kwargs):
        self._opened = True
        self._path = path

    def isOpened(self):
        return self._opened

    def read(self):
        with open(self._path, "rb") as handle:
            payload = handle.read()
        if b"recording-bad" in payload:
            return False, None
        return True, object()

    def release(self):
        return None


@pytest.mark.asyncio
async def test_reclassify_video_triggers_snapshot_upgrade_when_clip_valid(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-upgrade"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
            patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch("cv2.VideoCapture", _GoodVideoCapture):
            mock_frigate.get_event_with_error = AsyncMock(
                return_value=(
                    {
                        "has_clip": True,
                        "data": {
                            "box": [0.2, 0.3, 0.4, 0.5],
                            "region": [0.1, 0.2, 0.8, 0.9],
                        },
                    },
                    None,
                )
            )
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypisomclip", None))
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        mock_hq.replace_from_clip_bytes.assert_awaited_once_with(
            event_id,
            b"\x00\x00\x00\x18ftypisomclip",
            event_data={
                "has_clip": True,
                "data": {
                    "box": [0.2, 0.3, 0.4, 0.5],
                    "region": [0.1, 0.2, 0.8, 0.9],
                },
            },
        )
        classifier.classify_video_async.assert_awaited_once()
        assert classifier.classify_video_async.await_args.kwargs["input_context"] == {
            "is_cropped": False,
            "event_id": event_id,
            "clip_variant": "event",
            "frigate_box": [0.2, 0.3, 0.4, 0.5],
            "frigate_region": [0.1, 0.2, 0.8, 0.9],
        }
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_falls_back_to_event_clip_when_cached_recording_is_corrupt(
    client: httpx.AsyncClient,
    tmp_path,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-corrupt-recording"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])
    recording_path = tmp_path / f"{event_id}_recording.mp4"
    recording_path.write_bytes(b"\x00\x00\x00\x18ftypisomrecording-bad")

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch(
                 "app.routers.events._get_valid_cached_recording_clip_path",
                 new=AsyncMock(return_value=(str(recording_path), "cam1", 1700000000, 1700000030)),
             ), \
             patch("app.services.media_cache.media_cache.get_clip_path", return_value=None), \
             patch("cv2.VideoCapture", _ContentAwareVideoCapture):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": True}, None))
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypisomevent", None))
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        mock_frigate.get_clip_with_error.assert_awaited_once()
        mock_hq.replace_from_clip_bytes.assert_awaited_once_with(
            event_id,
            b"\x00\x00\x00\x18ftypisomevent",
            event_data={"has_clip": True},
        )
        classifier.classify_video_async.assert_awaited_once()
        assert classifier.classify_video_async.await_args.kwargs["input_context"]["clip_variant"] == "event"
        assert not recording_path.exists()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_falls_back_to_event_clip_when_cached_recording_is_too_short(
    client: httpx.AsyncClient,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-short-recording"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch(
                 "app.routers.events._get_valid_cached_recording_clip_path",
                 new=AsyncMock(return_value=(None, "cam1", 1700000000, 1700000030)),
             ), \
             patch("app.services.media_cache.media_cache.get_clip_path", return_value=None), \
             patch("cv2.VideoCapture", _GoodVideoCapture):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": True}, None))
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypisomevent", None))
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        mock_frigate.get_clip_with_error.assert_awaited_once()
        mock_hq.replace_from_clip_bytes.assert_awaited_once_with(
            event_id,
            b"\x00\x00\x00\x18ftypisomevent",
            event_data={"has_clip": True},
        )
        classifier.classify_video_async.assert_awaited_once()
        assert classifier.classify_video_async.await_args.kwargs["input_context"]["clip_variant"] == "event"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_prefers_cached_recording_clip_when_available(client: httpx.AsyncClient, tmp_path):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-recording"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])
    recording_path = tmp_path / f"{event_id}_recording.mp4"
    recording_bytes = b"\x00\x00\x00\x18ftypisomrecording"
    recording_path.write_bytes(recording_bytes)

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch(
                 "app.routers.events._get_valid_cached_recording_clip_path",
                 new=AsyncMock(return_value=(str(recording_path), "cam1", 1700000000, 1700000030)),
             ), \
             patch("app.services.media_cache.media_cache.get_clip_path", return_value=None), \
             patch("cv2.VideoCapture", _GoodVideoCapture):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": True}, None))
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypisomevent", None))
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        mock_hq.replace_from_clip_bytes.assert_awaited_once_with(
            event_id,
            recording_bytes,
            event_data={"has_clip": True},
        )
        mock_frigate.get_clip_with_error.assert_not_awaited()
        classifier.classify_video_async.assert_awaited_once()
        assert classifier.classify_video_async.await_args.kwargs["input_context"]["clip_variant"] == "recording"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_fallback_to_snapshot_does_not_trigger_snapshot_upgrade(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-fallback"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch("app.routers.events.Image.open", return_value=MagicMock()):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": False}, None))
            mock_frigate.get_snapshot = AsyncMock(return_value=b"snapshot-bytes")
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        mock_hq.replace_from_clip_bytes.assert_not_awaited()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_succeeds_even_if_snapshot_upgrade_fails(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-upgrade-failure"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch("cv2.VideoCapture", _GoodVideoCapture):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": True}, None))
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypisomclip", None))
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="frame_extract_failed")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_succeeds_even_if_snapshot_upgrade_raises(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-upgrade-exception"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_video_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch("cv2.VideoCapture", _GoodVideoCapture):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": True}, None))
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(b"\x00\x00\x00\x18ftypisomclip", None))
            mock_hq.replace_from_clip_bytes = AsyncMock(side_effect=RuntimeError("boom"))
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_falls_back_to_snapshot_when_clip_not_retained(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.media_cache.high_quality_event_snapshots = True
    event_id = "evt-reclassify-video-no-recordings"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.high_quality_snapshot_service", create=True) as mock_hq, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch("app.routers.events.Image.open", return_value=MagicMock()):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": True}, None))
            mock_frigate.get_clip_with_error = AsyncMock(return_value=(None, "clip_not_retained"))
            mock_frigate.get_snapshot = AsyncMock(return_value=b"snapshot-bytes")
            mock_hq.replace_from_clip_bytes = AsyncMock(return_value="replaced")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "video"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success"
        assert body["actual_strategy"] == "snapshot"
        mock_hq.replace_from_clip_bytes.assert_not_awaited()
        classifier.classify_async.assert_awaited_once()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_snapshot_passes_cropped_input_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-snapshot-context"
    await _insert_detection(event_id, "Unknown Bird", "cam1")
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.services.detection_service.DetectionService") as mock_detection_service, \
             patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock), \
             patch("app.routers.events.Image.open", return_value=MagicMock()):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": False}, None))
            mock_frigate.get_snapshot = AsyncMock(return_value=b"snapshot-bytes")
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "snapshot"})

        assert response.status_code == 200, response.text
        classifier.classify_async.assert_awaited_once()
        assert classifier.classify_async.await_args.kwargs["input_context"] == {
            "is_cropped": True,
            "event_id": event_id,
        }
    finally:
        await _delete_detection(event_id)
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_classifier_test_endpoint_passes_full_frame_input_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    original_mode = classifier_router.classifier_service._image_execution_mode
    classifier_router.classifier_service._image_execution_mode = "subprocess"
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    try:
        classifier_router.classifier_service.classify = MagicMock(
            side_effect=AssertionError("direct classify should not be used")
        )
        classifier_router.classifier_service.classify_async_background = AsyncMock(
            return_value=[{"label": "Robin", "score": 0.93, "index": 1}]
        )

        image_buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color="white").save(image_buffer, format="PNG")
        response = await client.post(
            "/api/classifier/test",
            files={"image": ("bird.png", image_buffer.getvalue(), "image/png")},
        )

        assert response.status_code == 200, response.text
        classifier_router.classifier_service.classify_async_background.assert_awaited_once()
        assert classifier_router.classifier_service.classify_async_background.await_args.kwargs["input_context"] == {
            "is_cropped": False
        }
    finally:
        classifier_router.classifier_service._image_execution_mode = original_mode
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_classifier_wildlife_test_endpoint_passes_full_frame_input_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    try:
        classifier_router.classifier_service.classify_wildlife = MagicMock(
            return_value=[{"label": "Mammal", "score": 0.94, "index": 2}]
        )

        image_buffer = io.BytesIO()
        Image.new("RGB", (8, 8), color="white").save(image_buffer, format="PNG")
        response = await client.post(
            "/api/classifier/wildlife/test",
            files={"image": ("animal.png", image_buffer.getvalue(), "image/png")},
        )

        assert response.status_code == 200, response.text
        classifier_router.classifier_service.classify_wildlife.assert_called_once()
        assert classifier_router.classifier_service.classify_wildlife.call_args.kwargs["input_context"] == {
            "is_cropped": False
        }
    finally:
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_events_classify_wildlife_passes_cropped_input_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-classify-wildlife-context"
    await _insert_detection(event_id, "Unknown Bird", "cam1")
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    classifier = MagicMock()
    classifier.classify_wildlife_async = AsyncMock(
        return_value=[{"label": "Mammal", "score": 0.94, "index": 2}]
    )

    try:
        with patch("app.routers.events.get_classifier", return_value=classifier), \
             patch("app.routers.events.frigate_client") as mock_frigate, \
             patch("app.routers.events.Image.open", return_value=MagicMock()):
            mock_frigate.get_snapshot = AsyncMock(return_value=b"snapshot-bytes")

            response = await client.post(f"/api/events/{event_id}/classify-wildlife")

        assert response.status_code == 200, response.text
        classifier.classify_wildlife_async.assert_awaited_once()
        assert classifier.classify_wildlife_async.await_args.kwargs["input_context"] == {"is_cropped": True}
    finally:
        await _delete_detection(event_id)
        app.dependency_overrides.pop(require_owner, None)
