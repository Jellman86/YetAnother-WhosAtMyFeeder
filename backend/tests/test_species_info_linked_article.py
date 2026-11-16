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
        self.language_links_time_out = False
        self.translations_time_out = False
        self.search: list[str] = []
        self.requests: list[str] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host == "api.inaturalist.org":
            return self._inaturalist(request)
        if request.url.path.endswith("/w/api.php"):
            if request.url.params.get("prop") == "langlinks" and self.language_links_time_out:
                raise httpx.ReadTimeout("language links timed out", request=request)
            return self._wikipedia_query(request)
        language = request.url.host.split(".")[0]
        if language != "en" and self.translations_time_out:
            raise httpx.ReadTimeout("translated article timed out", request=request)
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


# What the species catalogue records as names of these taxa. Wikipedia has renamed the chaffinch's
# article since iNaturalist linked it; the catalogue's IOC name is what says the two are one bird.
CATALOGUE_NAMES = {"Fringilla coelebs": frozenset({"eurasian chaffinch", "common chaffinch", "buchfink"})}


@pytest.fixture
def services(monkeypatch):
    services = Services()
    monkeypatch.setattr(
        router, "_catalogue_names", lambda scientific_name: CATALOGUE_NAMES.get(scientific_name, frozenset())
    )
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

    # iNaturalist links "Common chaffinch", which Wikipedia has since renamed. The redirect is followed
    # because the catalogue records "Eurasian chaffinch" as a name of this taxon.
    assert body["title"] == "Eurasian chaffinch"
    wikipedia = [url for url in services.requests if (httpx.URL(url).host or "").endswith(".wikipedia.org")]
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


# A redirect can land on another taxon. Each of these is where the house sparrow's linked title
# could come to point: the article that answers is real in shape, and none is about the sparrow.
WRONG_TARGETS = {
    "its predator": {
        "type": "standard",
        "title": "Eurasian sparrowhawk",
        "extract": "The Eurasian sparrowhawk is a small bird of prey that hunts the house sparrow (Passer domesticus).",
    },
    "a parasite that lists it as a host": {
        "type": "standard",
        "title": "Androlaelaps casalis",
        "extract": "Androlaelaps casalis is a species of mite. It has been recorded on Passer domesticus.",
    },
    "a louse that lives on it": {
        "type": "standard",
        "title": "Brueelia",
        "extract": "Brueelia is a genus of lice that lives on songbirds such as the house sparrow, Passer domesticus.",
    },
    "one of its subspecies": {
        "type": "standard",
        "title": "Indian house sparrow",
        "extract": "The Indian house sparrow (Passer domesticus indicus) is a subspecies of the house sparrow.",
    },
}


@pytest.mark.parametrize("by_scientific_name", [False, True], ids=["by bird name", "by scientific name"])
@pytest.mark.parametrize("target", WRONG_TARGETS.values(), ids=WRONG_TARGETS.keys())
def test_a_redirect_that_lands_on_another_taxon_is_not_its_description(
    info_api, monkeypatch, target, by_scientific_name
):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    services.articles["house sparrow"] = target
    params = {"scientific_name": "Passer domesticus"} if by_scientific_name else {}

    body = api.get("/api/species/House Sparrow/info", params=params).json()

    assert body["extract"] is None
    assert body["title"] != target["title"]
    if not by_scientific_name:
        saved = router._save_species_info.await_args.args[3]
        assert saved.extract is None
        assert not saved.identity_checked, "an unverified redirect is never recorded as checked"


def test_a_redirect_is_followed_when_the_catalogue_names_the_taxon_by_the_new_title(info_api, monkeypatch):
    api, _services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Fringilla coelebs"))

    body = api.get("/api/species/Common Chaffinch/info").json()

    assert body["title"] == "Eurasian chaffinch"
    assert body["extract"].startswith("The Eurasian chaffinch")


def test_the_same_redirect_is_unverified_when_nothing_says_the_new_title_is_this_taxon(info_api, monkeypatch):
    api, _services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Fringilla coelebs"))
    monkeypatch.setattr(router, "_catalogue_names", lambda _scientific_name: frozenset())

    assert api.get("/api/species/Common Chaffinch/info").json()["extract"] is None


