"""Domestic birds the owner keeps leave bird history for Garden, with their evidence.

Two paths reach here: a classified Frigate bird event, before it can become a bird
detection, and the owner's Move to Garden on an existing bird record. Pure
decisions live in ``garden_domestic_birds``.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
import structlog

from app.config import settings
from app.database import get_db
from app.models.garden import GardenDomesticRoute
from app.repositories.detection_repository import DetectionRepository
from app.repositories.garden_repository import GardenRepository
from app.services.broadcaster import broadcaster
from app.services.garden_capture_policy import observation_time, safe_event_id
from app.services.garden_domestic_birds import (
    DOMESTIC_BIRDS,
    DomesticBirdKey,
    bird_event_route,
    domestic_bird_for_bird_label,
    normalize_domestic_birds,
)
from app.services.settings_update import commit_settings_change
from app.services.species_catalog_resolver import species_catalog_resolver
from app.utils.api_datetime import utc_naive_now

log = structlog.get_logger()

# One request moves at most this many records, so it answers promptly; the owner repeats it for the rest.
KEEP_MOVE_LIMIT = 500


@dataclass(frozen=True)
class KeptBirdMove:
    declared: bool
    moved: int
    skipped: int
    remaining: int


def species_ids_by_bird() -> dict[str, frozenset[int]]:
    """Each domestic bird's scientific names as catalogue ids; empty without a catalogue."""
    resolved: dict[str, frozenset[int]] = {}
    for key, bird in DOMESTIC_BIRDS.items():
        ids = {species_catalog_resolver.resolve_scientific_name(name)[0] for name in bird.scientific_names}
        resolved[key] = frozenset(i for i in ids if i is not None)
    return resolved


def _result_species_id(result: dict) -> int | None:
    index = result.get("index")
    if type(index) is not int or index < 0:
        return None
    outputs = species_catalog_resolver.species_outputs(result.get("model_sha256"))
    return outputs.get(index) if outputs else None


def domestic_bird_for_result(result: dict | None, ids_by_bird: dict[str, frozenset[int]]) -> str | None:
    """The domestic bird a bird-model result stands for, by catalogue identity or exact name."""
    if not isinstance(result, dict):
        return None
    return domestic_bird_for_bird_label(
        species_id=_result_species_id(result),
        scientific_names=(result.get("label"), result.get("scientific_name")),
        species_ids_by_bird=ids_by_bird,
    )


def _score(result: dict | None) -> float | None:
    if not isinstance(result, dict):
        return None
    try:
        score = float(result.get("score"))
    except (TypeError, ValueError):
        return None
    return score if 0 <= score <= 1 else None


