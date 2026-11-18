"""A label saved under a translated common name resolves to its species without asking iNaturalist."""

import os
import sqlite3
from contextlib import closing

from unittest.mock import AsyncMock, patch

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app
from app.repositories.species_repository import SpeciesRepository


@pytest_asyncio.fixture
async def repository(tmp_path):
    path = tmp_path / "species.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.execute("DELETE FROM taxonomy_translations")
        target.execute("DELETE FROM taxonomy_cache")
        target.commit()
    async with aiosqlite.connect(path) as db:
        await db.executemany(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            [("Parus major", "Great Tit", 145252), ("Cyanistes caeruleus", "Blue Tit", 144849)],
        )
        await db.executemany(
            "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            [(145252, "ru", "Большая синица"), (145252, "de", "Kohlmeise"), (144849, "ru", "Обыкновенная лазоревка")],
        )
        await db.commit()
        yield SpeciesRepository(db)


@pytest.mark.asyncio
async def test_a_translated_name_resolves_in_its_own_language(repository):
    assert await repository.lookup_taxonomy("Большая синица", "ru") == ("Parus major", "Большая синица", 145252)


@pytest.mark.asyncio
async def test_a_translated_name_resolves_for_a_reader_in_another_language(repository):
    assert await repository.lookup_taxonomy("Большая синица", "en") == ("Parus major", "Great Tit", 145252)
    assert await repository.lookup_taxonomy("Kohlmeise", "ru") == ("Parus major", "Большая синица", 145252)


@pytest.mark.asyncio
async def test_a_name_two_species_share_in_one_language_is_not_guessed(repository):
    await repository.db.execute(
        "UPDATE taxonomy_translations SET common_name = 'Синица' WHERE language_code = 'ru'",
    )
    assert await repository.lookup_taxonomy("Синица", "ru") is None


@pytest.mark.asyncio
async def test_the_readers_language_settles_a_name_other_languages_use_for_another_species(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (144849, 'de', 'Большая синица')"
    )
    assert await repository.lookup_taxonomy("Большая синица", "ru") == ("Parus major", "Большая синица", 145252)
    assert await repository.lookup_taxonomy("Большая синица", "en") is None


@pytest.mark.asyncio
async def test_the_cached_names_still_win_and_unknown_names_stay_unknown(repository):
    assert await repository.lookup_taxonomy("great tit", "ru") == ("Parus major", "Большая синица", 145252)
    assert await repository.lookup_taxonomy("Parus major", "en") == ("Parus major", "Great Tit", 145252)
    assert await repository.lookup_taxonomy("Pica pica", "ru") is None


@pytest.mark.asyncio
async def test_a_scientific_name_in_the_label_beats_a_translation_of_its_local_half(repository):
    """ "Probmes (Probus caeruleus)" stays Probus caeruleus though "Probmes" means Probus major in Swedish."""
    await repository.db.executemany(
        "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
        [("Probus major", "Great Prob", 990001), ("Probus caeruleus", "Blue Prob", 990002)],
    )
    await repository.db.execute(
        "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (990001, 'sv', 'Probmes')"
    )
    names = ["Probmes (Probus caeruleus)", "Probmes", "Probus caeruleus"]
    assert await repository.lookup_taxonomy_for_names(names, "en") == ("Probus caeruleus", "Blue Prob", 990002)


@pytest.mark.asyncio
async def test_a_not_found_placeholder_does_not_hide_a_known_translation(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found) VALUES ('Kohlmeise', NULL, NULL, 1)"
    )
    assert await repository.lookup_taxonomy("Kohlmeise", "en") == ("Parus major", "Great Tit", 145252)


@pytest.mark.asyncio
async def test_a_not_found_placeholder_is_still_the_answer_when_nothing_else_knows_the_name(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found) VALUES ('Unknownus', NULL, NULL, 1)"
    )
    assert await repository.lookup_taxonomy("Unknownus", "en") == ("Unknownus", None, None)


@pytest.mark.asyncio
async def test_a_translation_whose_species_is_no_longer_cached_is_not_used(repository):
    await repository.db.execute(
        "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (990009, 'ru', 'Призрак')"
    )
    assert await repository.lookup_taxonomy("Призрак", "ru") is None


