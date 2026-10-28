"""Garden references must describe the saved taxon, not a similarly named bird or object."""

from datetime import datetime
from unittest.mock import AsyncMock
from urllib.parse import unquote

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.auth import AuthContext
from app.models import SpeciesInfo
from app.routers import species as router


DOG = {
    "title": "Dog",
    "description": "Domesticated mammal",
    "extract": "The dog (Canis familiaris) is a domesticated descendant of the wolf.",
    "thumbnail": {"source": "https://example.com/dog.jpg"},
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Dog"}},
}
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
    responses = {"dog": DOG, "taxa": []}

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
    assert body["thumbnail_url"] == "https://example.com/dog.jpg"
    assert "Canis familiaris" in body["extract"]
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
    queries = [request.url.params for request in calls if request.url.host == "api.inaturalist.org"]
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
