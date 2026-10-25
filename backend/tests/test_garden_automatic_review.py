"""Automatic presence checks reject evidence, never override an owner's review."""

import hashlib
import time
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.models.garden_motion import MotionSource
from app.repositories.garden_repository import GardenRepository


def test_complete_presence_mass_distinguishes_empty_from_unresolved_and_other_animals():
    from app.services.garden_visitors import Taxon, animal_presence_prediction

    outputs = [
        Taxon("bird", "bird", ("aves", "", "", "", "")),
        Taxon("animal", "animal", ("", "", "", "", "")),
        Taxon("reptile", "", ("reptilia", "", "", "", "")),
        Taxon("human", "human", ("mammalia", "primates", "hominidae", "homo", "sapiens")),
        Taxon("blank", "blank", ("", "", "", "", "")),
        Taxon("vehicle", "vehicle", ("", "", "", "", "")),
        Taxon("unknown", "", ("", "", "", "", "")),
    ]
    for index, expected in [
        (0, "bird"),
        (1, "animal"),
        (2, "animal"),
        (3, "human_rejected"),
        (4, "non_animal"),
        (5, "non_animal"),
        (6, "uncertain"),
    ]:
        scores = [0.0] * len(outputs)
        scores[index] = 1.0
        result = animal_presence_prediction(scores, outputs, expected_width=len(outputs))
        assert result.outcome == expected
        assert sum(result.mass.values()) == pytest.approx(1)
    result = animal_presence_prediction([0.18, 0, 0, 0.01, 0.75, 0.05, 0.01], outputs, expected_width=7)
    assert result.outcome == "non_animal"
    assert result.mass["non_animal"] == pytest.approx(0.8)
    assert animal_presence_prediction([0.2, 0, 0, 0, 0.79, 0, 0.01], outputs, expected_width=7).outcome == "uncertain"
    with pytest.raises(ValueError):
        animal_presence_prediction([float("nan")] * 7, outputs, expected_width=7)


@pytest_asyncio.fixture
async def context(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.services import garden_automatic_review as module
    from app.services.garden_identification import GardenIdentificationService

    monkeypatch.setattr(settings.system, "beta_garden_animals", True)
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM garden_captures")
        await db.commit()
        start = time.time() - 60
        source = MotionSource(
            camera="patio",
            clip_start=start,
            clip_end=start + 10,
            frame_index=1,
            frame_offset=1,
            clip_sha256="a" * 64,
            image_sha256=hashlib.sha256(b"photo").hexdigest(),
            detector_sha256="b" * 64,
            detector_score=0.9,
            box_xywh=(0.1, 0.1, 0.2, 0.2),
        )
        capture_id = await GardenRepository(db).capture_motion(source, b"photo")
    identification = GardenIdentificationService()
    identification.models = tmp_path
    for variant in ["4.0.3a", "4.0.3b"]:
        identification.model_path(variant).write_bytes(b"model")
    bundle = {
        "model_sha256": {v: hashlib.sha256(b"model").hexdigest() for v in ["4.0.3a", "4.0.3b"]},
        "package_sha256": "c" * 64,
    }
    monkeypatch.setattr(identification.catalog, "load", lambda: bundle)
    monkeypatch.setattr(module, "garden_identification_service", identification)
    monkeypatch.setattr(module, "garden_inference_pressure", lambda: {"live": {}, "background": {}})
    monkeypatch.setattr(module.garden_motion_service, "_camera_clear", AsyncMock(return_value=True))
    native = AsyncMock(
        return_value={
            "assessment": {
                "mass": {"bird": 0, "animal": 0.01, "non_animal": 0.98, "human": 0.001, "other": 0.009},
                "human_winner": False,
            },
            "devices": ["CPUExecutionProvider"],
            "frame_size": [640, 480],
            "package_sha256": bundle["package_sha256"],
        }
    )
    monkeypatch.setattr(identification, "_run_photo_worker", native)
    service = module.GardenAutomaticReviewService()
    yield SimpleNamespace(
        service=service,
        module=module,
        identification=identification,
        native=native,
        capture_id=capture_id,
        source=source,
    )
    assert not identification.busy
    await close_db()


async def capture(capture_id):
    async with get_db() as db:
        return await GardenRepository(db).get(capture_id)


@pytest.mark.asyncio
async def test_pending_detector_crop_is_checked_without_an_owner_click_and_rejection_is_restorable(context):
    c = context
    async with get_db() as db:
        before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "dismissed"
    assert result.automatic_check.outcome == "non_animal"
    assert result.automatic_check.image_sha256 == c.source.image_sha256
    assert result.automatic_check.box_xywh == c.source.box_xywh
    assert result.identification is None
    assert c.native.call_args.args[1]["provider"] == "cpu"
    assert c.native.call_args.args[1]["box"] == list(c.source.box_xywh)
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.motion_photo(c.capture_id) == b"photo"
        await repo.review(c.capture_id, "pending")
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == before
    await c.service.process_once()
    assert (await capture(c.capture_id)).status == "pending"
    assert (await capture(c.capture_id)).automation_overridden
    assert c.native.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mass",
    [
        {"bird": 0, "animal": 0.98, "non_animal": 0.01, "human": 0.001, "other": 0.009},
        {"bird": 0, "animal": 0.4, "non_animal": 0.4, "human": 0.001, "other": 0.199},
        {"bird": 0, "animal": 0, "non_animal": 0, "human": 0, "other": 1},
    ],
)
async def test_animals_and_uncertain_checks_remain_pending_without_species_confirmation(context, monkeypatch, mass):
    c = context
    # Naming is covered with the real catalogue below; this keeps presence-only behaviour pinned.
    monkeypatch.setattr(settings.frigate, "garden_automatic_naming", False)
    c.native.return_value["assessment"]["mass"] = mass
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "pending" and result.identification is None
    assert result.automatic_check.outcome in {"animal", "uncertain"}
    await c.service.process_once()
    assert c.native.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["confirmed", "dismissed", "restore_cycle", "person", "camera", "beta", "bird"])
