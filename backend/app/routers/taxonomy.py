"""A taxon's place in the classification, the branch beneath it, and what this install recorded of it."""

import asyncio
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.ratelimit import guest_rate_limit
from app.repositories.detection_repository import DetectionRepository
from app.repositories.garden_repository import GardenRepository
from app.services import garden_public
from app.services.species_catalog_resolver import species_catalog_resolver
from app.services.taxon_facts import TaxonFacts, reader_scope, taxon_facts_service
from app.services.taxonomy_tree import Taxon, taxonomy_tree
from app.utils.api_datetime import serialize_api_datetime
from app.utils.language import get_user_language
from app.utils.public_access import public_event_query_bounds

#: Taxa one facts request may ask about: an open level of the tree, not the catalogue.
FACTS_BATCH_LIMIT = 100

router = APIRouter()


class TaxonResponse(BaseModel):
    taxon_id: int = Field(..., description="Catalogue identity; for a species it is its species_id")
    rank: str = Field(..., description="kingdom, phylum, class, order, family, genus, species, or an intermediate rank")
    scientific_name: str
    name: Optional[str] = Field(None, description="Common name in the reader's language, else English, when one exists")
    source: Optional[str] = Field(None, description="The pinned source the taxon comes from")
    principal: bool = Field(..., description="False for intermediate ranks a view may collapse")
    parent_id: Optional[int] = None
    species_count: Optional[int] = Field(None, description="Species at or beneath this taxon in the catalogue")
    seen_species: Optional[int] = Field(
        None, description="Species beneath this taxon (or this species) with a detection here, in the reader's window"
    )
    seen_count: Optional[int] = Field(
        None, description="Detections and confirmed Garden captures of those species here, in the reader's window"
    )
    authorship: Optional[str] = Field(
        None, description="The accepted concept's authority and year exactly as the catalogue stores it"
    )


class TaxonLineageResponse(BaseModel):
    lineage: list[TaxonResponse] = Field(..., description="From the root down to the taxon asked for")


class TaxonChildrenResponse(BaseModel):
    parent_id: int
    children: list[TaxonResponse]


def _response(taxon: Taxon) -> TaxonResponse:
    return TaxonResponse(
        taxon_id=taxon.taxon_id,
        rank=taxon.rank,
        scientific_name=taxon.scientific_name,
        name=taxon.name,
        source=taxon.source,
        principal=taxon.principal,
        parent_id=taxon.parent_id,
        species_count=taxon.species_count,
        seen_species=taxon.seen_species,
        seen_count=taxon.seen_count,
        authorship=taxon.authorship,
    )


async def _seen_here(auth: AuthContext) -> dict[int, int]:
    """Detections and confirmed Garden captures per catalogue identity, in the window the reader may see."""
    bounds = {} if auth.is_owner else public_event_query_bounds()
    async with get_db() as db:
        seen = await DetectionRepository(db).species_identity_counts(**bounds)
        if garden_public.garden_visible(is_owner=auth.is_owner):
            start, end = (None, None) if auth.is_owner else garden_public.guest_history_window(None, None)
            garden = await GardenRepository(db).species_identity_counts(start=start, end=end, status="confirmed")
            for species_id, count in garden.items():
                seen[species_id] = seen.get(species_id, 0) + count
    return seen