def test_a_redirect_is_followed_when_the_target_names_the_exact_taxon_as_its_subject(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    services.articles["house sparrow"] = {
        "type": "standard",
        "title": "English sparrow",
        "extract": "The English sparrow (Passer domesticus) is a bird of the sparrow family Passeridae.",
    }

    body = api.get("/api/species/House Sparrow/info").json()

    assert body["title"] == "English sparrow"
    assert body["extract"].startswith("The English sparrow (Passer domesticus)")


def test_a_language_with_no_article_gets_the_taxons_linked_article_rather_than_nothing(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Rhipidura leucophrys"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    wagtail = next(bird for bird in BIRDS if bird["species"] == "Willie Wagtail")

    body = api.get("/api/species/Willie Wagtail/info").json()

    assert body["extract"] == _shown(wagtail)
    assert body["summary_source_url"] == "https://en.wikipedia.org/wiki/Willie_wagtail"
    # Asked for by its language link and then by its own title: nothing was searched.
    assert not any("list=search" in url for url in services.requests)


@pytest.mark.asyncio
async def test_an_unchecked_row_is_looked_up_again_even_when_its_text_names_the_taxon(cached_api):
    api, services = cached_api
    await _forget("House Sparrow")
    async with get_db() as db:
        await SpeciesRepository(db).save_cached_info(
            species_name="House Sparrow",
            taxa_id=None,
            language="en",
            values=SpeciesInfo(
                title="Passer domesticus",
                extract="Passer domesticus is an old cached summary whose identity was never recorded.",
                source="Wikipedia",
                summary_source="Wikipedia",
                scientific_name="Passer domesticus",
                cached_at=datetime.now(),
            ).model_dump(),
            cached_at=datetime.now(),
        )

    body = api.get("/api/species/House Sparrow/info").json()

    assert services.requests, "a row whose identity was never recorded is looked up again"
    assert body["extract"].startswith("The house sparrow is a bird")
    router._wiki_cache.clear()
    services.requests.clear()
    assert api.get("/api/species/House Sparrow/info").json()["extract"] == body["extract"]
    assert services.requests == [], "the refreshed row carries its checked identity"
    await _forget("House Sparrow")


def _german(services: Services, source_title: str, local_title: str, extract: str, *, answers_as: str | None = None):
    """A German article reached from an English one by Wikipedia's language link."""
    services.other_languages[("de", source_title.casefold())] = local_title
    services.articles[f"de:{local_title.casefold()}"] = {
        "type": "standard",
        "title": answers_as or local_title,
        "lang": "de",
        "extract": extract,
        "content_urls": {
            "desktop": {"page": f"https://de.wikipedia.org/wiki/{(answers_as or local_title).replace(' ', '_')}"}
        },
    }


@pytest.mark.parametrize("by_scientific_name", [False, True], ids=["by bird name", "by scientific name"])
def test_a_language_link_is_not_trusted_from_a_source_article_that_redirected_to_another_taxon(
    info_api, monkeypatch, by_scientific_name
):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    # The sparrow's linked title has come to redirect to another sparrow, which has a German article.
    services.articles["house sparrow"] = {
        "type": "standard",
        "title": "Spanish sparrow",
        "extract": "The Spanish sparrow or willow sparrow is a passerine bird of the sparrow family Passeridae.",
    }
    _german(
        services,
        "House sparrow",
        "Weidensperling",
        "Der Weidensperling ist eine Vogelart aus der Familie der Sperlinge.",
    )
    _german(
        services,
        "Spanish sparrow",
        "Weidensperling",
        "Der Weidensperling ist eine Vogelart aus der Familie der Sperlinge.",
    )
    params = {"scientific_name": "Passer domesticus"} if by_scientific_name else {}

    body = api.get("/api/species/Haussperling/info", params=params).json()

    assert body["extract"] is None
    assert "Weidensperling" not in body["title"]
    if not by_scientific_name:
        assert not router._save_species_info.await_args.args[3].identity_checked
    # The language link was never asked for: the source article failed its identity first.
    assert not any("prop=langlinks" in url for url in services.requests)


def test_the_source_article_is_read_and_verified_before_its_language_link_is_followed(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Anas platyrhynchos"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    _german(services, "Mallard", "Stockente", "Die Stockente ist eine Vogelart aus der Familie der Entenvögel.")

    body = api.get("/api/species/Stockente/info").json()

    assert body["extract"].startswith("Die Stockente")
    wikipedia = [url for url in services.requests if (httpx.URL(url).host or "").endswith(".wikipedia.org")]
    assert wikipedia[0] == "https://en.wikipedia.org/api/rest_v1/page/summary/Mallard"
    assert "prop=langlinks" in wikipedia[1] and "titles=Mallard" in wikipedia[1]
    assert wikipedia[2] == "https://de.wikipedia.org/api/rest_v1/page/summary/Stockente"


def test_a_translated_title_that_redirects_to_another_taxon_falls_back_to_the_verified_source(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    sparrow = next(bird for bird in BIRDS if bird["species"] == "House Sparrow")
    # The German title answers as the genus article.
    _german(
        services,
        "House sparrow",
        "Haussperling",
        "Passer ist eine Gattung der Sperlinge.",
        answers_as="Passer (Gattung)",
    )

    body = api.get("/api/species/Haussperling/info").json()

    assert body["extract"] == _shown(sparrow)
    assert body["summary_source_url"] == "https://en.wikipedia.org/wiki/House_sparrow"
    assert body["summary_language"] == "en"


def test_a_translated_title_that_redirects_to_a_recorded_name_of_the_taxon_is_followed(info_api, monkeypatch):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Fringilla coelebs"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    _german(
        services,
        "Eurasian chaffinch",
        "Fink",
        "Der Buchfink ist eine Vogelart aus der Familie der Finken.",
        answers_as="Buchfink",
    )

    body = api.get("/api/species/Buchfink/info").json()

    assert body["title"] == "Buchfink"
    assert body["summary_language"] == "de"


@pytest.mark.parametrize("bird", BIRDS, ids=BIRD_IDS)
def test_the_response_says_which_language_the_description_is_in(info_api, monkeypatch, bird):
    api, _services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value=bird["scientific_name"]))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "fr")

    body = api.get(f"/api/species/{bird['species']}/info").json()

    # French was asked for and has no article in this fixture: the description is the English one, and says so.
    assert body["extract"] == _shown(bird)
    assert body["summary_language"] == "en"


