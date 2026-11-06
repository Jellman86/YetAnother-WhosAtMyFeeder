"""The family tree as this feeder's own: visits, photographs, calls and the scientific record.

Each species states its visits, first and last seen, BirdNET calls and this install's newest
stored crop; each group rolls those up over the species seen beneath it. Confirmed Garden
visits count, unconfirmed ones never do. A visitor reads the shared window only and gets a
photograph or a call count only where the owner shares that medium. The catalogue lives in its
own database, so history and catalogue meet only through the opaque ``species_id``.
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
from app.routers import taxonomy as taxonomy_router
from app.services import taxon_facts
from app.services.taxonomy_tree import TaxonomyTree
from tests.test_taxonomy_classification import _col_concepts, _id, _manifest, _reference, seed_builder

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
RECENT = NOW - timedelta(hours=3)
OLD = NOW - timedelta(days=30)
CROP = "high_quality_bird_crop"
WHOLE_SCENE = "high_quality_snapshot"


def add_taxon(path, rank: str, scientific: str, parent: int, *, name: str | None = None) -> int:
    connection = sqlite3.connect(path)
    try:
        taxon_id = connection.execute("SELECT MAX(species_id) + 1 FROM species").fetchone()[0]
        connection.execute(
            "INSERT INTO species (species_id, rank, status, parent_species_id, sequence) VALUES (?, ?, 'accepted', ?, 1)",
            (taxon_id, rank, parent),
        )
        connection.execute(
            "INSERT INTO species_concepts (species_id, provider, provider_taxon_id, source_release, scientific_name)"
            " VALUES (?, 'google-speciesnet', ?, '1', ?)",
            (taxon_id, scientific, scientific),
        )
        if name:
            connection.execute(
                "INSERT INTO species_names (species_id, language_tag, name, name_kind, preferred, provider, source_release)"
                " VALUES (?, 'en', ?, 'vernacular', 0, 'google-speciesnet', '1')",
                (taxon_id, name),
            )
        connection.commit()
        return int(taxon_id)
    finally:
        connection.close()


def set_authorship(path, scientific: str, authorship: str) -> None:
    connection = sqlite3.connect(path)
    connection.execute("UPDATE species_concepts SET authorship = ? WHERE scientific_name = ?", (authorship, scientific))
    connection.commit()
    connection.close()


def add_name(path, scientific: str, language: str, name: str, preferred: bool) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO species_names (species_id, language_tag, name, name_kind, preferred, provider, source_release)"
        " VALUES (?, ?, ?, 'vernacular', ?, 'test', '1')",
        (_id(path, scientific), language, name, int(preferred)),
    )
    connection.commit()
    connection.close()


@pytest.fixture
def catalogue(tmp_path, monkeypatch):
    path = tmp_path / "species_catalog.db"
    seed_builder.build(
        _reference(tmp_path), path, manifest_path=_manifest(tmp_path), col_concepts_path=_col_concepts(tmp_path)
    )
    mammals = add_taxon(path, "class", "Mammalia", _id(path, "Chordata"))
    carnivores = add_taxon(path, "order", "Carnivora", mammals)
    dogs = add_taxon(path, "family", "Canidae", carnivores, name="dog family")
    foxes = add_taxon(path, "genus", "Vulpes", dogs)
    add_taxon(path, "species", "Vulpes vulpes", foxes, name="red fox")
    tree = TaxonomyTree(path)
    monkeypatch.setattr(taxonomy_router, "taxonomy_tree", tree)
    monkeypatch.setattr(taxon_facts, "taxonomy_tree", tree)
    return path


@pytest.fixture
def reader():
    current = {"auth": AuthContext(auth_level=AuthLevel.OWNER)}
    app.dependency_overrides[get_auth_context_with_legacy] = lambda: current["auth"]
    yield current
    app.dependency_overrides.pop(get_auth_context_with_legacy, None)


def as_guest(reader) -> None:
    reader["auth"] = AuthContext(auth_level=AuthLevel.GUEST)


@pytest.fixture
def snapshots(monkeypatch):
    """The stored photograph's provenance per event: a crop, a whole scene, or nothing stored."""
    sources: dict[str, str] = {}

    async def metadata(event_id: str):
        return {"source": sources[event_id]} if event_id in sources else None

    monkeypatch.setattr(taxon_facts.media_cache, "get_snapshot_metadata", AsyncMock(side_effect=metadata))
    return sources


