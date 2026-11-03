"""The Explorer's one search box: what was seen here, the cameras aside, and a record by its id.

Species and the genus, family and order above them come from the species catalogue, but only
where something beneath them was seen in the reader's window. A record pasted by id opens only
when the reader could already see it: a visitor never learns that a hidden or private record
exists. A chosen group of species filters the Explorer's reads through ``taxon``.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, AuthLevel, get_auth_context_with_legacy
from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models.garden import GardenIdentification
from app.routers import explorer
from app.services import explorer_search
from app.services.species_names import SpeciesNameLookup
from app.services.taxonomy_tree import TaxonomyTree
from tests.test_taxonomy_classification import _col_concepts, _id, _manifest, _reference, seed_builder


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    path = tmp_path / "species_catalog.db"
    seed_builder.build(
        _reference(tmp_path), path, manifest_path=_manifest(tmp_path), col_concepts_path=_col_concepts(tmp_path)
    )
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO species_names (species_id, language_tag, name, name_kind, preferred, provider, source_release)"
        " VALUES (?, 'fr', 'Mésange charbonnière', 'vernacular', 1, 'test', '1')",
        (_id(path, "Parus major"),),
    )
    connection.commit()
    connection.close()
    tree = TaxonomyTree(path)
    monkeypatch.setattr(explorer_search, "taxonomy_tree", tree)
    return path


def as_owner() -> AuthContext:
    return AuthContext(auth_level=AuthLevel.OWNER)


def as_guest() -> AuthContext:
    return AuthContext(auth_level=AuthLevel.GUEST)


@pytest.fixture
def reader():
    """Who is asking; the owner unless a test says otherwise."""
    current = {"auth": as_owner()}
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: current["auth"]
    yield current
    app.dependency_overrides.pop(get_auth_context_with_legacy, None)


@pytest_asyncio.fixture(autouse=True)
async def database(monkeypatch):
    monkeypatch.setattr("app.services.frigate_client.frigate_client.get_event", AsyncMock(return_value=None))
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "show_camera_names", True)
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM garden_owner_identifications")
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield
    await close_db()


RECENT = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
OLD = RECENT - timedelta(days=30)


async def add_detection(event: str, scientific: str, species_id: int, *, at: datetime = RECENT, hidden: bool = False):
    async with get_db() as db:
        await db.execute(
            "INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,"
            " display_name, category_name, scientific_name, species_id, is_hidden)"
            " VALUES (?, 'birdcam', ?, 1, 0.9, ?, ?, ?, ?, ?)",
            (event, at.isoformat(sep=" "), scientific, scientific, scientific, species_id, int(hidden)),
        )
        await db.commit()


async def add_garden(capture_id: str, species_id: int | None, status: str, *, at: datetime = RECENT) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO garden_captures (id, event_key, frigate_event, camera, label, observed_at, status, has_snapshot)"
            " VALUES (?, ?, ?, 'patio', 'bird', ?, ?, 1)",
            (capture_id, capture_id, f"{capture_id[:6]}.1-abc", at.isoformat(), status),
        )
        if species_id is not None:
            await db.execute(
                "INSERT INTO garden_owner_identifications (capture_id, species_id, name, scientific_name, changed_at)"
                " VALUES (?, ?, 'Wood Pigeon', 'Columba palumbus', ?)",
                (capture_id, species_id, at.isoformat() + "Z"),
            )
        await db.commit()


async def seed_birds(catalogue) -> None:
    await add_detection("1793624285.74056-6j3htl", "Prunella modularis", _id(catalogue, "Prunella modularis"))
    await add_detection("1793624290.10000-aaaaaa", "Prunella modularis", _id(catalogue, "Prunella modularis"))
    await add_detection("1793624300.20000-bbbbbb", "Parus major", _id(catalogue, "Parus major"))


async def get(path: str, **params) -> httpx.Response:
    headers = {"Accept-Language": params.pop("lang", "en")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, params=params, headers=headers)


async def search(q: str, **params) -> dict:
    response = await get("/api/explorer/search", q=q, **params)
    assert response.status_code == 200, response.text
    return response.json()


def names(result: dict) -> list[tuple[str, str]]:
    return [(taxon["rank"], taxon["scientific_name"]) for taxon in result["taxa"]]


@pytest.mark.asyncio
async def test_a_common_name_finds_the_species_seen_here_with_its_count(catalogue, reader):
    await seed_birds(catalogue)
    result = await search("dunnock")
    assert names(result) == [("species", "Prunella modularis")]
    dunnock = result["taxa"][0]
    assert dunnock["name"] == "Dunnock"
    assert (dunnock["bird_species"], dunnock["bird_detections"]) == (1, 2)
    assert (dunnock["garden_species"], dunnock["garden_captures"]) == (0, 0)


@pytest.mark.asyncio
async def test_matching_is_case_and_accent_insensitive_in_the_readers_language_and_english(catalogue, reader):
    await seed_birds(catalogue)
    french = await search("MESANGE charbon", lang="fr")
    assert names(french) == [("species", "Parus major")]
    assert french["taxa"][0]["name"] == "Mésange charbonnière"
    # English still finds it for a French reader.
    assert names(await search("great tit", lang="fr")) == [("species", "Parus major")]


@pytest.mark.asyncio
async def test_a_scientific_name_finds_its_species(catalogue, reader):
    await seed_birds(catalogue)
    assert names(await search("parus maj")) == [("species", "Parus major")]


@pytest.mark.asyncio
async def test_a_family_genus_or_order_is_offered_with_what_was_seen_beneath_it(catalogue, reader):
    await seed_birds(catalogue)
    family = (await search("Accentors"))["taxa"]
    assert [(t["rank"], t["scientific_name"]) for t in family] == [("family", "Prunellidae")]
    assert (family[0]["bird_species"], family[0]["bird_detections"]) == (1, 2)
    assert ("genus", "Prunella") in names(await search("prunella"))
    order = (await search("passeriformes"))["taxa"]
    assert [(t["rank"], t["bird_species"], t["bird_detections"]) for t in order] == [("order", 2, 3)]


@pytest.mark.asyncio
async def test_only_what_was_seen_here_is_offered(catalogue, reader):
    await seed_birds(catalogue)
    # The Alpine Accentor and every pigeon are in the catalogue but were never seen here.
    assert (await search("alpine"))["taxa"] == []
    assert (await search("pigeon"))["taxa"] == []
    # Ranks above order are not offered: they would match nearly everything.
    assert (await search("aves"))["taxa"] == []


@pytest.mark.asyncio
async def test_hidden_detections_do_not_make_a_species_findable(catalogue, reader):
    await add_detection("1793624400.1-hidden", "Columba palumbus", _id(catalogue, "Columba palumbus"), hidden=True)
    assert (await search("pigeon"))["taxa"] == []


@pytest.mark.asyncio
async def test_garden_animals_are_found_while_garden_is_on_and_counted_apart_from_birds(catalogue, reader, monkeypatch):
    await add_garden("a" * 32, _id(catalogue, "Columba palumbus"), "confirmed")
    pigeon = (await search("wood pigeon"))["taxa"]
    assert [
        (t["scientific_name"], t["garden_species"], t["garden_captures"], t["bird_detections"]) for t in pigeon
    ] == [("Columba palumbus", 1, 1, 0)]
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    assert (await search("wood pigeon"))["taxa"] == []


@pytest.mark.asyncio
async def test_a_visitor_finds_only_confirmed_garden_animals_inside_the_public_window(catalogue, reader):
    await add_garden("b" * 32, _id(catalogue, "Columba palumbus"), "pending")
    await add_garden("c" * 32, _id(catalogue, "Columba palumbus"), "confirmed", at=OLD)
    reader["auth"] = as_guest()
    assert (await search("wood pigeon"))["taxa"] == []
    reader["auth"] = as_owner()
    assert [t["garden_captures"] for t in (await search("wood pigeon"))["taxa"]] == [2]


@pytest.mark.asyncio
async def test_a_visitor_counts_only_detections_inside_the_public_window(catalogue, reader):
    await seed_birds(catalogue)
    await add_detection("1700000000.1-oldold", "Prunella modularis", _id(catalogue, "Prunella modularis"), at=OLD)
    reader["auth"] = as_guest()
    assert [t["bird_detections"] for t in (await search("dunnock"))["taxa"]] == [2]
    reader["auth"] = as_owner()
    assert [t["bird_detections"] for t in (await search("dunnock"))["taxa"]] == [3]


@pytest.mark.asyncio
async def test_a_frigate_event_id_finds_its_record(catalogue, reader):
    await seed_birds(catalogue)
    record = (await search("1793624285.74056-6j3htl"))["record"]
    assert record["kind"] == "detection" and record["id"] == "1793624285.74056-6j3htl"
    assert record["scientific_name"] == "Prunella modularis"
    assert (await search("1793624285.74056-zzzzzz"))["record"] is None


@pytest.mark.asyncio
async def test_a_hidden_record_is_found_by_the_owner_and_never_by_a_visitor(catalogue, reader):
    await add_detection("1793624500.1-secret", "Parus major", _id(catalogue, "Parus major"), hidden=True)
    owner = (await search("1793624500.1-secret"))["record"]
    assert owner is not None and owner["hidden"] is True
    reader["auth"] = as_guest()
    assert (await search("1793624500.1-secret"))["record"] is None


@pytest.mark.asyncio
async def test_a_visitor_cannot_find_a_record_older_than_the_public_window(catalogue, reader):
    await add_detection("1700000000.2-oldold", "Parus major", _id(catalogue, "Parus major"), at=OLD)
    reader["auth"] = as_guest()
    assert (await search("1700000000.2-oldold"))["record"] is None


@pytest.mark.asyncio
async def test_a_garden_capture_id_finds_a_record_a_visitor_only_when_confirmed(catalogue, reader):
    await add_garden("d" * 32, None, "pending")
    await add_garden("e" * 32, None, "confirmed")
    assert (await search("d" * 32))["record"] == {
        "kind": "garden",
        "id": "d" * 32,
        "observed_at": RECENT.isoformat() + "Z",
        "display_name": None,
        "scientific_name": None,
        "common_name": None,
        "camera": "patio",
        "hidden": False,
    }
    reader["auth"] = as_guest()
    assert (await search("d" * 32))["record"] is None
    assert (await search("e" * 32))["record"]["kind"] == "garden"


@pytest.mark.asyncio
async def test_a_garden_capture_is_not_found_while_garden_is_off(catalogue, reader, monkeypatch):
    await add_garden("f" * 32, None, "confirmed")
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    assert (await search("f" * 32))["record"] is None


@pytest.mark.asyncio
async def test_a_visitor_never_sees_a_camera_name_the_owner_hides(catalogue, reader, monkeypatch):
    await seed_birds(catalogue)
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    reader["auth"] = as_guest()
    assert (await search("1793624285.74056-6j3htl"))["record"]["camera"] is None


@pytest.mark.asyncio
async def test_the_query_and_limit_are_bounded(catalogue, reader):
    assert (await get("/api/explorer/search", q="")).status_code == 422
    assert (await get("/api/explorer/search", q="x" * 101)).status_code == 422
    assert (await get("/api/explorer/search", q="tit", limit=21)).status_code == 422
    assert (await get("/api/explorer/search", q="tit", limit=0)).status_code == 422
    assert (await get("/api/explorer/search", q="bad\x00text")).status_code == 422


@pytest.mark.asyncio
async def test_results_are_capped_and_say_when_more_matched(catalogue, reader):
    await seed_birds(catalogue)
    # "p" begins Prunella modularis, Prunella, Prunellidae, Parus major, Paridae, Parus and Passeriformes.
    capped = await search("p", limit=3)
    assert len(capped["taxa"]) == 3 and capped["truncated"] is True
    assert (await search("p", limit=20))["truncated"] is False


@pytest.mark.asyncio
async def test_a_taxon_filter_narrows_bird_reads_to_the_species_seen_beneath_it(catalogue, reader):
    await seed_birds(catalogue)
    family = _id(catalogue, "Prunellidae")
    events = (await get("/api/events", taxon=family)).json()
    assert sorted(event["frigate_event"] for event in events) == [
        "1793624285.74056-6j3htl",
        "1793624290.10000-aaaaaa",
    ]
    assert (await get("/api/events/count", taxon=family)).json()["count"] == 2
    visits = (await get("/api/visits", taxon=family)).json()
    assert {visit["representative"]["scientific_name"] for visit in visits["visits"]} == {"Prunella modularis"}
    # A taxon with nothing seen beneath it narrows to nothing rather than being ignored.
    assert (await get("/api/events", taxon=_id(catalogue, "Columbidae"))).json() == []
    # A stale history identity cannot make a missing catalogue taxon valid.
    await add_detection("1793624400.1-orphan", "Unmapped species", 999_999)
    assert (await get("/api/events/count", taxon=999_999)).json()["count"] == 0
    assert (await get("/api/events/count", taxon=2**100)).json()["count"] == 0


@pytest.mark.asyncio
async def test_a_taxon_filter_narrows_garden_reads_too(catalogue, reader):
    await add_garden("1" * 32, _id(catalogue, "Columba palumbus"), "confirmed")
    await add_garden("2" * 32, None, "confirmed")
    page = (await get("/api/garden/visits", taxon=_id(catalogue, "Columbidae"))).json()
    assert [visit["representative"]["id"] for visit in page["visits"]] == ["1" * 32]
    timeline = (await get("/api/garden/timeline", taxon=_id(catalogue, "Columba palumbus"))).json()
    assert [item["id"] for item in timeline["items"]] == ["1" * 32]
    assert (await get("/api/garden/visits", taxon=_id(catalogue, "Paridae"))).json()["total"] == 0


@pytest.mark.asyncio
async def test_search_stops_serving_a_guest_when_public_access_is_switched_off(catalogue, reader, monkeypatch):
    await seed_birds(catalogue)
    reader["auth"] = as_guest()
    monkeypatch.setattr(settings.public_access, "enabled", False)
    response = await get("/api/explorer/search", q="dunnock")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_results_cannot_be_cached_for_another_reader(catalogue, reader):
    response = await get("/api/explorer/search", q="dunnock")
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "private, no-store"


@pytest.mark.asyncio
async def test_a_blank_query_is_rejected_before_reading_history(catalogue, reader):
    assert (await get("/api/explorer/search", q="   ")).status_code == 422


@pytest.mark.asyncio
async def test_an_automatically_named_garden_record_has_its_scientific_and_localized_names(
    catalogue, reader, monkeypatch
):
    capture_id = "9" * 32
    await add_garden(capture_id, None, "confirmed")
    identification = GardenIdentification(
        outcome="suggestion",
        reason="garden",
        review="accepted",
        automatic=True,
        species_id=_id(catalogue, "Parus major"),
        name="great tit",
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
        identified_at=RECENT.isoformat() + "Z",
    )
    async with get_db() as db:
        await db.execute(
            "INSERT INTO garden_identifications(capture_id, result_json) VALUES (?, ?)",
            (capture_id, identification.model_dump_json()),
        )
        await db.commit()
    monkeypatch.setattr(explorer, "species_name_lookup", SpeciesNameLookup(catalogue))
    reader["auth"] = as_guest()
    result = await search(capture_id, lang="fr")
    assert result["record"]["scientific_name"] == "Parus major"
    assert result["record"]["display_name"] == "Mésange charbonnière"
