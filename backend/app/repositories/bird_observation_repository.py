"""Durable per-bird observations attached to one Frigate capture."""

from datetime import datetime
import json

import aiosqlite

from app.services.bird_observation_selection import BirdObservation, BirdObservationSelection
from app.utils.canonical_species import should_hide_species_label
from app.config import settings
from app.services.counted_bird_identity import resolve_bird_identities, species_aliases_from_taxonomy
from app.repositories.species_repository import SpeciesRepository

SUMMARY_EVENT_PAGE_SIZE = 400


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
        try:
            if self.db.in_transaction:
                # Repository callers may already own a write transaction. Reserve
                # writes without nesting BEGIN or releasing that caller's work.
                await self.db.execute("UPDATE bird_observations SET id = id WHERE 0")
            else:
                await self.db.execute("BEGIN IMMEDIATE")
            changed = await self._replace_generated_locked(frigate_event, selection)
            await self.db.commit()
            return changed
        except BaseException:
            await self.db.rollback()
            raise

    async def _replace_generated_locked(self, frigate_event: str, selection: BirdObservationSelection) -> bool:
        existing = await self.list_for_event(frigate_event)
        manually_reviewed = [bird for bird in existing if bird["manual_species"] or bird["is_hidden"]]
        if manually_reviewed and any(
            bird["clip_variant"] != selection.clip_variant or bird["frame_index"] != selection.frame_index
            for bird in manually_reviewed
        ):
            return False

        # Resolve every location together: an owner-reviewed box must not steal
        # a weaker overlap before another generated box gets its exact match.
        weights = [[self._association_score(old, bird, selection) for old in existing] for bird in selection.birds]
        assignment = self._maximum_weight_assignment(weights)
        total_score = sum(
            weights[index][old_index] for index, old_index in enumerate(assignment) if old_index is not None
        )
        for index, old_index in enumerate(assignment):
            if old_index is None or not (existing[old_index]["manual_species"] or existing[old_index]["is_hidden"]):
                continue
            # Equal global alternatives cannot identify which physical bird owns
            # the correction. Keep this frame intact instead of guessing or duplicating it.
            alternative_weights = [list(row) for row in weights]
            alternative_weights[index][old_index] = 0.0
            alternative = self._maximum_weight_assignment(alternative_weights)
            alternative_score = sum(
                alternative_weights[new][old] for new, old in enumerate(alternative) if old is not None
            )
            if abs(total_score - alternative_score) <= 1e-9:
                return False

        remaining = list(existing)
        rows = []
        for bird_index, bird in enumerate(selection.birds):
            old_index = assignment[bird_index]
            matched = existing[old_index] if old_index is not None else None
            reviewed = matched if matched and (matched["manual_species"] or matched["is_hidden"]) else None
            if matched is not None:
                remaining.remove(matched)
            rows.append(
                (
                    matched["id"] if matched else None,
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
        for reviewed in remaining:
            if not (reviewed["manual_species"] or reviewed["is_hidden"]):
                continue
            rows.append(
                (
                    reviewed["id"],
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

        retained_ids = {row[0] for row in rows if row[0] is not None}
        await self.db.executemany(
            "DELETE FROM bird_observations WHERE frigate_event = ? AND id = ?",
            [(frigate_event, old["id"]) for old in existing if old["id"] not in retained_ids],
        )
        # Free the unique per-capture indices while reranking. Keeping matched
        # IDs lets an owner edit waiting behind this transaction target its bird.
        await self.db.execute(
            "UPDATE bird_observations SET bird_index = -id - 1 WHERE frigate_event = ?", (frigate_event,)
        )
        await self.db.executemany(
            """UPDATE bird_observations
               SET bird_index = ?, candidate_id = ?, clip_variant = ?, frame_index = ?, crop_box_json = ?,
                   detector_confidence = ?, species = ?, classifier_label = ?, classifier_score = ?,
                   manual_species = ?, is_hidden = ?, updated_at = CURRENT_TIMESTAMP
               WHERE frigate_event = ? AND id = ?""",
            [(*row[2:], row[1], row[0]) for row in rows if row[0] is not None],
        )
        await self.db.executemany(
            """INSERT INTO bird_observations
               (frigate_event, bird_index, candidate_id, clip_variant, frame_index, crop_box_json,
                detector_confidence, species, classifier_label, classifier_score, manual_species, is_hidden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [row[1:] for row in rows if row[0] is None],
        )
        return True

    @classmethod
    def _association_score(cls, old: dict, bird: BirdObservation, selection: BirdObservationSelection) -> float:
        if old["clip_variant"] != selection.clip_variant or old["frame_index"] != selection.frame_index:
            return 0.0
        left, right = old["crop_box"], bird.box
        if cls._box_overlap(left, right) < 0.4:
            return 0.0
        intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
            0.0, min(left[3], right[3]) - max(left[1], right[1])
        )
        union = (left[2] - left[0]) * (left[3] - left[1]) + (right[2] - right[0]) * (right[3] - right[1]) - intersection
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _maximum_weight_assignment(weights: list[list[float]]) -> list[int | None]:
        """Rectangular Hungarian assignment with a zero-weight unmatched slot per new bird."""
        count = len(weights)
        if not count:
            return []
        old_count = len(weights[0])
        column_count = old_count + count
        costs = [[-value for value in row] + [0.0] * count for row in weights]
        row_potential = [0.0] * (count + 1)
        column_potential = [0.0] * (column_count + 1)
        matched_row = [0] * (column_count + 1)
        previous = [0] * (column_count + 1)
        for row in range(1, count + 1):
            matched_row[0] = row
            column = 0
            minimum = [float("inf")] * (column_count + 1)
            used = [False] * (column_count + 1)
            while True:
                used[column] = True
                current_row = matched_row[column]
                delta, next_column = float("inf"), 0
                for candidate in range(1, column_count + 1):
                    if used[candidate]:
                        continue
                    cost = (
                        costs[current_row - 1][candidate - 1] - row_potential[current_row] - column_potential[candidate]
                    )
                    if cost < minimum[candidate]:
                        minimum[candidate] = cost
                        previous[candidate] = column
                    if minimum[candidate] < delta:
                        delta, next_column = minimum[candidate], candidate
                for candidate in range(column_count + 1):
                    if used[candidate]:
                        row_potential[matched_row[candidate]] += delta
                        column_potential[candidate] -= delta
                    else:
                        minimum[candidate] -= delta
                column = next_column
                if matched_row[column] == 0:
                    break
            while column:
                predecessor = previous[column]
                matched_row[column] = matched_row[predecessor]
                column = predecessor
        assignment = [None] * count
        for column in range(1, old_count + 1):
            row = matched_row[column]
            if row and weights[row - 1][column - 1] > 0:
                assignment[row - 1] = column - 1
        return assignment

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

    async def resolved_for_events(self, frigate_events: list[str]) -> dict[str, list[dict]]:
        """Resolve stored crop evidence against current parent identity in bounded batches."""
        resolved: dict[str, list[dict]] = {}
        unique_events = list(dict.fromkeys(frigate_events))
        parent_fields = ("category_name", "scientific_name", "common_name", "display_name", "score", "manual_tagged")
        for start in range(0, len(unique_events), SUMMARY_EVENT_PAGE_SIZE):
            page = unique_events[start : start + SUMMARY_EVENT_PAGE_SIZE]
            placeholders = ",".join("?" for _ in page)
            parent_columns = ",".join(f"d.{field} AS parent_{field}" for field in parent_fields)
            async with self.db.execute(
                f"""SELECT b.*, {parent_columns} FROM bird_observations b
                    JOIN detections d ON d.frigate_event=b.frigate_event
                    WHERE b.frigate_event IN ({placeholders}) ORDER BY b.bird_index""",
                page,
            ) as cursor:
                names = [column[0] for column in cursor.description]
                rows = [dict(zip(names, row, strict=True)) for row in await cursor.fetchall()]
            birds_by_event: dict[str, list[dict]] = {}
            parents = {}
            for bird in rows:
                event = bird["frigate_event"]
                parents[event] = {field: bird.pop(f"parent_{field}") for field in parent_fields}
                bird["crop_box"] = json.loads(bird.pop("crop_box_json"))
                birds_by_event.setdefault(event, []).append(bird)
            labels = {
                str(label).strip().lower()
                for bird in rows
                for label in (bird.get("species"), bird.get("classifier_label"))
                if label and not should_hide_species_label(label)
            }
            labels.update(
                str(label).strip().lower()
                for parent in parents.values()
                for field, label in parent.items()
                if field in parent_fields[:4] and label and not should_hide_species_label(label)
            )
            aliases = await self._cached_species_aliases(sorted(labels))
            hints: dict[str, list[dict]] = {}
            async with self.db.execute(
                f"""SELECT frigate_event, clip_variant, frame_index, crop_box_json FROM snapshot_candidates
                    WHERE frigate_event IN ({placeholders}) AND source_mode='frigate_hint_crop'""",
                page,
            ) as cursor:
                for event, variant, frame, box in await cursor.fetchall():
                    hints.setdefault(event, []).append(
                        {
                            "source_mode": "frigate_hint_crop",
                            "clip_variant": variant,
                            "frame_index": frame,
                            "crop_box": json.loads(box) if box else None,
                        }
                    )
            for event, birds in birds_by_event.items():
                resolved[event] = resolve_bird_identities(
                    birds,
                    hints.get(event, []),
                    parents[event],
                    threshold=settings.classification.threshold,
                    species_aliases=aliases,
                )
        return resolved

    async def _cached_species_aliases(self, labels: list[str]) -> dict[str, str | None]:
        taxonomy = []
        # One cache lookup per label batch, shared by every capture on the page.
        # Three alias columns keep each batch below SQLite's legacy bind limit.
        for start in range(0, len(labels), 250):
            batch = labels[start : start + 250]
            placeholders = ",".join("?" for _ in batch)
            async with self.db.execute(
                f"""SELECT scientific_name, common_name, manual_common_name FROM taxonomy_cache
                    WHERE LOWER(scientific_name) IN ({placeholders})
                       OR LOWER(common_name) IN ({placeholders})
                       OR LOWER(manual_common_name) IN ({placeholders})""",
                batch * 3,
            ) as cursor:
                taxonomy.extend(await cursor.fetchall())
        return species_aliases_from_taxonomy(taxonomy)

    async def named_for_event(self, event: str, language: str = "en") -> list[dict]:
        birds = (await self.resolved_for_events([event])).get(event, [])
        names: dict[str, tuple | None] = {}
        taxonomy = SpeciesRepository(self.db)
        for bird in birds:
            label = bird.get("scientific_name")
            if not label or should_hide_species_label(label):
                continue
            if label not in names:
                names[label] = await taxonomy.lookup_taxonomy(label, language)
            if names[label]:
                scientific, common, _ = names[label]
                bird["scientific_name"], bird["common_name"] = scientific, common
        return birds

    async def summaries_for_events(self, frigate_events: list[str]) -> dict[str, dict]:
        """Per-capture totals from stored owner decisions; a capture without rows has no entry.

        No entry is not a measured zero: an empty count is never persisted. The join keeps
        the summary to current parents, so an orphaned row cannot describe a deleted capture.
        """
        events = await self.resolved_for_events(frigate_events)
        return {
            event: self._summarize(
                [(bird["species"], bool(bird["is_hidden"]), 1, bird["detector_confidence"] is None) for bird in birds]
            )
            for event, birds in events.items()
        }

    @staticmethod
    def _summarize(groups: list[tuple[str, bool, int, bool]]) -> dict:
        named: dict[str, int] = {}
        counted = unknown = excluded = 0
        for species, hidden, count, _ in groups:
            if hidden:
                excluded += count
                continue
            counted += count
            if should_hide_species_label(species):
                unknown += count
            else:
                named[species] = named.get(species, 0) + count
        return {
            "counted": counted,
            "unknown": unknown,
            "excluded": excluded,
            "species": [
                {"species": species, "count": count}
                for species, count in sorted(named.items(), key=lambda item: (-item[1], item[0]))
            ],
            "hint_only": all(hint_only for *_, hint_only in groups),
        }

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
