import io
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from PIL import Image

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.services.manual_observation_service import _gps_coordinates_from_ifd, _prepare_classification_results


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


def _jpeg_bytes(color: tuple[int, int, int] = (72, 116, 86)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (48, 32), color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_gps_coordinates_are_read_from_exif_rationals() -> None:
    coordinates = _gps_coordinates_from_ifd(
        {
            1: "N",
            2: ((51, 1), (30, 1), (0, 1)),
            3: "W",
            4: ((1, 1), (15, 1), (0, 1)),
        }
    )

    assert coordinates == pytest.approx((51.5, -1.25))


def test_gps_coordinates_reject_partial_or_out_of_range_metadata() -> None:
    assert _gps_coordinates_from_ifd({1: "N", 2: ((51, 1), (30, 1), (0, 1))}) is None
    assert (
        _gps_coordinates_from_ifd({1: "N", 2: ((95, 1), (0, 1), (0, 1)), 3: "E", 4: ((1, 1), (0, 1), (0, 1))}) is None
    )
    assert (
        _gps_coordinates_from_ifd({1: "N", 2: ((50, 1), (75, 1), (0, 1)), 3: "E", 4: ((1, 1), (0, 1), (0, 1))}) is None
    )


@pytest.mark.asyncio
async def test_image_results_include_runtime_model_and_taxonomy_metadata() -> None:
    classifier = MagicMock()
    classifier.get_status.return_value = {
        "active_provider": "intel_gpu",
        "inference_backend": "openvino",
        "effective_model_id": "convnext_large_inat21",
    }
    with patch(
        "app.services.manual_observation_service.taxonomy_service.get_names",
        new=AsyncMock(
            return_value={
                "scientific_name": "Erithacus rubecula",
                "common_name": "European Robin",
                "taxa_id": 55964,
            }
        ),
    ):
        results = await _prepare_classification_results([{"label": "Erithacus rubecula", "score": 0.94}], classifier)

    assert results[0] == {
        "label": "Erithacus rubecula",
        "score": 0.94,
        "scientific_name": "Erithacus rubecula",
        "common_name": "European Robin",
        "taxa_id": 55964,
        "model_id": "convnext_large_inat21",
        "model_name": "ConvNeXt Large (High Accuracy)",
        "inference_provider": "intel_gpu",
        "inference_backend": "openvino",
        "input_source": "full_frame",
        "input_is_cropped": False,
    }


@pytest.mark.asyncio
async def test_upload_creates_durable_analysis_draft(client: httpx.AsyncClient):
    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        response = await client.post(
            "/api/manual-observations",
            files={"media": ("garden-bird.jpg", _jpeg_bytes(), "image/jpeg")},
        )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["media_type"] == "image"
    assert payload["original_filename"] == "garden-bird.jpg"
    assert payload["progress_percent"] == 0
    assert payload["preview_url"].endswith("/preview")

    status = await client.get(f"/api/manual-observations/{payload['id']}")
    assert status.status_code == 200
    assert status.json()["content_sha256"]
    assert (await client.delete(f"/api/manual-observations/{payload['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_media(client: httpx.AsyncClient):
    response = await client.post(
        "/api/manual-observations",
        files={"media": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert "JPEG, PNG, WebP, MP4, MOV, or WebM" in response.json()["detail"]


@pytest.mark.asyncio
async def test_new_upload_purges_expired_unsaved_draft(client: httpx.AsyncClient):
    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        old = await client.post(
            "/api/manual-observations",
            files={"media": ("old.jpg", _jpeg_bytes((12, 34, 56)), "image/jpeg")},
        )
        old_id = old.json()["id"]
        async with get_db() as db:
            await db.execute(
                "UPDATE manual_observation_drafts SET updated_at = datetime('now', '-8 days') WHERE id = ?",
                (old_id,),
            )
            await db.commit()
        fresh = await client.post(
            "/api/manual-observations",
            files={"media": ("fresh.jpg", _jpeg_bytes((65, 43, 21)), "image/jpeg")},
        )

    assert fresh.status_code == 202
    assert (await client.get(f"/api/manual-observations/{old_id}")).status_code == 404
    assert (await client.delete(f"/api/manual-observations/{fresh.json()['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_confirmed_upload_becomes_manual_detection(client: httpx.AsyncClient):
    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        created = await client.post(
            "/api/manual-observations",
            files={"media": ("confirmed.jpg", _jpeg_bytes((92, 74, 48)), "image/jpeg")},
        )
    draft_id = created.json()["id"]

    async with get_db() as db:
        await db.execute(
            """
            UPDATE manual_observation_drafts
            SET status = 'ready', results_json = ?, progress_current = 1, progress_total = 1
            WHERE id = ?
            """,
            (
                '[{"label":"European Robin","score":0.91,"model_id":"convnext_large","inference_provider":"intel_gpu","input_source":"model_crop"}]',
                draft_id,
            ),
        )
        await db.commit()

    with patch(
        "app.services.manual_observation_service.taxonomy_service.get_names",
        new=AsyncMock(
            return_value={"scientific_name": "Passer domesticus", "common_name": "House Sparrow", "taxa_id": 2492481}
        ),
    ):
        response = await client.post(
            f"/api/manual-observations/{draft_id}/confirm",
            json={
                "label": "House Sparrow",
                "camera_name": "Garden upload",
                "notes": "Seen beside the bath",
                "latitude": 51.5074,
                "longitude": -0.1278,
                "location_source": "manual_pin",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "saved"
    assert payload["event_id"].startswith("manual_")

    async with get_db() as db:
        async with db.execute(
            """SELECT display_name, camera_name, manual_tagged, video_classification_label,
                      video_classification_score, video_classification_provider,
                      video_classification_model_id, video_classification_input_source
               FROM detections WHERE frigate_event = ?""",
            (payload["event_id"],),
        ) as cursor:
            row = await cursor.fetchone()
    assert row == (
        "House Sparrow",
        "Garden upload",
        1,
        "European Robin",
        0.91,
        "intel_gpu",
        "convnext_large",
        "model_crop",
    )

    with patch("app.routers.events.frigate_client.get_event", new=AsyncMock()) as frigate_lookup:
        event_response = await client.get("/api/events", params={"event_id": payload["event_id"]})
    assert event_response.status_code == 200
    assert event_response.json()[0]["observation_source"] == "manual_upload"
    assert event_response.json()[0]["observation_notes"] == "Seen beside the bath"
    assert event_response.json()[0]["observation_latitude"] == pytest.approx(51.5074)
    assert event_response.json()[0]["observation_longitude"] == pytest.approx(-0.1278)
    assert event_response.json()[0]["observation_location_source"] == "manual_pin"
    assert event_response.json()[0]["has_snapshot"] is True
    frigate_lookup.assert_not_awaited()

    snapshot = await client.get(f"/api/frigate/{payload['event_id']}/snapshot.jpg")
    assert snapshot.status_code == 200
    assert snapshot.headers["content-type"].startswith("image/jpeg")
    with patch("app.routers.proxy.get_http_client") as frigate_http:
        thumbnail = await client.get(f"/api/frigate/{payload['event_id']}/thumbnail.jpg")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"].startswith("image/jpeg")
    frigate_http.assert_not_called()
    assert (await client.delete(f"/api/events/{payload['event_id']}")).status_code == 200


@pytest.mark.asyncio
async def test_confirm_rejects_partial_manual_location(client: httpx.AsyncClient):
    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        created = await client.post(
            "/api/manual-observations",
            files={"media": ("location.jpg", _jpeg_bytes((9, 19, 29)), "image/jpeg")},
        )
    draft_id = created.json()["id"]
    async with get_db() as db:
        await db.execute(
            "UPDATE manual_observation_drafts SET status = 'ready', results_json = ? WHERE id = ?",
            ('[{"label":"Robin","score":0.8}]', draft_id),
        )
        await db.commit()

    response = await client.post(
        f"/api/manual-observations/{draft_id}/confirm",
        json={"label": "Robin", "latitude": 51.5},
    )

    assert response.status_code == 422

    missing_pin = await client.post(
        f"/api/manual-observations/{draft_id}/confirm",
        json={"label": "Robin", "location_source": "manual_pin"},
    )
    assert missing_pin.status_code == 422

    out_of_range = await client.post(
        f"/api/manual-observations/{draft_id}/confirm",
        json={"label": "Robin", "latitude": 91, "longitude": 0, "location_source": "manual_pin"},
    )
    assert out_of_range.status_code == 422
    assert (await client.delete(f"/api/manual-observations/{draft_id}")).status_code == 200


@pytest.mark.asyncio
async def test_manual_event_ids_are_not_sent_to_frigate_reconciliation(client: httpx.AsyncClient):
    del client
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (CURRENT_TIMESTAMP, 0, 1, 'Robin', 'Robin', 'manual_excluded', 'Upload', 0, 1)
            """
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (CURRENT_TIMESTAMP, 0, 1, 'Robin', 'Robin', 'frigate_included', 'Camera', 0, 0)
            """
        )
        await db.commit()
        from app.repositories.detection_repository import DetectionRepository

        event_ids = await DetectionRepository(db).get_all_frigate_event_ids()

    assert "manual_excluded" not in event_ids
    assert "frigate_included" in event_ids
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event IN ('manual_excluded', 'frigate_included')")
        await db.commit()


@pytest.mark.asyncio
async def test_interrupted_analysis_becomes_retryable(client: httpx.AsyncClient):
    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        created = await client.post(
            "/api/manual-observations",
            files={"media": ("interrupted.jpg", _jpeg_bytes((28, 67, 104)), "image/jpeg")},
        )
    draft_id = created.json()["id"]
    async with get_db() as db:
        await db.execute("UPDATE manual_observation_drafts SET status = 'analyzing' WHERE id = ?", (draft_id,))
        await db.commit()

    status = await client.get(f"/api/manual-observations/{draft_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "failed"
    assert status.json()["error_code"] == "interrupted"
    assert "original is safe" in status.json()["error_message"]

    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        retried = await client.post(f"/api/manual-observations/{draft_id}/retry")
    assert retried.status_code == 202
    assert retried.json()["status"] == "analyzing"
    assert retried.json()["error_code"] is None
    assert (await client.delete(f"/api/manual-observations/{draft_id}")).status_code == 200
