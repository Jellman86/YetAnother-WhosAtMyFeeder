"""An automatic snapshot fallback must not take a species from an HQ whole frame its crops dispute."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from app.config import settings
from app.database import get_db
from app.models.classification_evidence import ClassificationEvidence
from app.repositories.detection_repository import Detection, DetectionRepository
from app.services import auto_video_classifier_service as auto
from app.services import video_snapshot_service as photos
from app.utils.api_datetime import utc_naive_now

INGEST_INPUT = ClassificationEvidence(source="frigate_recording_frame", is_cropped=False)
CROP_INPUT = ClassificationEvidence(source="hq_candidate_model_crop", is_cropped=True, supporting_frames=2)


@pytest.fixture(autouse=True)
def classification_settings(monkeypatch):
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])


def _row(name, source_mode, label, score, crop_confidence, frame_index):
    return {
        "candidate_id": name,
        "frame_index": frame_index,
        "frame_offset_seconds": frame_index / 30.0,
        "clip_variant": "recording",
        "source_mode": source_mode,
        "crop_box": [10, 10, 40, 40] if source_mode != "full_frame" else None,
        "crop_confidence": crop_confidence,
        "classifier_label": label,
        "classifier_score": score,
        "ranking_score": score,
        "selected": name == "full-f510",
        "snapshot_source": f"hq_candidate_{source_mode}",
        "image_ref": f"{name}__image",
        "thumbnail_ref": f"{name}__thumb",
    }


# Detection 1564's saved photo choices: every crop reads Columba palumbus, every whole frame
# Pica pica. The frame-510 crops are below the detector floor and the frame-255 crops share a
# frame, so HQ selection could only offer a whole frame as the photo.
PIGEON_CROPS = [
    _row("crop-f510-c1", "model_crop", "Columba palumbus", 0.977, 0.35, 510),
    _row("crop-f510", "model_crop", "Columba palumbus", 0.957, 0.45, 510),
    _row("crop-f255", "model_crop", "Columba palumbus", 0.942, 0.85, 255),
    _row("crop-f255-c1", "model_crop", "Columba palumbus", 0.854, 0.80, 255),
]
MAGPIE_WHOLE_FRAMES = [
    _row("full-f765", "full_frame", "Pica pica", 0.768, None, 765),
    _row("full-f510", "full_frame", "Pica pica", 0.726, 0.45, 510),
    _row("full-f255", "full_frame", "Pica pica", 0.462, 0.85, 255),
]
MAGPIE_CROPS = [
    _row("crop-f255", "model_crop", "Pica pica", 0.91, 0.85, 255),
    _row("crop-f510", "model_crop", "Pica pica", 0.88, 0.80, 510),
]


async def _seed(event_id, *, species, score, classification_input, candidates, snapshot_source):
    display_name, scientific_name = species
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=3775,
                score=score,
                display_name=display_name,
                category_name=scientific_name,
                scientific_name=scientific_name,
                common_name=display_name,
                frigate_event=event_id,
                camera_name="greenhousecam",
                classification_input=classification_input,
            )
        )
        await repo.replace_snapshot_candidates(event_id, candidates)
    await photos.media_cache.cache_snapshot(
        event_id, photos._jpeg(Image.new("RGB", (64, 48), "green")), source=snapshot_source
    )


def _service(monkeypatch, label="Pica pica", score=0.7264):
    service = auto.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_async_background = AsyncMock(
        return_value=[{"label": label, "score": score, "index": 3775}]
    )
    service._update_status = AsyncMock()
    service._save_results = AsyncMock(return_value=True)
    monkeypatch.setattr(auto.broadcaster, "broadcast", AsyncMock())
    monkeypatch.setattr(auto, "reconcile_snapshot_identity", AsyncMock(return_value="replaced"))
    return service


async def _identity(event_id):
    async with get_db() as db:
        detection = await DetectionRepository(db).get_by_frigate_event(event_id)
    return (
        detection.display_name,
        detection.category_name,
        detection.score,
        detection.classification_input.source if detection.classification_input else None,
        detection.video_classification_label,
        detection.video_classification_input_source,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("species", "score", "classification_input"),
    [
        # The live record: ingest named the magpie from an uncropped recording frame.
        (("Eurasian Magpie", "Pica pica"), 0.7245, INGEST_INPUT),
        # A crop-based identification the whole frame would rename.
        (("Common Wood-Pigeon", "Columba palumbus"), 0.942, CROP_INPUT),
    ],
)
async def test_hq_whole_frame_disputed_by_every_crop_does_not_rewrite_the_identification(
    monkeypatch, species, score, classification_input
):
    event_id = f"whole-frame-disputed-{species[1].replace(' ', '-')}"
    await _seed(
        event_id,
        species=species,
        score=score,
        classification_input=classification_input,
        candidates=PIGEON_CROPS + MAGPIE_WHOLE_FRAMES,
        snapshot_source="hq_candidate_full_frame",
    )
    before = await _identity(event_id)
    service = _service(monkeypatch)

    error = await service._classify_from_snapshot(event_id, "greenhousecam")

    assert error == "snapshot_no_usable_result"
    service._save_results.assert_not_awaited()
    service._update_status.assert_awaited_with(event_id, "failed", error="snapshot_no_usable_result", broadcast=True)
    assert await _identity(event_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidates",
    [MAGPIE_CROPS + MAGPIE_WHOLE_FRAMES, MAGPIE_WHOLE_FRAMES, []],
    ids=["crops-agree", "whole-frames-only", "no-photo-choices"],
)
async def test_hq_whole_frame_still_classifies_when_no_crop_disputes_it(monkeypatch, candidates):
    event_id = f"whole-frame-undisputed-{len(candidates)}"
    await _seed(
        event_id,
        species=("Eurasian Magpie", "Pica pica"),
        score=0.7245,
        classification_input=INGEST_INPUT,
        candidates=candidates,
        snapshot_source="hq_candidate_full_frame",
    )
    service = _service(monkeypatch)

    assert await service._classify_from_snapshot(event_id, "greenhousecam") is None

    saved = service._save_results.await_args.args[1]
    assert (saved["label"], saved["input_source"]) == ("Pica pica", "hq_candidate_full_frame")


@pytest.mark.asyncio
async def test_owner_requested_reclassification_of_an_hq_whole_frame_is_not_overruled(monkeypatch):
    event_id = "whole-frame-manual-reclassification"
    await _seed(
        event_id,
        species=("Common Wood-Pigeon", "Columba palumbus"),
        score=0.942,
        classification_input=CROP_INPUT,
        candidates=PIGEON_CROPS + MAGPIE_WHOLE_FRAMES,
        snapshot_source="hq_candidate_full_frame",
    )
    service = _service(monkeypatch)

    assert await service._classify_from_snapshot(event_id, "greenhousecam", manual_tagged=True) is None

    service._save_results.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_cropped_hq_photo_is_not_judged_as_a_whole_frame(monkeypatch):
    event_id = "cropped-photo-with-other-crops"
    await _seed(
        event_id,
        species=("Eurasian Magpie", "Pica pica"),
        score=0.7245,
        classification_input=INGEST_INPUT,
        candidates=PIGEON_CROPS,
        snapshot_source="hq_candidate_model_crop",
    )
    service = _service(monkeypatch)

    assert await service._classify_from_snapshot(event_id, "greenhousecam") is None

    service._save_results.assert_awaited_once()
