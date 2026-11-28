"""A finished video reading is compared with the capture's snapshot reading, by catalogue species (#804)."""

import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import INITIAL_LABEL_SOURCE_FRIGATE_SUBLABEL, Detection, DetectionRepository
from app.services import detection_service as detection_module
from app.services.detection_service import DetectionService
from app.services.species_catalog_resolver import ShadowResolution

MODEL_SHA = "a" * 64
REGIONAL_SHA = "b" * 64
ARTIFACT_ID = 7
CARRION_CROW, MAGPIE, GREAT_TIT, BLUE_TIT, WOODPECKER = 201, 202, 203, 204, 205
OUTPUTS = {
    MODEL_SHA: {
        10: ("Corvus corone", CARRION_CROW),
        11: ("Pica pica", MAGPIE),
        12: ("Parus major", GREAT_TIT),
        13: ("Cyanistes caeruleus", BLUE_TIT),
        14: ("Dendrocopos major", WOODPECKER),
    },
    # A regional model that cannot name a Carrion Crow.
    REGIONAL_SHA: {0: ("Pica pica", MAGPIE), 1: ("Cyanistes caeruleus", BLUE_TIT)},
}


class FakeCatalogue:
    def model_sha256_for_artifact_id(self, artifact_id):
        return MODEL_SHA if artifact_id == ARTIFACT_ID else None

    def species_outputs(self, model_sha256):
        outputs = OUTPUTS.get(model_sha256)
        return None if outputs is None else {index: species for index, (_label, species) in outputs.items()}

    def cached_output_species_id(self, model_sha256, output_index, label):
        entry = OUTPUTS.get(model_sha256, {}).get(output_index)
        return entry[1] if entry and entry[0].casefold() == str(label).strip().casefold() else None

    def shadow_resolve(self, model_sha256, output_index, scientific_name, event_id=None):
        return ShadowResolution(verdict="unavailable")


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(detection_module, "species_catalog_resolver", FakeCatalogue())
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "min_confidence", 0.4)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])
    monkeypatch.setattr(settings.classification, "display_common_names", False)
    monkeypatch.setattr(sys.modules["app.services.classifier_service"], "_classifier_instance", SimpleNamespace())
    monkeypatch.setattr(
        detection_module.taxonomy_service,
        "get_names",
        AsyncMock(side_effect=lambda name, db=None: {"scientific_name": name, "common_name": None, "taxa_id": None}),
    )
    from app.services.audio.audio_service import audio_service
    from app.services.garden_domestic_service import garden_domestic_service

    monkeypatch.setattr(audio_service, "correlate_species", AsyncMock(return_value=(False, None, None)))
    monkeypatch.setattr(garden_domestic_service, "move_renamed_detection", AsyncMock())
    monkeypatch.setattr(detection_module.broadcaster, "broadcast", AsyncMock())
    monkeypatch.setattr(DetectionService, "is_known_nonbird", AsyncMock(return_value=False))
    return DetectionService(SimpleNamespace())


async def _seed(event_id, label, score, output_index, *, artifact_id=ARTIFACT_ID, label_source=None):
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=datetime(2026, 11, 20, 9, 30),
                detection_index=output_index,
                score=score,
                display_name=label,
                category_name=label,
                scientific_name=label,
                frigate_event=event_id,
                camera_name="feeder",
                model_artifact_id=artifact_id,
                model_output_index=output_index,
            )
        )
        if label_source:
            await db.execute(
                """UPDATE detection_initial_classifications SET label_source = ?
                   WHERE detection_id = (SELECT id FROM detections WHERE frigate_event = ?)""",
                (label_source, event_id),
            )
        await db.commit()


async def _stored(event_id):
    async with get_db() as db:
        return await DetectionRepository(db).get_by_frigate_event(event_id)


async def _video(service, event_id, label, score, index, *, model_sha256=MODEL_SHA, **kwargs):
    return await service.apply_video_result(
        event_id, label, score, index, video_model_sha256=model_sha256, video_input_source="model_crop", **kwargs
    )


@pytest.mark.asyncio
async def test_a_video_reading_of_another_bird_is_flagged_and_the_name_kept(pipeline):
    await _seed("crow-magpie", "Corvus corone", 0.98, 10)

    await _video(pipeline, "crow-magpie", "Pica pica", 0.68, 11)

    stored = await _stored("crow-magpie")
    assert stored.reading_agreement == "disagree"
    assert stored.category_name == "Corvus corone"
    assert stored.video_classification_label == "Pica pica"
    assert stored.snapshot_reading == {
        "display_name": "Corvus corone",
        "category_name": "Corvus corone",
        "scientific_name": "Corvus corone",
        "common_name": None,
        "score": pytest.approx(0.98),
    }


