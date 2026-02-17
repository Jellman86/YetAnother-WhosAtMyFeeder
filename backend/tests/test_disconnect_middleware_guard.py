from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.main as main_module


@pytest.mark.asyncio
async def test_count_requests_returns_499_for_disconnect_runtime_error():
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/events/example/reclassify"),
        is_disconnected=AsyncMock(return_value=True),
    )
    call_next = AsyncMock(side_effect=RuntimeError("No response returned."))

    response = await main_module.count_requests(request, call_next)

    assert response.status_code == 499


@pytest.mark.asyncio
async def test_count_requests_reraises_runtime_error_when_client_connected():
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/events/example/reclassify"),
        is_disconnected=AsyncMock(return_value=False),
    )
    call_next = AsyncMock(side_effect=RuntimeError("No response returned."))

    with pytest.raises(RuntimeError, match="No response returned."):
        await main_module.count_requests(request, call_next)
