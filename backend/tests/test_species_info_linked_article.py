"""A taxon is described by the article its own iNaturalist record links to.

Wikipedia's REST summary leaves the scientific-name parenthetical out of its
extract ("The house sparrow is a bird of the sparrow family..."), so the text
of an ordinary summary cannot show which taxon it is about. iNaturalist's
record of the taxon carries the link to its article, and that link is the
identity: the summary of exactly that article is the taxon's description.

The summaries here are captured REST responses, not written for the test.
"""

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
from app.database import get_db
from app.models import SpeciesInfo
from app.repositories.species_repository import SpeciesRepository
from app.routers import species as router
from app.services.reference_identity import article_describes_taxon

REAL_ASYNC_CLIENT = httpx.AsyncClient
CAPTURED = json.loads((Path(__file__).parent / "fixtures" / "wikipedia_rest_summaries.json").read_text("utf-8"))
BIRDS = CAPTURED["birds"]
BIRD_IDS = [bird["species"] for bird in BIRDS]


def _shown(bird: dict) -> str:
    """The captured extract as the API returns it: its non-breaking spaces become plain ones."""
    return SpeciesInfo(title=bird["summary"]["title"], extract=bird["summary"]["extract"]).extract


def _linked_title(bird: dict) -> str:
    return unquote(bird["taxon"]["wikipedia_url"].split("/wiki/")[-1]).replace("_", " ")


class Services:
    """iNaturalist and Wikipedia as they answered when the fixtures were captured."""

    def __init__(self) -> None:
        self.taxa = {bird["scientific_name"]: bird["taxon"] for bird in BIRDS}
        # Wikipedia answers a title and its redirects with the same article.
        self.articles = {_linked_title(bird).casefold(): bird["summary"] for bird in BIRDS}
        self.articles.update({bird["summary"]["title"].casefold(): bird["summary"] for bird in BIRDS})
        self.other_languages: dict[tuple[str, str], str] = {}
        self.search: list[str] = []
        self.requests: list[str] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host == "api.inaturalist.org":
            return self._inaturalist(request)
        if request.url.path.endswith("/w/api.php"):
            return self._wikipedia_query(request)
        language = request.url.host.split(".")[0]
        title = unquote(request.url.path.split("/")[-1]).replace("_", " ").casefold()
        found = self.articles.get(title) if language == "en" else self.articles.get(f"{language}:{title}")
        return httpx.Response(200, json=found) if found else httpx.Response(404)

    def _inaturalist(self, request: httpx.Request) -> httpx.Response:
        last = request.url.path.rsplit("/", 1)[-1]
        if last.isdigit():
            return httpx.Response(
                200, json={"results": [taxon for taxon in self.taxa.values() if taxon["id"] == int(last)]}
            )
        asked = request.url.params.get("q", "").casefold()
        return httpx.Response(
            200, json={"results": [taxon for name, taxon in self.taxa.items() if name.casefold() == asked]}
        )

    def _wikipedia_query(self, request: httpx.Request) -> httpx.Response:
        if request.url.params.get("prop") == "langlinks":
            title = request.url.params["titles"].replace("_", " ")
            local = self.other_languages.get((request.url.params["lllang"], title.casefold()))
            page = {"title": title, "langlinks": [{"lang": request.url.params["lllang"], "*": local}]} if local else {}
            return httpx.Response(200, json={"query": {"pages": {"1": page}}})
        return httpx.Response(200, json={"query": {"search": [{"title": title} for title in self.search]}})


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router.router, prefix="/api")
    app.dependency_overrides[router.get_auth_context_with_legacy] = lambda: AuthContext("owner")
    return app


@pytest.fixture
def services(monkeypatch):
    services = Services()
    monkeypatch.setattr(router, "_wiki_cache", {})
    monkeypatch.setattr(router, "_definitive_misses", {})
    monkeypatch.setattr(router, "_resolve_summary_sources", lambda: ["wikipedia", "inaturalist"])
    monkeypatch.setattr(
        router.httpx,
        "AsyncClient",
        lambda **kwargs: REAL_ASYNC_CLIENT(transport=httpx.MockTransport(services.respond), **kwargs),
    )
    return services


@pytest.fixture
def info_api(services, monkeypatch):
    monkeypatch.setattr(router, "_lookup_taxa_id", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_get_cached_species_info", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_save_species_info", AsyncMock())
    with TestClient(_app()) as api:
        yield api, services


@pytest.mark.parametrize("bird", BIRDS, ids=BIRD_IDS)
def test_the_text_of_a_real_summary_does_not_say_which_taxon_it_is_about(bird):
    """Why the link is needed: the subject rule alone turns every one of these away."""
    assert bird["scientific_name"].casefold() not in bird["summary"]["extract"].casefold()
    assert not article_describes_taxon(bird["summary"], bird["scientific_name"])


@pytest.mark.parametrize("bird", BIRDS, ids=BIRD_IDS)
def test_a_bird_is_described_by_the_article_its_taxon_links_to(info_api, monkeypatch, bird):
    api, _services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value=bird["scientific_name"]))

    body = api.get(f"/api/species/{bird['species']}/info").json()

    assert body["extract"] == _shown(bird)
    assert body["title"] == bird["summary"]["title"]
    assert body["summary_source"] == "Wikipedia"
    assert body["summary_source_url"] == bird["summary"]["content_urls"]["desktop"]["page"]
    assert body["scientific_name"] == bird["scientific_name"]


