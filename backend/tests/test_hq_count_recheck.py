from copy import deepcopy
from io import BytesIO
from unittest.mock import AsyncMock, Mock
import threading
import time

from PIL import Image
import pytest

from app.services import high_quality_snapshot_service as hq
from app.services.bird_crop_service import BirdCropService
from app.services.bird_observation_selection import select_bird_observations


def bundle():
    stream = BytesIO()
    Image.new("RGB", (3840, 2160)).save(stream, format="JPEG")
    base = {"clip_variant": "event", "frame_width": 3840, "frame_height": 2160}
    weak = {
        **base,
        "candidate_id": "cardinal",
        "source_mode": "model_crop",
        "frame_index": 150,
        "frame_offset_seconds": 10.0,
        "detector_box": (1235, 1257, 1365, 1413),
        "crop_box": (1221, 1246, 1388, 1420),
        "crop_confidence": 0.032,
        "classifier_label": "Cardinalis cardinalis",
        "classifier_score": 0.155,
        "ranking_score": 0.2,
    }
    return [
        {
            **base,
            "candidate_id": "whole",
            "source_mode": "full_frame",
            "frame_index": 150,
            "image_bytes": stream.getvalue(),
        },
        weak,
        {
            **weak,
            "candidate_id": "strong",
            "frame_index": 75,
            "frame_offset_seconds": 5.0,
            "detector_box": (1060, 1220, 1380, 1450),
            "crop_confidence": 0.72,
            "classifier_score": 0.75,
        },
        {
            **weak,
            "candidate_id": "titmouse",
            "detector_box": (894, 801, 1142, 1098),
            "crop_confidence": 0.14,
            "classifier_label": "Baeolophus bicolor",
            "classifier_score": 0.75,
        },
    ]


@pytest.mark.asyncio
async def test_recheck_counts_two_real_regions_without_borrowing_neighbor_identity(monkeypatch):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    original = deepcopy(rows)
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(return_value=None))
    detector = Mock(return_value={"detector_box": (1239, 1261, 1370, 1431), "confidence": 0.557})
    monkeypatch.setattr(hq.bird_crop_service, "refine_observation_box", detector)
    observations = await service._recheck_weak_count_candidates(rows)
    selection = select_bird_observations(rows + observations, selected_candidate=rows[3])
    assert len(selection.birds) == 2
    assert selection.frame_index == 150
    rescued = selection.birds[1]
    assert rescued.species == "Unknown Bird"
    assert rescued.classifier_label == "Cardinalis cardinalis"
    assert rescued.classifier_score == 0.155
    assert rescued.detector_confidence == 0.557
    assert rows == original
    detector.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        {"detector_box": (1239, 1261, 1370, 1431), "confidence": 0.03},
        {"detector_box": (894, 801, 1142, 1098), "confidence": 0.9},
        {"reason": "inference_failed", "runtime_error": True},
    ],
)
async def test_failed_or_unrelated_recheck_does_not_create_a_bird(monkeypatch, result):
    service = hq.HighQualitySnapshotService()
    monkeypatch.setattr(hq.bird_crop_service, "refine_observation_box", Mock(return_value=result))
    assert await service._recheck_weak_count_candidates(bundle()) == []


@pytest.mark.asyncio
async def test_missing_or_mismatched_frame_does_not_run_detector(monkeypatch):
    service = hq.HighQualitySnapshotService()
    detector = Mock(side_effect=AssertionError("no usable full frame"))
    monkeypatch.setattr(hq.bird_crop_service, "refine_observation_box", detector)
    rows = bundle()
    assert await service._recheck_weak_count_candidates(rows[1:]) == []
    rows[0]["frame_width"] = 1920
    assert await service._recheck_weak_count_candidates(rows) == []
    detector.assert_not_called()


def test_regional_recheck_uses_two_model_widths_and_never_falls_back(monkeypatch):
    service = BirdCropService()
    guided = Mock(return_value={"reason": "below_threshold"})
    monkeypatch.setattr(service, "generate_guided_classification_candidate_crop", guided)
    service.refine_observation_box(Image.new("RGB", (3840, 2160)), (1235, 1257, 1365, 1413))
    guided.assert_called_once()
    region = guided.call_args.kwargs["search_box"]
    assert region[2] - region[0] == region[3] - region[1] == 2 * service.CLASSIFICATION_TILE_MODEL_INPUT_SIZE
    assert guided.call_args.kwargs["allow_fallback"] is False


