"""Attribution readings for #314.

Container resident memory grew from 633MiB to 4.8GiB over about a day with no
change of model, and nothing in the process could say what held it. Health now
reports where the memory sits — RSS split by kind, the Python allocator's block
count, and the size of the audio correlation buffer — so a sampled curve can be
attributed instead of guessed at.
"""

from collections import deque
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.services import process_memory
from app.services.audio.audio_service import AudioService


def test_rss_is_reported_by_kind(tmp_path):
    status = tmp_path / "status"
    status.write_text(
        "Name:\tuvicorn\nVmRSS:\t 1252224 kB\nRssAnon:\t 1000000 kB\nRssFile:\t 200000 kB\nRssShmem:\t 52224 kB\n"
    )

    with patch.object(process_memory, "PROC_SELF_STATUS", str(status)):
        facts = process_memory.collect_process_memory()

    assert facts["rss_bytes"] == 1252224 * 1024
    assert facts["anonymous_bytes"] == 1000000 * 1024
    assert facts["file_bytes"] == 200000 * 1024
    assert facts["shmem_bytes"] == 52224 * 1024


def test_an_unreadable_platform_reports_unknown_not_zero(tmp_path):
    """No /proc on this platform must not break a health read (CLAUDE.md section 1)."""
    with patch.object(process_memory, "PROC_SELF_STATUS", str(tmp_path / "missing")):
        facts = process_memory.collect_process_memory()

    assert facts["rss_bytes"] is None
    assert facts["anonymous_bytes"] is None
    # The Python allocator can always be asked, whatever the platform.
    assert isinstance(facts["python_allocated_blocks"], int)


def test_the_audio_buffer_says_how_big_it_is():
    """The correlation buffer holds up to a day of raw payloads; its size is a reading, not a guess."""
    service = AudioService.__new__(AudioService)
    service._buffer = deque(["one", "two", "three"])

    assert service.buffer_size() == 3


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_carries_the_memory_attribution(client: httpx.AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    memory = response.json()["process_memory"]
    assert "rss_bytes" in memory
    assert "anonymous_bytes" in memory
    assert "shmem_bytes" in memory
    assert "python_allocated_blocks" in memory
    assert "audio_buffer_entries" in memory
