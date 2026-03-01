import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import get_db, init_db

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("""
            INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, audio_confirmed)
            VALUES 
            ('event_audio_1', 'cam1', '2026-01-01 10:00:00', 1, 0.9, 'Robin', 'Robin', 1),
            ('event_audio_2', 'cam1', '2026-01-01 10:05:00', 1, 0.9, 'Robin', 'Robin', 1),
            ('event_no_audio', 'cam1', '2026-01-01 10:10:00', 1, 0.9, 'Robin', 'Robin', 0)
        """)
        await db.commit()

@pytest.mark.asyncio
async def test_get_events_with_audio_filter():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without filter
        res = await client.get("/api/events")
        assert res.status_code == 200
        assert len(res.json()) == 3
        
        # With filter
        res = await client.get("/api/events?audio_confirmed_only=true")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 2
        for item in data:
            assert item["audio_confirmed"] is True

@pytest.mark.asyncio
async def test_get_events_count_with_audio_filter():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Without filter
        res = await client.get("/api/events/count")
        assert res.status_code == 200
        assert res.json()["count"] == 3
        
        # With filter
        res = await client.get("/api/events/count?audio_confirmed_only=true")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 2
        assert data["filtered"] is True