async def test_late_native_result_cannot_overwrite_owner_privacy_or_priority_changes(context, monkeypatch, change):
    c = context
    original = c.native.return_value

    async def native(*args):
        async with get_db() as db:
            repo = GardenRepository(db)
            if change in {"confirmed", "dismissed"}:
                await repo.review(c.capture_id, change)
            elif change == "restore_cycle":
                await repo.review(c.capture_id, "dismissed")
                await repo.review(c.capture_id, "pending")
            elif change == "person":
                await repo.block_capture(c.capture_id)
        if change == "camera":
            monkeypatch.setattr(settings.frigate, "garden_cameras", [])
        if change == "beta":
            monkeypatch.setattr(settings.system, "beta_garden_animals", False)
        if change == "bird":
            monkeypatch.setattr(
                c.module, "garden_inference_pressure", lambda: {"live": {"queued": 1}, "background": {}}
            )
        return original

    c.native.side_effect = native
    await c.service.process_once()
    result = await capture(c.capture_id)
    if change == "person":
        assert result is None
    else:
        assert result.status == (change if change in {"confirmed", "dismissed"} else "pending")
        assert result.automatic_check is None


@pytest.mark.asyncio
async def test_native_failure_stays_visible_and_does_not_spin_or_reject(context):
    c = context
    c.native.side_effect = TimeoutError("private path must not be persisted")
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "pending" and result.automatic_check.outcome == "unavailable"
    assert "private path" not in result.automatic_check.model_dump_json()
    await c.service.process_once()
    assert c.native.await_count == 1


@pytest.mark.asyncio
async def test_speciesnet_human_evidence_removes_media_instead_of_retaining_a_rejected_photo(context):
    c = context
    c.native.return_value["assessment"]["mass"] = {
        "bird": 0,
        "animal": 0.88,
        "non_animal": 0.01,
        "human": 0.1,
        "other": 0.01,
    }
    await c.service.process_once()
    assert await capture(c.capture_id) is None
    async with get_db() as db:
        assert await GardenRepository(db).motion_photo(c.capture_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["beta", "camera", "bird", "camera_pressure", "busy", "quarantine"])
async def test_automatic_checks_do_not_start_when_garden_or_hardware_is_unavailable(context, monkeypatch, reason):
    c = context
    if reason == "beta":
        monkeypatch.setattr(settings.system, "beta_garden_animals", False)
    if reason == "camera":
        monkeypatch.setattr(settings.frigate, "garden_cameras", [])
    if reason == "bird":
        monkeypatch.setattr(c.module, "garden_inference_pressure", lambda: None)
    if reason == "camera_pressure":
        monkeypatch.setattr(c.module.garden_motion_service, "_camera_clear", AsyncMock(return_value=False))
    if reason == "busy":
        c.identification.busy = True
    if reason == "quarantine":
        c.identification.error = "Worker cleanup failed"
    await c.service.process_once()
    c.native.assert_not_awaited()
    c.identification.busy = False
    assert (await capture(c.capture_id)).status == "pending"


