from unittest.mock import AsyncMock, Mock

from PIL import Image
import pytest

from app.config import settings
from app.config_models import MediaCacheSettings
from app.services import high_quality_snapshot_service as hq


def test_automatic_multi_bird_scan_defaults_off():
    assert MediaCacheSettings().automatic_multi_bird_scan is False


@pytest.mark.parametrize("include_additional_birds", [False, True])
def test_photo_crops_only_enumerate_additional_birds_when_requested(monkeypatch, include_additional_birds):
    service = hq.HighQualitySnapshotService()
    image = Image.new("RGB", (3840, 2160))
    target = {"crop_image": Image.new("RGB", (300, 300)), "detector_box": (10, 10, 200, 200)}
    single = Mock(return_value=target)
    multiple = Mock(return_value=[target, {**target, "detector_box": (1000, 10, 1200, 200)}])
    monkeypatch.setattr(service, "_crop_candidate_from_bird_model", single)
    monkeypatch.setattr(hq.bird_crop_service, "generate_classification_candidate_crops", multiple)
    monkeypatch.setattr(settings.media_cache, "bird_scan_mode", "intensive")

    result = service._model_crop_images_for_frame(
        image, event_id="event", search_box=(0, 0, 400, 400), include_additional_birds=include_additional_birds
    )

    assert len(result) == (2 if include_additional_birds else 1)
    if include_additional_birds:
        multiple.assert_called_once_with(image, max_crops=8, raise_on_error=True, search_box=(0, 0, 400, 400))
        single.assert_not_called()
    else:
        single.assert_called_once_with(image, event_id="event", search_box=(0, 0, 400, 400))
        multiple.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("include_additional_birds", [False, True])
@pytest.mark.parametrize(
    "classifier_label,crop_confidence,selected",
    [("Cardinalis cardinalis", 0.95, True), ("House Finch", 0.95, False), ("Cardinalis cardinalis", 0.05, False)],
)
async def test_photo_presence_survives_without_optional_count_work(
    monkeypatch, include_additional_birds, classifier_label, crop_confidence, selected
):
    service = hq.HighQualitySnapshotService()
    target = {
        "candidate_id": "target",
        "source_mode": "model_crop",
        "clip_variant": "event",
        "frame_index": 5,
        "frame_width": 3840,
        "frame_height": 2160,
        "image_width": 400,
        "image_height": 400,
        "crop_box": (100, 100, 500, 500),
        "detector_box": (150, 150, 450, 450),
        "crop_confidence": crop_confidence,
        "classifier_label": classifier_label,
        "classifier_score": 0.95,
        "ranking_score": 0.95,
    }
    full = {
        **target,
        "candidate_id": "full",
        "source_mode": "full_frame",
        "crop_box": None,
        "image_width": 3840,
        "image_height": 2160,
        "ranking_score": 0.8,
    }
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda candidate: dict(candidate)))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"Cardinalis cardinalis"}))
    monkeypatch.setattr(service, "_available_photo_candidates", AsyncMock(side_effect=lambda _event, rows: rows))
    monkeypatch.setattr(service, "_load_verified_incumbent_photo", AsyncMock(return_value=None))
    counter = AsyncMock(return_value=[])
    recheck = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "_detect_count_candidates", counter)
    monkeypatch.setattr(service, "_recheck_weak_count_candidates", recheck)

    result = await service._score_and_select_snapshot_candidates(
        "event", [target, full], include_additional_birds=include_additional_birds
    )

    assert (result["selected_candidate"] is not None) is selected
    if selected:
        assert result["selected_candidate"]["classifier_label"] == "Cardinalis cardinalis"
    else:
        assert result["photo_outcome"] == "bird_presence_unconfirmed"
    assert result["additional_bird_scan_performed"] is include_additional_birds
    if include_additional_birds:
        assert result["bird_selection"] is not None
        counter.assert_awaited_once()
        recheck.assert_awaited_once()
    else:
        assert result["bird_selection"] is None
        counter.assert_not_awaited()
        recheck.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configured,requested,expected", [(False, None, False), (True, False, False), (False, True, True)]
)
async def test_clip_scan_freezes_policy_before_awaiting_sources(monkeypatch, tmp_path, configured, requested, expected):
    service = hq.HighQualitySnapshotService()
    monkeypatch.setattr(settings.media_cache, "automatic_multi_bird_scan", configured)

    async def load_frames(*_args, **_kwargs):
        settings.media_cache.automatic_multi_bird_scan = not expected
        return []

    monkeypatch.setattr(service, "_load_preferred_frame_indices", load_frames)
    extract = Mock(return_value=[])
    final_snapshot = AsyncMock(return_value=[])
    score = AsyncMock(return_value={"sentinel": True})
    monkeypatch.setattr(service, "_extract_snapshot_candidate_payloads_from_clip_path", extract)
    monkeypatch.setattr(service, "_load_final_frigate_snapshot_candidates", final_snapshot)
    monkeypatch.setattr(service, "_score_and_select_snapshot_candidates", score)

    result = await service.generate_snapshot_candidates_from_clip_path(
        "event", tmp_path / "fixture.mp4", include_additional_birds=requested
    )

    assert result == {"sentinel": True}
    assert extract.call_args.kwargs["include_additional_birds"] is expected
    assert final_snapshot.await_args.kwargs["include_additional_birds"] is expected
    assert score.await_args.kwargs["include_additional_birds"] is expected


