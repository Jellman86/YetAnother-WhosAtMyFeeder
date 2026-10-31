"""Page Garden groups before loading their captures; no animal data enters bird history."""

from datetime import datetime
from typing import Any

from app.models.garden_motion import MotionSource
from app.services.garden_visit_grouping import same_position
from app.repositories.garden_repository import GardenRepository, GardenTimelineStatus, GardenCapture


class GardenVisitRepository(GardenRepository):
    async def _groups(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        camera: str | None,
        status: GardenTimelineStatus = "reviewable",
    ) -> tuple[str, list[Any]]:
        where, values = self._timeline_filter(start, end, camera, status)
        source = f"""scoped AS (
            SELECT garden_captures.id, camera, observed_at, status, i.result_json AS identification,
                   m.source_json AS motion, o.species_id AS owner_species, d.domestic_bird AS domestic,
                   EXISTS (SELECT 1 FROM garden_saved_crops WHERE capture_id=garden_captures.id AND image IS NOT NULL) AS has_crop
            FROM garden_captures
            LEFT JOIN garden_identifications i ON i.capture_id=garden_captures.id
            LEFT JOIN garden_motion_sources m ON m.capture_id=garden_captures.id
            LEFT JOIN garden_owner_identifications o ON o.capture_id=garden_captures.id
            LEFT JOIN garden_domestic_routes d ON d.capture_id=garden_captures.id
            WHERE {where}
        )"""
        # Motion storage retains at most 128 live photos. Compare each proposal with
        # a fixed first box, so drifting boxes cannot chain into a stationary stack.
        async with self.db.execute(
            f"WITH {source} SELECT id, motion FROM scoped WHERE status='pending' AND motion IS NOT NULL "
            "ORDER BY observed_at DESC,id DESC LIMIT 128",
            values,
        ) as cursor:
            proposals = await cursor.fetchall()
        anchors: list[tuple[str, MotionSource]] = []
        members: list[str] = []
        position_values: list[str] = []
        for capture_id, raw in proposals:
            motion = MotionSource.model_validate_json(raw)
            anchor = next((key for key, first in anchors if same_position(first, motion)), None)
            if anchor is None:
                anchor = capture_id
                anchors.append((anchor, motion))
            members.append("(?,?)")
            position_values.extend((capture_id, anchor))
        positions = "VALUES " + ",".join(members) if members else "SELECT NULL,NULL WHERE 0"
        return (
            f"""WITH {source}, positions(id,anchor) AS ({positions}),
        identities AS (
            SELECT s.*, julianday(observed_at) AS at,
                CASE WHEN status='pending' AND motion IS NOT NULL THEN 1 ELSE 0 END AS position,
                CASE WHEN status='pending' AND motion IS NOT NULL THEN 'position:' || COALESCE(p.anchor,s.id)
                     ELSE status || ':' || CASE
                        WHEN owner_species IS NOT NULL THEN 'species:' || owner_species
                        WHEN domestic IS NOT NULL THEN 'domestic:' || domestic
                        WHEN json_extract(identification,'$.outcome')='suggestion'
                         AND json_extract(identification,'$.review') != 'dismissed'
                         AND NULLIF(json_extract(identification,'$.name'),'') IS NOT NULL
                        THEN COALESCE('species:' || json_extract(identification,'$.species_id'),
                                      'taxon:' || json_extract(identification,'$.taxon_id'),
                                      'name:' || LOWER(TRIM(json_extract(identification,'$.name'))))
                        WHEN status='confirmed' THEN 'animal'
                        ELSE 'label:' || (SELECT label FROM garden_captures WHERE id=s.id) END END AS identity
            FROM scoped s LEFT JOIN positions p ON p.id=s.id
        ), previous AS (
            SELECT *, LAG(at) OVER (PARTITION BY camera,identity ORDER BY at,id) AS previous_at FROM identities
        ), numbered AS (
            SELECT *, SUM(CASE WHEN position=0 AND
                (previous_at IS NULL OR (at-previous_at)*86400 > 60.001) THEN 1 ELSE 0 END)
                OVER (PARTITION BY camera,identity ORDER BY at,id ROWS UNBOUNDED PRECEDING) AS number
            FROM previous
        ), members AS (
            SELECT *, FIRST_VALUE(id) OVER (PARTITION BY camera,identity,number ORDER BY at,id) AS visit_id,
                ROW_NUMBER() OVER (PARTITION BY camera,identity,number ORDER BY has_crop DESC,at DESC,id DESC) AS representative
            FROM numbered
        ), summaries AS (
            SELECT visit_id, MIN(observed_at) AS start_time, MAX(observed_at) AS end_time,
                   COUNT(*) AS capture_count, MAX(position) AS position
            FROM members GROUP BY visit_id
        )""",
            [*values, *position_values],
        )

    async def visits(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        camera: str | None,
        newest_first: bool,
        limit: int,
        offset: int,
        status: GardenTimelineStatus = "reviewable",
        page_start: datetime | None = None,
        page_end: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        cte, values = await self._groups(start=start, end=end, camera=camera, status=status)
        clauses, bounds = ["1=1"], []
        for bound, operator in [(page_start, ">=" if newest_first else ">"), (page_end, "<" if newest_first else "<=")]:
            if bound is not None:
                clauses.append(f"julianday(end_time) {operator} julianday(?)")
                bounds.append(bound.isoformat())
        where = " AND ".join(clauses)
        async with self.db.execute(
            f"{cte} SELECT COUNT(*), COALESCE(SUM(capture_count),0) FROM summaries WHERE {where}",
            [*values, *bounds],
        ) as cursor:
            total, captures = await cursor.fetchone()
        direction = "DESC" if newest_first else "ASC"
        async with self.db.execute(
            f"""{cte} SELECT s.visit_id,s.start_time,s.end_time,s.capture_count,s.position,m.id
                FROM summaries s JOIN members m ON m.visit_id=s.visit_id AND m.representative=1
                WHERE {where} ORDER BY s.end_time {direction},s.visit_id {direction} LIMIT ? OFFSET ?""",
            [*values, *bounds, limit, offset],
        ) as cursor:
            rows = await cursor.fetchall()
        return (
            [
                dict(zip(("id", "start_time", "end_time", "capture_count", "position", "representative"), row))
                for row in rows
            ],
            total,
            captures,
        )

    async def visit_captures(
        self,
        visit_id: str,
        *,
        start: datetime | None,
        end: datetime | None,
        camera: str | None,
        status: GardenTimelineStatus,
        limit: int,
        offset: int,
    ) -> tuple[list[GardenCapture], int]:
        cte, values = await self._groups(start=start, end=end, camera=camera, status=status)
        async with self.db.execute(
            f"{cte} SELECT COUNT(*) FROM members WHERE visit_id=?", [*values, visit_id]
        ) as cursor:
            total = (await cursor.fetchone())[0]
        async with self.db.execute(
            f"{cte} SELECT id FROM members WHERE visit_id=? ORDER BY observed_at DESC,id DESC LIMIT ? OFFSET ?",
            [*values, visit_id, limit, offset],
        ) as cursor:
            ids = [row[0] for row in await cursor.fetchall()]
        return await self.get_many(ids), total

    async def get_many(self, ids: list[str]) -> list[GardenCapture]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE status != 'blocked' AND id IN ({placeholders}) LIMIT ?",
            [*ids, len(ids)],
        ) as cursor:
            captures = {row[0]: self._capture(row) for row in await cursor.fetchall()}
        return [captures[key] for key in ids if key in captures]