@pytest.mark.asyncio
async def test_a_promoted_video_reading_still_records_that_the_snapshot_disagreed(pipeline):
    await _seed("tit-swap", "Parus major", 0.6, 12)

    await _video(pipeline, "tit-swap", "Cyanistes caeruleus", 0.92, 13)

    stored = await _stored("tit-swap")
    assert stored.category_name == "Cyanistes caeruleus"
    assert stored.reading_agreement == "disagree"
    assert stored.snapshot_reading["category_name"] == "Parus major"
    assert stored.snapshot_reading["score"] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_a_video_reading_of_the_same_bird_agrees(pipeline):
    await _seed("same-bird", "Pica pica", 0.81, 11)

    await _video(pipeline, "same-bird", "Pica pica", 0.9, 11)

    stored = await _stored("same-bird")
    assert stored.reading_agreement == "agree"
    assert stored.snapshot_reading is None


@pytest.mark.asyncio
async def test_running_the_same_video_reading_again_changes_nothing(pipeline):
    await _seed("rerun", "Corvus corone", 0.98, 10)

    await _video(pipeline, "rerun", "Pica pica", 0.68, 11)
    first = await _stored("rerun")
    await _video(pipeline, "rerun", "Pica pica", 0.68, 11)
    second = await _stored("rerun")

    assert second.reading_agreement == first.reading_agreement == "disagree"
    assert second.category_name == first.category_name == "Corvus corone"
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM detections WHERE frigate_event = 'rerun'") as cursor:
            assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_a_later_video_reading_replaces_the_earlier_comparison(pipeline):
    await _seed("second-run", "Corvus corone", 0.98, 10)

    await _video(pipeline, "second-run", "Pica pica", 0.68, 11)
    await _video(pipeline, "second-run", "Corvus corone", 0.95, 10)

    stored = await _stored("second-run")
    assert stored.reading_agreement == "agree"
    assert stored.snapshot_reading is None


@pytest.mark.asyncio
async def test_a_video_reading_below_the_naming_floor_is_not_a_disagreement(pipeline):
    await _seed("weak-video", "Corvus corone", 0.98, 10)

    await _video(pipeline, "weak-video", "Pica pica", 0.3, 11)

    assert (await _stored("weak-video")).reading_agreement == "cannot_compare"


@pytest.mark.asyncio
async def test_a_video_model_that_cannot_name_the_snapshot_species_cannot_disagree(pipeline):
    await _seed("regional", "Corvus corone", 0.98, 10)

    await _video(pipeline, "regional", "Pica pica", 0.9, 0, model_sha256=REGIONAL_SHA)

    assert (await _stored("regional")).reading_agreement == "cannot_compare"


@pytest.mark.asyncio
async def test_a_label_borrowed_from_frigate_is_not_a_snapshot_reading(pipeline):
    await _seed("borrowed", "Corvus corone", 0.98, 10, label_source=INITIAL_LABEL_SOURCE_FRIGATE_SUBLABEL)

    await _video(pipeline, "borrowed", "Pica pica", 0.68, 11)

    assert (await _stored("borrowed")).reading_agreement == "cannot_compare"


@pytest.mark.asyncio
async def test_a_snapshot_reading_without_a_known_model_cannot_be_compared(pipeline):
    await _seed("no-provenance", "Corvus corone", 0.98, 10, artifact_id=None)

    await _video(pipeline, "no-provenance", "Pica pica", 0.68, 11)

    assert (await _stored("no-provenance")).reading_agreement == "cannot_compare"


@pytest.mark.asyncio
async def test_a_crop_refinement_is_not_a_video_reading_and_leaves_the_comparison_alone(pipeline):
    await _seed("hq-only", "Corvus corone", 0.98, 10)
    await _video(pipeline, "hq-only", "Pica pica", 0.68, 11)

    await _video(pipeline, "hq-only", "Corvus corone", 0.99, 10, persist_video_result=False)

    assert (await _stored("hq-only")).reading_agreement == "disagree"


@pytest.mark.asyncio
async def test_a_catalogue_that_fails_leaves_the_readings_uncompared_and_the_reading_recorded(pipeline, monkeypatch):
    await _seed("catalogue-down", "Corvus corone", 0.98, 10)

    def broken(_model_sha256):
        raise OSError("catalogue unreadable")

    monkeypatch.setattr(detection_module.species_catalog_resolver, "species_outputs", broken)
    await _video(pipeline, "catalogue-down", "Pica pica", 0.68, 11)

    stored = await _stored("catalogue-down")
    assert stored.reading_agreement is None
    assert stored.video_classification_status == "completed"
    assert stored.video_classification_label == "Pica pica"
