"""Daily summary unresolved count must match across owner and guest for the same window (#1086).

Previously guests counted unresolved detections client-side from a 50-item recent-events buffer,
so a busy day with 128 unresolved captures could report 2 for a guest while the owner saw 128.
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers import events as events_router
from app.routers import stats as stats_router
from app.utils.api_datetime import serialize_storage_datetime

NOW = datetime(2034, 3, 10, 18, 0, 0)
THRESHOLD = 0.6


@pytest_asyncio.fixture(autouse=True)
async def isolated_db(monkeypatch):
    monkeypatch.setattr(stats_router, "utc_naive_now", lambda: NOW)
    monkeypatch.setattr(events_router, "utc_naive_now", lambda: NOW)
    monkeypatch.setattr(settings.classification, "threshold", THRESHOLD)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.auth, "username", "owner")
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        yield
    finally:
        await close_db()


def _owner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('owner')}"}


async def _seed_rows(rows: list[tuple]) -> None:
    async with get_db() as db:
        await db.executemany(
            """
            INSERT INTO detections (
                frigate_event, camera_name, detection_time, detection_index, score,
                display_name, category_name, scientific_name, is_hidden, manual_tagged
            )
            VALUES (?, 'birdcam', ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        await db.commit()


def _row(
    event: str,
    *,
    at: datetime | str,
    name: str = "European Robin",
    category: str | None = None,
    score: float = 0.9,
    scientific: str | None = "Erithacus rubecula",
    hidden: int = 0,
    manual: int = 0,
) -> tuple:
    stored = at if isinstance(at, str) else serialize_storage_datetime(at)
    return (event, stored, score, name, category if category is not None else name, scientific, hidden, manual)


@pytest.mark.asyncio
async def test_guest_and_owner_receive_same_unresolved_count_beyond_recent_page_limit():
    rows: list[tuple] = []
    # Establish European Robin so it is never a new-species candidate.
    for index in range(5):
        rows.append(_row(f"hist-{index}", at=NOW - timedelta(days=20, hours=index)))

    # 126 older unresolved captures inside the 24h window (outside the newest 50 events):
    # 100 Unknown Bird + 26 named below threshold.
    for index in range(100):
        rows.append(
            _row(
                f"unknown-old-{index}",
                at=NOW - timedelta(hours=20) + timedelta(minutes=index),
                name="Unknown Bird",
                score=0.9,
                scientific=None,
            )
        )
    for index in range(26):
        rows.append(
            _row(
                f"low-old-{index}",
                at=NOW - timedelta(hours=12) + timedelta(minutes=index),
                name="European Robin",
                score=THRESHOLD - 0.05,
            )
        )

    # 48 recent confident named captures + 2 recent unresolved captures (newest 50 total).
    for index in range(48):
        rows.append(_row(f"named-recent-{index}", at=NOW - timedelta(minutes=50 - index)))
    rows.append(
        _row(
            "unknown-recent-1",
            at=NOW - timedelta(minutes=2),
            name="Unknown Bird",
            score=0.9,
            scientific=None,
        )
    )
    rows.append(
        _row(
            "low-recent-2",
            at=NOW - timedelta(minutes=1),
            name="European Robin",
            score=THRESHOLD - 0.01,
        )
    )

    # Non-qualifying controls inside the window.
    rows.append(_row("on-threshold", at=NOW - timedelta(hours=3), score=THRESHOLD))
    rows.append(_row("hidden-unknown", at=NOW - timedelta(hours=3), name="Unknown Bird", scientific=None, hidden=1))
    rows.append(_row("manual-unknown", at=NOW - timedelta(hours=3), name="Unknown Bird", scientific=None, manual=1))
    rows.append(_row("manual-low", at=NOW - timedelta(hours=3), score=0.2, manual=1))

    # A 72-hour-old new species outside the 24h window still appears in the owner review queue.
    rows.append(
        _row(
            "newcomer-72h",
            at=NOW - timedelta(hours=72),
            name="Eurasian Hoopoe",
            scientific="Upupa epops",
            score=0.96,
        )
    )
    # An unknown outside the 24h window must not count.
    rows.append(_row("unknown-25h", at=NOW - timedelta(hours=25), name="Unknown Bird", scientific=None))

    await _seed_rows(rows)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        owner_summary = await client.get("/api/stats/daily-summary", headers=_owner_headers())
        guest_summary = await client.get("/api/stats/daily-summary")
        guest_events = await client.get("/api/events?limit=200")
        guest_queue = await client.get("/api/events/review-queue?limit=1")
        owner_queue = await client.get("/api/events/review-queue?limit=1", headers=_owner_headers())

    assert owner_summary.status_code == 200, owner_summary.text
    assert guest_summary.status_code == 200, guest_summary.text
    assert owner_summary.json()["unresolved_count"] == 128
    assert guest_summary.json()["unresolved_count"] == 128

    # Guest events list is still capped at 50 and review-queue stays owner-only.
    assert guest_events.status_code == 200
    assert len(guest_events.json()) == 50
    assert guest_queue.status_code in (401, 403)

    # Owner review queue still includes the 72-hour newcomer alongside the 128 windowed captures.
    assert owner_queue.status_code == 200
    assert owner_queue.json()["total"] == 129


@pytest.mark.asyncio
async def test_guest_unresolved_count_respects_public_history_cutoff(monkeypatch):
    # At 18:00 UTC, rolling 24h starts yesterday 18:00 UTC; with show_historical_days=0 the guest
    # history floor is today 00:00 UTC.
    monkeypatch.setattr(settings.public_access, "show_historical_days", 0)
    await _seed_rows(
        [
            _row("before-midnight", at=datetime(2034, 3, 9, 21, 0, 0), name="Unknown Bird", scientific=None),
            _row("after-midnight", at=datetime(2034, 3, 10, 9, 0, 0), name="Unknown Bird", scientific=None),
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        owner = (await client.get("/api/stats/daily-summary", headers=_owner_headers())).json()
        guest = (await client.get("/api/stats/daily-summary")).json()

    assert owner["unresolved_count"] == 2
    assert guest["unresolved_count"] == 1


@pytest.mark.asyncio
async def test_daily_summary_today_and_legacy_timestamps_count_exact_window(monkeypatch):
    # Viewer in America/New_York (UTC-5 on 2034-03-10 before DST): midnight local is 05:00 UTC.
    await _seed_rows(
        [
            _row("before-ny-midnight", at="2034-03-10 04:59:59", name="Unknown Bird", scientific=None),
            _row("at-ny-midnight", at="2034-03-10T05:00:00Z", name="Unknown Bird", scientific=None),
            _row("legacy-space-format", at="2034-03-10 12:30:00", score=THRESHOLD - 0.1),
            _row("at-window-end", at="2034-03-10 18:00:00", name="background", scientific=None),
        ]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        today_ny = (
            await client.get("/api/stats/daily-summary?window=today", headers={"X-Timezone": "America/New_York"})
        ).json()
        rolling = (await client.get("/api/stats/daily-summary")).json()

    assert today_ny["unresolved_count"] == 3
    assert rolling["unresolved_count"] == 4