@pytest_asyncio.fixture(autouse=True)
async def database(monkeypatch):
    monkeypatch.setattr("app.services.frigate_client.frigate_client.get_event", AsyncMock(return_value=None))
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "media_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "media_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "show_snapshots", True)
    monkeypatch.setattr(settings.public_access, "show_audio", True)
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    taxon_facts.taxon_facts_service.clear()
    await init_db()
    async with get_db() as db:
        for table in (
            "detections",
            "audio_detections",
            "garden_saved_crops",
            "garden_owner_identifications",
            "garden_captures",
        ):
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
    yield
    taxon_facts.taxon_facts_service.clear()
    await close_db()


async def add_detection(event: str, species_id: int, at: datetime, *, hidden: bool = False, name: str = "Bird"):
    async with get_db() as db:
        await db.execute(
            "INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,"
            " display_name, category_name, scientific_name, species_id, is_hidden)"
            " VALUES (?, 'birdcam', ?, 1, 0.9, ?, ?, ?, ?, ?)",
            (event, at.isoformat(sep=" "), name, name, name, species_id, int(hidden)),
        )
        await db.commit()


async def add_garden(capture_id: str, species_id: int, status: str, at: datetime, *, crop: bool = False) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO garden_captures (id, event_key, frigate_event, camera, label, observed_at, status, has_snapshot)"
            " VALUES (?, ?, ?, 'patio', 'fox', ?, ?, 1)",
            (capture_id, capture_id, f"{capture_id[:6]}.1-abc", at.isoformat(), status),
        )
        await db.execute(
            "INSERT INTO garden_owner_identifications (capture_id, species_id, name, scientific_name, changed_at)"
            " VALUES (?, ?, 'Red Fox', 'Vulpes vulpes', ?)",
            (capture_id, species_id, at.isoformat() + "Z"),
        )
        if crop:
            await db.execute(
                "INSERT INTO garden_saved_crops (capture_id, image, evidence_json, state, updated_at)"
                " VALUES (?, x'ff', '{}', 'available', ?)",
                (capture_id, at.isoformat()),
            )
        await db.commit()


async def add_call(species_id: int, at: datetime, *, hidden: bool = False) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, is_hidden, species_id)"
            " VALUES (?, 'Dunnock', 0.8, 'mic', ?, ?)",
            (at.isoformat(sep=" "), int(hidden), species_id),
        )
        await db.commit()


async def get(path: str, params=None, lang: str = "en") -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, params=params, headers={"Accept-Language": lang})


async def facts(*ids: int) -> dict[int, dict]:
    response = await get("/api/taxonomy/facts", params=[("ids", taxon_id) for taxon_id in ids])
    assert response.status_code == 200, response.text
    return {entry["taxon_id"]: entry for entry in response.json()["facts"]}


def stamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.removesuffix("Z")) if value else None


@pytest.mark.asyncio
async def test_a_species_states_its_visits_and_first_and_last_seen_without_hidden_records(catalogue, reader):
    dunnock = _id(catalogue, "Prunella modularis")
    start = RECENT - timedelta(days=2)
    # Three frames inside the visit gap are one visit; a frame two hours later is a second.
    for offset, event in ((0, "a"), (10, "b"), (20, "c")):
        await add_detection(f"1793600000.{event}-aaaaaa", dunnock, start + timedelta(seconds=offset))
    await add_detection("1793600001.d-aaaaaa", dunnock, start + timedelta(hours=2))
    await add_detection("1793600002.e-aaaaaa", dunnock, start + timedelta(hours=5), hidden=True)
    entry = (await facts(dunnock))[dunnock]
    assert (entry["rank"], entry["visits"], entry["species_seen"]) == ("species", 2, 1)
    assert stamp(entry["first_seen"]) == start
    assert stamp(entry["last_seen"]) == start + timedelta(hours=2)
    assert entry["sources"] == ["camera"]


@pytest.mark.asyncio
async def test_a_group_rolls_up_the_species_seen_beneath_it_and_an_unseen_one_says_so(catalogue, reader):
    dunnock, great_tit = _id(catalogue, "Prunella modularis"), _id(catalogue, "Parus major")
    await add_detection("1793600000.a-aaaaaa", dunnock, RECENT - timedelta(days=4))
    await add_detection("1793600001.a-aaaaaa", dunnock, RECENT - timedelta(days=1))
    await add_detection("1793600002.a-aaaaaa", great_tit, RECENT)
    found = await facts(
        _id(catalogue, "Prunellidae"), _id(catalogue, "Passeriformes"), _id(catalogue, "Prunella collaris")
    )
    family, order = found[_id(catalogue, "Prunellidae")], found[_id(catalogue, "Passeriformes")]
    assert (family["rank"], family["species_seen"], family["visits"]) == ("family", 1, 2)
    assert (order["species_seen"], order["visits"]) == (2, 3)
    assert stamp(order["last_seen"]) == RECENT
    assert stamp(order["first_seen"]) == RECENT - timedelta(days=4)
    alpine = found[_id(catalogue, "Prunella collaris")]
    assert (alpine["visits"], alpine["species_seen"], alpine["first_seen"], alpine["photo"]) == (0, 0, None, None)


