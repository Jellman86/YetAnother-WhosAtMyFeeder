"""A taxon's place in the classification: its lineage and the branch beneath it."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.services.taxonomy_tree import Taxon, taxonomy_tree
from app.utils.language import get_user_language

router = APIRouter()


class TaxonResponse(BaseModel):
    taxon_id: int = Field(..., description="Catalogue identity; for a species it is its species_id")
    rank: str = Field(..., description="kingdom, phylum, class, order, family, genus, species, or an intermediate rank")
    scientific_name: str
    name: Optional[str] = Field(None, description="Common name in the reader's language, else English, when one exists")
    source: Optional[str] = Field(None, description="The pinned source the taxon comes from")
    principal: bool = Field(..., description="False for intermediate ranks a view may collapse")
    parent_id: Optional[int] = None
    species_count: Optional[int] = Field(None, description="Species beneath this taxon, on branch reads")


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
    )


@router.get("/taxonomy/{taxon_id}/lineage", response_model=TaxonLineageResponse)
@guest_rate_limit()
async def get_taxon_lineage(
    request: Request, taxon_id: int, auth: AuthContext = Depends(get_auth_context_with_legacy)
) -> TaxonLineageResponse:
    """Where a taxon sits: every taxon above it, root first. Catalogue data only, so the same for every reader."""
    lineage = await asyncio.to_thread(taxonomy_tree.lineage, taxon_id, language=get_user_language(request))
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
    children = await asyncio.to_thread(
        taxonomy_tree.children, taxon_id, language=get_user_language(request), limit=limit
    )
    return TaxonChildrenResponse(parent_id=taxon_id, children=[_response(taxon) for taxon in children])