@pytest.mark.asyncio
async def test_target_only_scan_does_not_publish_a_replacement_count(monkeypatch):
    service = hq.HighQualitySnapshotService()
    database = Mock(side_effect=AssertionError("target-only photos must not rewrite counted history"))
    monkeypatch.setattr(hq, "get_db", database)
    await service._persist_bird_observations("event", None)
    database.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("has_model_crop,cropped", [(True, False), (False, False), (True, True)])
async def test_retained_incumbent_is_not_added_to_actual_count_traversal(monkeypatch, has_model_crop, cropped):
    from app.services.bird_observation_selection import BirdObservationSelection

    service = hq.HighQualitySnapshotService()
    full = {
        "candidate_id": "scored-full-frame",
        "source_mode": "full_frame",
        "clip_variant": "event",
        "frame_index": 5,
        "frame_width": 120,
        "frame_height": 80,
        "image_width": 120,
        "image_height": 80,
        "crop_box": None,
        "classifier_label": "House Finch",
        "classifier_score": 0.9,
        "ranking_score": 0.8,
        "input_is_cropped": cropped,
    }
    target = {
        **full,
        "candidate_id": "scored-crop",
        "source_mode": "model_crop",
        "crop_box": (1, 1, 30, 30),
        "detector_box": (1, 1, 30, 30),
        "crop_confidence": 0.9,
    }
    incumbent = {**full, "candidate_id": "retained-old-photo", "frame_index": 99, "input_is_cropped": False}
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda candidate: dict(candidate)))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"House Finch"}))
    monkeypatch.setattr(service, "_available_photo_candidates", AsyncMock(side_effect=lambda _event, rows: rows))
    monkeypatch.setattr(service, "_load_verified_incumbent_photo", AsyncMock(return_value=incumbent))
    monkeypatch.setattr(service, "_select_canonical_snapshot_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_recheck_weak_count_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        hq, "select_bird_observations", lambda *_args, **_kwargs: BirdObservationSelection(None, None, None, ())
    )
    raw = [target, full] if has_model_crop else [full]
    bundle = await service._score_and_select_snapshot_candidates("event", raw, include_additional_birds=True)
    assert bundle["selected_candidate"]["candidate_id"] == "retained-old-photo"
    assert "retained-old-photo" in {candidate["candidate_id"] for candidate in bundle["candidates"]}
    actual_scenes = {candidate["candidate_id"] for candidate in bundle["automatic_scan_scenes"]}
    assert actual_scenes == ({"scored-full-frame"} if has_model_crop and not cropped else set())
    assert not bundle["bird_selection"].birds
