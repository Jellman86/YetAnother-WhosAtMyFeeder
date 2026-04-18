import pytest
import aiosqlite

from app.repositories.detection_repository import DetectionRepository


async def _create_video_top_frames_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE video_classification_top_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frigate_event TEXT NOT NULL,
            clip_variant TEXT NOT NULL,
            frame_index INTEGER NOT NULL,
            frame_offset_seconds FLOAT,
            frame_score FLOAT NOT NULL,
            top_label TEXT,
            top_score FLOAT,
            rank INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        "CREATE INDEX ix_video_top_frames_event_rank ON video_classification_top_frames (frigate_event, rank)"
    )
    await db.execute(
        "CREATE INDEX ix_video_top_frames_event_created ON video_classification_top_frames (frigate_event, created_at)"
    )


@pytest.mark.asyncio
async def test_video_top_frame_replace_and_list():
    async with aiosqlite.connect(":memory:") as db:
        await _create_video_top_frames_table(db)
        await db.commit()

        repo = DetectionRepository(db)

        frames = [
            {
                "clip_variant": "recording",
                "frame_index": 42,
                "frame_offset_seconds": 1.68,
                "frame_score": 0.91,
                "top_label": "European Robin",
                "top_score": 0.91,
                "rank": 1,
            },
            {
                "clip_variant": "recording",
                "frame_index": 38,
                "frame_offset_seconds": 1.52,
                "frame_score": 0.83,
                "top_label": "European Robin",
                "top_score": 0.83,
                "rank": 2,
            },
            {
                "clip_variant": "recording",
                "frame_index": 50,
                "frame_offset_seconds": 2.0,
                "frame_score": 0.75,
                "top_label": "European Robin",
                "top_score": 0.75,
                "rank": 3,
            },
        ]

        await repo.replace_video_top_frames("evt-1", frames)

        result = await repo.list_video_top_frames("evt-1")
        assert len(result) == 3
        assert [r["rank"] for r in result] == [1, 2, 3]
        assert result[0]["frame_index"] == 42
        assert result[0]["frame_score"] == pytest.approx(0.91)
        assert result[0]["clip_variant"] == "recording"
        assert result[0]["top_label"] == "European Robin"


@pytest.mark.asyncio
async def test_video_top_frame_replace_removes_stale_rows():
    async with aiosqlite.connect(":memory:") as db:
        await _create_video_top_frames_table(db)
        await db.commit()

        repo = DetectionRepository(db)

        await repo.replace_video_top_frames(
            "evt-1",
            [
                {"clip_variant": "event", "frame_index": 5, "frame_offset_seconds": 0.2, "frame_score": 0.6, "top_label": "Sparrow", "top_score": 0.6, "rank": 1},
                {"clip_variant": "event", "frame_index": 10, "frame_offset_seconds": 0.4, "frame_score": 0.55, "top_label": "Sparrow", "top_score": 0.55, "rank": 2},
            ],
        )
        first = await repo.list_video_top_frames("evt-1")
        assert len(first) == 2

        await repo.replace_video_top_frames(
            "evt-1",
            [
                {"clip_variant": "recording", "frame_index": 20, "frame_offset_seconds": 0.8, "frame_score": 0.88, "top_label": "Blue Tit", "top_score": 0.88, "rank": 1},
            ],
        )
        replaced = await repo.list_video_top_frames("evt-1")
        assert len(replaced) == 1
        assert replaced[0]["frame_index"] == 20
        assert replaced[0]["top_label"] == "Blue Tit"


@pytest.mark.asyncio
async def test_video_top_frame_list_ordered_by_rank():
    async with aiosqlite.connect(":memory:") as db:
        await _create_video_top_frames_table(db)
        await db.commit()

        repo = DetectionRepository(db)

        # insert in reverse rank order
        await repo.replace_video_top_frames(
            "evt-2",
            [
                {"clip_variant": "event", "frame_index": 3, "frame_offset_seconds": 0.12, "frame_score": 0.5, "top_label": None, "top_score": None, "rank": 3},
                {"clip_variant": "event", "frame_index": 1, "frame_offset_seconds": 0.04, "frame_score": 0.9, "top_label": None, "top_score": None, "rank": 1},
                {"clip_variant": "event", "frame_index": 2, "frame_offset_seconds": 0.08, "frame_score": 0.7, "top_label": None, "top_score": None, "rank": 2},
            ],
        )

        result = await repo.list_video_top_frames("evt-2")
        assert [r["rank"] for r in result] == [1, 2, 3]
        assert [r["frame_index"] for r in result] == [1, 2, 3]


@pytest.mark.asyncio
async def test_video_top_frame_gracefully_handles_missing_table():
    async with aiosqlite.connect(":memory:") as db:
        repo = DetectionRepository(db)

        assert await repo.list_video_top_frames("evt-missing") == []

        # replace should not raise when table is absent
        await repo.replace_video_top_frames(
            "evt-missing",
            [{"clip_variant": "event", "frame_index": 1, "frame_offset_seconds": 0.04, "frame_score": 0.9, "top_label": None, "top_score": None, "rank": 1}],
        )
        assert await repo.list_video_top_frames("evt-missing") == []
