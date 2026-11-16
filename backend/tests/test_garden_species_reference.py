"""Garden references must describe the saved taxon, not a similarly named bird or object."""

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import unquote

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.auth import AuthContext
from app.models import SpeciesInfo
from app.routers import species as router

# The real client, taken before any test swaps `httpx.AsyncClient` for one on a mock transport.
REAL_ASYNC_CLIENT = httpx.AsyncClient

# Captured REST summaries and the iNaturalist records that link to them. A real summary does not
# carry the scientific name, so these are reached through the record's link, as in production.
_CAPTURED = {
    entry["scientific_name"]: entry
    for entry in json.loads((Path(__file__).parent / "fixtures" / "wikipedia_rest_summaries.json").read_text("utf-8"))[
        "others"
    ]
}
DOG = _CAPTURED["Canis familiaris"]["summary"]
DOG_TAXON = _CAPTURED["Canis familiaris"]["taxon"]
AIRCRAFT = {
    "title": "Cessna O-1 Bird Dog",
    "description": "Liaison and observation aircraft",
    "extract": "The Cessna O-1 Bird Dog is a liaison and observation aircraft.",
    "thumbnail": {"source": "https://example.com/aircraft.jpg"},
}


@pytest.fixture
def reference_api(monkeypatch):
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[router.get_auth_context_with_legacy] = lambda: AuthContext("owner")
    monkeypatch.setattr(router, "_wiki_cache", {})
    monkeypatch.setattr(router, "_definitive_misses", {})
    monkeypatch.setattr(router, "_resolve_summary_sources", lambda: ["wikipedia", "inaturalist"])
    monkeypatch.setattr(router, "_lookup_taxa_id", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_get_cached_species_info", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_save_species_info", AsyncMock())
    calls = []
    responses = {"dog": DOG, "taxa": [DOG_TAXON]}

    def response(request):
        calls.append(request)
        if request.url.host == "api.inaturalist.org":
            return httpx.Response(200, json={"results": responses["taxa"]})
        if request.url.path.endswith("/w/api.php"):
            return httpx.Response(200, json={"query": {"search": [{"title": AIRCRAFT["title"]}]}})
        title = unquote(request.url.path.split("/")[-1]).replace("_", " ")
        if title in {"Domestic Dog", "Domestic dog", "Canis familiaris", "Dog"}:
            return httpx.Response(200, json=responses["dog"])
        if title == AIRCRAFT["title"]:
            return httpx.Response(200, json=AIRCRAFT)
        return httpx.Response(404)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        router.httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(response), **kwargs)
    )
    with TestClient(app) as api:
        yield api, calls, responses


def test_dog_reference_uses_its_scientific_identity_instead_of_bird_search(reference_api):
    api, calls, _ = reference_api
    result = api.get("/api/species/Domestic%20Dog/info", params={"scientific_name": "Canis familiaris"})
    assert result.status_code == 200
    body = result.json()
    assert body["title"] == "Dog"
    photo = httpx.URL(body["thumbnail_url"])
    assert photo.host.endswith(".wikimedia.org") and photo.path.startswith("/wikipedia/commons/")
    assert body["extract"].startswith("The dog is a domesticated descendant of wolves.")
    assert body["summary_source_url"] == "https://en.wikipedia.org/wiki/Dog"
    assert body["scientific_name"] == "Canis familiaris"
    assert not any("bird" in request.url.params.get("srsearch", "").casefold() for request in calls)


def test_old_name_only_aircraft_cache_cannot_poison_a_taxon_reference(reference_api):
    api, _, _ = reference_api
    stale = SpeciesInfo(title=AIRCRAFT["title"], extract=AIRCRAFT["extract"], cached_at=datetime.now())
    router._get_cached_species_info.return_value = stale
    router._wiki_cache["Domestic Dog:en"] = (stale, datetime.now())
    result = api.get("/api/species/Domestic%20Dog/info", params={"scientific_name": "Canis familiaris"})
    assert result.json()["title"] == "Dog"
    router._get_cached_species_info.assert_not_called()
    router._save_species_info.assert_not_called()


def test_scientific_redirect_to_an_aircraft_returns_no_reference(reference_api):
    api, _, responses = reference_api
    # No record links an article, so the title is tried, and what answers is about something else.
    responses["taxa"] = []
    responses["dog"] = AIRCRAFT
    result = api.get("/api/species/Domestic%20Dog/info", params={"scientific_name": "Canis familiaris"})
    assert result.status_code == 200
    assert result.json()["extract"] is None
    assert result.json()["thumbnail_url"] is None


def test_animal_fallback_queries_all_taxa_and_requires_the_exact_identity(reference_api):
    api, calls, responses = reference_api
    responses["dog"] = AIRCRAFT
    responses["taxa"] = [
        {"id": 1, "name": "Cyanistes caeruleus", "preferred_common_name": "Domestic Dog", "iconic_taxon_name": "Aves"},
        {
            "id": 2,
            "name": "Canis familiaris",
            "preferred_common_name": "Dog",
            "iconic_taxon_name": "Mammalia",
            "wikipedia_summary": "A domesticated mammal.",
            "default_photo": {"medium_url": "https://example.com/dog.jpg"},
        },
    ]
    result = api.get("/api/species/Domestic%20Dog/info", params={"scientific_name": "Canis familiaris"})
    body = result.json()
    assert body["thumbnail_url"] == "https://example.com/dog.jpg"
    assert body["scientific_name"] == "Canis familiaris"
    assert body["summary_source"] == "iNaturalist"
    # Searches carry the identity; a detail read of the chosen taxon (for its IUCN status) has no query.
    queries = [
        request.url.params
        for request in calls
        if request.url.host == "api.inaturalist.org" and "q" in request.url.params
    ]
    assert queries
    assert all(query["q"] == "Canis familiaris" and "iconic_taxa" not in query for query in queries)