@pytest.mark.asyncio
async def test_bird_only_capture_is_dismissed_without_becoming_a_bird_detection(context):
    c = context
    c.native.return_value["assessment"]["mass"] = {
        "bird": 0.98,
        "animal": 0.01,
        "human": 0.001,
        "non_animal": 0.009,
        "other": 0,
    }
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "dismissed" and result.automatic_check.outcome == "bird"
    assert result.reviewed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["probabilities", "nonfinite", "provider", "mapping", "human_flag", "image_changed"])
async def test_invalid_or_changed_native_evidence_never_rejects_a_photo(context, monkeypatch, fault):
    c = context
    if fault == "probabilities":
        c.native.return_value["assessment"]["mass"]["other"] = 0.5
    if fault == "nonfinite":
        c.native.return_value["assessment"]["mass"]["animal"] = float("nan")
    if fault == "provider":
        c.native.return_value["devices"] = ["CUDAExecutionProvider"]
    if fault == "mapping":
        c.native.return_value["package_sha256"] = "d" * 64
    if fault == "human_flag":
        c.native.return_value["assessment"]["human_winner"] = "false"
    if fault == "image_changed":
        monkeypatch.setattr(c.module.garden_capture_service, "snapshot", AsyncMock(side_effect=[b"photo", b"changed"]))
    await c.service.process_once()
    assert (await capture(c.capture_id)).status == "pending"


@pytest.mark.asyncio
async def test_two_concurrent_cycles_share_the_single_garden_admission_slot(context):
    import asyncio

    c = context
    entered, resume = asyncio.Event(), asyncio.Event()
    response = c.native.return_value

    async def native(*args):
        entered.set()
        await resume.wait()
        return response

    c.native.side_effect = native
    task = asyncio.create_task(c.service.process_once())
    try:
        await entered.wait()
        await c.service.process_once()
        assert c.native.await_count == 1
    finally:
        resume.set()
        await task


@pytest.mark.asyncio
async def test_unavailable_checks_retry_after_cooldown_even_after_service_restart(context):
    from datetime import timedelta
    from app.utils.api_datetime import utc_naive_now

    c = context
    c.native.side_effect = ValueError("model unavailable")
    await c.service.process_once()
    async with get_db() as db:
        await db.execute(
            "UPDATE garden_automatic_checks SET result_json=json_set(result_json,'$.checked_at',?)",
            ((utc_naive_now() - timedelta(minutes=6)).isoformat(),),
        )
        await db.commit()
    c.native.side_effect = None
    await c.module.GardenAutomaticReviewService().process_once()
    assert (await capture(c.capture_id)).status == "dismissed"
    assert c.native.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("box", [[0.1, 0.2, 0.3, 0.4], None, [0.9, 0.9, 0.5, 0.5]])
async def test_frigate_event_uses_exact_snapshot_box_and_never_falls_back_to_whole_image(context, monkeypatch, box):
    from app.utils.api_datetime import utc_naive_now

    c = context
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.block_capture(c.capture_id)
        await repo.capture("automatic-cat", "patio", "cat", utc_naive_now().isoformat(), True)
        original = (await repo.list("pending", 10, 0))[0]
    monkeypatch.setattr(
        c.module.frigate_client,
        "get_event",
        AsyncMock(return_value={"camera": "patio", "label": "cat", "data": {"box": box}}),
    )
    monkeypatch.setattr(c.module.frigate_client, "get_snapshot", AsyncMock(return_value=b"photo"))
    await c.service.process_once()
    result = await capture(original.id)
    if box == [0.1, 0.2, 0.3, 0.4]:
        assert result.status == "dismissed"
        assert c.native.call_args.args[1]["box"] == box
        assert c.native.call_args.args[1]["variant"] == "4.0.3a"
    else:
        assert result.status == "pending" and result.automatic_check.outcome == "unavailable"
        c.native.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_confirmed_or_batch_restored_capture_is_never_selected(context):
    c = context
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.review_batch([c.capture_id], "dismiss")
        await repo.review_batch([c.capture_id], "restore")
    await c.service.process_once()
    c.native.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["person", "box"])
