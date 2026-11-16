"""A bird looked up by name is described only by an article about that bird.

When the taxonomy cache knows the bird's scientific name, a Wikipedia article
found by search must be about that taxon: one that merely mentions the name,
such as a parasite's article listing its hosts, is not a description of it.
"""

from datetime import datetime
from unittest.mock import AsyncMock
from urllib.parse import unquote

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.auth import AuthContext
from app.database import get_db
from app.models import SpeciesInfo
from app.repositories.species_repository import SpeciesRepository
from app.routers import species as router

REAL_ASYNC_CLIENT = httpx.AsyncClient

STARLING = {
    "title": "Common starling",
    "description": "Species of bird",
    "extract": "The common starling (Sturnus vulgaris), also known as the European starling, is a medium-sized passerine bird.",
    "thumbnail": {"source": "https://example.com/starling.jpg"},
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Common_starling"}},
}
LOUSE = {
    "title": "Brueelia nebulosa",
    "description": "Species of louse",
    "extract": (
        "Brueelia nebulosa is a species of chewing louse that lives on birds. "
        "Its usual host is the common starling, Sturnus vulgaris, a passerine bird."
    ),
    "thumbnail": {"source": "https://example.com/louse.jpg"},
}


@pytest.fixture
def info_api(monkeypatch):
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[router.get_auth_context_with_legacy] = lambda: AuthContext("owner")
    monkeypatch.setattr(router, "_wiki_cache", {})
    monkeypatch.setattr(router, "_definitive_misses", {})
    monkeypatch.setattr(router, "_resolve_summary_sources", lambda: ["wikipedia", "inaturalist"])
    monkeypatch.setattr(router, "_lookup_taxa_id", AsyncMock(return_value=14850))
    monkeypatch.setattr(router, "_get_cached_species_info", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_save_species_info", AsyncMock())
    articles: dict[str, dict] = {}
    search: list[str] = []

    def response(request):
        if request.url.host == "api.inaturalist.org":
            return httpx.Response(200, json={"results": []})
        if request.url.path.endswith("/w/api.php"):
            return httpx.Response(200, json={"query": {"search": [{"title": title} for title in search]}})
        # Wikipedia resolves a title whatever its capitalisation.
        title = unquote(request.url.path.split("/")[-1]).replace("_", " ").casefold()
        found = next((article for name, article in articles.items() if name.casefold() == title), None)
        return httpx.Response(200, json=found) if found else httpx.Response(404)

    monkeypatch.setattr(
        router.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(response), **kwargs),
    )
    with TestClient(app) as api:
        yield api, articles, search


def test_a_searched_article_that_only_mentions_the_bird_is_not_its_description(info_api, monkeypatch):
    api, articles, search = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Sturnus vulgaris"))
    articles[LOUSE["title"]] = LOUSE
    search.append(LOUSE["title"])

    body = api.get("/api/species/European%20Starling/info").json()

    assert body["extract"] is None
    assert body["thumbnail_url"] is None
    router._save_species_info.assert_awaited()
    saved = router._save_species_info.await_args.args[3]
    assert saved.extract is None, "a mismatched description must not be cached"


def test_the_birds_own_article_is_still_found_by_search(info_api, monkeypatch):
    api, articles, search = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Sturnus vulgaris"))
    articles[LOUSE["title"]] = LOUSE
    articles[STARLING["title"]] = STARLING
    search.extend([LOUSE["title"], STARLING["title"]])

    body = api.get("/api/species/European%20Starling/info").json()

    assert body["title"] == "Common starling"
    assert "passerine" in body["extract"]


def test_a_bird_the_taxonomy_does_not_know_keeps_the_name_based_search(info_api, monkeypatch):
    api, articles, search = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value=None))
    articles[STARLING["title"]] = STARLING
    search.append(STARLING["title"])

    body = api.get("/api/species/Common%20Starling/info").json()

    assert body["title"] == "Common starling"


@pytest.fixture
def seeded_cache_api(monkeypatch):
    """The real reference cache, in memory and in the database, with Wikipedia mocked."""
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[router.get_auth_context_with_legacy] = lambda: AuthContext("owner")
    monkeypatch.setattr(router, "_wiki_cache", {})
    monkeypatch.setattr(router, "_definitive_misses", {})
    monkeypatch.setattr(router, "_resolve_summary_sources", lambda: ["wikipedia", "inaturalist"])
    monkeypatch.setattr(router, "_lookup_taxa_id", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Sturnus vulgaris"))
    articles = {STARLING["title"]: STARLING}
    requests: list[str] = []

    def response(request):
        requests.append(str(request.url))
        if request.url.host == "api.inaturalist.org":
            return httpx.Response(200, json={"results": []})
        if request.url.path.endswith("/w/api.php"):
            return httpx.Response(200, json={"query": {"search": [{"title": STARLING["title"]}]}})
        title = unquote(request.url.path.split("/")[-1]).replace("_", " ").casefold()
        found = next((article for name, article in articles.items() if name.casefold() == title), None)
        return httpx.Response(200, json=found) if found else httpx.Response(404)

    monkeypatch.setattr(
        router.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(response), **kwargs),
    )
    with TestClient(app) as api:
        yield api, requests


