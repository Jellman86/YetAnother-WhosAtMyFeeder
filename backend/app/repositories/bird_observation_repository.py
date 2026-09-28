"""Durable per-bird observations attached to one Frigate capture."""

from datetime import datetime
import json

import aiosqlite

from app.services.bird_observation_selection import BirdObservationSelection


class BirdObservationRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def list_for_event(self, frigate_event: str) -> list[dict]:
        async with self.db.execute(
            """SELECT id, frigate_event, bird_index, candidate_id, clip_variant, frame_index,
                      crop_box_json, detector_confidence, species, classifier_label,
                      classifier_score, manual_species, is_hidden
               FROM bird_observations WHERE frigate_event = ? ORDER BY bird_index""",
            (frigate_event,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "frigate_event": row[1],
                "bird_index": row[2],
                "candidate_id": row[3],
                "clip_variant": row[4],
                "frame_index": row[5],
                "crop_box": json.loads(row[6]),
                "detector_confidence": row[7],
                "species": row[8],
                "classifier_label": row[9],
                "classifier_score": row[10],
                "manual_species": bool(row[11]),
                "is_hidden": bool(row[12]),
            }
            for row in rows
        ]

    async def replace_generated(self, frigate_event: str, selection: BirdObservationSelection) -> bool:
        """Replace one analyzed frame; an empty retry never erases counted history."""
        if not selection.birds or selection.clip_variant is None or selection.frame_index is None:
            return False
        existing = await self.list_for_event(frigate_event)
        manually_reviewed = [bird for bird in existing if bird["manual_species"] or bird["is_hidden"]]
        if manually_reviewed and any(
            bird["clip_variant"] != selection.clip_variant or bird["frame_index"] != selection.frame_index
            for bird in manually_reviewed
        ):
            return False

        reviewed_remaining = list(manually_reviewed)
        rows = []
        for bird_index, bird in enumerate(selection.birds):
            # Crop indices can shift when the detector reranks boxes. A stable-looking
            # candidate ID is not enough to transfer a person's species correction.
            reviewed = max(
                reviewed_remaining,
                key=lambda old: self._box_overlap(old["crop_box"], bird.box),
                default=None,
            )
            if reviewed is not None and self._box_overlap(reviewed["crop_box"], bird.box) >= 0.4:
                reviewed_remaining.remove(reviewed)
            else:
                reviewed = None
            rows.append(
                (
                    frigate_event,
                    bird_index,
                    bird.candidate_id,
                    selection.clip_variant,
                    selection.frame_index,
                    json.dumps(bird.box),
                    bird.detector_confidence,
                    reviewed["species"] if reviewed and reviewed["manual_species"] else bird.species,
                    bird.classifier_label,
                    bird.classifier_score,
                    int(bool(reviewed and reviewed["manual_species"])),
                    int(bool(reviewed and reviewed["is_hidden"])),
                )
            )
        for reviewed in reviewed_remaining:
            rows.append(
                (
                    frigate_event,
                    len(rows),
                    reviewed["candidate_id"],
                    reviewed["clip_variant"],
                    reviewed["frame_index"],
                    json.dumps(reviewed["crop_box"]),
                    reviewed["detector_confidence"],
                    reviewed["species"],
                    reviewed["classifier_label"],
                    reviewed["classifier_score"],
                    int(reviewed["manual_species"]),
                    int(reviewed["is_hidden"]),
                )
            )

        try:
            await self.db.execute("DELETE FROM bird_observations WHERE frigate_event = ?", (frigate_event,))
            await self.db.executemany(
                """INSERT INTO bird_observations
                   (frigate_event, bird_index, candidate_id, clip_variant, frame_index, crop_box_json,
                    detector_confidence, species, classifier_label, classifier_score, manual_species, is_hidden)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return True

    @staticmethod
    def _box_overlap(left: list[float], right: tuple[float, float, float, float]) -> float:
        intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
            0.0, min(left[3], right[3]) - max(left[1], right[1])
        )
        left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
        right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
        smaller_area = min(left_area, right_area)
        return intersection / smaller_area if smaller_area > 0 else 0.0

    async def count_visible_between(self, start: datetime, end: datetime) -> dict[str, int]:
        async with self.db.execute(
            """SELECT COUNT(CASE WHEN b.is_hidden = 0 THEN 1 END), COUNT(DISTINCT b.frigate_event)
               FROM bird_observations b JOIN detections d ON d.frigate_event = b.frigate_event
               WHERE d.detection_time >= ? AND d.detection_time < ?
                 AND COALESCE(d.is_hidden, 0) = 0""",
            (start.isoformat(sep=" "), end.isoformat(sep=" ")),
        ) as cursor:
            row = await cursor.fetchone()
        return {"birds": int(row[0] or 0), "captures": int(row[1] or 0)}

    async def count_by_species_between(self, start: datetime, end: datetime) -> list[dict[str, int | str]]:
        async with self.db.execute(
            """SELECT b.species, COUNT(*)
               FROM bird_observations b JOIN detections d ON d.frigate_event = b.frigate_event
               WHERE d.detection_time >= ? AND d.detection_time < ?
                 AND COALESCE(d.is_hidden, 0) = 0 AND b.is_hidden = 0
               GROUP BY b.species ORDER BY COUNT(*) DESC, b.species""",
            (start.isoformat(sep=" "), end.isoformat(sep=" ")),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"species": str(species), "birds": int(count)} for species, count in rows]

    async def set_species(self, frigate_event: str, bird_id: int, species: str) -> bool:
        await self.db.execute(
            """UPDATE bird_observations
               SET species = ?, manual_species = 1, updated_at = CURRENT_TIMESTAMP
               WHERE frigate_event = ? AND id = ?""",
            (species, frigate_event, bird_id),
        )
        async with self.db.execute("SELECT changes()") as cursor:
            row = await cursor.fetchone()
        await self.db.commit()
        return bool(row and row[0])

    async def set_hidden(self, frigate_event: str, bird_id: int, hidden: bool) -> bool:
        await self.db.execute(
            """UPDATE bird_observations
               SET is_hidden = ?, updated_at = CURRENT_TIMESTAMP
               WHERE frigate_event = ? AND id = ?""",
            (int(hidden), frigate_event, bird_id),
        )
        async with self.db.execute("SELECT changes()") as cursor:
            row = await cursor.fetchone()
        await self.db.commit()
        return bool(row and row[0])
