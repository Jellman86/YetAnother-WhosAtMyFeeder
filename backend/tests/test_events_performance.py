from datetime import datetime
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from app.repositories.detection_repository import Detection, DetectionRepository
from app.routers.events import CLIP_CHECK_TIMEOUT_SECONDS, batch_check_clips

from test_detection_repository import _create_detections_table, _create_taxonomy_tables


@pytest.mark.asyncio
async def test_unfiltered_events_do_not_join_or_duplicate_taxonomy_aliases():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.executemany(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            [
                ("Cyanistes caeruleus", "Blue Tit", 1),
                ("Alias caeruleus", "Blue Tit", 2),
            ],
        )
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=datetime(2026, 8, 8, 9, 0, 0),
                detection_index=1,
                score=0.9,
                display_name="Blue Tit",
                category_name="Blue Tit",
                frigate_event="evt-unfiltered-taxonomy",
                camera_name="birdcam",
            )
        )

        rows = await repo.get_all()
        count = await repo.get_count()

        assert [row.frigate_event for row in rows] == ["evt-unfiltered-taxonomy"]
        assert count == 1


@pytest.mark.asyncio
async def test_filtered_events_deduplicate_multiple_legacy_alias_rows():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.executemany(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            [
                ("Cyanistes caeruleus", "Blue Tit", 1),
                ("Alias caeruleus", "Blue Tit", 2),
            ],
        )
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=datetime(2026, 8, 8, 9, 0, 0),
                detection_index=1,
                score=0.9,
                display_name="Blue Tit",
                category_name="Blue Tit",
                frigate_event="evt-filtered-taxonomy",
                camera_name="birdcam",
            )
        )

        rows = await repo.get_all(species="Blue Tit")
        count = await repo.get_count(species="Blue Tit")

        assert [row.frigate_event for row in rows] == ["evt-filtered-taxonomy"]
        assert count == 1


@pytest.mark.asyncio
async def test_clip_checks_use_a_short_explicit_frigate_timeout():
    event = {"has_clip": True, "has_snapshot": True}
    with (
        patch(
            "app.routers.events.frigate_client.get_event_with_error", new=AsyncMock(return_value=(event, None))
        ) as get_event,
        patch("app.routers.events.media_cache.has_clip", return_value=False),
        patch("app.routers.events.media_cache.has_recording_clip", return_value=False),
        patch("app.routers.events.media_cache.has_snapshot", return_value=False),
    ):
        result = await batch_check_clips(["evt-a", "evt-b"])

    assert result["evt-a"] == {"has_frigate_event": True, "has_clip": True, "has_snapshot": True}
    assert get_event.await_count == 2
    assert all(call.kwargs["timeout"] == CLIP_CHECK_TIMEOUT_SECONDS for call in get_event.await_args_list)
