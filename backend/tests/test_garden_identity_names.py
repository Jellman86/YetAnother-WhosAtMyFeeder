"""Garden records name an animal the way bird records name a bird: cased, scientific, in the reader's language."""

import json
import sqlite3
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models.garden import GardenIdentification
from app.repositories.garden_repository import GardenRepository
from app.services.species_catalog_migrations import upgrade_catalog
from app.services.species_names import SpeciesNameLookup, vernacular_case


@pytest.mark.parametrize(
    "name,expected",
    [
        ("domestic dog", "Domestic Dog"),
        ("white-tailed deer", "White-tailed Deer"),
        ("eurasian red squirrel", "Eurasian Red Squirrel"),
        ("eastern grey kangaroo", "Eastern Grey Kangaroo"),
        ("island fox of the channel", "Island Fox of the Channel"),
        ("Our fox", "Our fox"),
        ("European Hedgehog", "European Hedgehog"),
    ],
)
def test_lowercase_model_names_read_like_catalogue_names_and_cased_names_are_left_alone(name, expected):
    assert vernacular_case(name) == expected


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "catalog.db"
    upgrade_catalog(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (501,'species','accepted')")
        db.execute(
            "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) "
            "VALUES (501,'google-speciesnet','dog','4.0.3','Canis familiaris')"
        )
        db.executemany(
            "INSERT INTO species_names(species_id,language_tag,name,name_kind,preferred,provider,source_release) "
            "VALUES (501,?,?,'vernacular',0,'test','1')",
            [("en", "domestic dog"), ("de", "Haushund")],
        )
    return SpeciesNameLookup(path)


def test_lookup_resolves_the_display_and_scientific_name_together(catalogue):
    names = catalogue.resolve([501, 999], language="de")
    assert names[501].display == "Haushund"
    assert names[501].scientific == "Canis familiaris"
    assert 999 not in names
    assert catalogue.display_names([501], language="en") == {501: "domestic dog"}


@pytest_asyncio.fixture
async def history(monkeypatch, catalogue):
    import app.routers.garden as garden_router

    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(garden_router, "species_name_lookup", catalogue)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
        yield GardenRepository(db)
    await close_db()


def _named_dog() -> GardenIdentification:
    return GardenIdentification(
        outcome="suggestion",
        reason="garden",
        review="accepted",
        automatic=True,
        species_id=501,
        name="domestic dog",
        rank="species",
        score=0.94,
        country="GBR",
        variant="4.0.3a",
        provider="cpu",
        devices=["CPU"],
        model_sha256="a" * 64,
        package_sha256="b" * 64,
        image_sha256="c" * 64,
        output_index=0,
        input_kind="tracked_crop",
        frame_size=(640, 480),
        identified_at="2026-10-24T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_capture_names_follow_the_reader_language_with_scientific_name(history):
    at = datetime(2026, 10, 24, tzinfo=timezone.utc).replace(tzinfo=None).isoformat()
    await history.capture("dog-event", "patio", "dog", at, True)
    await history.db.execute("UPDATE garden_captures SET status='confirmed' WHERE frigate_event='dog-event'")
    await history.db.execute(
        "INSERT INTO garden_identifications(capture_id,result_json) SELECT id,? FROM garden_captures WHERE frigate_event=?",
        (json.dumps(_named_dog().model_dump()), "dog-event"),
    )
    await history.db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        english = (await client.get("/api/garden/visits")).json()["visits"][0]["representative"]
        german = (await client.get("/api/garden/visits", headers={"Accept-Language": "de-DE"})).json()
        captures = (await client.get(f"/api/garden/visits/{english['id']}/captures")).json()
    assert english["identification"]["name"] == "Domestic Dog"
    assert english["scientific_name"] == "Canis familiaris"
    assert german["visits"][0]["representative"]["identification"]["name"] == "Haushund"
    assert captures["items"][0]["scientific_name"] == "Canis familiaris"


@pytest.mark.asyncio
async def test_unnamed_capture_claims_no_scientific_name(history):
    at = datetime(2026, 10, 24, tzinfo=timezone.utc).replace(tzinfo=None).isoformat()
    await history.capture("cat-event", "patio", "cat", at, True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        item = (await client.get("/api/garden/timeline")).json()["items"][0]
    assert item["scientific_name"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("clips_enabled", [True, False])
async def test_a_frigate_capture_offers_its_clip_only_while_clips_are_enabled(history, monkeypatch, clips_enabled):
    monkeypatch.setattr(settings.frigate, "clips_enabled", clips_enabled)
    at = datetime(2026, 10, 24, tzinfo=timezone.utc).replace(tzinfo=None).isoformat()
    await history.capture("1729000000.123-dog", "patio", "dog", at, True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        item = (await client.get("/api/garden/timeline")).json()["items"][0]
    assert item["clip_event"] == ("1729000000.123-dog" if clips_enabled else None)
