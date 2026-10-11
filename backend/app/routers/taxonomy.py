"""A taxon's place in the classification: its lineage and the branch beneath it."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_auth_context_with_legacy
from app.database import get_db
from app.ratelimit import guest_rate_limit
from app.repositories.detection_repository import DetectionRepository
from app.services.species_catalog_resolver import species_catalog_resolver
from app.services.taxonomy_tree import Taxon, taxonomy_tree
from app.utils.language import get_user_language
from app.utils.public_access import public_event_query_bounds

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
    seen_count: Optional[int] = Field(None, description="Detections of those species here, in the reader's window")


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
    )


async def _seen_here(auth: AuthContext) -> dict[int, int]:
    """Detections per catalogue identity, in the window the reader may see: all history for the owner."""
    bounds = {} if auth.is_owner else public_event_query_bounds()
    async with get_db() as db:
        return await DetectionRepository(db).species_identity_counts(**bounds)


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
