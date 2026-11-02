"""A family or order is described only by the taxon of that name at that rank, and a species
carries the IUCN Red List's global category when iNaturalist records one.

A bare name can land on the wrong page (a "Bird Dog" is an aircraft; *Prunella* is also a plant
genus), so a group's description never comes from a name search: it comes from the one
iNaturalist taxon with that exact name and rank, or from the Wikipedia page that taxon links to,
and only when that page names it.
"""

from unittest.mock import AsyncMock
from urllib.parse import unquote

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.auth import AuthContext
from app.routers import species as router

ACCENTORS = {
    "id": 71358,
    "name": "Prunellidae",
    "rank": "family",
    "iconic_taxon_name": "Aves",
    "is_active": True,
    "wikipedia_summary": "The accentors are a genus of birds in the family Prunellidae.",
    "wikipedia_url": "http://en.wikipedia.org/wiki/Accentor",
    "default_photo": {"medium_url": "https://example.com/accentor.jpg"},
}
DUNNOCK = {
    "id": 13988,
    "name": "Prunella modularis",
    "rank": "species",
    "iconic_taxon_name": "Aves",
    "is_active": True,
    "preferred_common_name": "Dunnock",
    "wikipedia_summary": "The dunnock (Prunella modularis) is a small passerine.",
    "default_photo": {"medium_url": "https://example.com/dunnock.jpg"},
}
GLOBAL_LC = {"authority": "IUCN Red List", "status": "LC", "iucn": 10, "place": None}
EUROPE_NT = {"authority": "IUCN Red List", "status": "NT", "iucn": 20, "place": {"name": "Europe"}}
NATURESERVE = {"authority": "NatureServe", "status": "G5", "iucn": 10, "place": None}


@pytest.fixture
def lookup(monkeypatch):
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[router.get_auth_context_with_legacy] = lambda: AuthContext("owner")
    monkeypatch.setattr(router, "_wiki_cache", {})
    monkeypatch.setattr(router, "_definitive_misses", {})
    monkeypatch.setattr(router, "_resolve_summary_sources", lambda: ["wikipedia", "inaturalist"])
    monkeypatch.setattr(router, "_lookup_taxa_id", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_get_cached_species_info", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_save_species_info", AsyncMock())
    state: dict = {"taxa": [], "details": {}, "pages": {}}
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "api.inaturalist.org":
            last = request.url.path.rsplit("/", 1)[-1]
            if last.isdigit():
                detail = state["details"].get(int(last))
                return httpx.Response(200, json={"results": [detail] if detail else []})
            return httpx.Response(200, json={"results": state["taxa"]})
        title = unquote(request.url.path.split("/")[-1]).replace("_", " ")
        page = state["pages"].get(title)
        return httpx.Response(200, json=page) if page else httpx.Response(404)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        router.httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs)
    )
    with TestClient(app) as api:
        yield api, state, calls


def wikipedia_titles(calls: list[httpx.Request]) -> list[str]:
    return [
        unquote(request.url.path.split("/")[-1]).replace("_", " ")
        for request in calls
        if request.url.host.endswith("wikipedia.org")
    ]