def test_a_description_with_no_wikipedia_address_claims_no_language():
    assert SpeciesInfo(title="Robin", extract="A bird.", summary_source="iNaturalist").summary_language is None
    assert SpeciesInfo(title="Robin").summary_language is None
    german = SpeciesInfo(
        title="Rotkehlchen",
        extract="Ein Vogel.",
        summary_source="Wikipedia",
        summary_source_url="https://de.wikipedia.org/wiki/Rotkehlchen",
    )
    assert german.summary_language == "de"
    # The address is the evidence; a summary credited to Wikipedia with another address claims nothing.
    assert (
        SpeciesInfo(
            title="x", extract="y", summary_source="Wikipedia", summary_source_url="https://example.org/wiki/X"
        ).summary_language
        is None
    )


@pytest.mark.parametrize("by_scientific_name", [False, True], ids=["by bird name", "by scientific name"])
@pytest.mark.parametrize("stage", ["language_links_time_out", "translations_time_out"])
def test_a_translation_that_times_out_keeps_the_verified_source_article(
    info_api, monkeypatch, by_scientific_name, stage
):
    api, services = info_api
    monkeypatch.setattr(router, "_lookup_scientific_name", AsyncMock(return_value="Passer domesticus"))
    monkeypatch.setattr(router, "get_user_language", lambda _request: "de")
    sparrow = next(bird for bird in BIRDS if bird["species"] == "House Sparrow")
    _german(services, "House sparrow", "Haussperling", "Der Haussperling ist eine Vogelart.")
    setattr(services, stage, True)
    params = {"scientific_name": "Passer domesticus"} if by_scientific_name else {}

    body = api.get("/api/species/Haussperling/info", params=params).json()

    # The English article was read and verified before the translation was asked for: it is kept.
    assert body["extract"] == _shown(sparrow)
    assert body["summary_language"] == "en"
    assert body["summary_source_url"] == "https://en.wikipedia.org/wiki/House_sparrow"
    if not by_scientific_name:
        assert router._save_species_info.await_args.args[3].identity_checked
