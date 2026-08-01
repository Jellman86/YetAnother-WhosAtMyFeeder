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
from app.services.detection_service import DetectionService


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


def _image_bytes(*, color: str = "white", image_format: str = "JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_reclassify_video_enqueues_canonical_manual_job(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-video-queued"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    try:
        with patch(
            "app.routers.events.auto_video_classifier.queue_classification",
            new=AsyncMock(return_value="queued"),
        ) as queue:
            response = await client.post(
                f"/api/events/{event_id}/reclassify",
                params={"strategy": "video"},
            )

        assert response.status_code == 200, response.text
        assert response.json() == {
            "status": "queued",
            "queue_state": "queued",
            "event_id": event_id,
            "old_species": "Unknown Bird",
            "new_species": "Unknown Bird",
            "new_score": 0.77,
            "updated": False,
            "actual_strategy": "video",
        }
        queue.assert_awaited_once_with(
            event_id,
            "cam1",
            skip_delay=True,
            fallback_to_snapshot=True,
            source="manual",
        )
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_video_joins_existing_event_job(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-video-duplicate"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    try:
        with patch(
            "app.routers.events.auto_video_classifier.queue_classification",
            new=AsyncMock(return_value="duplicate"),
        ):
            response = await client.post(
                f"/api/events/{event_id}/reclassify",
                params={"strategy": "video"},
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "queued"
        assert response.json()["queue_state"] == "duplicate"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("queue_state", "expected_detail"),
    [
        ("blocked", "temporarily paused"),
        ("full", "at capacity"),
    ],
)
async def test_reclassify_video_reports_queue_backpressure(
    client: httpx.AsyncClient,
    queue_state: str,
    expected_detail: str,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = f"evt-reclassify-video-{queue_state}"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    try:
        with patch(
            "app.routers.events.auto_video_classifier.queue_classification",
            new=AsyncMock(return_value=queue_state),
        ):
            response = await client.post(
                f"/api/events/{event_id}/reclassify",
                params={"strategy": "video"},
            )

        assert response.status_code == 503, response.text
        assert expected_detail in response.json()["detail"]
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_completed_snapshot_does_not_assume_crop_query_was_applied(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-snapshot-context"
    await _insert_detection(event_id, "Unknown Bird", "cam1")
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.91, "index": 1}])

    try:
        with (
            patch("app.routers.events.get_classifier", return_value=classifier),
            patch("app.routers.events.frigate_client") as mock_frigate,
            patch("app.services.detection_service.DetectionService") as mock_detection_service,
            patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock),
        ):
            mock_frigate.get_event_with_error = AsyncMock(
                return_value=(
                    {
                        "has_clip": False,
                        "data": {
                            "box": [0.2, 0.3, 0.4, 0.5],
                            "region": [0.1, 0.2, 0.8, 0.9],
                        },
                    },
                    None,
                )
            )
            mock_frigate.get_snapshot = AsyncMock(return_value=_image_bytes())
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(
                f"/api/events/{event_id}/reclassify",
                params={"strategy": "snapshot"},
            )

        assert response.status_code == 200, response.text
        classifier.classify_async.assert_awaited_once()
        assert classifier.classify_async.await_args.kwargs["input_context"] == {
            "is_cropped": False,
            "event_id": event_id,
            "input_source": "frigate_snapshot",
            "frigate_box": [0.2, 0.3, 0.4, 0.5],
            "frigate_region": [0.1, 0.2, 0.8, 0.9],
            "restore_frigate_snapshot_crop": True,
        }
    finally:
        await _delete_detection(event_id)
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_reclassify_snapshot_preserves_identification_when_result_is_below_threshold(
    client: httpx.AsyncClient,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-snapshot-below-threshold"
    await _insert_detection(event_id, "Eurasian Blackbird", "cam1")
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Thamnophis proximus", "score": 0.657, "index": 42}])

    try:
        with (
            patch.object(settings.classification, "threshold", 0.7),
            patch.object(settings.classification, "min_confidence", 0.5),
            patch("app.routers.events.get_classifier", return_value=classifier),
            patch("app.routers.events.frigate_client") as mock_frigate,
            patch.object(DetectionService, "apply_video_result", new=AsyncMock()) as apply_result,
            patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock),
        ):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": False}, None))
            mock_frigate.get_snapshot = AsyncMock(return_value=_image_bytes())

            response = await client.post(
                f"/api/events/{event_id}/reclassify",
                params={"strategy": "snapshot"},
            )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "no_result"
        assert response.json()["reason"] == "below_threshold"
        assert response.json()["updated"] is False
        assert response.json()["new_species"] == "Eurasian Blackbird"
        apply_result.assert_not_awaited()
    finally:
        await _delete_detection(event_id)


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
async def test_reclassify_snapshot_uses_cached_snapshot_when_frigate_event_not_found(client: httpx.AsyncClient):
    """Use a locally cached snapshot when Frigate no longer knows the event."""
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-snapshot-cached"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    image_buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color="green").save(image_buffer, format="JPEG")
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.88, "index": 1}])

    try:
        with (
            patch("app.routers.events.get_classifier", return_value=classifier),
            patch("app.routers.events.frigate_client") as mock_frigate,
            patch("app.services.detection_service.DetectionService") as mock_detection_service,
            patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock),
            patch("app.routers.events.media_cache") as mock_cache,
        ):
            mock_frigate.get_event_with_error = AsyncMock(return_value=(None, "event_not_found"))
            mock_frigate.get_snapshot = AsyncMock(return_value=None)
            mock_cache.get_snapshot = AsyncMock(return_value=image_buffer.getvalue())
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "success"
        mock_frigate.get_snapshot.assert_not_awaited()
        classifier.classify_async.assert_awaited_once()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_snapshot_falls_back_to_cached_snapshot_when_frigate_fetch_fails(
    client: httpx.AsyncClient,
):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-snapshot-frigate-empty"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    image_buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color="blue").save(image_buffer, format="JPEG")
    classifier = MagicMock()
    classifier.classify_async = AsyncMock(return_value=[{"label": "Robin", "score": 0.88, "index": 1}])

    try:
        with (
            patch("app.routers.events.get_classifier", return_value=classifier),
            patch("app.routers.events.frigate_client") as mock_frigate,
            patch("app.services.detection_service.DetectionService") as mock_detection_service,
            patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock),
            patch("app.routers.events.media_cache") as mock_cache,
        ):
            mock_frigate.get_event_with_error = AsyncMock(return_value=({"has_clip": False}, None))
            mock_frigate.get_snapshot = AsyncMock(return_value=None)
            mock_cache.get_snapshot = AsyncMock(return_value=image_buffer.getvalue())
            mock_detection_service.return_value.apply_video_result = AsyncMock()

            response = await client.post(f"/api/events/{event_id}/reclassify")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "success"
        classifier.classify_async.assert_awaited_once()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_reclassify_snapshot_returns_502_when_both_frigate_and_cache_empty(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-reclassify-snapshot-no-source"
    await _insert_detection(event_id, "Unknown Bird", "cam1")

    try:
        with (
            patch("app.routers.events.frigate_client") as mock_frigate,
            patch("app.routers.events.broadcaster.broadcast", new_callable=AsyncMock),
            patch("app.routers.events.media_cache") as mock_cache,
        ):
            mock_frigate.get_event_with_error = AsyncMock(return_value=(None, "event_not_found"))
            mock_frigate.get_snapshot = AsyncMock(return_value=None)
            mock_cache.get_snapshot = AsyncMock(return_value=None)

            response = await client.post(f"/api/events/{event_id}/reclassify")

        assert response.status_code == 502, response.text
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_events_classify_wildlife_passes_cropped_input_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    event_id = "evt-classify-wildlife-context"
    await _insert_detection(event_id, "Unknown Bird", "cam1")
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="owner")

    classifier = MagicMock()
    classifier.classify_wildlife_async = AsyncMock(return_value=[{"label": "Mammal", "score": 0.94, "index": 2}])

    try:
        with (
            patch("app.routers.events.get_classifier", return_value=classifier),
            patch("app.routers.events.frigate_client") as mock_frigate,
        ):
            mock_frigate.get_snapshot = AsyncMock(return_value=_image_bytes())

            response = await client.post(f"/api/events/{event_id}/classify-wildlife")

        assert response.status_code == 200, response.text
        classifier.classify_wildlife_async.assert_awaited_once()
        assert classifier.classify_wildlife_async.await_args.kwargs["input_context"] == {"is_cropped": True}
    finally:
        await _delete_detection(event_id)
        app.dependency_overrides.pop(require_owner, None)