@pytest.mark.parametrize("bird", BIRDS, ids=BIRD_IDS)
def test_a_record_asked_for_by_scientific_name_gets_the_linked_article_too(info_api, bird):
    api, _services = info_api

    body = api.get(f"/api/species/{bird['species']}/info", params={"scientific_name": bird["scientific_name"]}).json()

    assert body["extract"] == _shown(bird)
    assert body["summary_source"] == "Wikipedia"


def test_the_linked_article_is_asked_for_by_its_exact_title_and_nothing_is_searched(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Fringilla coelebs"))

    body = api.get("/api/species/Common Chaffinch/info").json()

    # iNaturalist links "Common chaffinch", which Wikipedia has since renamed: its own redirect is followed.
    assert body["title"] == "Eurasian chaffinch"
    wikipedia = [url for url in services.requests if "wikipedia.org" in url]
    assert wikipedia == ["https://en.wikipedia.org/api/rest_v1/page/summary/Common_chaffinch"]


def test_a_linked_page_that_is_a_disambiguation_is_not_a_description(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Erithacus rubecula"))
    services.articles["european robin"] = {"type": "disambiguation", "title": "Robin", "extract": "Robin may refer to:"}

    assert api.get("/api/species/European Robin/info").json()["extract"] is None


def test_a_taxon_with_no_linked_article_falls_back_to_the_subject_rule(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    services.taxa["Passer domesticus"] = {**services.taxa["Passer domesticus"], "wikipedia_url": None}
    # Found by title, with nothing in its text to say it is this taxon: refused.
    assert api.get("/api/species/House Sparrow/info").json()["extract"] is None

    router._wiki_cache.clear()
    router._definitive_misses.clear()
    services.articles["house sparrow"] = {
        "type": "standard",
        "title": "House sparrow",
        "extract": "The house sparrow (Passer domesticus) is a bird of the sparrow family Passeridae.",
    }
    assert api.get("/api/species/House Sparrow/info").json()["extract"].startswith("The house sparrow (Passer")


def test_a_predator_found_by_title_is_still_refused_when_the_prey_has_no_link(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    services.taxa["Passer domesticus"] = {**services.taxa["Passer domesticus"], "wikipedia_url": None}
    services.articles["passer domesticus"] = {
        "type": "standard",
        "title": "Eurasian sparrowhawk",
        "extract": "The Eurasian sparrowhawk hunts the house sparrow (Passer domesticus) and other small birds.",
    }

    assert api.get("/api/species/House Sparrow/info").json()["extract"] is None


def test_another_language_gets_the_article_wikipedia_links_from_the_taxons_own(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Anas platyrhynchos"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    services.other_languages[("de", "mallard")] = "Stockente"
    services.articles["de:stockente"] = {
        "type": "standard",
        "title": "Stockente",
        "lang": "de",
        "extract": "Die Stockente ist eine Vogelart aus der Familie der Entenvögel.",
        "content_urls": {"desktop": {"page": "https://de.wikipedia.org/wiki/Stockente"}},
    }

    body = api.get("/api/species/Stockente/info").json()

    assert body["extract"] == "Die Stockente ist eine Vogelart aus der Familie der Entenvögel."
    assert body["summary_source_url"] == "https://de.wikipedia.org/wiki/Stockente"


@pytest.fixture
def cached_api(services, monkeypatch):
    """The real reference cache, in memory and in the database."""
    monkeypatch.setattr(router, "_lookup_taxa_id", AsyncMock(return_value=None))
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    with TestClient(_app()) as api:
        yield api, services


async def _forget(species: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM species_info_cache WHERE species_name = ?", (species,))
        await db.commit()


@pytest.mark.asyncio
async def test_a_description_accepted_through_the_link_is_served_from_the_cache_without_a_lookup(cached_api):
    api, services = cached_api
    await _forget("House Sparrow")
    sparrow = next(bird for bird in BIRDS if bird["species"] == "House Sparrow")

    first = api.get("/api/species/House Sparrow/info").json()
    router._wiki_cache.clear()
    services.requests.clear()
    again = api.get("/api/species/House Sparrow/info").json()

    assert first["extract"] == again["extract"] == _shown(sparrow)
    assert services.requests == [], "the database row is trusted: its identity was checked when it was saved"
    await _forget("House Sparrow")


@pytest.mark.asyncio
async def test_a_row_cached_before_identity_was_recorded_is_looked_up_once_and_then_trusted(cached_api):
    api, services = cached_api
    await _forget("House Sparrow")
    # The louse article an older release could have saved against the sparrow's name.
    async with get_db() as db:
        await SpeciesRepository(db).save_cached_info(
            species_name="House Sparrow",
            taxa_id=None,
            language="en",
            values=SpeciesInfo(
                title="Brueelia",
                extract="Brueelia is a genus of lice found on songbirds.",
                source="Wikipedia",
                summary_source="Wikipedia",
                scientific_name="Passer domesticus",
                cached_at=datetime.now(),
            ).model_dump(),
            cached_at=datetime.now(),
        )

    body = api.get("/api/species/House Sparrow/info").json()

    assert "lice" not in body["extract"]
    assert body["extract"].startswith("The house sparrow is a bird")
    router._wiki_cache.clear()
    services.requests.clear()
    assert api.get("/api/species/House Sparrow/info").json()["extract"] == body["extract"]
    assert services.requests == []
    await _forget("House Sparrow")
