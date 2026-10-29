"""Owner corrections are independent of inference, retained media and bird history."""

from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models.garden import GardenIdentification
from app.repositories.garden_catalog import GardenCatalog
from app.repositories.garden_repository import GardenRepository
from app.services.garden_identification import garden_identification_service
from app.services.species_catalog_migrations import upgrade_catalog


@pytest_asyncio.fixture
async def history(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    catalog = GardenCatalog(tmp_path / "catalog.db")
    upgrade_catalog(catalog.path)
    catalog.initialize()
    monkeypatch.setattr(garden_identification_service, "catalog", catalog)
    bundle = catalog.load()
    fox = next(t for t in bundle["outputs"] if t["ranks"][3:] == ["vulpes", "vulpes"])
    species_id = bundle["bindings"][fox["id"]]
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        repo = GardenRepository(db)
        await repo.capture("owner-edit", "patio", "dog", "2026-10-29T00:00:00", False)
        await db.execute("UPDATE garden_captures SET status='confirmed'")
        original = (await repo.list("confirmed", 1, 0))[0]
        evidence = GardenIdentification(
            outcome="suggestion",
            reason="confident",
            review="accepted",
            automatic=True,
            species_id=999999,
            name="Domestic Dog",
            rank="species",
            score=0.97,
            country="GBR",
            variant="4.0.3a",
            provider="intel_npu",
            devices=["NPU"],
            model_sha256="a" * 64,
            package_sha256="b" * 64,
            image_sha256="c" * 64,
            output_index=1,
            input_kind="tracked_crop",
            frame_size=(640, 480),
            identified_at="2026-10-29T00:00:00Z",
        )
        await db.execute("INSERT INTO garden_identifications VALUES (?,?)", (original.id, evidence.model_dump_json()))
        await db.commit()
        original = await repo.get(original.id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, original, species_id
    await close_db()


@pytest.mark.asyncio
async def test_an_owner_can_rename_after_photo_expiry_without_fabricating_an_inference(history, monkeypatch):
    from app.services.broadcaster import broadcaster
    from app.services import garden_motion_privacy

    client, original, fox = history

    async def refreshed(message):
        assert not garden_motion_privacy.lock.locked()
        async with get_db() as db:
            assert (await GardenRepository(db).get(original.id)).owner_identification.species_id == fox

    update = AsyncMock(side_effect=refreshed)
    monkeypatch.setattr(broadcaster, "broadcast", update)
    response = await client.put(
        f"/api/garden/{original.id}/species", json={"species_id": fox, "review_token": original.review_token}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["owner_identification"]["species_id"] == fox
    assert result["owner_identification"]["scientific_name"] == "Vulpes vulpes"
    assert not {"score", "devices", "provider", "variant"} & result["owner_identification"].keys()
    assert result["identification"]["score"] == 0.97
    assert result["identification"]["devices"] == ["NPU"]
    assert result["automatic_check_overridden"] and result["review_token"] != original.review_token
    assert result["scientific_name"] == "Vulpes vulpes"
    assert "no-store" in response.headers["cache-control"]
    update.assert_awaited_once_with({"type": "garden_history_changed"})
    await close_db()
    await init_db()
    async with get_db() as db:
        repo = GardenRepository(db)
        saved = await repo.get(original.id)
        assert saved.owner_identification.species_id == fox
        assert saved.identification == original.identification
        assert not await repo.save_identification(
            original, original.identification.model_copy(update={"review": "unreviewed"})
        )
        await repo.review(original.id, "dismissed")
        assert (await repo.get(original.id)).owner_identification.species_id == fox
        await repo.block_capture(original.id)
        assert await (await db.execute("SELECT COUNT(*) FROM garden_owner_identifications")).fetchone() == (0,)


@pytest.mark.asyncio
async def test_stale_owner_actions_cannot_replace_or_dismiss_a_new_correction(history):
    client, original, fox = history
    request = {"species_id": fox, "review_token": original.review_token}
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 200
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 409
    dismissed = await client.post(
        "/api/garden/dismiss-captures", json={"captures": [{"id": original.id, "review_token": original.review_token}]}
    )
    assert dismissed.json()["updated_ids"] == []
    assert (
        await client.delete(f"/api/garden/{original.id}/species", params={"review_token": original.review_token})
    ).status_code == 409


@pytest.mark.asyncio
async def test_correction_changes_canonical_visit_group_and_can_return_to_original(history):
    client, original, fox = history
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.capture("second-fox", "patio", "fox", "2026-10-29T00:00:05", False)
        await db.execute("UPDATE garden_captures SET status='confirmed' WHERE frigate_event='second-fox'")
        await db.execute(
            "INSERT INTO garden_identifications SELECT id,? FROM garden_captures WHERE frigate_event='second-fox'",
            (original.identification.model_copy(update={"species_id": fox, "name": "Red Fox"}).model_dump_json(),),
        )
        await db.commit()
    assert (await client.get("/api/garden/visits")).json()["total"] == 2
    response = await client.put(
        f"/api/garden/{original.id}/species", json={"species_id": fox, "review_token": original.review_token}
    )
    assert response.status_code == 200, response.text
    assert (await client.get("/api/garden/visits")).json()["total"] == 1
    response = await client.delete(
        f"/api/garden/{original.id}/species", params={"review_token": response.json()["review_token"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["owner_identification"] is None
    assert response.json()["identification"]["name"] == "Domestic Dog"
    assert response.json()["automatic_check_overridden"]
    assert (await client.get("/api/garden/visits")).json()["total"] == 2


@pytest.mark.asyncio
async def test_species_search_uses_local_animal_catalogue_and_rejects_humans_and_aggregates(history):
    client, original, fox = history
    for term in ("Vulpes vulpes", "red fox"):
        response = await client.get("/api/garden/species", params={"q": term})
        assert response.status_code == 200, response.text
        assert fox in {v["species_id"] for v in response.json()}
    assert (await client.get("/api/garden/species", params={"q": "Homo sapiens"})).json() == []
    bundle = garden_identification_service.catalog.load()
    human = next(t for t in bundle["outputs"] if t["ranks"][3:] == ["homo", "sapiens"])
    for species_id in (bundle["bindings"][human["id"]], 999999999):
        result = await client.put(
            f"/api/garden/{original.id}/species", json={"species_id": species_id, "review_token": original.review_token}
        )
        assert result.status_code == 422, result.text


@pytest.mark.asyncio
async def test_pending_blocked_and_dismissed_records_cannot_be_renamed(history):
    client, original, fox = history
    async with get_db() as db:
        await db.execute("UPDATE garden_captures SET status='pending' WHERE id=?", (original.id,))
        await db.commit()
        pending = await GardenRepository(db).get(original.id)
    request = {"species_id": fox, "review_token": pending.review_token}
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 409
    async with get_db() as db:
        await GardenRepository(db).review(original.id, "dismissed")
        dismissed = await GardenRepository(db).get(original.id)
    request["review_token"] = dismissed.review_token
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 409
    async with get_db() as db:
        await GardenRepository(db).block_capture(original.id)
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 404


@pytest.mark.asyncio
async def test_late_automatic_and_manual_results_never_replace_an_owner_identity(history):
    from app.models.garden import GardenAutomaticCheck
    from app.services.garden_notifications import eligible
    from datetime import datetime, timezone

    client, original, fox = history
    async with get_db() as db:
        # Model work started while this capture was pending, before the owner acted.
        pending = original.__class__(**{**original.__dict__, "status": "pending"})
    response = await client.put(
        f"/api/garden/{original.id}/species", json={"species_id": fox, "review_token": original.review_token}
    )
    assert response.status_code == 200
    async with get_db() as db:
        repo = GardenRepository(db)
        check = GardenAutomaticCheck(outcome="unavailable", checked_at="2026-10-29T00:00:00Z")
        assert not await repo.save_automatic_check(pending, check)
        current = await repo.get(original.id)
        assert not await repo.save_identification(
            current, original.identification.model_copy(update={"review": "unreviewed"})
        )
        assert not eligible(current, enabled=True, cameras=["patio"], now=datetime(2026, 10, 29, tzinfo=timezone.utc))
        assert current.owner_identification.species_id == fox


@pytest.mark.asyncio
async def test_anonymous_and_guest_requests_cannot_write_owner_corrections(history, monkeypatch):
    from app.auth import create_access_token

    client, original, fox = history
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    request = {"species_id": fox, "review_token": original.review_token}
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 401
    client.headers["Authorization"] = "Bearer " + create_access_token("garden-guest", auth_level="guest")
    assert (await client.put(f"/api/garden/{original.id}/species", json=request)).status_code == 403
    assert (await client.get("/api/garden/species?q=fox")).status_code == 403


@pytest.mark.asyncio
async def test_existing_crop_bytes_survive_correction_and_person_revocation_removes_owner_data(history):
    import hashlib
    from io import BytesIO
    from PIL import Image
    from app.services.garden_crop_service import build_saved_crop

    client, original, fox = history
    output = BytesIO()
    Image.new("RGB", (640, 480), "green").save(output, format="JPEG")
    image = output.getvalue()
    evidence, cropped = build_saved_crop(
        image,
        box=(0.1, 0.1, 0.3, 0.3),
        expected_sha256=hashlib.sha256(image).hexdigest(),
        source_start=100,
        source_end=110,
        source_kind="frigate_clean",
        frame_time=105,
    )
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.save_crop(original, evidence, cropped)
    response = await client.put(
        f"/api/garden/{original.id}/species", json={"species_id": fox, "review_token": original.review_token}
    )
    assert response.status_code == 200
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.crop_photo(original.id) == cropped
        assert (await repo.get(original.id)).crop == evidence
        await repo.block(original.frigate_event, create=False)
        assert await (await db.execute("SELECT COUNT(*) FROM garden_owner_identifications")).fetchone() == (0,)
        assert await repo.crop_photo(original.id) is None


@pytest.mark.asyncio
async def test_localized_correction_keeps_the_raw_review_token_and_original_model_name(history, monkeypatch):
    import sqlite3
    import app.routers.garden as router
    from app.services.species_names import SpeciesNameLookup

    client, original, fox = history
    catalog = garden_identification_service.catalog
    with sqlite3.connect(catalog.path) as db:
        db.execute(
            "INSERT INTO species_names(species_id,language_tag,name,name_kind,preferred,provider,source_release) VALUES (?,'de','Rotfuchs','vernacular',1,'test','1')",
            (fox,),
        )
    monkeypatch.setattr(router, "species_name_lookup", SpeciesNameLookup(catalog.path))
    response = await client.get("/api/garden/species?q=Rotfuchs", headers={"Accept-Language": "de"})
    assert response.json()[0]["species_id"] == fox
    response = await client.put(
        f"/api/garden/{original.id}/species",
        json={"species_id": fox, "review_token": original.review_token},
        headers={"Accept-Language": "de"},
    )
    assert response.status_code == 200
    assert response.json()["owner_identification"]["name"] == "Rotfuchs"
    async with get_db() as db:
        raw = await GardenRepository(db).get(original.id)
        assert raw.review_token == response.json()["review_token"]
        assert raw.identification.name == "Domestic Dog"