def test_animal_reference_never_falls_back_to_a_different_taxon(reference_api):
    api, _, responses = reference_api
    responses["dog"] = AIRCRAFT
    responses["taxa"] = [
        {
            "id": 1,
            "name": "Canis familiaris unrelated",
            "preferred_common_name": "Domestic Dog",
            "iconic_taxon_name": "Aves",
            "wikipedia_summary": "Wrong species.",
            "default_photo": {"medium_url": "https://example.com/wrong.jpg"},
        }
    ]
    body = api.get("/api/species/Domestic%20Dog/info", params={"scientific_name": "Canis familiaris"}).json()
    assert body["thumbnail_url"] is None
    assert body["extract"] is None


def test_taxon_cache_is_separate_for_each_identity_and_reusable(reference_api):
    api, calls, _ = reference_api
    path = "/api/species/Domestic%20Dog/info"
    first = api.get(path, params={"scientific_name": "Canis familiaris"}).json()
    count = len(calls)
    assert api.get(path, params={"scientific_name": "Canis familiaris"}).json() == first
    assert len(calls) == count
    assert api.get(path, params={"scientific_name": "Vulpes vulpes"}).json()["extract"] is None
    assert len(calls) > count
    count = len(calls)
    api.get(path, params={"scientific_name": "Canis familiaris", "refresh": True})
    assert len(calls) > count


def test_blank_scientific_identity_is_rejected(reference_api):
    api, calls, _ = reference_api
    assert api.get("/api/species/Dog/info", params={"scientific_name": "  "}).status_code == 422
    assert not calls


@pytest.mark.parametrize("text", ["XCanis familiaris", "Canis familiarisX", "Canis lupus familiaris"])
def test_wikipedia_identity_requires_the_complete_name(text):
    assert not router._has_scientific_identity({"extract": text}, "Canis familiaris")


def test_disambiguation_page_cannot_supply_a_reference():
    assert not router._has_scientific_identity(
        {"type": "disambiguation", "title": "Canis familiaris"}, "Canis familiaris"
    )


SQUIRREL = _CAPTURED["Sciurus carolinensis"]["summary"]
SQUIRREL_TAXON = _CAPTURED["Sciurus carolinensis"]["taxon"]
MITE = {
    "title": "Androlaelaps fahrenholzi",
    "description": "Species of mite",
    "extract": (
        "Androlaelaps fahrenholzi is a species of mite in the genus Androlaelaps of the family Laelapidae. "
        "It has been recorded on the following mammals: Blarina brevicauda, Sciurus carolinensis."
    ),
    "thumbnail": {"source": "https://example.com/mite.jpg"},
}


def _squirrel_wikipedia(monkeypatch, *, direct: dict | None, taxa: tuple[dict, ...] = ()):
    """Wikipedia as the squirrel lookup meets it: the direct title, then a search that finds a mite."""

    def response(request):
        if request.url.host == "api.inaturalist.org":
            return httpx.Response(200, json={"results": list(taxa)})
        if request.url.path.endswith("/w/api.php"):
            return httpx.Response(200, json={"query": {"search": [{"title": MITE["title"]}]}})
        title = unquote(request.url.path.split("/")[-1]).replace("_", " ")
        if title == MITE["title"]:
            return httpx.Response(200, json=MITE)
        if title in {"Sciurus carolinensis", SQUIRREL["title"]} and direct is not None:
            return httpx.Response(200, json=direct)
        return httpx.Response(404)

    monkeypatch.setattr(
        router.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(response), **kwargs),
    )


def test_a_squirrel_is_never_described_by_a_mite_that_lists_it_as_a_host(reference_api, monkeypatch):
    api, _, _ = reference_api
    _squirrel_wikipedia(monkeypatch, direct=None)
    body = api.get(
        "/api/species/Eastern%20Gray%20Squirrel/info", params={"scientific_name": "Sciurus carolinensis"}
    ).json()
    assert body["extract"] is None
    assert body["thumbnail_url"] is None
    assert body["wikipedia_url"] is None


def test_a_squirrel_is_described_by_its_own_article(reference_api, monkeypatch):
    api, _, _ = reference_api
    _squirrel_wikipedia(monkeypatch, direct=SQUIRREL, taxa=(SQUIRREL_TAXON,))
    body = api.get(
        "/api/species/Eastern%20Gray%20Squirrel/info", params={"scientific_name": "Sciurus carolinensis"}
    ).json()
    assert body["title"] == "Eastern gray squirrel"
    assert "Sciurus carolinensis" not in body["extract"], "the real summary does not name its taxon"
    assert "tree squirrel" in body["extract"]


def test_a_squirrel_with_no_linked_article_is_not_described_by_text_that_cannot_be_checked(reference_api, monkeypatch):
    api, _, _ = reference_api
    _squirrel_wikipedia(monkeypatch, direct=SQUIRREL)
    body = api.get(
        "/api/species/Eastern%20Gray%20Squirrel/info", params={"scientific_name": "Sciurus carolinensis"}
    ).json()
    assert body["extract"] is None
