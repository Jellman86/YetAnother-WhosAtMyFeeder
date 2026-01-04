from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.services.broadcaster import broadcaster
import json
import asyncio

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # seconds

@router.get("/sse")
async def sse_stream():
    async def event_generator():
        queue = await broadcaster.subscribe()
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'SSE connection established'})}\n\n"

            while True:
                try:
                    # Wait for message with timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                    yield f"data: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
