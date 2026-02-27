import uuid

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.config import settings
from app.database import get_db, init_db, close_db


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
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


@pytest.mark.asyncio
async def test_classifier_status_includes_personalization_summary(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    event_prefix = f"status-{uuid.uuid4().hex[:8]}"
    async with get_db() as db:
        for idx in range(20):
            await db.execute(
                """
                INSERT INTO classification_feedback (
                    frigate_event, camera_name, model_id, predicted_label, corrected_label, predicted_score, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{event_prefix}-{idx}",
                    "front",
                    "default",
                    "Blue Tit",
                    "Great Tit",
                    0.82,
                    "manual_tag",
                ),
            )
        await db.commit()

    try:
        response = await client.get("/api/classifier/status")
        assert response.status_code == 200, response.text
        payload = response.json()

        assert "personalized_rerank_enabled" in payload
        assert payload["personalization_min_feedback_tags"] == 20
        assert payload["personalization_feedback_rows"] >= 20
        assert payload["personalization_active_camera_models"] >= 1
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM classification_feedback WHERE frigate_event LIKE ?", (f"{event_prefix}-%",))
            await db.commit()