@pytest.mark.asyncio
async def test_a_translated_name_matches_ascii_case_and_keeps_the_owners_own_name(repository):
    assert await repository.lookup_taxonomy("kohlmeise", "en") == ("Parus major", "Great Tit", 145252)
    await repository.db.execute("UPDATE taxonomy_cache SET manual_common_name = 'Big Tit' WHERE taxa_id = 145252")
    assert await repository.lookup_taxonomy("Большая синица", "ru") == ("Parus major", "Big Tit", 145252)


SEARCH_TAXA = ((991001, "Probus searchus", "Search Prob", "Поисковая проба"),)


@pytest.fixture
def cached_search_species():
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as db:
        for taxa_id, scientific, common, russian in SEARCH_TAXA:
            db.execute(
                "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
                (scientific, common, taxa_id),
            )
            db.execute(
                "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, 'ru', ?)",
                (taxa_id, russian),
            )
        db.commit()
    try:
        yield
    finally:
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as db:
            for taxa_id, *_ in SEARCH_TAXA:
                db.execute("DELETE FROM taxonomy_translations WHERE taxa_id = ?", (taxa_id,))
                db.execute("DELETE FROM taxonomy_cache WHERE taxa_id = ?", (taxa_id,))
            db.commit()


@pytest.mark.asyncio
@pytest.mark.usefixtures("cached_search_species")
@pytest.mark.parametrize("hydrate", ["false", "true"])
async def test_species_search_offers_a_stored_translated_label_once_without_asking_inaturalist(hydrate):
    """Bulk reclassify and the species check skip hydration; neither may see the bird twice."""
    original = (settings.auth.enabled, settings.public_access.enabled)
    settings.auth.enabled = False
    settings.public_access.enabled = False
    get_names = AsyncMock(return_value=None)
    try:
        with (
            patch("app.routers.species.get_classifier", return_value=type("C", (), {"labels": ["Probus searchus"]})()),
            patch(
                "app.repositories.species_repository.SpeciesRepository.most_detected_labels",
                new=AsyncMock(return_value=["Поисковая проба"]),
            ),
            patch("app.routers.species.taxonomy_service.get_names", new=get_names),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    f"/api/species/search?q=&limit=20&hydrate_missing={hydrate}",
                    headers={"Accept-Language": "ru"},
                )
    finally:
        settings.auth.enabled, settings.public_access.enabled = original

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "id": "Probus searchus",
            "display_name": "Probus searchus",
            "scientific_name": "Probus searchus",
            "common_name": "Поисковая проба",
            "taxa_id": 991001,
        }
    ]
    get_names.assert_not_awaited()


@pytest.mark.asyncio
async def test_species_search_keeps_a_labels_scientific_name_over_a_translation_of_its_local_half(repository):
    from app.routers.species import _lookup_species_search_taxonomy

    await repository.db.executemany(
        "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
        [("Probus major", "Great Prob", 990001), ("Probus caeruleus", "Blue Prob", 990002)],
    )
    await repository.db.execute(
        "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (990001, 'sv', 'Probmes')"
    )

    cached = await _lookup_species_search_taxonomy(repository.db, label="Probmes (Probus caeruleus)", lang="en")
    uncached = await _lookup_species_search_taxonomy(repository.db, label="Probmes (Probus novus)", lang="en")

    assert cached == ("Probus caeruleus", "Blue Prob", 990002)
    # The label names its own species; a translation meaning another one does not overrule it.
    assert uncached[0] == "Probus novus" and uncached[2] is None


@pytest.mark.asyncio
async def test_a_common_name_that_looks_scientific_still_resolves_as_a_translation(repository):
    """Polish "Sikora bogatka" fits the Genus-species pattern but is the name being translated."""
    await repository.db.execute(
        "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (145252, 'pl', 'Sikora bogatka')"
    )
    from app.routers.species import _lookup_species_search_taxonomy

    assert await repository.lookup_taxonomy("Sikora bogatka", "pl") == ("Parus major", "Sikora bogatka", 145252)
    assert await _lookup_species_search_taxonomy(repository.db, label="Sikora bogatka (Parus major)", lang="en") == (
        "Parus major",
        "Great Tit",
        145252,
    )
