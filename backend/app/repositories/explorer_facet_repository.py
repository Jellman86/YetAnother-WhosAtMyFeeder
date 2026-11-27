"""Facet counts for the Explorer's filter rail, taken the way its results are read.

Captures are counted with the capture count's own conditions; visits with the shared visit rule
and the visit list's own match. A species is counted by the same match terms its filter renders
(``SpeciesMatch``), joined for every option at once, so a count and the results it describes
cannot match different records.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.repositories.bird_observation_repository import BirdObservationRepository, events_condition
from app.repositories.detection_repository import SpeciesMatch, capture_taxon_match, visit_taxon_match
from app.repositories.visit_repository import VisitRepository
from app.services.explorer_facets import FacetScope

# A visit's members carry no video status of their own, so it is read from the capture.
_VIDEO_ANALYSED_MEMBER = "d.id IN (SELECT id FROM detections WHERE video_classification_status = 'completed')"
_VIDEO_ANALYSED_CAPTURE = "d.video_classification_status = 'completed'"

# The facet source carries each record's names already lowered, so every term is an equality the
# planner can probe through an automatic index, rather than every option tested on every record.
_SOURCE_COLUMNS = (
    "d.taxa_id AS taxa_id, LOWER(d.display_name) AS dn, LOWER(d.scientific_name) AS sn, "
    "LOWER(d.common_name) AS cn, LOWER(d.category_name) AS cat"
)


@dataclass(frozen=True)
class OptionFilter:
    """One species option as its filter reads it: a name, several names, or a taxon id."""

    species: str | None = None
    species_any: tuple[str, ...] | None = None
    taxa_id: int | None = None


@dataclass(frozen=True)
class FacetCount:
    """One facet count to take: the scope it is taken under and what it is broken down by."""

    scope: FacetScope
    #: ``species``, ``camera``, or ``None`` for one number under the key ``""``.
    by: str | None = None
    #: For ``by="species"``: each option value and the filter it stands for.
    options: Mapping[str, OptionFilter] = field(default_factory=dict)


def _values(rows: Sequence[tuple[str, object]], lower: bool = False) -> tuple[str, list]:
    value = "LOWER(?)" if lower else "?"
    return ", ".join(f"(?, {value})" for _ in rows), [item for row in rows for item in row]


class ExplorerFacetRepository(VisitRepository):
    async def facet_counts(
        self, facets: Sequence[FacetCount], *, visits: bool, gap_seconds: int
    ) -> list[dict[str, int]]:
        """Each facet's counts, in the order asked.

        Facets reading the same history share one statement, so it is grouped into visits once:
        SQLite materialises a CTE used more than once. A chosen camera narrows each facet's own
        condition rather than the grouping, which it leaves unchanged, so the camera list shares it.
        """
        mixed: dict[tuple, list[str]] = {}
        statements: dict[tuple[str, tuple], list[tuple[int, list[tuple[str, list]], str, list]]] = {}
        for index, facet in enumerate(facets):
            head, head_params, ctes, body, body_params = await self._facet_sql(
                index, facet, visits=visits, gap_seconds=gap_seconds, mixed=mixed
            )
            statements.setdefault((head, tuple(head_params)), []).append((index, ctes, body, body_params))
        results: list[dict[str, int]] = [{} for _ in facets]
        for (head, head_params), branches in statements.items():
            ctes = [(head, list(head_params))] if head else []
            ctes += [cte for _, own, _, _ in branches for cte in own]
            query = (f"WITH {', '.join(sql for sql, _ in ctes)} " if ctes else "") + " UNION ALL ".join(
                f"SELECT {index}, {body}" for index, _, body, _ in branches
            )
            params = [*(value for _, values in ctes for value in values)]
            params += [value for *_, values in branches for value in values]
            async with self.db.execute(query, params) as cursor:
                for index, key, count in await cursor.fetchall():
                    if key is not None:
                        results[index][str(key)] = int(count)
        return results

    async def _mixed_events(self, mixed: dict[tuple, list[str]], scope: FacetScope) -> list[str] | None:
        """The captures holding several named species, read once per window for every facet.

        Read across every camera: each facet's own condition narrows it to a chosen camera.
        """
        if not scope.multiple_species_only:
            return None
        key = (scope.start, scope.end, scope.hidden_only)
        if key not in mixed:
            mixed[key] = await BirdObservationRepository(self.db).multiple_species_events(
                start=scope.start, end=scope.end, hidden_only=scope.hidden_only
            )
        return mixed[key]

    async def _facet_sql(
        self, index: int, facet: FacetCount, *, visits: bool, gap_seconds: int, mixed: dict[tuple, list[str]]
    ) -> tuple[str, list, list[tuple[str, list]], str, list]:
        """The shared head of a facet's statement, its own CTEs, and the columns that count it."""
        scope = facet.scope
        mixed_events = await self._mixed_events(mixed, scope)
        if visits:
            head, head_params, condition, condition_params, _ = await self.visit_match(
                start=scope.start,
                end=scope.end,
                camera=scope.camera,
                camera_in_condition=True,
                hidden_only=scope.hidden_only,
                gap_seconds=gap_seconds,
                species=scope.species,
                species_any=list(scope.species_any) if scope.species_any else None,
                taxa_id=scope.taxa_id,
                favorites=scope.favorites,
                audio_only=scope.audio_only,
                public_audio=scope.public_audio,
                multiple_species_only=scope.multiple_species_only,
                owner_confirmed_only=scope.owner_confirmed_only,
                species_ids=scope.species_ids,
                mixed_events=mixed_events,
            )
            conditions = [condition]
            source, record = "visit_members d", "d.visit_id"
            counted = "COUNT(DISTINCT d.visit_id)"
        else:
            joins, conditions, condition_params = await self.capture_filter_sql(
                start_date=scope.start,
                end_date=scope.end,
                species=scope.species,
                species_any=list(scope.species_any) if scope.species_any else None,
                taxa_id=scope.taxa_id,
                camera=scope.camera,
                hidden_only=scope.hidden_only,
                favorite_only=scope.favorites,
                audio_confirmed_only=scope.audio_only,
                public_audio_evidence=scope.public_audio,
                owner_confirmed_only=scope.owner_confirmed_only,
                species_ids=scope.species_ids,
            )
            if mixed_events is not None:
                clause, values = events_condition("d", mixed_events)
                conditions = [*conditions, clause]
                condition_params = [*condition_params, *values]
            head, head_params = "", []
            source, record = f"detections d {joins}", "d.id"
            # As the capture count reads it: only the taxonomy join can repeat a capture.
            counted = "COUNT(DISTINCT d.id)" if "tc_filter" in joins else "COUNT(*)"
        if scope.video_analysed:
            conditions = [*conditions, _VIDEO_ANALYSED_MEMBER if visits else _VIDEO_ANALYSED_CAPTURE]
        where = " AND ".join(conditions) or "1 = 1"
        if facet.by == "species":
            ctes = await self._species_ctes(index, facet.options, source, record, where, condition_params, visits)
            if not ctes:
                return head, head_params, [], "NULL, 0", []
            return (
                head,
                head_params,
                ctes,
                f"option, COUNT(DISTINCT record) FROM facet_matched_{index} GROUP BY option",
                [],
            )
        if facet.by == "camera":
            body = f"d.camera_name, {counted} FROM {source} WHERE {where} GROUP BY d.camera_name"
        else:
            body = f"'', {counted} FROM {source} WHERE {where}"
        return head, head_params, [], body, condition_params

    async def _species_ctes(
        self,
        index: int,
        options: Mapping[str, OptionFilter],
        source: str,
        record: str,
        where: str,
        params: list,
        visits: bool,
    ) -> list[tuple[str, list]]:
        """The records in scope, each option's terms, and the records each option matches."""
        terms: dict[str, list[tuple[str, object]]] = {}
        for value, option in options.items():
            match = await self._option_match(option, visits=visits)
            for kind in match.__dataclass_fields__:
                terms.setdefault(kind, []).extend((value, term) for term in getattr(match, kind))
        terms = {kind: rows for kind, rows in terms.items() if rows}
        if not terms:
            return []
        scoped = f"facet_scope_{index}"
        ctes: list[tuple[str, list]] = [
            (
                f"{scoped} AS MATERIALIZED (SELECT {record} AS record, {_SOURCE_COLUMNS} FROM {source} WHERE {where})",
                params,
            )
        ]
        branches: list[str] = []

        def table(kind: str, lower: bool = False) -> str:
            name = f"facet_{kind}_{index}"
            rows, values = _values(terms[kind], lower)
            ctes.append((f"{name}(option, term) AS (VALUES {rows})", values))
            return name

        def equal(name: str, column: str, extra: str = "") -> None:
            branches.append(f"SELECT m.option, s.record FROM {scoped} s JOIN {name} m ON m.term = s.{column}{extra}")

        if "taxa_ids" in terms:
            equal(table("taxa_ids"), "taxa_id")
        if "cached_taxa_ids" in terms:
            name = table("cached_taxa_ids")
            equal(name, "taxa_id")
            # A record with no id of its own takes the cache's id for its names, as the capture
            # filter's taxonomy join reads them.
            ctes.append(
                (
                    f"facet_cache_{index} AS MATERIALIZED (SELECT LOWER(scientific_name) AS sn, "
                    "LOWER(common_name) AS cn, taxa_id FROM taxonomy_cache)",
                    [],
                )
            )
            for cache_column, own, when in (
                ("sn", "sn", "s.sn IS NOT NULL"),
                ("sn", "dn", "s.sn IS NULL"),
                ("cn", "dn", "s.sn IS NULL"),
            ):
                branches.append(
                    f"SELECT m.option, s.record FROM {scoped} s "
                    f"JOIN facet_cache_{index} c ON c.{cache_column} = s.{own} "
                    f"JOIN {name} m ON m.term = c.taxa_id WHERE s.taxa_id IS NULL AND {when}"
                )
        if "scientific_names" in terms:
            equal(table("scientific_names", lower=True), "sn")
        if "names" in terms:
            name = table("names")
            for column in ("dn", "sn", "cn"):
                equal(name, column)
        if "display_names" in terms:
            equal(table("display_names", lower=True), "dn")
        if "labels" in terms:
            name = table("labels")
            for column in ("dn", "cat", "sn", "cn"):
                equal(name, column)
        if "label_patterns" in terms:
            name = table("label_patterns")
            for column in ("dn", "cat", "sn", "cn"):
                branches.append(f"SELECT m.option, s.record FROM {scoped} s JOIN {name} m ON s.{column} LIKE m.term")
        ctes.append((f"facet_matched_{index}(option, record) AS ({' UNION ALL '.join(branches)})", []))
        return ctes

    async def _option_match(self, option: OptionFilter, *, visits: bool) -> SpeciesMatch:
        """The terms the results' filter matches for this option, in this unit."""
        if option.taxa_id is not None:
            if visits or not await self._table_exists("taxonomy_cache"):
                return visit_taxon_match(option.taxa_id)
            return capture_taxon_match(option.taxa_id)
        names = option.species_any or ((option.species,) if option.species else ())
        match = SpeciesMatch()
        for name in names:
            match = match.merged(await self.species_match(name))
        return match
