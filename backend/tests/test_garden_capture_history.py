"""Animal reviews stay private and cannot create bird detections."""

import copy
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.config import settings
from app.config_models import FrigateSettings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.garden_repository import GardenRepository
from app.services.garden_capture_service import garden_capture_service
from app.services.mqtt_service import MQTTService


@pytest_asyncio.fixture(autouse=True)
async def database():
    original = copy.deepcopy(settings.frigate)
    original_history = garden_capture_service.has_history
    auth, public = settings.auth.enabled, settings.public_access.enabled
    settings.frigate.garden_cameras = ["patio"]
    settings.frigate.garden_labels = ["cat", "dog"]
    settings.auth.enabled = settings.public_access.enabled = False
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
    yield
    settings.frigate = original
    garden_capture_service.has_history = original_history
    settings.auth.enabled, settings.public_access.enabled = auth, public
    await close_db()


def event(label="cat", camera="patio", event_type="end", **extra):
    return {
        "type": event_type,
        "after": {
            "id": "garden-test-1",
            "camera": camera,
            "label": label,
            "start_time": 1791748800.0,
            "has_snapshot": True,
            **extra,
        },
    }


def test_garden_defaults_off_and_rejects_non_animal_labels():
    config = FrigateSettings(frigate_url="http://frigate", garden_labels=[" Cat ", "DOG", "cat"])
    assert config.garden_cameras == []
    assert config.garden_labels == ["cat", "dog"]
    for label in ("person", "human", "bird", "car", "duck"):
        with pytest.raises(ValidationError):
            FrigateSettings(frigate_url="http://frigate", garden_labels=[label])


@pytest.mark.asyncio
async def test_only_terminal_opted_in_animals_create_one_review_without_bird_writes():
    for payload in (
        event(event_type="new"),
        event(event_type="update"),
        event(camera="other"),
        event("bird"),
        event("car"),
    ):
        await garden_capture_service.process(payload)
    async with get_db() as db:
        assert await GardenRepository(db).list("pending", 20, 0) == []
        before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
    for _ in range(3):
        await garden_capture_service.process(event())
    async with get_db() as db:
        rows = await GardenRepository(db).list("pending", 20, 0)
        assert len(rows) == 1
        assert rows[0].label == "cat"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/garden/{rows[0].id}/confirm")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "confirmed"
        await garden_capture_service.process(event())
        assert (await client.get("/api/garden", params={"status": "confirmed"})).json()["total"] == 1
        assert (await client.post(f"/api/garden/{rows[0].id}/dismiss")).status_code == 200
        assert (await client.post(f"/api/garden/{rows[0].id}/restore")).json()["status"] == "pending"
    async with get_db() as db:
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rejection", [{"label": "person"}, {"label": "human"}, {"false_positive": True}, {"label": "bird"}]
)
async def test_rejected_capture_erases_identity_and_blocks_stale_redelivery(rejection):
    await garden_capture_service.process(event())
    async with get_db() as db:
        capture = (await GardenRepository(db).list("pending", 20, 0))[0]
    await garden_capture_service.process(event(**rejection))
    await garden_capture_service.process(event())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/garden")).json()["total"] == 0
        assert (await client.post(f"/api/garden/{capture.id}/confirm")).status_code == 404
        with patch("app.services.garden_capture_service.frigate_client.get_snapshot", new=AsyncMock()) as snapshot:
            assert (await client.get(f"/api/garden/{capture.id}/snapshot")).status_code == 404
            snapshot.assert_not_awaited()
    async with get_db() as db:
        row = await (await db.execute("SELECT frigate_event, camera, label, status FROM garden_captures")).fetchone()
        assert row == (None, "", "", "blocked")


@pytest.mark.asyncio
async def test_disabled_path_has_no_database_or_network_work():
    settings.frigate.garden_cameras = []
    with (
        patch("app.services.garden_capture_service.get_db") as database,
        patch("app.services.garden_capture_service.frigate_client.get_snapshot", new=AsyncMock()) as snapshot,
    ):
        await garden_capture_service.process(event())
        database.assert_not_called()
        snapshot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["../secret", "x/y", ".", "..", "", "x" * 129])
async def test_invalid_ids_never_reach_history(identifier):
    await garden_capture_service.process(event(id=identifier))
    async with get_db() as db:
        assert await GardenRepository(db).list("pending", 20, 0) == []