class GardenDomesticService:
    async def route_bird_event(
        self,
        *,
        event_id: str,
        camera: str,
        start_time: float,
        has_snapshot: bool,
        top: dict | None,
        accepted: dict | None,
    ) -> bool:
        """Record a declared domestic bird as a Garden animal instead of a bird detection.

        True means the event is Garden's, so bird admission must stop, whether the capture
        is new or already recorded (including a privacy tombstone for the event).
        """
        declared = settings.frigate.garden_domestic_birds
        if not declared or not settings.system.beta_garden_animals:
            return False
        species_ids = await asyncio.to_thread(species_ids_by_bird)
        top_bird = domestic_bird_for_result(top, species_ids)
        accepted_bird = domestic_bird_for_result(accepted, species_ids)
        route = bird_event_route(
            top_bird,
            _score(top),
            accepted_bird,
            declared,
            threshold=settings.classification.threshold,
            garden_enabled=settings.system.beta_garden_animals,
        )
        if route != "garden":
            return False
        kept = accepted_bird if accepted_bird in declared else top_bird
        evidence = accepted if accepted_bird in declared else top
        if kept is None or evidence is None or not safe_event_id(event_id):
            return False
        retention = settings.maintenance.retention_days if settings.maintenance.cleanup_enabled else 0
        observed_at = observation_time(start_time, datetime.now(timezone.utc), retention) or utc_naive_now().isoformat()
        async with get_db() as db:
            capture_id = await GardenRepository(db).save_domestic_capture(
                event_id,
                camera,
                observed_at,
                has_snapshot,
                GardenDomesticRoute(
                    domestic_bird=kept,
                    origin="bird_detection",
                    source_label=str(evidence.get("label") or kept)[:256],
                    source_scientific_name=evidence.get("scientific_name"),
                    source_score=_score(evidence),
                    source_model=evidence.get("model_id") or evidence.get("model_sha256"),
                    routed_at=utc_naive_now().isoformat() + "Z",
                ),
            )
        log.info("garden_domestic_bird_routed", event_id=event_id, camera=camera, domestic_bird=kept)
        if capture_id:
            await broadcaster.broadcast({"type": "garden_history_changed"})
        return True

    async def move_detection(self, frigate_event: str) -> str:
        """Move one bird record of a declared domestic bird to Garden, hiding (not deleting) it."""
        capture_id = await self._move_one(frigate_event)
        await broadcaster.broadcast({"type": "garden_history_changed"})
        return capture_id

    async def keep_bird(self, bird: DomesticBirdKey) -> KeptBirdMove:
        """Declare a domestic bird the owner keeps and move its visible bird records to Garden.

        Each record moves through the single-record path: hidden in the same transaction
        that creates its capture, never deleted. A record that cannot move is counted as
        skipped and stays in bird history.
        """
        if not settings.system.beta_garden_animals:
            raise HTTPException(409, "Turn on Garden animals before moving a record to Garden")
        declared = bird not in settings.frigate.garden_domestic_birds
        if declared:
            await commit_settings_change(
                lambda candidate: setattr(
                    candidate.frigate,
                    "garden_domestic_birds",
                    normalize_domestic_birds([*candidate.frigate.garden_domestic_birds, bird]),
                )
            )
        species_ids = (await asyncio.to_thread(species_ids_by_bird)).get(bird, frozenset())
        async with get_db() as db:
            events, total = await GardenRepository(db).visible_bird_events(
                species_ids, DOMESTIC_BIRDS[bird].scientific_names, KEEP_MOVE_LIMIT
            )
        moved = skipped = 0
        for event in events:
            try:
                await self._move_one(event)
                moved += 1
            except HTTPException as error:
                skipped += 1
                log.info("garden_keep_bird_skipped", bird=bird, status=error.status_code)
        if moved:
            await broadcaster.broadcast({"type": "garden_history_changed"})
        log.info("garden_keep_bird", bird=bird, declared=declared, moved=moved, skipped=skipped)
        return KeptBirdMove(declared=declared, moved=moved, skipped=skipped, remaining=total - len(events))

    async def _move_one(self, frigate_event: str) -> str:
        if not settings.system.beta_garden_animals:
            raise HTTPException(409, "Turn on Garden animals before moving a record to Garden")
        async with get_db() as db:
            detection = await DetectionRepository(db).get_by_frigate_event(frigate_event)
        if detection is None or detection.id is None:
            raise HTTPException(404, "Bird record not found")
        if detection.is_hidden:
            raise HTTPException(409, "This bird record is hidden. Show it again before moving it.")
        species_ids = await asyncio.to_thread(species_ids_by_bird)
        kept = domestic_bird_for_bird_label(
            species_id=detection.species_id,
            scientific_names=(detection.scientific_name, detection.display_name),
            species_ids_by_bird=species_ids,
        )
        if kept is None or kept not in settings.frigate.garden_domestic_birds:
            raise HTTPException(409, "Only a bird you declared under Domestic birds you keep can be moved to Garden")
        observed = detection.detection_time
        if observed.tzinfo is not None:
            observed = observed.astimezone(timezone.utc).replace(tzinfo=None)
        route = GardenDomesticRoute(
            domestic_bird=kept,
            origin="moved_from_birds",
            source_label=detection.display_name[:256],
            source_scientific_name=detection.scientific_name,
            source_score=detection.score if 0 <= detection.score <= 1 else None,
            source_model=detection.video_classification_model_id,
            detection_id=detection.id,
            routed_at=utc_naive_now().isoformat() + "Z",
        )
        async with get_db() as db:
            capture_id = await GardenRepository(db).move_detection_to_garden(
                detection.id,
                frigate_event,
                detection.camera_name,
                observed.isoformat(),
                detection.frigate_status == "present",
                route,
            )
        if capture_id is None:
            raise HTTPException(409, "Garden already has a record for this Frigate event")
        return capture_id


garden_domestic_service = GardenDomesticService()
