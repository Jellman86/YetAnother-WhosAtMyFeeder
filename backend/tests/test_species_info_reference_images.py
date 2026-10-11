from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models import SpeciesInfo


@pytest.mark.parametrize("host", ["upload.wikimedia.org", "thumb.wikimedia.org"])
@pytest.mark.parametrize("extension", ["jpg", "jpeg", "png"])
def test_original_reference_photos_use_a_bounded_standard_thumbnail(host, extension):
    filename = f"Blue_tit_%28bird%29.{extension}"
    url = f"https://{host}/wikipedia/commons/a/ab/{filename}?utm_source=wikipedia"
    info = SpeciesInfo(title="Blue Tit", thumbnail_url=url)
    assert info.thumbnail_url == (
        f"https://{host}/wikipedia/commons/thumb/a/ab/{filename}/960px-{filename}?utm_source=wikipedia"
    )


@pytest.mark.parametrize("host", ["upload.wikimedia.org", "thumb.wikimedia.org"])
def test_oversized_cached_reference_thumbnails_are_bounded_without_refresh(host):
    url = f"https://{host}/wikipedia/commons/thumb/a/ab/Bird.jpg/3840px-Bird.jpg"
    info = SpeciesInfo.model_validate({"title": "Bird", "thumbnail_url": url, "source": "Wikipedia"})
    assert info.thumbnail_url == url.replace("3840px-", "960px-")
    assert info.source == "Wikipedia"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Bird.jpg/330px-Bird.jpg",
        "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
        "/api/about/showcase/event.jpg",
        "https://example.com/wikipedia/commons/a/ab/Bird.jpg",
        "https://upload.wikimedia.org.evil.example/wikipedia/commons/a/ab/Bird.jpg",
        "https://upload.wikimedia.org@evil.example/wikipedia/commons/a/ab/Bird.jpg",
        "https://user:pass@upload.wikimedia.org/wikipedia/commons/a/ab/Bird.jpg",
        "https://upload.wikimedia.org:8443/wikipedia/commons/a/ab/Bird.jpg",
        "http://upload.wikimedia.org/wikipedia/commons/a/ab/Bird.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Bird.svg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Bird.gif",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Bird.svg/3840px-Bird.svg.png",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Bird%2Fother.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Bird.jpg/anything",
        "https://[invalid",
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Bird.jpg/" + "9" * 4500 + "px-Bird.jpg",
    ],
)
def test_small_or_unrecognised_reference_urls_are_preserved(url):
    assert SpeciesInfo(title="Bird", thumbnail_url=url).thumbnail_url == url


def test_normalisation_is_idempotent_and_preserves_species_content():
    info = SpeciesInfo(
        title="Bird",
        thumbnail_url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Bird.jpg",
        extract="Species facts",
        taxa_id=42,
    )
    normalised = info.model_dump()
    assert SpeciesInfo.model_validate(normalised).model_dump() == normalised
    assert normalised["extract"] == "Species facts"
    assert normalised["taxa_id"] == 42


@pytest.mark.asyncio
async def test_cached_reference_photo_is_bounded_without_writing_or_refreshing(monkeypatch):
    from app.routers import species as router

    now = datetime.now()
    row = (
        "Blue Tit",
        "Small bird",
        "Species facts",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Bird.jpg",
        "https://en.wikipedia.org/wiki/Blue_tit",
        "Wikipedia",
        None,
        "Wikipedia",
        None,
        "Cyanistes caeruleus",
        "LC",
        now.isoformat(),
        42,
    )
    repository = AsyncMock()
    repository.get_cached_info.return_value = row

    @asynccontextmanager
    async def database():
        yield object()

    monkeypatch.setattr(router, "_wiki_cache", {})
    monkeypatch.setattr(router, "get_db", database)
    monkeypatch.setattr(router, "SpeciesRepository", lambda db: repository)
    info = await router._get_cached_species_info("Blue Tit", 42, "en", False)
    assert info is not None
    assert info.thumbnail_url.endswith("/960px-Bird.jpg")
    assert info.extract == row[2]
    assert info.cached_at == now
    repository.save_cached_info.assert_not_called()
    assert await router._get_cached_species_info("Blue Tit", 42, "en", False) is info
    repository.get_cached_info.assert_awaited_once()


@pytest.mark.asyncio
async def test_wikipedia_thumbnail_fallback_preserves_the_provider_rendition():
    from app.routers.species import _get_wikipedia_summary

    source = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Bird.jpg/330px-Bird.jpg"

    def summary(request):
        return httpx.Response(200, json={"title": "Blue Tit", "thumbnail": {"source": source}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(summary)) as client:
        info = await _get_wikipedia_summary(client, "Blue tit", "Blue Tit", "en")
    assert info is not None
    assert info.thumbnail_url == source