@pytest.mark.asyncio
async def test_guest_cannot_read_history_act_or_request_media():
    from app.auth import create_access_token

    await garden_capture_service.process(event())
    async with get_db() as db:
        capture = (await GardenRepository(db).list("pending", 20, 0))[0]
    settings.auth.enabled = settings.public_access.enabled = True
    token = create_access_token("guest", auth_level="guest")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as client:
        for method, path in (
            ("GET", "/api/garden"),
            ("GET", "/api/garden/identification"),
            ("POST", "/api/garden/models/4.0.3b/install"),
            ("POST", f"/api/garden/{capture.id}/identify"),
            ("POST", f"/api/garden/{capture.id}/identification/accept"),
            ("POST", f"/api/garden/{capture.id}/identification/dismiss"),
            ("GET", f"/api/garden/{capture.id}/snapshot"),
            ("POST", f"/api/garden/{capture.id}/confirm"),
        ):
            assert (await client.request(method, path)).status_code == 403


def test_mqtt_schedules_animals_and_preserves_person_rejection():
    mqtt = MQTTService()
    assert mqtt._parse_frigate_payload_meta(json.dumps(event()).encode())["should_process"]
    assert not mqtt._parse_frigate_payload_meta(json.dumps(event(camera="other")).encode())["should_process"]
    person = json.dumps(event("person")).encode()
    assert mqtt._parse_frigate_payload_meta(person)["should_process"]
    assert mqtt._merge_pending_frigate_payload(person, json.dumps(event()).encode()) == person


@pytest.mark.asyncio
async def test_disabling_capture_does_not_prevent_later_privacy_cleanup():
    await garden_capture_service.process(event())
    settings.frigate.garden_cameras = []
    # The flag is rebuilt from durable history after an application restart.
    await garden_capture_service.initialize()
    payload = event("person")
    assert MQTTService()._parse_frigate_payload_meta(json.dumps(payload).encode())["should_process"]
    await garden_capture_service.process(payload)
    async with get_db() as db:
        assert await GardenRepository(db).list("pending", 20, 0) == []


@pytest.mark.asyncio
async def test_cookie_can_load_owner_photo_but_cannot_authorize_a_review():
    from app.auth import SESSION_COOKIE, create_access_token

    await garden_capture_service.process(event())
    async with get_db() as db:
        capture = (await GardenRepository(db).list("pending", 20, 0))[0]
    settings.auth.enabled = True
    token = create_access_token("owner")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", cookies={SESSION_COOKIE: token}
    ) as client:
        with patch(
            "app.services.garden_capture_service.frigate_client.get_snapshot", new=AsyncMock(return_value=b"photo")
        ):
            response = await client.get(f"/api/garden/{capture.id}/snapshot")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "private, no-store"
        assert (await client.post(f"/api/garden/{capture.id}/confirm")).status_code in {401, 403}


@pytest.mark.asyncio
async def test_garden_settings_roundtrip_preserves_bird_role_and_partial_updates():
    settings.frigate.camera_roles = {"patio": "nest"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/settings", json={"garden_cameras": [" patio ", "patio"], "garden_labels": [" Cat "]}
        )
        assert response.status_code == 200, response.text
        data = (await client.get("/api/settings")).json()
        assert data["garden_cameras"] == ["patio"]
        assert data["garden_labels"] == ["cat"]
        assert data["camera_roles"] == {"patio": "nest"}
        assert (await client.post("/api/settings", json={"nest_dedupe_minutes": 42})).status_code == 200
        assert settings.frigate.garden_cameras == ["patio"]
        assert (await client.post("/api/settings", json={"garden_labels": ["person"]})).status_code == 422
        assert settings.frigate.garden_labels == ["cat"]