async def _seed_cached_description(info: SpeciesInfo) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM species_info_cache WHERE species_name = ?", ("European Starling",))
        await db.commit()
        await SpeciesRepository(db).save_cached_info(
            species_name="European Starling",
            taxa_id=None,
            language="en",
            values=info.model_dump(),
            cached_at=datetime.now(),
        )


LOUSE_CACHED = dict(
    title=LOUSE["title"],
    extract=LOUSE["extract"],
    thumbnail_url=LOUSE["thumbnail"]["source"],
    source="Wikipedia",
    summary_source="Wikipedia",
    scientific_name="Sturnus vulgaris",
)


@pytest.mark.asyncio
async def test_a_wrong_description_cached_under_the_old_rule_is_not_returned(seeded_cache_api):
    api, requests = seeded_cache_api
    await _seed_cached_description(SpeciesInfo(**LOUSE_CACHED, cached_at=datetime.now()))

    body = api.get("/api/species/European%20Starling/info").json()

    assert "louse" not in (body["extract"] or "")
    assert body["title"] == "Common starling"
    assert requests, "the stale entry is looked up again, not served"
    # The replacement is what the cache now holds.
    again = api.get("/api/species/European%20Starling/info").json()
    assert again["title"] == "Common starling"


@pytest.mark.asyncio
async def test_a_wrong_description_held_in_memory_is_not_returned_either(seeded_cache_api):
    api, _requests = seeded_cache_api
    stale = SpeciesInfo(**LOUSE_CACHED, cached_at=datetime.now())
    router._wiki_cache["European Starling:en"] = (stale, datetime.now())

    body = api.get("/api/species/European%20Starling/info").json()

    assert "louse" not in (body["extract"] or "")


@pytest.mark.asyncio
async def test_a_cached_description_of_the_right_bird_is_still_served_without_a_lookup(seeded_cache_api):
    api, requests = seeded_cache_api
    await _seed_cached_description(
        SpeciesInfo(
            title=STARLING["title"],
            extract=STARLING["extract"],
            source="Wikipedia",
            summary_source="Wikipedia",
            scientific_name="Sturnus vulgaris",
            cached_at=datetime.now(),
        )
    )

    body = api.get("/api/species/European%20Starling/info").json()

    assert body["title"] == "Common starling"
    assert requests == []


@pytest.mark.asyncio
async def test_a_cached_summary_of_another_taxon_from_inaturalist_is_not_returned(seeded_cache_api):
    api, _requests = seeded_cache_api
    await _seed_cached_description(
        SpeciesInfo(
            title="Spotless Starling",
            extract="A starling of Iberia and north-west Africa.",
            source="iNaturalist",
            summary_source="iNaturalist",
            scientific_name="Sturnus unicolor",
            cached_at=datetime.now(),
        )
    )

    body = api.get("/api/species/European%20Starling/info").json()

    assert body["title"] == "Common starling"


SPARROWHAWK = {
    "title": "Eurasian sparrowhawk",
    "description": "Species of bird of prey",
    "extract": "The Eurasian sparrowhawk hunts the house sparrow (Passer domesticus) and other small birds.",
    "thumbnail": {"source": "https://example.com/hawk.jpg"},
}
HOST_LOUSE = {
    "title": "Brueelia nebulosa",
    "description": "Species of louse",
    "extract": "Brueelia nebulosa lives on the common starling (Sturnus vulgaris), a passerine bird.",
    "thumbnail": {"source": "https://example.com/louse.jpg"},
}


@pytest.mark.parametrize(
    ("species", "scientific", "wrong"),
    [("House Sparrow", "Passer domesticus", SPARROWHAWK), ("European Starling", "Sturnus vulgaris", HOST_LOUSE)],
)
def test_a_direct_scientific_name_lookup_that_lands_on_a_predator_or_parasite_is_refused(
    info_api, monkeypatch, species, scientific, wrong
):
    api, articles, _search = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value=scientific))
    # The title lookup by scientific name resolves, as a redirect would, to an article about something else.
    articles[scientific] = wrong

    body = api.get(f"/api/species/{species}/info").json()

    assert body["extract"] is None
    assert body["thumbnail_url"] is None


def test_a_subspecies_article_is_not_returned_for_its_parent_species(info_api, monkeypatch):
    api, articles, search = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Troglodytes troglodytes"))
    articles["St Kilda wren"] = {
        "title": "St Kilda wren",
        "description": "Subspecies of bird",
        "extract": "The St Kilda wren (Troglodytes troglodytes hirtensis) is a small passerine bird.",
    }
    search.append("St Kilda wren")

    body = api.get("/api/species/Eurasian%20Wren/info").json()

    assert body["extract"] is None
