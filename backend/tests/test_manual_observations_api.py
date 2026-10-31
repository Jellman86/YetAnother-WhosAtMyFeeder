import io
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from PIL import Image

from app.config import settings
from app.auth import create_access_token, SESSION_COOKIE
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
@pytest.mark.parametrize("media_type", ["image", "video"])
async def test_owner_cookie_reads_upload_preview_and_ranged_media_without_authorizing_writes(
    client: httpx.AsyncClient, monkeypatch, tmp_path, media_type
):
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    token = create_access_token("draft-owner")
    headers = {"Authorization": f"Bearer {token}"}
    content = _jpeg_bytes((31, 90, 122))
    filename, mime = "bird.jpg", "image/jpeg"
    if media_type == "video":
        import cv2
        import numpy as np

        path = tmp_path / "bird.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5, (64, 48))
        assert writer.isOpened(), "The test runtime must provide the existing OpenCV MPEG4 encoder"
        try:
            for _ in range(5):
                writer.write(np.full((48, 64, 3), (31, 90, 122), dtype=np.uint8))
        finally:
            writer.release()
        content = path.read_bytes()
        filename, mime = "bird.mp4", "video/mp4"
    with patch("app.services.manual_observation_service.manual_observation_service._run_analysis", new=AsyncMock()):
        upload = await client.post(
            "/api/manual-observations", headers=headers, files={"media": (filename, content, mime)}
        )
    assert upload.status_code == 202
    draft = upload.json()
    client.cookies.set(SESSION_COOKIE, token, path="/api")
    try:
        preview = await client.get(draft["preview_url"])
        assert preview.status_code == 200
        with Image.open(io.BytesIO(preview.content)) as image:
            image.load()
            assert image.width > 0 and image.height > 0
        assert preview.headers["cache-control"].startswith("private")
        head = await client.head(draft["preview_url"])
        assert head.status_code == 200 and head.content == b""
        assert int(head.headers["content-length"]) == len(preview.content)
        media = await client.get(draft["media_url"], headers={"Range": "bytes=0-31"})
        assert media.status_code == 206
        assert media.content == content[:32]
        assert media.headers["content-range"] == f"bytes 0-31/{len(content)}"
        assert media.headers["cache-control"] == "private, no-store"
        media_head = await client.head(draft["media_url"])
        assert media_head.status_code == 200 and media_head.content == b""
        assert int(media_head.headers["content-length"]) == len(content)

        # Cookie admission is limited to these media reads. All draft operations
        # still require a Bearer-authenticated owner, even with an owner cookie.
        for method, route in [
            ("GET", f"/api/manual-observations/{draft['id']}"),
            ("POST", f"/api/manual-observations/{draft['id']}/retry"),
            ("POST", f"/api/manual-observations/{draft['id']}/confirm"),
            ("DELETE", f"/api/manual-observations/{draft['id']}"),
        ]:
            assert (await client.request(method, route, json={})).status_code == 401
        assert (
            await client.post("/api/manual-observations", files={"media": (filename, content, mime)})
        ).status_code == 401

        client.cookies.clear()
        for bad_cookie in (None, "forged-token"):
            if bad_cookie:
                client.cookies.set(SESSION_COOKIE, bad_cookie, path="/api")
            for route in (draft["preview_url"], draft["media_url"]):
                assert (await client.get(route)).status_code == 401
        monkeypatch.setattr(settings.auth, "session_expiry_hours", -1)
        client.cookies.set(SESSION_COOKIE, create_access_token("expired-owner"), path="/api")
        for route in (draft["preview_url"], draft["media_url"]):
            assert (await client.get(route)).status_code == 401
        client.cookies.clear()
        monkeypatch.setattr(settings.public_access, "enabled", True)
        for route in (draft["preview_url"], draft["media_url"]):
            assert (await client.get(route)).status_code == 403
        client.cookies.set(SESSION_COOKIE, token, path="/api")
        assert (await client.get("/api/manual-observations/not-a-draft/preview")).status_code == 403
    finally:
        assert (await client.delete(f"/api/manual-observations/{draft['id']}", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_media(client: httpx.AsyncClient):
    response = await client.post(
        "/api/manual-observations",
        files={"media": ("notes.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 415
    assert "JPEG, PNG, WebP, MP4, MOV, or WebM" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "limit_name", "expected_detail"),
    (
        ("too-large.jpg", "image/jpeg", "MAX_IMAGE_BYTES", "Image exceeds the 0 MB limit."),
        ("too-large.mp4", "video/mp4", "MAX_VIDEO_BYTES", "Video exceeds the 0 MB limit."),
    ),
)
async def test_upload_size_limit_removes_partial_draft(
    client: httpx.AsyncClient,
    filename: str,
    content_type: str,
    limit_name: str,
    expected_detail: str,
) -> None:
    from app.services import manual_observation_service as service_module

    service = service_module.manual_observation_service
    before = set(service.base_dir.iterdir()) if service.base_dir.exists() else set()

    with patch.object(service_module, limit_name, 1):
        response = await client.post(
            "/api/manual-observations",
            files={"media": (filename, b"too large", content_type)},
        )

    after = set(service.base_dir.iterdir()) if service.base_dir.exists() else set()
    assert response.status_code == 413
    assert response.json()["detail"] == expected_detail
    assert after == before


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


def _jpeg_with_capture_time(original: str, offset: str | None, color: tuple[int, int, int]) -> bytes:
    exif = Image.Exif()
    sub = exif.get_ifd(0x8769)
    sub[0x9003] = original
    if offset is not None:
        sub[0x9011] = offset
    buffer = io.BytesIO()
    Image.new("RGB", (48, 32), color=color).save(buffer, format="JPEG", exif=exif.tobytes())
    return buffer.getvalue()


async def _upload(client: httpx.AsyncClient, name: str, content: bytes) -> httpx.Response:
    with patch(
        "app.services.manual_observation_service.manual_observation_service._run_analysis",
        new=AsyncMock(),
    ):
        return await client.post("/api/manual-observations", files={"media": (name, content, "image/jpeg")})


async def _mark_ready(draft_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            """UPDATE manual_observation_drafts SET status = 'ready', results_json = ?,
               progress_current = 1, progress_total = 1 WHERE id = ?""",
            ('[{"label":"Erithacus rubecula","score":0.9}]', draft_id),
        )
        await db.commit()


async def _detection_time(event_id: str) -> str:
    async with get_db() as db:
        async with db.execute("SELECT detection_time FROM detections WHERE frigate_event = ?", (event_id,)) as cursor:
            row = await cursor.fetchone()
    return str(row[0])


@pytest.mark.asyncio
async def test_upload_reports_the_capture_time_from_exif(client: httpx.AsyncClient):
    response = await _upload(
        client, "dated.jpg", _jpeg_with_capture_time("2026:05:01 08:15:30", "+02:00", (11, 120, 33))
    )

    assert response.status_code == 202, response.text
    assert response.json()["captured_at"] == "2026-05-01T06:15:30Z"
    assert response.json()["captured_at_source"] == "exif"
    fetched = await client.get(f"/api/manual-observations/{response.json()['id']}")
    assert fetched.json()["captured_at"] == "2026-05-01T06:15:30Z"
    assert fetched.json()["captured_at_source"] == "exif"


@pytest.mark.asyncio
async def test_upload_without_a_capture_time_says_so(client: httpx.AsyncClient):
    response = await _upload(client, "undated.jpg", _jpeg_bytes((12, 121, 34)))

    assert response.status_code == 202, response.text
    assert response.json()["captured_at"] is None
    assert response.json()["captured_at_source"] == "none"


@pytest.mark.asyncio
async def test_upload_ignores_a_future_capture_time(client: httpx.AsyncClient):
    response = await _upload(
        client, "future.jpg", _jpeg_with_capture_time("2999:01:01 00:00:00", "+00:00", (13, 122, 35))
    )

    assert response.status_code == 202, response.text
    assert response.json()["captured_at"] is None
    assert response.json()["captured_at_source"] == "none"


@pytest.mark.asyncio
async def test_confirm_without_a_time_uses_the_capture_time_not_the_save_time(client: httpx.AsyncClient):
    created = await _upload(
        client, "dated-save.jpg", _jpeg_with_capture_time("2026:05:01 08:15:30", "+02:00", (14, 123, 36))
    )
    draft_id = created.json()["id"]
    await _mark_ready(draft_id)

    with patch(
        "app.services.manual_observation_service.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Erithacus rubecula", "common_name": "European Robin"}),
    ):
        saved = await client.post(f"/api/manual-observations/{draft_id}/confirm", json={"label": "Erithacus rubecula"})

    assert saved.status_code == 200, saved.text
    assert (await _detection_time(saved.json()["event_id"])).startswith("2026-05-01 06:15:30")
    assert (await client.delete(f"/api/events/{saved.json()['event_id']}")).status_code == 200


@pytest.mark.asyncio
async def test_confirm_with_a_time_keeps_the_persons_time(client: httpx.AsyncClient):
    created = await _upload(
        client, "dated-override.jpg", _jpeg_with_capture_time("2026:05:01 08:15:30", "+02:00", (15, 124, 37))
    )
    draft_id = created.json()["id"]
    await _mark_ready(draft_id)

    with patch(
        "app.services.manual_observation_service.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Erithacus rubecula", "common_name": "European Robin"}),
    ):
        saved = await client.post(
            f"/api/manual-observations/{draft_id}/confirm",
            json={"label": "Erithacus rubecula", "observed_at": "2026-05-02T09:00:00Z"},
        )

    assert saved.status_code == 200, saved.text
    assert (await _detection_time(saved.json()["event_id"])).startswith("2026-05-02 09:00:00")
    assert (await client.delete(f"/api/events/{saved.json()['event_id']}")).status_code == 200


@pytest.mark.asyncio
async def test_duplicate_upload_names_the_draft_and_then_the_saved_observation(client: httpx.AsyncClient):
    content = _jpeg_bytes((16, 125, 38))
    created = await _upload(client, "first.jpg", content)
    draft_id = created.json()["id"]

    duplicate = await _upload(client, "again.jpg", content)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "message": "This media has already been uploaded.",
        "draft_id": draft_id,
        "event_id": None,
    }

    await _mark_ready(draft_id)
    with patch(
        "app.services.manual_observation_service.taxonomy_service.get_names",
        new=AsyncMock(return_value={"scientific_name": "Erithacus rubecula", "common_name": "European Robin"}),
    ):
        saved = await client.post(f"/api/manual-observations/{draft_id}/confirm", json={"label": "Erithacus rubecula"})
    event_id = saved.json()["event_id"]

    after_save = await _upload(client, "again.jpg", content)
    assert after_save.status_code == 409
    assert after_save.json()["detail"]["draft_id"] == draft_id
    assert after_save.json()["detail"]["event_id"] == event_id
    assert (await client.delete(f"/api/events/{event_id}")).status_code == 200