@pytest.mark.asyncio
async def test_pagination_and_retention_do_not_include_blocked_captures():
    from datetime import datetime, timezone

    for index in range(11):
        await garden_capture_service.process(event(id=f"visit-{index}"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = (await client.get("/api/garden", params={"limit": 8})).json()
        second = (await client.get("/api/garden", params={"limit": 8, "offset": 8})).json()
        assert first["total"] == second["total"] == 11
        assert len(first["items"]) == 8 and len(second["items"]) == 3
        assert not ({row["id"] for row in first["items"]} & {row["id"] for row in second["items"]})
        assert (await client.get("/api/garden", params={"limit": 1000})).status_code == 422
    async with get_db() as db:
        await GardenRepository(db).delete_older_than(datetime(2026, 10, 12, tzinfo=timezone.utc))
        assert await GardenRepository(db).count("pending") == 0


@pytest.mark.asyncio
async def test_rejection_during_photo_download_does_not_serve_the_photo():
    await garden_capture_service.process(event())
    async with get_db() as db:
        capture = (await GardenRepository(db).list("pending", 20, 0))[0]

    async def download(*args, **kwargs):
        await garden_capture_service.process(event("person"))
        return b"private photo"

    with patch("app.services.garden_capture_service.frigate_client.get_snapshot", new=download):
        with pytest.raises(Exception) as error:
            await garden_capture_service.snapshot(capture.id)
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_vehicle_relabel_revokes_the_earlier_animal_candidate():
    await garden_capture_service.process(event())
    payload = event("car")
    assert MQTTService()._parse_frigate_payload_meta(json.dumps(payload).encode())["should_process"]
    await garden_capture_service.process(payload)
    async with get_db() as db:
        assert await GardenRepository(db).count("pending") == 0


@pytest.mark.asyncio
async def test_non_bird_events_do_not_enter_bird_logging_or_processing():
    from app.services.event_processor import EventProcessor

    processor = EventProcessor()
    with patch.object(processor, "_parse_and_validate_event") as bird_parser:
        await processor._process_event_payload(event("person"))
        bird_parser.assert_not_called()


def test_observation_time_rejects_future_and_expired_events():
    from datetime import datetime, timezone
    from app.services.garden_capture_policy import observation_time

    now = datetime(2026, 10, 11, 23, tzinfo=timezone.utc)
    assert observation_time(True, now, 90) is None
    assert observation_time(float("inf"), now, 90) is None
    assert observation_time(now.timestamp() + 86400, now, 90) is None
    assert observation_time(now.timestamp() - 91 * 86400, now, 90) is None
    assert observation_time(now.timestamp() - 91 * 86400, now, 0) is not None


def identification(image=b"photo"):
    import hashlib
    from app.models.garden import GardenIdentification

    return GardenIdentification(
        outcome="suggestion",
        reason="garden",
        taxon_id="fox",
        species_id=123,
        name="red fox",
        rank="species",
        score=0.9,
        country="GBR",
        variant="4.0.3b",
        provider="cpu",
        devices=["CPUExecutionProvider"],
        model_sha256="a" * 64,
        package_sha256="b" * 64,
        image_sha256=hashlib.sha256(image).hexdigest(),
        output_index=1,
        input_kind="whole_image",
        frame_size=(640, 360),
        identified_at="2026-10-12T07:00:00Z",
    )


@pytest.mark.asyncio
async def test_late_suggestion_cannot_overwrite_owner_identification_review():
    await garden_capture_service.process(event())
    async with get_db() as db:
        repository = GardenRepository(db)
        capture = (await repository.list("pending", 20, 0))[0]
        capture = await repository.review(capture.id, "confirmed")
        assert await repository.save_identification(capture, identification())
        original = await repository.get(capture.id)
        assert await repository.review_identification(capture.id, "dismissed")
        assert not await repository.save_identification(original, identification())
        assert (await repository.get(capture.id)).identification.review == "dismissed"


@pytest.mark.asyncio
async def test_species_confirmation_checks_the_current_photo_and_never_writes_birds(monkeypatch):
    await garden_capture_service.process(event())
    async with get_db() as db:
        repository = GardenRepository(db)
        capture = (await repository.list("pending", 20, 0))[0]
        capture = await repository.review(capture.id, "confirmed")
        assert await repository.save_identification(capture, identification())
        before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
    monkeypatch.setattr(garden_capture_service, "snapshot", AsyncMock(return_value=b"changed photo"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/garden/{capture.id}/identification/accept"
        assert (await client.post(path)).status_code == 409
        monkeypatch.setattr(garden_capture_service, "snapshot", AsyncMock(return_value=b"photo"))
        assert (await client.post(path)).status_code == 200
    async with get_db() as db:
        assert (await GardenRepository(db).get(capture.id)).identification.review == "accepted"
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == before


@pytest.mark.asyncio
async def test_human_rejection_erases_species_and_late_result_cannot_resurrect_it():
    await garden_capture_service.process(event())
    async with get_db() as db:
        repository = GardenRepository(db)
        capture = (await repository.list("pending", 20, 0))[0]
        capture = await repository.review(capture.id, "confirmed")
        assert await repository.save_identification(capture, identification())
        original = await repository.get(capture.id)
        await repository.block(capture.frigate_event, create=False)
        assert not await repository.save_identification(original, identification())
        assert await (await db.execute("SELECT COUNT(*) FROM garden_identifications")).fetchone() == (0,)


@pytest_asyncio.fixture
async def garden_inference(monkeypatch, tmp_path):
    from app.repositories.garden_catalog import read_shipped_package
    from app.services.garden_identification import GardenIdentificationService

    original_country = settings.location.country
    settings.location.country = "GB"
    raw, checksum = read_shipped_package()
    bundle = json.loads(raw)
    bundle.update(package_sha256=checksum, bindings={t["id"]: i + 1 for i, t in enumerate(bundle["outputs"])})
    service = GardenIdentificationService()
    service.models = tmp_path
    service.model_path("4.0.3b").touch()
    monkeypatch.setattr(service.catalog, "load", lambda: bundle)
    monkeypatch.setattr(
        "app.services.garden_identification.garden_inference_pressure", lambda: {"live": {}, "background": {}}
    )
    monkeypatch.setattr(
        "app.services.garden_identification.frigate_client.get_event",
        AsyncMock(
            return_value={
                "camera": "patio",
                "label": "cat",
                "data": {"box": [0.1, 0.2, 0.3, 0.4]},
            }
        ),
    )
    monkeypatch.setattr(garden_capture_service, "snapshot", AsyncMock(return_value=b"photo"))
    fox = next(i for i, t in enumerate(bundle["outputs"]) if t["ranks"][3:] == ["vulpes", "vulpes"])
    others = [i for i in range(6) if i != fox][:4]
    native = {
        "predictions": [[fox, 0.9], *[[i, 0.01] for i in others]],
        "devices": ["CPUExecutionProvider"],
        "frame_size": [640, 360],
    }
    process = AsyncMock()
    process.returncode = 0
    process.communicate = AsyncMock(side_effect=lambda _: (b"GARDEN_RESULT:" + json.dumps(native).encode(), b""))
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr("app.services.garden_identification.asyncio.create_subprocess_exec", launch)
    await garden_capture_service.process(event())
    async with get_db() as db:
        repository = GardenRepository(db)
        capture = (await repository.list("pending", 20, 0))[0]
        capture = await repository.review(capture.id, "confirmed")
    yield service, capture, launch, native
    settings.location.country = original_country


@pytest.mark.asyncio
async def test_explicit_suggestion_uses_catalogue_country_and_private_disposable_worker(garden_inference):
    from app.models.garden import GardenIdentifyRequest

    service, capture, launch, _ = garden_inference
    async with get_db() as db:
        before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
    await service.identify(capture.id, GardenIdentifyRequest())
    launch.assert_awaited_once()
    async with get_db() as db:
        result = (await GardenRepository(db).get(capture.id)).identification
        assert result.country == "GBR" and result.review == "unreviewed"
        assert result.outcome == "suggestion" and result.rank == "species"
        assert result.species_id and result.package_sha256
        assert result.input_kind == "whole_image" and result.box_xywh is None
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == before
    assert not service.busy


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["bird", "country", "pending", "crop"])
async def test_unavailable_or_unsafe_suggestion_never_launches_native_work(garden_inference, monkeypatch, reason):
    from fastapi import HTTPException
    from app.models.garden import GardenIdentifyRequest

    service, capture, launch, _ = garden_inference
    request = GardenIdentifyRequest()
    if reason == "bird":
        monkeypatch.setattr(
            "app.services.garden_identification.garden_inference_pressure",
            lambda: {"live": {"queued": 1}, "background": {}},
        )
    elif reason == "country":
        settings.location.country = "Unknown country"
    elif reason == "pending":
        async with get_db() as db:
            await GardenRepository(db).review(capture.id, "pending")
    else:
        request.variant = "4.0.3a"
        service.model_path("4.0.3a").touch()
        monkeypatch.setattr(
            "app.services.garden_identification.frigate_client.get_event",
            AsyncMock(return_value={"camera": "patio", "label": "cat", "data": {"box": [10, 20, 30, 40]}}),
        )
    with pytest.raises(HTTPException) as failure:
        await service.identify(capture.id, request)
    assert failure.value.status_code == 409
    launch.assert_not_awaited()
    assert not service.busy


@pytest.mark.asyncio
async def test_human_model_result_removes_capture_instead_of_persisting_species(garden_inference):
    from fastapi import HTTPException
    from app.models.garden import GardenIdentifyRequest
    from app.repositories.garden_catalog import read_shipped_package

    service, capture, _, native = garden_inference
    raw, _ = read_shipped_package()
    human = next(i for i, t in enumerate(json.loads(raw)["outputs"]) if t["name"] == "human")
    native["predictions"][0][0] = human
    with pytest.raises(HTTPException) as failure:
        await service.identify(capture.id, GardenIdentifyRequest())
    assert failure.value.status_code == 404
    async with get_db() as db:
        assert await GardenRepository(db).get(capture.id) is None
        assert await (await db.execute("SELECT COUNT(*) FROM garden_identifications")).fetchone() == (0,)


@pytest.mark.asyncio
async def test_dismissing_animal_presence_also_revokes_identification_confirmation():
    await garden_capture_service.process(event())
    async with get_db() as db:
        repository = GardenRepository(db)
        capture = (await repository.list("pending", 20, 0))[0]
        capture = await repository.review(capture.id, "confirmed")
        assert await repository.save_identification(capture, identification())
        assert await repository.review_identification(capture.id, "accepted")
        assert (await repository.review(capture.id, "dismissed")).identification.review == "dismissed"
        assert (await repository.review(capture.id, "pending")).identification.review == "dismissed"