@pytest.mark.asyncio
async def test_confirmed_garden_visits_join_the_tree_and_unconfirmed_captures_never_do(catalogue, reader):
    fox = _id(catalogue, "Vulpes vulpes")
    await add_garden("a" * 32, fox, "confirmed", RECENT - timedelta(hours=5))
    await add_garden("b" * 32, fox, "confirmed", RECENT - timedelta(hours=5) + timedelta(seconds=30))
    await add_garden("c" * 32, fox, "confirmed", RECENT)
    await add_garden("d" * 32, fox, "pending", RECENT + timedelta(hours=1))
    await add_garden("e" * 32, fox, "dismissed", RECENT + timedelta(hours=2))
    found = await facts(fox, _id(catalogue, "Canidae"))
    assert (found[fox]["visits"], found[fox]["sources"]) == (2, ["garden"])
    assert stamp(found[fox]["last_seen"]) == RECENT
    assert found[_id(catalogue, "Canidae")]["species_seen"] == 1
    # The tree itself counts the same confirmed captures as seen here.
    children = (await get(f"/api/taxonomy/{_id(catalogue, 'Carnivora')}/children")).json()["children"]
    assert [(c["scientific_name"], c["seen_species"], c["seen_count"]) for c in children] == [("Canidae", 1, 3)]


@pytest.mark.asyncio
async def test_garden_visits_leave_the_tree_while_garden_animals_are_switched_off(catalogue, reader, monkeypatch):
    fox = _id(catalogue, "Vulpes vulpes")
    await add_garden("a" * 32, fox, "confirmed", RECENT)
    monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    assert (await facts(fox))[fox]["visits"] == 0
    children = (await get(f"/api/taxonomy/{_id(catalogue, 'Carnivora')}/children")).json()["children"]
    assert children[0]["seen_species"] == 0


@pytest.mark.asyncio
async def test_heard_counts_visible_birdnet_detections_even_for_a_species_never_seen(catalogue, reader):
    dunnock, alpine = _id(catalogue, "Prunella modularis"), _id(catalogue, "Prunella collaris")
    await add_detection("1793600000.a-aaaaaa", dunnock, RECENT)
    for minutes in (1, 2, 3):
        await add_call(dunnock, RECENT + timedelta(minutes=minutes))
    await add_call(dunnock, RECENT + timedelta(minutes=9), hidden=True)
    await add_call(alpine, RECENT)
    found = await facts(dunnock, alpine, _id(catalogue, "Prunella"))
    assert found[dunnock]["heard"] == 3
    assert stamp(found[dunnock]["last_heard"]) == RECENT + timedelta(minutes=3)
    assert (found[alpine]["visits"], found[alpine]["heard"]) == (0, 1)
    assert (found[_id(catalogue, "Prunella")]["heard"], found[_id(catalogue, "Prunella")]["species_seen"]) == (4, 1)


@pytest.mark.asyncio
async def test_a_guest_reads_the_shared_window_and_calls_only_while_audio_is_shared(catalogue, reader, monkeypatch):
    dunnock = _id(catalogue, "Prunella modularis")
    await add_detection("1793600000.a-aaaaaa", dunnock, OLD)
    await add_detection("1793600001.a-aaaaaa", dunnock, RECENT)
    await add_call(dunnock, OLD)
    await add_call(dunnock, RECENT)
    owner = await get("/api/taxonomy/facts", params={"ids": dunnock})
    assert owner.json()["scope"] == "all"
    assert (owner.json()["facts"][0]["visits"], owner.json()["facts"][0]["heard"]) == (2, 2)
    as_guest(reader)
    taxon_facts.taxon_facts_service.clear()
    guest = await get("/api/taxonomy/facts", params={"ids": dunnock})
    assert (guest.json()["scope"], guest.json()["shared_days"]) == ("shared", 7)
    entry = guest.json()["facts"][0]
    assert (entry["visits"], entry["heard"]) == (1, 1)
    assert stamp(entry["first_seen"]) == RECENT
    monkeypatch.setattr(settings.public_access, "show_audio", False)
    # The sharing settings are part of what is cached, so the change is immediate.
    assert (await facts(dunnock))[dunnock]["heard"] is None
    monkeypatch.setattr(settings.public_access, "enabled", False)
    assert (await get("/api/taxonomy/facts", params={"ids": dunnock})).status_code == 403


