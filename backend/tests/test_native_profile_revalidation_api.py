from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import AuthContext, require_owner
from app.routers import native_profile
from app.services.native_profile_revalidation import RevalidationStatus


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(native_profile.router)
    app.dependency_overrides[require_owner] = lambda: AuthContext("owner")
    runner = AsyncMock()
    runner.claim_upload = lambda _id: None
    runner.prepare.return_value = RevalidationStatus(state="uploading", attempt_id=str(uuid4()))
    runner.start_prepared.return_value = RevalidationStatus(state="checking")
    monkeypatch.setattr(native_profile, "native_profile_revalidation", runner)
    return app, runner


@pytest.mark.asyncio
async def test_prepare_reserves_without_native_upload(api):
    app, runner = api
    request_id = str(uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/classifier/quarantine/revalidation/prepare",
            json={"profile_fingerprint": "a" * 64, "attempt_id": request_id},
        )
    assert response.status_code == 200
    runner.prepare.assert_awaited_once_with("a" * 64, attempt_id=request_id)
    runner.start_prepared.assert_not_awaited()


@pytest.mark.asyncio
async def test_three_photos_and_clip_are_passed_only_after_bounded_upload(api):
    app, runner = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/classifier/quarantine/revalidation/{uuid4()}/inputs",
            files=[
                ("images", ("a.jpg", b"one", "image/jpeg")),
                ("images", ("b.jpg", b"two", "image/jpeg")),
                ("images", ("c.jpg", b"three", "image/jpeg")),
                ("video", ("clip.mp4", b"clip", "video/mp4")),
            ],
        )
    assert response.status_code == 200
    assert runner.start_prepared.await_args.args[1:] == ([b"one", b"two", b"three"], b"clip")


@pytest.mark.asyncio
async def test_unknown_or_cancelled_upload_is_refused_before_reading_body(api):
    app, runner = api

    def refuse(_id):
        raise ValueError("This diagnostic upload is no longer current.")

    runner.claim_upload = refuse
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/classifier/quarantine/revalidation/{uuid4()}/inputs", content=b"invalid")
    assert response.status_code == 409
    runner.start_prepared.assert_not_awaited()


@pytest.mark.asyncio
async def test_oversized_stream_cancels_reservation_without_starting_probe(api, monkeypatch):
    app, runner = api
    monkeypatch.setattr(native_profile, "MAX_UPLOAD_BYTES", 5)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/classifier/quarantine/revalidation/{uuid4()}/inputs", files={"images": ("a.jpg", b"larger-than-limit")}
        )
    assert response.status_code == 413
    runner.start_prepared.assert_not_awaited()
    runner.abandon_upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_guest_cannot_prepare_or_upload(api):
    from fastapi import HTTPException

    app, runner = api

    def deny():
        raise HTTPException(403, "Owner access required")

    app.dependency_overrides[require_owner] = deny
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ["prepare", f"{uuid4()}/inputs", f"{uuid4()}/cancel"]:
            response = await client.post("/classifier/quarantine/revalidation/" + path, content=b"invalid")
            assert response.status_code == 403
    runner.prepare.assert_not_awaited()
    runner.start_prepared.assert_not_awaited()