async def test_late_frigate_metadata_change_cannot_publish_an_old_crop_result(context, monkeypatch, changed):
    from app.utils.api_datetime import utc_naive_now

    c = context
    async with get_db() as db:
        repo = GardenRepository(db)
        await repo.block_capture(c.capture_id)
        await repo.capture("changing-cat", "patio", "cat", utc_naive_now().isoformat(), True)
        original = (await repo.list("pending", 10, 0))[0]
    metadata = {"camera": "patio", "label": "cat", "data": {"box": [0.1, 0.2, 0.3, 0.4]}}
    monkeypatch.setattr(c.module.frigate_client, "get_event", AsyncMock(side_effect=lambda _: metadata))
    monkeypatch.setattr(c.module.frigate_client, "get_snapshot", AsyncMock(return_value=b"photo"))
    native_result = c.native.return_value

    async def native(*args):
        if changed == "person":
            metadata["label"] = "person"
        else:
            metadata["data"]["box"] = [0.5, 0.5, 0.2, 0.2]
        return native_result

    c.native.side_effect = native
    await c.service.process_once()
    result = await capture(original.id)
    if changed == "person":
        assert result is None
    else:
        assert result.status == "pending" and result.automatic_check is None


@pytest.mark.asyncio
async def test_automatic_result_is_visible_only_in_private_garden_api(context, monkeypatch):
    import httpx
    from app.main import app

    c = context
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    await c.service.process_once()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/garden", params={"status": "dismissed"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        item = response.json()["items"][0]
        assert item["automatic_check"]["outcome"] == "non_animal" and item["snapshot_url"]
        monkeypatch.setattr(settings.public_access, "enabled", True)
        monkeypatch.setattr(settings.auth, "enabled", True)
        assert (await client.get("/api/garden", params={"status": "dismissed"})).status_code in {401, 403}


DOMESTIC_CAT = 1806
JUNGLE_CAT = 893
HUMAN = 916


@pytest_asyncio.fixture
async def naming(context, monkeypatch):
    """The automatic check names a confident animal from the same crop pass, with the real catalogue."""
    import json

    from app.repositories.garden_catalog import read_shipped_package

    raw, checksum = read_shipped_package()
    bundle = json.loads(raw)
    bundle.update(
        package_sha256=checksum,
        model_sha256={v: hashlib.sha256(b"model").hexdigest() for v in ["4.0.3a", "4.0.3b"]},
        bindings={t["id"]: i + 1 for i, t in enumerate(bundle["outputs"])},
    )
    monkeypatch.setattr(context.identification.catalog, "load", lambda: bundle)
    monkeypatch.setattr(settings.location, "country", "GB")
    monkeypatch.setattr(settings.frigate, "garden_automatic_naming", True)
    monkeypatch.setattr(settings.frigate, "garden_naming_threshold", 0.8)
    context.native.return_value = {
        "assessment": {
            "mass": {"bird": 0.0, "animal": 0.97, "non_animal": 0.01, "human": 0.001, "other": 0.019},
            "human_winner": False,
        },
        "predictions": [[DOMESTIC_CAT, 0.93], [JUNGLE_CAT, 0.02], [1, 0.01], [2, 0.01], [3, 0.005]],
        "devices": ["CPUExecutionProvider"],
        "frame_size": [640, 480],
        "package_sha256": checksum,
    }
    context.bundle = bundle
    return context


@pytest.mark.asyncio
async def test_confident_animal_is_confirmed_and_named_automatically_from_the_same_crop(naming):
    c = naming
    async with get_db() as db:
        birds_before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "confirmed"
    assert result.reviewed_at is None and not result.automation_overridden
    assert result.automatic_check.outcome == "animal"
    named = result.identification
    assert named.automatic and named.review == "accepted" and named.outcome == "suggestion"
    assert named.name == "domestic cat" and named.species_id == DOMESTIC_CAT + 1
    assert named.score == pytest.approx(0.93) and named.country == "GBR"
    assert named.input_kind == "tracked_crop" and named.box_xywh == c.source.box_xywh
    assert named.image_sha256 == c.source.image_sha256 and named.variant == "4.0.3a"
    # One native pass: naming reuses the presence check's output.
    assert c.native.await_count == 1
    async with get_db() as db:
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == birds_before


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["below_threshold", "naming_off", "no_country", "unbound"])
async def test_animal_stays_in_review_when_it_cannot_be_named_honestly(naming, monkeypatch, reason):
    c = naming
    if reason == "below_threshold":
        c.native.return_value["predictions"][0][1] = 0.79
    elif reason == "naming_off":
        monkeypatch.setattr(settings.frigate, "garden_automatic_naming", False)
    elif reason == "no_country":
        monkeypatch.setattr(settings.location, "country", None)
    else:
        c.bundle["bindings"][c.bundle["outputs"][DOMESTIC_CAT]["id"]] = None
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == ("dismissed" if reason == "below_threshold" else "pending")
    assert result.identification is None
    assert result.automatic_check.outcome == "animal"


