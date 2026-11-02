"""The Explorer's one search box, answered under the reader's own visibility rules.

Cameras and the species facet are already on the page, so the client matches those itself; this
answers what needs the species catalogue or the database: the species and groups seen here, and
a record pasted by its id. A visitor never learns that a hidden or private record exists: a
record outside their view is answered exactly as one that does not exist.
"""

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.ratelimit import guest_rate_limit
from app.repositories.detection_repository import DetectionRepository
from app.repositories.garden_repository import GardenCapture, GardenRepository
from app.services import garden_public
from app.services.explorer_search import TaxonHit, record_id_kind, search_seen_taxa
from app.services.species_names import species_name_lookup, vernacular_case
from app.utils.api_datetime import serialize_api_datetime
from app.utils.language import get_user_language
from app.utils.public_access import public_event_query_bounds

router = APIRouter(tags=["explorer"])

#: Long enough for any name or id; anything longer is not a search.
MAX_QUERY_LENGTH = 100


class ExplorerSearchTaxon(BaseModel):
    taxon_id: int = Field(..., description="Catalogue identity; the Explorer's `taxon` filter takes it")
    rank: Literal["species", "genus", "family", "order"]
    scientific_name: str
    name: Optional[str] = Field(None, description="Common name in the reader's language, else English")
    bird_species: int = Field(..., description="Species at or beneath this taxon with a bird detection the reader sees")
    bird_detections: int
    garden_species: int = Field(..., description="Species at or beneath this taxon in Garden captures the reader sees")
    garden_captures: int


class ExplorerSearchRecord(BaseModel):
    kind: Literal["detection", "garden"]
    id: str = Field(..., description="The Frigate event of a detection, or a Garden capture id")
    observed_at: str
    display_name: Optional[str] = None
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    camera: Optional[str] = Field(None, description="Absent when the owner does not share camera names")
    hidden: bool = Field(False, description="A hidden detection; only the owner is ever shown one")


class ExplorerSearchResponse(BaseModel):
    taxa: list[ExplorerSearchTaxon]
    truncated: bool = Field(..., description="More taxa matched than the limit returned")
    record: Optional[ExplorerSearchRecord] = Field(None, description="The record the query names, when visible")


def _garden_visible(auth: AuthContext) -> bool:
    return settings.system.beta_garden_animals and (auth.is_owner or settings.public_access.enabled)


def _camera(auth: AuthContext, camera: str) -> Optional[str]:
    return camera if auth.is_owner or settings.public_access.show_camera_names else None


def _taxon_response(hit: TaxonHit) -> ExplorerSearchTaxon:
    return ExplorerSearchTaxon(
        taxon_id=hit.taxon.taxon_id,
        rank=hit.taxon.rank,
        scientific_name=hit.taxon.scientific_name,
        name=hit.taxon.name,
        bird_species=hit.bird_species,
        bird_detections=hit.bird_detections,
        garden_species=hit.garden_species,
        garden_captures=hit.garden_captures,
    )


async def _garden_record(capture: GardenCapture, auth: AuthContext, language: str) -> Optional[ExplorerSearchRecord]:
    if not auth.is_owner and (
        capture.status != "confirmed" or not garden_public.guest_history_visible(capture.observed_at)
    ):
        return None
    suggestion = capture.identification
    if suggestion and (suggestion.outcome != "suggestion" or suggestion.review == "dismissed"):
        suggestion = None
    named = capture.owner_identification or suggestion
    catalogue_names = (
        await asyncio.to_thread(species_name_lookup.resolve, [named.species_id], language=language)
        if named and named.species_id
        else {}
    )
    catalogue = catalogue_names.get(named.species_id) if named else None
    name = (catalogue.display if catalogue else None) or (named.name if named else None)
    scientific_name = catalogue.scientific if catalogue else None
    if capture.owner_identification:
        scientific_name = capture.owner_identification.scientific_name
    return ExplorerSearchRecord(
        kind="garden",
        id=capture.id,
        observed_at=capture.observed_at + "Z",
        display_name=vernacular_case(name) if name else None,
        scientific_name=scientific_name,
        common_name=vernacular_case(name) if name else None,
        camera=_camera(auth, capture.camera),
    )


async def _find_record(query: str, auth: AuthContext, language: str) -> Optional[ExplorerSearchRecord]:
    kind = record_id_kind(query)
    if kind is None:
        return None
    garden = _garden_visible(auth)
    async with get_db() as db:
        if kind == "garden":
            capture = await GardenRepository(db).get(query) if garden else None
        else:
            bounds = {} if auth.is_owner else public_event_query_bounds()
            detection = await DetectionRepository(db).find_record(query, include_hidden=auth.is_owner, **bounds)
            if detection is not None:
                return ExplorerSearchRecord(
                    kind="detection",
                    id=detection.frigate_event,
                    observed_at=serialize_api_datetime(detection.detection_time) or "",
                    display_name=detection.display_name,
                    scientific_name=detection.scientific_name,
                    common_name=detection.common_name,
                    camera=_camera(auth, detection.camera_name),
                    hidden=bool(detection.is_hidden),
                )
            # An animal event Frigate tracked is a Garden capture, not a detection.
            capture = await GardenRepository(db).find_by_frigate_event(query) if garden else None
    return await _garden_record(capture, auth, language) if capture else None


async def _seen_counts(auth: AuthContext) -> tuple[dict[int, int], dict[int, int]]:
    """What the reader may see, per catalogue identity: bird detections, then Garden captures."""
    bounds = {} if auth.is_owner else public_event_query_bounds()
    async with get_db() as db:
        birds = await DetectionRepository(db).species_identity_counts(**bounds)
        if not _garden_visible(auth):
            return birds, {}
        if auth.is_owner:
            garden = await GardenRepository(db).species_identity_counts(start=None, end=None, status="reviewable")
        else:
            start, end = garden_public.guest_history_window(None, None)
            garden = await GardenRepository(db).species_identity_counts(start=start, end=end, status="confirmed")
    return birds, garden


@router.get("/explorer/search", response_model=ExplorerSearchResponse)
@guest_rate_limit()
async def search_explorer(
    request: Request,
    response: Response,
    q: str = Query(..., min_length=1, max_length=MAX_QUERY_LENGTH, pattern=r"^[^\x00-\x1f\x7f]+$"),
    limit: int = Query(8, ge=1, le=20, description="Most taxa to return"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> ExplorerSearchResponse:
    """Species and groups seen here whose names match, and the record an id names, as this reader sees them."""
    response.headers["Cache-Control"] = "private, no-store"
    if not auth.is_owner and not settings.public_access.enabled:
        raise HTTPException(403, "Public access is switched off.")
    query = q.strip()
    if not query:
        raise HTTPException(422, "Enter a species, group or record id to search.")
    language = get_user_language(request)
    birds, garden = await _seen_counts(auth)
    hits = await search_seen_taxa(query, language=language, bird_counts=birds, garden_counts=garden)
    return ExplorerSearchResponse(
        taxa=[_taxon_response(hit) for hit in hits[:limit]],
        truncated=len(hits) > limit,
        record=await _find_record(query, auth, language),
    )
