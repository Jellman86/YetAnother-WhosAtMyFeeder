import pytest
import asyncio
from app.services.broadcaster import Broadcaster


@pytest.mark.asyncio
async def test_subscribe_adds_queue():
    """Subscribe should add queue to subscribers."""
    b = Broadcaster()
    queue = await b.subscribe()

    assert queue in b.queues
    assert len(b.queues) == 1

    await b.unsubscribe(queue)


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    """Unsubscribe should remove queue from subscribers."""
    b = Broadcaster()
    queue = await b.subscribe()

    assert queue in b.queues

    await b.unsubscribe(queue)

    assert queue not in b.queues
    assert len(b.queues) == 0


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent_queue_does_not_error():
    """Unsubscribing a queue that doesn't exist should not raise error."""
    b = Broadcaster()
    fake_queue = asyncio.Queue()

    # Should not raise KeyError
    await b.unsubscribe(fake_queue)


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_subscribers():
    """Broadcast should send message to all queues."""
    b = Broadcaster()
    queue1 = await b.subscribe()
    queue2 = await b.subscribe()
    queue3 = await b.subscribe()

    message = {"type": "test", "data": "hello world"}
    await b.broadcast(message)

    # All queues should receive the message
    received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
    received3 = await asyncio.wait_for(queue3.get(), timeout=1.0)

    assert received1 == message
    assert received2 == message
    assert received3 == message

    # Cleanup
    await b.unsubscribe(queue1)
    await b.unsubscribe(queue2)
    await b.unsubscribe(queue3)


@pytest.mark.asyncio
async def test_broadcast_with_no_subscribers():
    """Broadcast with no subscribers should not raise error."""
    b = Broadcaster()

    message = {"type": "test", "data": "no one listening"}

    # Should not raise
    await b.broadcast(message)


@pytest.mark.asyncio
async def test_broadcast_continues_after_queue_error():
    """Broadcast should continue to other queues if one fails."""
    b = Broadcaster()
    queue1 = await b.subscribe()
    queue2 = await b.subscribe()

    # Close queue1 to simulate error
    # In asyncio.Queue, we can't directly "break" it, but we can test
    # that broadcast handles exceptions gracefully

    message = {"type": "test", "data": "resilient"}

    # Manually inject a broken queue
    broken_queue = asyncio.Queue()

    # Monkey-patch put to raise exception
    async def broken_put(*args, **kwargs):
        raise RuntimeError("Queue is broken")

    broken_queue.put = broken_put
    b.queues.add(broken_queue)

    # Should not raise, should remove broken queue
    await b.broadcast(message)

    # Good queues should still receive
    received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

    assert received1 == message
    assert received2 == message

    # Broken queue should be removed
    assert broken_queue not in b.queues

    # Cleanup
    await b.unsubscribe(queue1)
    await b.unsubscribe(queue2)


@pytest.mark.asyncio
async def test_concurrent_subscriptions():
    """Should handle multiple concurrent subscriptions."""
    b = Broadcaster()
    queues = []

    # Subscribe 20 clients concurrently
    async def subscribe_client():
        queue = await b.subscribe()
        queues.append(queue)

    await asyncio.gather(*[subscribe_client() for _ in range(20)])

    assert len(b.queues) == 20

    # Broadcast to all
    message = {"type": "concurrent_test", "count": 20}
    await b.broadcast(message)

    # All should receive
    for queue in queues:
        msg = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert msg == message

    # Cleanup
    for queue in queues:
        await b.unsubscribe(queue)

    assert len(b.queues) == 0


@pytest.mark.asyncio
async def test_broadcast_order_preserved():
    """Messages should be received in the order they were broadcast."""
    b = Broadcaster()
    queue = await b.subscribe()

    messages = [
        {"type": "msg", "seq": 1},
        {"type": "msg", "seq": 2},
        {"type": "msg", "seq": 3},
    ]

    for msg in messages:
        await b.broadcast(msg)

    # Receive in order
    for expected_msg in messages:
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == expected_msg

    await b.unsubscribe(queue)


@pytest.mark.asyncio
async def test_multiple_broadcasts():
    """Should handle multiple sequential broadcasts."""
    b = Broadcaster()
    queue1 = await b.subscribe()
    queue2 = await b.subscribe()

    # Send 5 messages
    for i in range(5):
        await b.broadcast({"seq": i})

    # Each queue should have all 5 messages
    for i in range(5):
        msg1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        msg2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
        assert msg1["seq"] == i
        assert msg2["seq"] == i

    await b.unsubscribe(queue1)
    await b.unsubscribe(queue2)


@pytest.mark.asyncio
async def test_queue_isolation():
    """Each queue should be independent."""
    b = Broadcaster()
    queue1 = await b.subscribe()
    queue2 = await b.subscribe()

    message = {"type": "test"}
    await b.broadcast(message)

    # Get from queue1
    msg1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
    assert msg1 == message

    # queue2 should still have its message
    msg2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
    assert msg2 == message

    # queue1 should be empty now
    assert queue1.empty()

    await b.unsubscribe(queue1)
    await b.unsubscribe(queue2)
