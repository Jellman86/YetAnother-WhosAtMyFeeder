import pytest
import aiosqlite

from app.repositories.detection_repository import DetectionRepository


async def _create_snapshot_candidate_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE snapshot_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frigate_event TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            frame_index INTEGER NOT NULL,
            frame_offset_seconds FLOAT,
            source_mode TEXT NOT NULL,
            clip_variant TEXT NOT NULL,
            crop_box_json TEXT,
            crop_confidence FLOAT,
            classifier_label TEXT,
            classifier_score FLOAT,
            ranking_score FLOAT NOT NULL,
            selected BOOLEAN DEFAULT 0,
            thumbnail_ref TEXT,
            image_ref TEXT,
            snapshot_source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(frigate_event, candidate_id)
        )
        """
    )


@pytest.mark.asyncio
async def test_snapshot_candidate_repository_replaces_and_selects_candidates():
    async with aiosqlite.connect(":memory:") as db:
        await _create_snapshot_candidate_table(db)
        await db.commit()

        repo = DetectionRepository(db)

        await repo.replace_snapshot_candidates(
            "evt-1",
            [
                {
                    "candidate_id": "cand-a",
                    "frame_index": 10,
                    "frame_offset_seconds": 0.4,
                    "source_mode": "full_frame",
                    "clip_variant": "event",
                    "crop_box": None,
                    "crop_confidence": None,
                    "classifier_label": "Robin",
                    "classifier_score": 0.61,
                    "ranking_score": 0.61,
                    "selected": False,
                    "thumbnail_ref": "evt-1-cand-a",
                    "image_ref": "evt-1-cand-a-full",
                    "snapshot_source": "hq_candidate_full_frame",
                },
                {
                    "candidate_id": "cand-b",
                    "frame_index": 12,
                    "frame_offset_seconds": 0.48,
                    "source_mode": "model_crop",
                    "clip_variant": "recording",
                    "crop_box": [10, 12, 110, 112],
                    "crop_confidence": 0.92,
                    "classifier_label": "Robin",
                    "classifier_score": 0.88,
                    "ranking_score": 0.95,
                    "selected": True,
                    "thumbnail_ref": "evt-1-cand-b",
                    "image_ref": "evt-1-cand-b-full",
                    "snapshot_source": "hq_candidate_model_crop",
                },
            ],
        )

        candidates = await repo.list_snapshot_candidates("evt-1")
        assert [candidate["candidate_id"] for candidate in candidates] == ["cand-b", "cand-a"]
        assert candidates[0]["selected"] is True
        assert candidates[0]["crop_box"] == [10, 12, 110, 112]

        selected = await repo.get_selected_snapshot_candidate("evt-1")
        assert selected is not None
        assert selected["candidate_id"] == "cand-b"
        assert selected["source_mode"] == "model_crop"

        await repo.replace_snapshot_candidates(
            "evt-1",
            [
                {
                    "candidate_id": "cand-c",
                    "frame_index": 4,
                    "frame_offset_seconds": 0.16,
                    "source_mode": "frigate_hint_crop",
                    "clip_variant": "event",
                    "crop_box": [2, 4, 80, 84],
                    "crop_confidence": 0.71,
                    "classifier_label": "Blue Tit",
                    "classifier_score": 0.77,
                    "ranking_score": 0.83,
                    "selected": True,
                    "thumbnail_ref": "evt-1-cand-c",
                    "image_ref": "evt-1-cand-c-full",
                    "snapshot_source": "hq_candidate_frigate_hint_crop",
                }
            ],
        )

        replaced = await repo.list_snapshot_candidates("evt-1")
        assert [candidate["candidate_id"] for candidate in replaced] == ["cand-c"]
        assert replaced[0]["selected"] is True


@pytest.mark.asyncio
async def test_snapshot_candidate_repository_gracefully_handles_missing_table():
    async with aiosqlite.connect(":memory:") as db:
        repo = DetectionRepository(db)

        assert await repo.list_snapshot_candidates("evt-missing") == []
        assert await repo.get_selected_snapshot_candidate("evt-missing") is None

        await repo.replace_snapshot_candidates(
            "evt-missing",
            [{"candidate_id": "cand-a", "frame_index": 1, "ranking_score": 0.5}],
        )