@pytest.mark.asyncio
async def test_a_species_outside_the_country_is_named_by_its_plausible_group(naming):
    c = naming
    c.native.return_value["predictions"] = [[JUNGLE_CAT, 0.9], [DOMESTIC_CAT, 0.05], [1, 0.01], [2, 0.01], [3, 0.005]]
    await c.service.process_once()
    named = (await capture(c.capture_id)).identification
    assert named.automatic and named.geofenced
    # Jungle cat is not plausible in Great Britain; only its own ancestry may stand in.
    assert named.name == "cat family" and named.rank != "species"


@pytest.mark.asyncio
async def test_person_evidence_in_the_naming_output_removes_the_capture(naming):
    c = naming
    c.native.return_value["predictions"] = [[DOMESTIC_CAT, 0.85], [HUMAN, 0.12], [1, 0.01], [2, 0.01], [3, 0.005]]
    await c.service.process_once()
    assert await capture(c.capture_id) is None
    async with get_db() as db:
        assert await GardenRepository(db).motion_photo(c.capture_id) is None
        assert await (await db.execute("SELECT COUNT(*) FROM garden_identifications")).fetchone() == (0,)


@pytest.mark.asyncio
async def test_owner_review_during_naming_wins_and_later_dismissal_sticks(naming, monkeypatch):
    c = naming
    original = c.native.side_effect

    async def owner_dismisses_mid_check(*args):
        async with get_db() as db:
            await GardenRepository(db).review(c.capture_id, "dismissed")
        return c.native.return_value

    c.native.side_effect = owner_dismisses_mid_check
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "dismissed" and result.identification is None
    c.native.side_effect = original


@pytest.mark.asyncio
async def test_dismissing_an_automatically_named_capture_is_final(naming):
    c = naming
    await c.service.process_once()
    async with get_db() as db:
        await GardenRepository(db).review(c.capture_id, "dismissed")
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "dismissed" and result.automation_overridden
    assert result.identification.review == "dismissed"
    assert c.native.await_count == 1


@pytest.mark.asyncio
async def test_malformed_naming_output_never_confirms_or_names(naming):
    c = naming
    c.native.return_value["predictions"] = [[DOMESTIC_CAT, 0.93]]
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "pending" and result.identification is None
    assert result.automatic_check.outcome == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,devices",
    [("intel_npu", ["NPU"]), ("intel_gpu", ["GPU.0"]), ("cuda", ["CUDAExecutionProvider", "CPUExecutionProvider"])],
)
async def test_automatic_review_persists_the_qualified_execution_device(context, monkeypatch, provider, devices):
    c = context
    native = dict(c.native.return_value, devices=devices)
    runtime = AsyncMock()
    runtime.run.return_value = (native, provider)
    monkeypatch.setattr(c.service, "runtime", runtime, raising=False)
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.automatic_check.devices == devices
    assert result.status == "dismissed"
    runtime.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_automatic_check_explains_actual_cpu_fallback(context, monkeypatch):
    c = context
    runtime = AsyncMock()
    runtime.run.return_value = (dict(c.native.return_value), "cpu")
    monkeypatch.setattr(c.service, "runtime", runtime)
    monkeypatch.setattr(c.module, "candidate_providers", lambda: ("intel_npu", "cpu"), raising=False)
    await c.service.process_once()
    assert "CPU fallback" in c.identification.automatic_message


@pytest.mark.asyncio
async def test_low_confidence_is_soft_dismissed_with_score_and_device_evidence(naming):
    c = naming
    c.native.return_value["predictions"][0][1] = 0.79
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "dismissed"
    assert not result.automation_overridden
    assert result.automatic_check.decision_reason == "below_threshold"
    assert result.automatic_check.naming_score == pytest.approx(0.79)
    assert result.automatic_check.naming_threshold == 0.8
    assert result.automatic_check.execution.provider == "cpu"
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.motion_photo(c.capture_id) == b"photo"
        await repo.review(c.capture_id, "pending")
    await c.service.process_once()
    assert (await capture(c.capture_id)).status == "pending"
    assert c.native.await_count == 1


