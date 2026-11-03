import asyncio

import pytest

from app.services.video_classification_waiter import VideoClassificationWaiter


@pytest.mark.asyncio
async def test_waiter_returns_immediate_completed_state():
    waiter = VideoClassificationWaiter(ttl_seconds=60, max_entries=100)
    await waiter.publish("evt1", "completed", label="Blue Jay", score=0.91)

    state = await waiter.wait_for_final_status("evt1", timeout=1)
    assert state is not None
    assert state["status"] == "completed"
    assert state["label"] == "Blue Jay"
    assert state["score"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_waiter_unblocks_when_final_status_arrives():
    waiter = VideoClassificationWaiter(ttl_seconds=60, max_entries=100)
    await waiter.publish("evt2", "pending")

    async def publish_later():
        await asyncio.sleep(0.05)
        await waiter.publish("evt2", "failed", error="clip_unavailable")

    publisher = asyncio.create_task(publish_later())
    state = await waiter.wait_for_final_status("evt2", timeout=1)
    await publisher

    assert state is not None
    assert state["status"] == "failed"
    assert state["error"] == "clip_unavailable"


@pytest.mark.asyncio
async def test_waiter_timeout_returns_latest_non_final_state():
    waiter = VideoClassificationWaiter(ttl_seconds=60, max_entries=100)
    await waiter.publish("evt3", "processing")

    state = await waiter.wait_for_final_status("evt3", timeout=0.05)
    assert state is not None
    assert state["status"] == "processing"