@pytest.mark.asyncio
async def test_the_photo_is_the_newest_stored_crop_the_reader_may_see(catalogue, reader, snapshots, monkeypatch):
    dunnock = _id(catalogue, "Prunella modularis")
    await add_detection("1793600000.old-aaaaa", dunnock, RECENT - timedelta(days=3))
    await add_detection("1793600001.mid-aaaaa", dunnock, RECENT - timedelta(days=2))
    await add_detection("1793600002.new-aaaaa", dunnock, RECENT - timedelta(days=1))
    await add_detection("1793600003.hid-aaaaa", dunnock, RECENT, hidden=True)
    snapshots.update(
        {
            "1793600000.old-aaaaa": CROP,
            "1793600001.mid-aaaaa": CROP,
            "1793600002.new-aaaaa": WHOLE_SCENE,
            "1793600003.hid-aaaaa": CROP,
        }
    )
    photo = (await facts(dunnock))[dunnock]["photo"]
    assert photo["url"] == "/api/about/showcase/1793600001.mid-aaaaa.jpg"
    assert (photo["kind"], photo["species_id"]) == ("camera", dunnock)
    as_guest(reader)
    assert (await facts(dunnock))[dunnock]["photo"]["url"] == photo["url"]
    # Outside the shared photograph window, or with photographs not shared, a guest gets none.
    monkeypatch.setattr(settings.public_access, "media_historical_days", 1)
    assert (await facts(dunnock))[dunnock]["photo"] is None
    monkeypatch.setattr(settings.public_access, "media_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "show_snapshots", False)
    entry = (await facts(dunnock))[dunnock]
    assert (entry["photo"], entry["visits"]) == (None, 3)


@pytest.mark.asyncio
async def test_a_group_shows_the_photo_of_its_most_seen_member(catalogue, reader, snapshots):
    dunnock, great_tit = _id(catalogue, "Prunella modularis"), _id(catalogue, "Parus major")
    await add_detection("1793600000.dun-aaaaa", dunnock, RECENT)
    for hours in (30, 20, 10):
        await add_detection(f"1793600{hours}.tit-aaaaa", great_tit, RECENT - timedelta(hours=hours))
    snapshots.update({"1793600000.dun-aaaaa": CROP, "179360010.tit-aaaaa": CROP})
    order = (await facts(_id(catalogue, "Passeriformes")))[_id(catalogue, "Passeriformes")]
    assert order["photo"]["species_id"] == great_tit
    assert order["photo"]["url"] == "/api/about/showcase/179360010.tit-aaaaa.jpg"
    # The card names whose photograph illustrates the group.
    assert (order["photo"]["scientific_name"], order["photo"]["name"]) == ("Parus major", "Great Tit")


@pytest.mark.asyncio
async def test_a_garden_animal_shows_its_saved_crop_under_the_garden_sharing_rules(
    catalogue, reader, snapshots, monkeypatch
):
    fox = _id(catalogue, "Vulpes vulpes")
    await add_garden("a" * 32, fox, "confirmed", RECENT - timedelta(days=2), crop=True)
    await add_garden("b" * 32, fox, "confirmed", RECENT - timedelta(days=1))
    await add_garden("c" * 32, fox, "pending", RECENT, crop=True)
    photo = (await facts(fox))[fox]["photo"]
    assert (photo["url"], photo["kind"]) == (f"/api/garden/{'a' * 32}/crop", "garden")
    assert (await facts(_id(catalogue, "Canidae")))[_id(catalogue, "Canidae")]["photo"]["url"] == photo["url"]
    as_guest(reader)
    assert (await facts(fox))[fox]["photo"]["url"] == photo["url"]
    monkeypatch.setattr(settings.public_access, "show_snapshots", False)
    assert (await facts(fox))[fox]["photo"] is None


@pytest.mark.asyncio
async def test_facts_are_read_in_bounded_batches(catalogue, reader):
    dunnock = _id(catalogue, "Prunella modularis")
    too_many = [("ids", taxon_id) for taxon_id in range(1, 102)]
    assert (await get("/api/taxonomy/facts", params=too_many)).status_code == 422
    assert (await get("/api/taxonomy/facts")).status_code == 422
    assert (await get("/api/taxonomy/facts", params={"ids": 0})).status_code == 422
    # Repeats are answered once; an id the catalogue does not hold is left out.
    found = await get("/api/taxonomy/facts", params=[("ids", dunnock), ("ids", dunnock), ("ids", 999999)])
    assert [entry["taxon_id"] for entry in found.json()["facts"]] == [dunnock]


@pytest.mark.asyncio
async def test_the_tree_carries_the_accepted_concepts_authorship_exactly_as_stored(catalogue, reader):
    set_authorship(catalogue, "Prunella modularis", "(Linnaeus, 1758)")
    set_authorship(catalogue, "Prunellidae", "Vigors, 1831")
    set_authorship(catalogue, "Prunella", "  ")
    lineage = (await get(f"/api/taxonomy/{_id(catalogue, 'Prunella modularis')}/lineage")).json()["lineage"]
    authors = {taxon["scientific_name"]: taxon["authorship"] for taxon in lineage}
    assert authors["Prunella modularis"] == "(Linnaeus, 1758)"
    assert authors["Prunellidae"] == "Vigors, 1831"
    # Blank is unknown, not an empty authority.
    assert authors["Prunella"] is None
    assert authors["Aves"] is None
    children = (await get(f"/api/taxonomy/{_id(catalogue, 'Prunella')}/children")).json()["children"]
    assert {c["scientific_name"]: c["authorship"] for c in children} == {
        "Prunella collaris": None,
        "Prunella modularis": "(Linnaeus, 1758)",
    }


@pytest.mark.asyncio
async def test_other_names_list_the_other_languages_with_the_preferred_name_first(catalogue, reader):
    add_name(catalogue, "Prunella modularis", "fr", "Mouchet", False)
    add_name(catalogue, "Prunella modularis", "fr", "Accenteur mouchet", True)
    add_name(catalogue, "Prunella modularis", "de", "Heckenbraunelle", True)
    add_name(catalogue, "Prunella modularis", "de", "heckenbraunelle", False)
    dunnock = _id(catalogue, "Prunella modularis")
    body = (await get(f"/api/taxonomy/{dunnock}/names")).json()
    # The reader's own language is the name they already see; the rest, preferred first.
    assert body["names"] == [
        {"language": "de", "name": "Heckenbraunelle", "preferred": True},
        {"language": "fr", "name": "Accenteur mouchet", "preferred": True},
        {"language": "fr", "name": "Mouchet", "preferred": False},
    ]
    assert (body["languages"], body["truncated"]) == (2, False)
    french = (await get(f"/api/taxonomy/{dunnock}/names", lang="fr")).json()
    assert [(n["language"], n["name"]) for n in french["names"]] == [("de", "Heckenbraunelle"), ("en", "Dunnock")]
    bounded = (await get(f"/api/taxonomy/{dunnock}/names", params={"limit": 1})).json()
    assert (len(bounded["names"]), bounded["languages"], bounded["truncated"]) == (1, 2, True)
    assert (await get(f"/api/taxonomy/{dunnock}/names", params={"limit": 101})).status_code == 422
    assert (await get("/api/taxonomy/999999/names")).status_code == 404


@pytest.mark.asyncio
async def test_garden_animal_names_reach_the_tree_cased_as_the_garden_record_shows_them(catalogue, reader, snapshots):
    # SpeciesNet stores "red fox"; the Field log and Explorer show "Red Fox" through the shared
    # `vernacular_case`. The tree, its cards and the photo caption read the same names.
    fox = _id(catalogue, "Vulpes vulpes")
    await add_garden("a" * 32, fox, "confirmed", RECENT, crop=True)
    add_name(catalogue, "Vulpes vulpes", "de", "rotfuchs", False)
    lineage = (await get(f"/api/taxonomy/{fox}/lineage")).json()["lineage"]
    named = {taxon["scientific_name"]: taxon["name"] for taxon in lineage}
    assert (named["Vulpes vulpes"], named["Canidae"]) == ("Red Fox", "Dog Family")
    children = (await get(f"/api/taxonomy/{_id(catalogue, 'Carnivora')}/children")).json()["children"]
    assert [(c["scientific_name"], c["name"]) for c in children] == [("Canidae", "Dog Family")]
    photo = (await facts(_id(catalogue, "Canidae")))[_id(catalogue, "Canidae")]["photo"]
    # Scientific names are never re-cased.
    assert (photo["name"], photo["scientific_name"]) == ("Red Fox", "Vulpes vulpes")
    other = (await get(f"/api/taxonomy/{fox}/names", lang="fr")).json()["names"]
    assert [(n["language"], n["name"]) for n in other] == [("de", "rotfuchs"), ("en", "Red Fox")]