@pytest.mark.asyncio
async def test_old_unreviewed_uncertain_checks_are_reconsidered_once(naming):
    c = naming
    c.native.return_value["predictions"][0][1] = 0.3
    c.native.return_value["assessment"]["mass"] = {
        "bird": 0.2,
        "animal": 0.4,
        "human": 0.0,
        "non_animal": 0.3,
        "other": 0.1,
    }
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "dismissed"
    assert result.automatic_check.decision_reason == "below_threshold"
    # Reproduce an old successful pending assessment, before the automatic policy existed.
    async with get_db() as db:
        await db.execute("UPDATE garden_captures SET status='pending' WHERE id=?", (c.capture_id,))
        await db.execute(
            "UPDATE garden_automatic_checks SET result_json=json_remove(result_json,'$.policy_version') WHERE capture_id=?",
            (c.capture_id,),
        )
        await db.commit()
    await c.service.process_once()
    assert (await capture(c.capture_id)).status == "dismissed"
    await c.service.process_once()
    assert c.native.await_count == 2


@pytest.mark.asyncio
async def test_garden_status_reads_completed_execution_after_service_restart(naming):
    c = naming
    await c.service.process_once()
    status = await c.identification.status()
    assert status.last_execution.provider == "cpu"
    assert status.last_execution.model_id == "garden-speciesnet-4.0.3a"
    assert status.last_execution.checked_at.endswith("Z")
    # Legacy records still expose their actual devices without inventing a fallback.
    async with get_db() as db:
        await db.execute(
            "UPDATE garden_automatic_checks SET result_json=json_remove(result_json,'$.execution') WHERE capture_id=?",
            (c.capture_id,),
        )
        await db.commit()
    status = await c.identification.status()
    assert status.last_execution.devices == ["CPUExecutionProvider"]
    assert status.last_execution.fallback_reason is None


@pytest.mark.asyncio
async def test_owner_naming_threshold_is_not_overridden_by_the_coarse_presence_floor(naming, monkeypatch):
    c = naming
    monkeypatch.setattr(settings.frigate, "garden_naming_threshold", 0.7)
    c.native.return_value["assessment"]["mass"] = {
        "bird": 0.1,
        "animal": 0.75,
        "human": 0.0,
        "non_animal": 0.1,
        "other": 0.05,
    }
    c.native.return_value["predictions"][0][1] = 0.73
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "confirmed"
    assert result.identification.automatic
    assert result.identification.score == pytest.approx(0.73)


@pytest.mark.asyncio
async def test_setting_country_resumes_automatic_naming_without_manual_confirmation(naming, monkeypatch):
    c = naming
    monkeypatch.setattr(settings.location, "country", None)
    await c.service.process_once()
    assert (await capture(c.capture_id)).automatic_check.decision_reason == "location_required"
    monkeypatch.setattr(settings.location, "country", "GB")
    await c.service.process_once()
    assert (await capture(c.capture_id)).identification.automatic


@pytest.mark.asyncio
async def test_disabling_automatic_naming_during_inference_prevents_a_late_decision(naming, monkeypatch):
    c = naming

    async def changed(*args):
        monkeypatch.setattr(settings.frigate, "garden_automatic_naming", False)
        return c.native.return_value

    c.native.side_effect = changed
    await c.service.process_once()
    result = await capture(c.capture_id)
    assert result.status == "pending"
    assert result.automatic_check is None


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["named", "dismissed", "unavailable", "person", "stale"])
async def test_automatic_results_invalidate_owner_history_only_after_committed_change(naming, monkeypatch, outcome):
    from app.services.broadcaster import broadcaster

    c = naming
    if outcome == "dismissed":
        c.native.return_value["predictions"][0][1] = 0.6
    elif outcome == "unavailable":
        c.native.side_effect = TimeoutError()
    elif outcome == "person":
        c.native.return_value["assessment"]["human_winner"] = True
    elif outcome == "stale":
        monkeypatch.setattr(GardenRepository, "save_automatic_naming", AsyncMock(return_value=False))
    delivered = []

    async def notify(message):
        saved = await capture(c.capture_id)
        delivered.append((message, saved.status if saved else None))

    monkeypatch.setattr(broadcaster, "broadcast", notify)
    await c.service.process_once()
    expected = {"named": "confirmed", "dismissed": "dismissed", "unavailable": "pending", "person": None}
    assert delivered == ([] if outcome == "stale" else [({"type": "garden_history_changed"}, expected[outcome])])