def test_keeps_low_scoring_crop_used_by_count_when_pruning_photos():
    service = hq.HighQualitySnapshotService()
    ranked = [{"candidate_id": f"photo{index}", "ranking_score": 0.9} for index in range(20)]
    weak = {"candidate_id": "rescued", "source_mode": "model_crop", "ranking_score": 0.1}
    persisted = service._select_persisted_candidates(
        ranked + [weak], selected_candidate=ranked[0], count_candidate_ids={"rescued"}
    )
    assert weak in persisted
    assert len(persisted) == hq.HQ_MAX_PERSISTED_CANDIDATES


def test_counted_frame_and_rescued_crop_take_priority_when_final_baselines_fill_capacity():
    service = hq.HighQualitySnapshotService()
    finals = [
        {"candidate_id": f"final{index}", "clip_variant": "frigate_snapshot", "ranking_score": 0.9}
        for index in range(10)
    ]
    chosen = {
        "candidate_id": "chosen",
        "source_mode": "model_crop",
        "frame_index": 1,
        "clip_variant": "event",
        "ranking_score": 0.9,
    }
    chosen_full = {**chosen, "candidate_id": "chosen-full", "source_mode": "full_frame"}
    counted = [{"candidate_id": f"counted{index}", "ranking_score": 0.8} for index in range(4)]
    count_full = {
        "candidate_id": "count-full",
        "source_mode": "full_frame",
        "frame_index": 2,
        "clip_variant": "event",
        "ranking_score": 0.2,
    }
    rescued = {"candidate_id": "rescued", "source_mode": "model_crop", "ranking_score": 0.1}
    persisted = service._select_persisted_candidates(
        finals + [chosen, chosen_full] + counted + [count_full, rescued],
        selected_candidate=chosen,
        count_full_frame_candidate_id="count-full",
        count_candidate_ids={"rescued", *(row["candidate_id"] for row in counted)},
    )
    assert len(persisted) == hq.HQ_MAX_PERSISTED_CANDIDATES
    for needed in [chosen, chosen_full, count_full, rescued, *counted]:
        assert needed in persisted


@pytest.mark.asyncio
async def test_rechecks_share_one_decoded_frame_and_budget_includes_failures(monkeypatch):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    rows = [rows[0]] + [
        dict(
            template,
            candidate_id=f"{kind}{index}",
            detector_box=(index * 300, 100, index * 300 + 100, 200),
            crop_box=(index * 300, 100, index * 300 + 100, 200),
        )
        for index in range(8)
        for kind, template in (("weak", rows[1]), ("donor", rows[2]))
    ]
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(return_value=None))
    decode = Mock(wraps=hq.decode_image_bytes)
    monkeypatch.setattr(hq, "decode_image_bytes", decode)
    lock = threading.Lock()
    active = peak = calls = 0

    def detect(image, box):
        nonlocal active, peak, calls
        with lock:
            active += 1
            peak = max(peak, active)
            calls += 1
        try:
            time.sleep(0.005)
            if calls % 2:
                raise RuntimeError("regional detector failed")
            return {"confidence": 0.7, "detector_box": box}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(hq.bird_crop_service, "refine_observation_box", detect)
    observations = await service._recheck_weak_count_candidates(rows)
    assert len(observations) == 2
    assert calls == 4
    assert peak == 1
    assert sum(call.args[0] == rows[0]["image_bytes"] for call in decode.call_args_list) == 1


@pytest.mark.asyncio
async def test_count_recheck_does_not_promote_photo_presence_or_change_original_crop_evidence(monkeypatch):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    rows[1]["classifier_score"] = 0.99
    rows[1]["ranking_score"] = 0.99
    rescued = {
        **rows[1],
        "source_mode": "model_observation",
        "crop_box": (1239, 1261, 1370, 1431),
        "crop_confidence": 0.557,
    }
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda candidate: dict(candidate)))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value=set()))
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_recheck_weak_count_candidates", AsyncMock(return_value=[rescued]))
    result = await service._score_and_select_snapshot_candidates("event", rows, include_additional_birds=True)
    weak = next(row for row in result["candidates"] if row["candidate_id"] == "cardinal")
    assert weak["crop_confidence"] == 0.032
    assert weak.get("crop_strategy") != "detector_supported"
    assert (result["selected_candidate"] or {}).get("candidate_id") != "cardinal"
    assert len(result["bird_selection"].birds) == 2
