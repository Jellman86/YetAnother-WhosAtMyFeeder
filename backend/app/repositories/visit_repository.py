from datetime import datetime

from app.repositories.detection_repository import (
    DETECTION_SELECT_COLUMNS,
    Detection,
    DetectionRepository,
    _row_to_detection,
    _public_audio_evidence_sql,
)
from app.services.visit_grouping import VISIT_GAP_SECONDS, valid_event_bounds
from app.utils.canonical_species import hidden_species_exact_labels


class VisitRepository(DetectionRepository):
    async def save_event_bounds(self, event_id: str, start: object, end: object) -> bool:
        bounds = valid_event_bounds(start, end)
        if bounds is None or event_id.startswith("manual_"):
            return False
        await self.db.execute(
            """INSERT INTO detection_event_bounds (frigate_event, start_time, end_time)
            SELECT frigate_event, ?, ? FROM detections WHERE frigate_event = ?
            ON CONFLICT(frigate_event) DO UPDATE SET
                end_time = MAX(detection_event_bounds.end_time, excluded.end_time)
            WHERE detection_event_bounds.start_time = excluded.start_time""",
            (*bounds, event_id),
        )
        changed = await self._last_statement_changes() > 0
        await self.db.commit()
        return changed

    async def grouping_cte(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        camera: str | None = None,
        hidden_only: bool = False,
    ) -> tuple[str, list]:
        conditions = ["d.is_hidden = 1" if hidden_only else "COALESCE(d.is_hidden, 0) = 0"]
        params: list = []
        for bound, operator in ((start, ">="), (end, "<=")):
            if bound is not None:
                conditions.append(f"d.detection_time {operator} ?")
                params.append(bound.isoformat(sep=" "))
        camera_condition = "WHERE s.camera_name = ?" if camera else ""
        has_bounds = await self._table_exists("detection_event_bounds")
        bounds_join = "LEFT JOIN detection_event_bounds b ON b.frigate_event = d.frigate_event" if has_bounds else ""
        finish_at = (
            "CASE WHEN julianday(b.end_time) > julianday(d.detection_time) THEN b.end_time ELSE d.detection_time END"
            if has_bounds
            else "d.detection_time"
        )
        finish = f"julianday({finish_at})"
        labels = sorted(
            {str(label).strip().casefold() for label in hidden_species_exact_labels()} | {"unknown bird", ""}
        )
        placeholders = ",".join("?" for _ in labels)
        # Infer identities across the visible time window before filtering cameras,
        # so listing a camera and expanding its visits resolve legacy rows identically.
        # Taxonomy cache joins can multiply captures; use unambiguous catalogue ids.
        sql = f"""
        visit_source AS (
            SELECT d.id, d.detection_time, d.score, d.display_name, d.category_name,
                   d.frigate_event, d.camera_name, d.scientific_name, d.common_name,
                   d.species_id, d.taxa_id, d.is_hidden, d.manual_tagged, d.audio_confirmed, d.audio_species, d.audio_score,
                   julianday(d.detection_time) AS at,
                   {finish} AS finish, {finish_at} AS finish_at, LOWER(TRIM(COALESCE(d.scientific_name, ''))) AS name_key
            FROM detections d {bounds_join}
            WHERE {" AND ".join(conditions)}
        ),
        name_catalogue AS (
            SELECT name_key, MIN(species_id) AS species_id, MIN(taxa_id) AS taxa_id
            FROM visit_source WHERE name_key <> '' GROUP BY name_key
            HAVING COUNT(DISTINCT species_id) <= 1 AND COUNT(DISTINCT taxa_id) <= 1
        ),
        taxon_catalogue AS (
            SELECT taxa_id, MIN(species_id) AS species_id FROM visit_source
            WHERE taxa_id IS NOT NULL GROUP BY taxa_id HAVING COUNT(DISTINCT species_id) = 1
        ),
        visit_identity AS (
            SELECT s.*,
                CASE WHEN s.frigate_event LIKE 'manual_%'
                       OR LOWER(TRIM(s.display_name)) IN ({placeholders}) OR s.at IS NULL
                     THEN 'event:' || s.frigate_event
                     ELSE COALESCE('species:' || COALESCE(s.species_id, n.species_id, t.species_id),
                         'taxon:' || COALESCE(s.taxa_id, n.taxa_id),
                         'name:' || NULLIF(s.name_key, ''), 'label:' || LOWER(TRIM(s.display_name)))
                END AS visit_identity
            FROM visit_source s
            LEFT JOIN name_catalogue n ON n.name_key = s.name_key
            LEFT JOIN taxon_catalogue t ON t.taxa_id = s.taxa_id
            {camera_condition}
        ),
        visit_previous AS (
            SELECT *, MAX(finish) OVER (
                PARTITION BY visit_identity, camera_name ORDER BY at, id
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ) AS previous_finish FROM visit_identity
        ),
        visit_numbered AS (
            SELECT *, SUM(CASE WHEN previous_finish IS NULL
                              OR (at - previous_finish) * 86400 > {VISIT_GAP_SECONDS} + 0.001
                              THEN 1 ELSE 0 END) OVER (
                PARTITION BY visit_identity, camera_name ORDER BY at, id
                ROWS UNBOUNDED PRECEDING
            ) AS visit_number FROM visit_previous
        ),
        visit_members AS (
            SELECT *, FIRST_VALUE(frigate_event) OVER (
                PARTITION BY visit_identity, camera_name, visit_number ORDER BY at, id
            ) AS visit_id,
            ROW_NUMBER() OVER (
                PARTITION BY visit_identity, camera_name, visit_number ORDER BY at, id
            ) AS visit_position,
            ROW_NUMBER() OVER (
                PARTITION BY visit_identity, camera_name, visit_number
                ORDER BY manual_tagged DESC, score DESC, at DESC, id DESC
            ) AS representative_position,
            ROW_NUMBER() OVER (
                PARTITION BY visit_identity, camera_name, visit_number ORDER BY at DESC, id DESC
            ) AS latest_position
            FROM visit_numbered
        )
        """
        return sql, [*params, *labels, *([camera] if camera else [])]

    async def _matching_condition(
        self,
        *,
        species: str | None = None,
        species_any: list[str] | None = None,
        taxa_id: int | None = None,
        favorites: bool = False,
        audio_only: bool = False,
        public_audio: bool = False,
        multiple_species_only: bool = False,
        start: datetime | None = None,
        end: datetime | None = None,
        camera: str | None = None,
        hidden_only: bool = False,
    ) -> tuple[str, list]:
        clauses = []
        params: list = []
        names = species_any or ([species] if species else [])
        if names:
            species_clauses = []
            for name in names:
                clause, values = await self._build_canonical_species_condition(
                    detection_alias="d",
                    species_name=name,
                    has_taxonomy_cache=False,
                )
                species_clauses.append(clause)
                params.extend(values)
            clauses.append("(" + " OR ".join(species_clauses) + ")")
        if taxa_id is not None:
            clauses.append("d.taxa_id = ?")
            params.append(taxa_id)
        if multiple_species_only:
            from app.repositories.bird_observation_repository import BirdObservationRepository

            clause, values = await BirdObservationRepository(self.db).multiple_species_condition(
                start=start, end=end, camera=camera, hidden_only=hidden_only
            )
            clauses.append(clause)
            params.extend(values)
        if favorites:
            clauses.append("EXISTS (SELECT 1 FROM detection_favorites f WHERE f.detection_id = d.id)")
        if audio_only:
            if public_audio:
                condition, values = await _public_audio_evidence_sql(self.db)
                condition = "d.audio_confirmed = 1 AND " + condition
                clauses.append(condition)
                params.extend(values)
            else:
                clauses.append("d.audio_confirmed = 1")
        return " AND ".join(clauses) or "1 = 1", params

    async def list_visits(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        camera: str | None = None,
        hidden_only: bool = False,
        limit: int = 24,
        offset: int = 0,
        sort: str = "newest",
        species: str | None = None,
        species_any: list[str] | None = None,
        taxa_id: int | None = None,
        favorites: bool = False,
        audio_only: bool = False,
        public_audio: bool = False,
        multiple_species_only: bool = False,
    ) -> tuple[list[dict], int]:
        cte, params = await self.grouping_cte(start=start, end=end, camera=camera, hidden_only=hidden_only)
        condition, values = await self._matching_condition(
            species=species,
            species_any=species_any,
            taxa_id=taxa_id,
            favorites=favorites,
            audio_only=audio_only,
            public_audio=public_audio,
            multiple_species_only=multiple_species_only,
            start=start,
            end=end,
            camera=camera,
            hidden_only=hidden_only,
        )
        audio_sql, audio_params = ("1 = 1", [])
        if public_audio:
            audio_sql, audio_params = await _public_audio_evidence_sql(self.db)
            audio_sql = audio_sql.replace("d.", "v.")
        source_cte = cte
        source_params = [*params, *values]
        cte += f""", matching_visits AS (
            SELECT DISTINCT d.visit_id FROM visit_members d WHERE {condition}
        ), matched_members AS (
            SELECT v.* FROM visit_members v WHERE v.visit_id IN (SELECT visit_id FROM matching_visits)
        )"""
        if not public_audio and await self._table_exists("bird_observations"):
            cte += """, bird_counts AS (
                SELECT frigate_event, COUNT(*) AS counted FROM bird_observations
                WHERE is_hidden = 0 GROUP BY frigate_event
            ), header_members AS (
                SELECT v.*, b.counted, ROW_NUMBER() OVER (
                    PARTITION BY v.visit_id ORDER BY COALESCE(b.counted, 0) DESC, v.score DESC, v.id DESC
                ) AS peak_position FROM matched_members v
                LEFT JOIN bird_counts b ON b.frigate_event = v.frigate_event
            )"""
            peak = "MAX(CASE WHEN peak_position = 1 AND counted > 0 THEN frigate_event END)"
        else:
            cte += ", header_members AS (SELECT * FROM matched_members)"
            peak = "NULL"
        cte += f""", visit_headers AS (
            SELECT v.visit_id, MIN(v.detection_time) AS start_time,
                MAX(v.finish_at) AS end_time, MAX(v.detection_time) AS latest_time,
                COUNT(*) AS capture_count, MAX(v.score) AS best_score,
                MAX(CASE WHEN v.representative_position = 1 THEN v.frigate_event END) AS representative_event,
                MAX(CASE WHEN v.latest_position = 1 THEN v.frigate_event END) AS latest_event,
                MAX(v.manual_tagged) AS manual_tagged, {peak} AS peak_event,
                MAX(CASE WHEN v.audio_confirmed = 1 AND {audio_sql} THEN 1 ELSE 0 END) AS audio_confirmed
            FROM header_members v GROUP BY v.visit_id
        )"""
        params.extend([*values, *audio_params])
        order = {
            "newest": "latest_time DESC",
            "oldest": "start_time ASC",
            "confidence": "best_score DESC, latest_time DESC",
        }.get(sort, "latest_time DESC")
        async with self.db.execute(
            f"WITH {cte} SELECT *, COUNT(*) OVER () AS total FROM visit_headers ORDER BY {order}, visit_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ) as cursor:
            rows = await cursor.fetchall()
            names = [column[0] for column in cursor.description]
        headers = [dict(zip(names, row, strict=True)) for row in rows]
        if headers:
            total = int(headers[0]["total"])
        else:
            async with self.db.execute(
                f"WITH {source_cte} SELECT COUNT(DISTINCT d.visit_id) FROM visit_members d WHERE {condition}",
                source_params,
            ) as cursor:
                total = int((await cursor.fetchone())[0])
        return headers, total

    async def visit_captures(
        self,
        visit_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        hidden_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Detection], int]:
        cte, params = await self.grouping_cte(start=start, end=end, hidden_only=hidden_only)
        async with self.db.execute(
            f"WITH {cte} SELECT COUNT(*) FROM visit_members WHERE visit_id = ?", [*params, visit_id]
        ) as cursor:
            total = int((await cursor.fetchone())[0])
        async with self.db.execute(
            f"WITH {cte} SELECT {DETECTION_SELECT_COLUMNS} FROM visit_members v JOIN detections d ON d.id = v.id "
            "LEFT JOIN detection_favorites f ON f.detection_id = d.id "
            "WHERE v.visit_id = ? ORDER BY v.at, v.id LIMIT ? OFFSET ?",
            [*params, visit_id, limit, offset],
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_detection(row) for row in rows], total