def describe(api, name: str, rank: str | None = None) -> dict:
    params = {"scientific_name": name, **({"rank": rank} if rank else {})}
    response = api.get(f"/api/species/{name}/info", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_family_is_described_by_the_taxon_of_that_name_at_that_rank(lookup):
    api, state, calls = lookup
    # A Wikipedia page titled with the bare name would be accepted by a name match; it is never asked.
    state["pages"]["Prunellidae"] = {"title": "Prunellidae", "extract": "Prunellidae is a band."}
    state["taxa"] = [{**ACCENTORS, "id": 1, "rank": "genus", "wikipedia_summary": "Wrong rank."}, ACCENTORS]
    body = describe(api, "Prunellidae", "family")
    assert body["extract"] == ACCENTORS["wikipedia_summary"]
    assert (body["taxa_id"], body["summary_source"], body["conservation_status"]) == (71358, "iNaturalist", None)
    assert wikipedia_titles(calls) == []


@pytest.mark.parametrize(
    "taxa",
    [
        [{**ACCENTORS, "rank": "genus"}],
        [{**ACCENTORS, "name": "Prunellidae nova"}],
        # Two taxa share the name and rank (a homonym across kingdoms): no way to know which is meant.
        [ACCENTORS, {**ACCENTORS, "id": 2, "iconic_taxon_name": "Plantae"}],
    ],
)
def test_a_family_without_one_exact_taxon_at_its_rank_gets_no_description(lookup, taxa):
    api, state, _ = lookup
    state["taxa"] = taxa
    body = describe(api, "Prunellidae", "family")
    assert (body["extract"], body["thumbnail_url"]) == (None, None)


def test_a_family_without_an_inaturalist_summary_reads_the_page_its_taxon_links_to_if_it_names_it(lookup):
    api, state, calls = lookup
    state["taxa"] = [{**ACCENTORS, "wikipedia_summary": None}]
    state["details"][71358] = {**ACCENTORS, "wikipedia_summary": None}
    state["pages"]["Accentor"] = {"title": "Accentor", "extract": "Accentors form the family Prunellidae."}
    assert describe(api, "Prunellidae", "family")["extract"] == "Accentors form the family Prunellidae."
    assert wikipedia_titles(calls) == ["Accentor"]
    router._wiki_cache.clear()
    state["pages"]["Accentor"] = {"title": "Accentor", "extract": "A Cessna liaison aircraft."}
    assert describe(api, "Prunellidae", "family")["extract"] is None


def test_an_order_lookup_is_cached_apart_from_a_species_lookup_of_the_same_text(lookup):
    api, state, calls = lookup
    order = {**ACCENTORS, "id": 7251, "name": "Passeriformes", "rank": "order", "wikipedia_summary": "Passerines."}
    state["taxa"] = [order]
    assert describe(api, "Passeriformes", "order")["extract"] == "Passerines."
    count = len(calls)
    assert describe(api, "Passeriformes", "order")["extract"] == "Passerines."
    assert len(calls) == count
    assert api.get("/api/species/Passeriformes/info", params={"rank": "order"}).status_code == 200
    assert api.get("/api/species/x/info", params={"scientific_name": "x", "rank": "kingdom"}).status_code == 422


def test_a_species_carries_the_global_iucn_category_even_when_wikipedia_answered_first(lookup):
    api, state, _ = lookup
    page = {
        "title": "Dunnock",
        "extract": "The dunnock (Prunella modularis) is a small passerine.",
        "thumbnail": {"source": "https://example.com/wiki-dunnock.jpg"},
    }
    state["pages"].update({"Prunella modularis": page, "Dunnock": page})
    state["taxa"] = [DUNNOCK]
    state["details"][13988] = {**DUNNOCK, "conservation_statuses": [EUROPE_NT, NATURESERVE, GLOBAL_LC]}
    body = describe(api, "Prunella modularis")
    assert body["conservation_status"] == "LC"
    # Wikipedia still supplies the text and photograph it found.
    assert body["thumbnail_url"] == "https://example.com/wiki-dunnock.jpg"


@pytest.mark.parametrize(
    "statuses",
    [[], [EUROPE_NT], [NATURESERVE], [{**GLOBAL_LC, "status": "secure", "iucn": 99}]],
)
def test_without_a_global_iucn_assessment_a_species_has_no_status(lookup, statuses):
    api, state, _ = lookup
    state["taxa"] = [DUNNOCK]
    state["details"][13988] = {**DUNNOCK, "conservation_statuses": statuses}
    assert describe(api, "Prunella modularis")["conservation_status"] is None


def test_the_iucn_category_is_read_from_its_number_when_the_code_is_spelled_out(lookup):
    api, state, _ = lookup
    state["taxa"] = [DUNNOCK]
    state["details"][13988] = {**DUNNOCK, "conservation_statuses": [{**GLOBAL_LC, "status": "vulnerable", "iucn": 30}]}
    assert describe(api, "Prunella modularis")["conservation_status"] == "VU"
