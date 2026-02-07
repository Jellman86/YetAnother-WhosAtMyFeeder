import pytest
import httpx

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ya-wamf-backend"
    assert "status" in data
    assert "ml" in data

