"""Running the scan: what it touches, and what it refuses to touch."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.services import media_integrity_scan as scan_module
from app.services.media_integrity_scan import run_media_integrity_scan


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.commit()
    try:
        yield
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        await close_db()


@pytest.fixture(autouse=True)
def scan_settings():
    m = settings.maintenance
    original = (
        m.media_integrity_scan_enabled,
        m.media_integrity_scan_media,
        m.media_integrity_scan_batch_size,
        m.media_integrity_scan_interval_hours,
        m.frigate_missing_behavior,
        settings.frigate.clips_enabled,
    )
    m.media_integrity_scan_enabled = True
    m.media_integrity_scan_media = "any"
    m.media_integrity_scan_batch_size = 100
    m.media_integrity_scan_interval_hours = 6
    m.frigate_missing_behavior = "mark_missing"
    settings.frigate.clips_enabled = True
    scan_module._state.last = None
    scan_module._state.running = False
    yield
    (
        m.media_integrity_scan_enabled,
        m.media_integrity_scan_media,
        m.media_integrity_scan_batch_size,
        m.media_integrity_scan_interval_hours,
        m.frigate_missing_behavior,
        settings.frigate.clips_enabled,
    ) = original


async def _insert(event_id: str, *, days_since_check=30, status="present"):
    checked = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_since_check)
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, frigate_status, frigate_last_checked_at
            ) VALUES (?, 1, 0.9, 'Robin', 'Robin', ?, 'cam1', 0, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                event_id,
                status,
                checked.isoformat(sep=" "),
            ),
        )
        await db.commit()


async def _status_of(event_id: str):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT frigate_status, frigate_last_checked_at FROM detections WHERE frigate_event = ?",
            (event_id,),
        )
        return await cur.fetchone()


@pytest.mark.asyncio
async def test_a_frigate_outage_never_marks_history_missing():
    """The most destructive mistake this job could make.

    "We could not reach Frigate" is not "Frigate no longer has it". Recording
    the first as the second marks a healthy history missing, and on `delete`
    removes it, during an outage the owner is probably already dealing with.
    """
    await _insert("evt-outage")

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value=None)),
        patch.object(scan_module.frigate_client, "get_event_with_error", new=AsyncMock()) as never_asked,
    ):
        result = await run_media_integrity_scan()

    assert result.status == "frigate_unreachable"
    assert result.checked == 0
    never_asked.assert_not_awaited()
    assert (await _status_of("evt-outage"))[0] == "present"


@pytest.mark.asyncio
async def test_a_frigate_client_that_raises_is_treated_as_unreachable():
    """`get_version` raising must be as safe as it returning nothing."""
    await _insert("evt-raise")

    with patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(side_effect=OSError("refused"))):
        result = await run_media_integrity_scan()

    assert result.status == "frigate_unreachable"
    assert (await _status_of("evt-raise"))[0] == "present"


@pytest.mark.asyncio
async def test_a_retired_event_is_marked_missing():
    await _insert("evt-gone")

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.14")),
        patch.object(
            scan_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=(None, "event_not_found")),
        ),
    ):
        result = await run_media_integrity_scan()

    assert result.status == "completed"
    assert result.marked_missing_count == 1
    assert (await _status_of("evt-gone"))[0] == "missing"


@pytest.mark.asyncio
async def test_a_confirmed_present_detection_is_stamped_so_it_is_not_re_asked():
    """Without stamping the check, a healthy row stays permanently stale and
    every run spends its whole batch on the same detections."""
    await _insert("evt-here")
    before = (await _status_of("evt-here"))[1]

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.14")),
        patch.object(
            scan_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True, "has_snapshot": True}, None)),
        ),
    ):
        result = await run_media_integrity_scan()

    assert result.status == "completed"
    assert result.missing == 0
    status, after = await _status_of("evt-here")
    assert status == "present"
    assert after > before, "A confirmed detection must carry a fresh check time"


@pytest.mark.asyncio
async def test_the_scan_does_nothing_while_turned_off():
    settings.maintenance.media_integrity_scan_enabled = False
    await _insert("evt-off")

    with patch.object(scan_module.frigate_client, "get_version", new=AsyncMock()) as never_asked:
        result = await run_media_integrity_scan()

    assert result.status == "disabled"
    never_asked.assert_not_awaited()
    assert (await _status_of("evt-off"))[0] == "present"


@pytest.mark.asyncio
async def test_the_batch_bounds_how_many_events_frigate_is_asked_about():
    """The old scan asked about every row every cycle. On a large history that
    is tens of thousands of requests per run, about events retired months ago."""
    for i in range(12):
        await _insert(f"evt-{i}")
    settings.maintenance.media_integrity_scan_batch_size = 5

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.14")),
        patch.object(
            scan_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True, "has_snapshot": True}, None)),
        ) as asked,
    ):
        result = await run_media_integrity_scan()

    assert result.checked == 5
    assert asked.await_count == 5
    assert result.pending == 7, "The remaining backlog must be visible"


@pytest.mark.asyncio
async def test_one_unreadable_event_does_not_condemn_it_or_stop_the_batch():
    """A transient error on a single event is not evidence the event is gone."""
    await _insert("evt-boom")
    await _insert("evt-fine")

    async def flaky(event_id, *a, **kw):
        if event_id == "evt-boom":
            raise TimeoutError("slow")
        return ({"has_clip": True, "has_snapshot": True}, None)

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.14")),
        patch.object(scan_module.frigate_client, "get_event_with_error", new=flaky),
    ):
        result = await run_media_integrity_scan()

    assert result.status == "completed"
    assert result.errors == 1
    assert (await _status_of("evt-boom"))[0] == "present", "An error must never mark a detection missing"
    assert (await _status_of("evt-fine"))[0] == "present"


@pytest.mark.asyncio
async def test_health_reports_the_scan_without_running_it():
    from app.services.media_integrity_scan import get_media_integrity_scan_status

    status = get_media_integrity_scan_status()
    assert status["enabled"] is True
    assert status["running"] is False
    assert status["batch_size"] == 100
    assert status["last_run"] is None


def test_health_carries_the_scan_so_a_stale_history_is_visible(monkeypatch):
    """#254 is a database quietly disagreeing with reality. The fix is only
    trustworthy if an owner can see the scan running and how far behind it is."""
    from app import main as main_module

    payload = main_module.build_health_payload()
    scan = payload.get("media_integrity_scan")
    assert scan is not None, "Health must report the scan alongside the other background work"
    assert scan["enabled"] is True
    assert "running" in scan and "last_run" in scan and "batch_size" in scan


@pytest.mark.asyncio
async def test_the_scheduled_cleanup_no_longer_runs_its_own_purge():
    """Two jobs walking the same rows under different settings would be worse
    than the gap being fixed: the daily cleanup's unbounded scan is gone, and
    the bounded scan owns this work."""
    import inspect

    from app import main as main_module

    source = inspect.getsource(main_module.run_cleanup)
    assert "_purge_missing_all_media" not in source
    assert "_purge_missing_media" not in source


@pytest.mark.asyncio
async def test_writes_are_chunked_so_one_scan_cannot_monopolise_a_connection():
    """The batch is configurable up to 20,000. Writing that many rows under a
    single connection holds one of five for seconds, which is the contention
    the connection-pool work exists to remove. Chunking keeps the hold bounded
    regardless of how large an owner sets the batch.
    """
    for i in range(10):
        await _insert(f"evt-chunk-{i}")
    settings.maintenance.media_integrity_scan_batch_size = 10

    acquisitions = 0
    real_get_db = scan_module.get_db

    def counting_get_db(*args, **kwargs):
        nonlocal acquisitions
        acquisitions += 1
        return real_get_db(*args, **kwargs)

    with (
        patch.object(scan_module, "MEDIA_INTEGRITY_WRITE_CHUNK", 4),
        patch.object(scan_module, "get_db", counting_get_db),
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.14")),
        patch.object(
            scan_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=(None, "event_not_found")),
        ),
    ):
        result = await run_media_integrity_scan()

    assert result.marked_missing_count == 10
    # 1 read + 3 write chunks (4, 4, 2) + 1 pending count
    assert acquisitions == 5, f"expected chunked writes, got {acquisitions} acquisitions"


@pytest.mark.asyncio
async def test_a_detection_already_marked_missing_is_never_revisited_by_the_schedule():
    """Documents a deliberate limit, and guards a dead branch.

    The scan excludes rows already `missing`, because Frigate does not un-retire
    an event and on a long history that is nearly every row. The consequence is
    that a row marked missing in error stays missing: the scheduled scan cannot
    clear it, and the manual full scan in Settings is the recovery path.
    """
    await _insert("evt-terminal", status="missing")

    with (
        patch.object(scan_module.frigate_client, "get_version", new=AsyncMock(return_value="0.14")),
        patch.object(
            scan_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True, "has_snapshot": True}, None)),
        ) as asked,
    ):
        result = await run_media_integrity_scan()

    assert result.status == "nothing_to_check"
    asked.assert_not_awaited()
    assert (await _status_of("evt-terminal"))[0] == "missing"


@pytest.mark.asyncio
async def test_a_scheduled_scan_stands_down_while_a_manual_one_is_running():
    """They walk the same rows and ask the same Frigate.

    The manual scan takes no maintenance slot today, so adding a schedule that
    actually runs makes it possible for both to be in flight at once: sixteen
    concurrent requests to Frigate instead of eight, and two writers on the same
    detections. They now share one slot, and the scheduled one yields.
    """
    from app.services.maintenance_coordinator import maintenance_coordinator
    from app.services.media_integrity_scan import MEDIA_INTEGRITY_SCAN_KIND

    await _insert("evt-contended")
    assert await maintenance_coordinator.try_acquire("manual-scan", kind=MEDIA_INTEGRITY_SCAN_KIND)
    try:
        with patch.object(scan_module.frigate_client, "get_version", new=AsyncMock()) as never_asked:
            result = await run_media_integrity_scan()
        assert result.status == "busy"
        never_asked.assert_not_awaited()
    finally:
        await maintenance_coordinator.release("manual-scan")

    assert (await _status_of("evt-contended"))[0] == "present"


@pytest.mark.asyncio
async def test_a_manual_scan_takes_the_same_slot_so_it_cannot_race_the_schedule():
    """The other half of the contract: the manual scan must claim the slot too,
    or the scheduled one has nothing to stand down for."""
    import httpx

    from app.main import app
    from app.services.maintenance_coordinator import maintenance_coordinator
    from app.services.media_integrity_scan import MEDIA_INTEGRITY_SCAN_KIND

    original_auth = settings.auth.enabled
    settings.auth.enabled = False
    assert await maintenance_coordinator.try_acquire("scheduled-scan", kind=MEDIA_INTEGRITY_SCAN_KIND)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            with patch.object(scan_module.frigate_client, "get_version", new=AsyncMock()) as never_asked:
                response = await client.post("/api/maintenance/purge-missing-media")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "busy"
            never_asked.assert_not_awaited()
    finally:
        await maintenance_coordinator.release("scheduled-scan")
        settings.auth.enabled = original_auth