@router.get("/taxonomy/lineage", response_model=TaxonLineageResponse)
@guest_rate_limit()
async def get_species_lineage(
    request: Request,
    scientific_name: str = Query(..., min_length=1, max_length=200),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> TaxonLineageResponse:
    """Where a species sits, found by its scientific name through the catalogue (synonyms included)."""
    species_id, _status = await asyncio.to_thread(species_catalog_resolver.resolve_scientific_name, scientific_name)
    if species_id is None:
        raise HTTPException(status_code=404, detail="Species not in the catalogue")
    seen = await _seen_here(auth)
    lineage = await asyncio.to_thread(taxonomy_tree.lineage, species_id, language=get_user_language(request), seen=seen)
    if not lineage:
        raise HTTPException(status_code=404, detail="Species not in the catalogue")
    return TaxonLineageResponse(lineage=[_response(taxon) for taxon in lineage])


@router.get("/taxonomy/{taxon_id}/lineage", response_model=TaxonLineageResponse)
@guest_rate_limit()
async def get_taxon_lineage(
    request: Request, taxon_id: int, auth: AuthContext = Depends(get_auth_context_with_legacy)
) -> TaxonLineageResponse:
    """Where a taxon sits: every taxon above it, root first, with what was seen here beneath each."""
    seen = await _seen_here(auth)
    lineage = await asyncio.to_thread(taxonomy_tree.lineage, taxon_id, language=get_user_language(request), seen=seen)
    if not lineage:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return TaxonLineageResponse(lineage=[_response(taxon) for taxon in lineage])


@router.get("/taxonomy/{taxon_id}/children", response_model=TaxonChildrenResponse)
@guest_rate_limit()
async def get_taxon_children(
    request: Request,
    taxon_id: int,
    limit: int = Query(500, ge=1, le=5000),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> TaxonChildrenResponse:
    """The taxa directly beneath one, in the source's order, each with the number of species it holds."""
    seen = await _seen_here(auth)
    children = await asyncio.to_thread(
        taxonomy_tree.children, taxon_id, language=get_user_language(request), limit=limit, seen=seen
    )
    return TaxonChildrenResponse(parent_id=taxon_id, children=[_response(taxon) for taxon in children])


class TaxonPhotoResponse(BaseModel):
    url: str = Field(..., description="A card-sized photograph, served under the access rules of the record it shows")
    kind: Literal["camera", "garden"]
    species_id: int = Field(..., description="The species pictured: the taxon, or a group's most-seen member")
    scientific_name: str = Field(..., description="The pictured species' scientific name")
    name: Optional[str] = Field(None, description="The pictured species' common name in the reader's language")
    taken_at: str


class TaxonFactsItem(BaseModel):
    taxon_id: int
    rank: str
    visits: int = Field(
        ..., description="Bird visits by the shared visit rule plus confirmed Garden visits; 0 when none"
    )
    species_seen: int = Field(..., description="Species at or beneath this taxon with a visit here")
    first_seen: Optional[str] = None
    last_seen: Optional[str] = Field(None, description="The most recent visit at or beneath this taxon")
    heard: Optional[int] = Field(
        None,
        description="BirdNET-Go detections at or beneath this taxon; null when audio is not shared with the reader",
    )
    last_heard: Optional[str] = None
    sources: list[Literal["camera", "garden"]] = Field(..., description="Where the visits were recorded")
    photo: Optional[TaxonPhotoResponse] = Field(
        None, description="This install's newest stored crop the reader may load; null when there is none"
    )


class TaxonFactsResponse(BaseModel):
    scope: Literal["all", "shared"] = Field(..., description="All history, or the window shared with visitors")
    shared_days: Optional[int] = Field(None, description="The shared window's length in days, for a visitor")
    facts: list[TaxonFactsItem] = Field(..., description="One entry per taxon asked for that the catalogue holds")


class TaxonOtherNameResponse(BaseModel):
    language: str = Field(..., description="BCP 47 language tag")
    name: str
    preferred: bool


class TaxonNamesResponse(BaseModel):
    taxon_id: int
    names: list[TaxonOtherNameResponse] = Field(..., description="By language, the preferred name first in each")
    languages: int = Field(..., description="Languages among all the other names, before the limit")
    truncated: bool


def _time(value: Optional[datetime]) -> Optional[str]:
    return serialize_api_datetime(value)


def _facts_item(facts: TaxonFacts, pictured: dict[int, tuple[str, Optional[str]]]) -> TaxonFactsItem:
    photo = facts.photo if facts.photo and facts.photo.species_id in pictured else None
    return TaxonFactsItem(
        taxon_id=facts.taxon_id,
        rank=facts.rank,
        visits=facts.visits,
        species_seen=facts.species_seen,
        first_seen=_time(facts.first_seen),
        last_seen=_time(facts.last_seen),
        heard=facts.heard,
        last_heard=_time(facts.last_heard),
        sources=list(facts.sources),
        photo=TaxonPhotoResponse(
            url=photo.url,
            kind=photo.kind,
            species_id=photo.species_id,
            scientific_name=pictured[photo.species_id][0],
            name=pictured[photo.species_id][1],
            taken_at=serialize_api_datetime(photo.taken_at),
        )
        if photo
        else None,
    )


@router.get("/taxonomy/facts", response_model=TaxonFactsResponse)
@guest_rate_limit()
async def get_taxon_facts(
    request: Request,
    ids: list[int] = Query(..., description=f"Taxa to describe, at most {FACTS_BATCH_LIMIT}"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> TaxonFactsResponse:
    """What this install recorded of each taxon: visits, first and last seen, calls heard and its own photograph.

    A group rolls these up over the species seen beneath it. One open level of the family tree
    is one request. A visitor reads the shared window only.
    """
    if not 1 <= len(ids) <= FACTS_BATCH_LIMIT or any(not 0 < taxon_id < 2**63 for taxon_id in ids):
        raise HTTPException(422, f"Ask for between 1 and {FACTS_BATCH_LIMIT} taxa by their catalogue ids.")
    if not auth.is_owner and not settings.public_access.enabled:
        raise HTTPException(403, "Public access is switched off.")
    scope = reader_scope(is_owner=auth.is_owner)
    facts = await taxon_facts_service.facts(ids, scope)
    pictured = await asyncio.to_thread(
        taxonomy_tree.display_names,
        {entry.photo.species_id for entry in facts if entry.photo},
        language=get_user_language(request),
    )
    return TaxonFactsResponse(
        scope="shared" if scope.guest else "all",
        shared_days=scope.shared_days,
        facts=[_facts_item(entry, pictured) for entry in facts],
    )


@router.get("/taxonomy/{taxon_id}/names", response_model=TaxonNamesResponse)
@guest_rate_limit()
async def get_taxon_names(
    request: Request,
    taxon_id: int,
    limit: int = Query(40, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> TaxonNamesResponse:
    """A taxon's common names in the catalogue's other languages, the preferred name first in each."""
    found = await asyncio.to_thread(
        taxonomy_tree.other_names, taxon_id, language=get_user_language(request), limit=limit
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Taxon not found")
    return TaxonNamesResponse(
        taxon_id=taxon_id,
        names=[TaxonOtherNameResponse(language=n.language, name=n.name, preferred=n.preferred) for n in found.names],
        languages=found.languages,
        truncated=found.truncated,
    )
