from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import high_quality_snapshot_service as hq
from app.services.bird_observation_selection import select_bird_observations
from tests.test_hq_count_recheck import bundle


@pytest.mark.asyncio
async def test_recovered_bird_uses_new_same_frame_context_evidence_without_changing_photos(monkeypatch):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    original = deepcopy(rows)
    monkeypatch.setattr(
        hq.bird_crop_service,
        "refine_observation_box",
        Mock(return_value={"detector_box": (1239, 1261, 1370, 1431), "confidence": 0.75}),
    )
    scorer = AsyncMock(
        side_effect=lambda candidate: {
            **candidate,
            "classifier_label": "Cardinalis cardinalis",
            "classifier_score": 0.82,
            "classifier_index": 3709,
        }
    )
    monkeypatch.setattr(service, "_score_snapshot_candidate", scorer)
    recovered = await service._recheck_weak_count_candidates(rows)
    assert recovered[0]["classifier_score"] == 0.82
    assert recovered[0]["candidate_id"] != rows[1]["candidate_id"]
    assert recovered[0]["source_mode"] == "model_observation"
    assert recovered[0]["crop_box"] == (1134, 1125, 1474, 1567)
    assert recovered[0]["image_bytes"] and recovered[0]["thumbnail_bytes"]
    assert recovered[0]["detector_box"] == (1239, 1261, 1370, 1431)
    assert rows == original
    selection = select_bird_observations(rows + recovered, selected_candidate=rows[3])
    assert len(selection.birds) == 2
    assert selection.birds[1].species == "Cardinalis cardinalis"
    assert selection.birds[1].box == (1239, 1261, 1370, 1431)
    scorer.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "label,score",
    [
        ("Baeolophus bicolor", 0.99),
        ("Cardinalis cardinalis", 0.64),
        ("Cardinalis cardinalis", float("nan")),
        ("Unknown Bird", 0.99),
    ],
)
async def test_context_disagreement_or_weak_result_preserves_original_identity(monkeypatch, label, score):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    monkeypatch.setattr(
        hq.bird_crop_service,
        "refine_observation_box",
        Mock(return_value={"detector_box": (1239, 1261, 1370, 1431), "confidence": 0.75}),
    )
    monkeypatch.setattr(
        service,
        "_score_snapshot_candidate",
        AsyncMock(side_effect=lambda c: {**c, "classifier_label": label, "classifier_score": score}),
    )
    recovered = await service._recheck_weak_count_candidates(rows)
    assert recovered[0]["candidate_id"] == rows[1]["candidate_id"]
    assert recovered[0]["classifier_score"] == 0.155


@pytest.mark.asyncio
async def test_context_classifier_failure_does_not_discard_recovered_count(monkeypatch):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    monkeypatch.setattr(
        hq.bird_crop_service,
        "refine_observation_box",
        Mock(return_value={"detector_box": (1239, 1261, 1370, 1431), "confidence": 0.75}),
    )
    monkeypatch.setattr(
        service, "_score_snapshot_candidate", AsyncMock(side_effect=hq.PhotoScanRetry("classifier_error"))
    )
    recovered = await service._recheck_weak_count_candidates(rows)
    assert len(recovered) == 1 and recovered[0]["classifier_score"] == 0.155


def test_context_clamps_at_frame_edges_and_rejects_other_birds():
    from app.services.bird_count_recheck import contextual_recheck_box

    seed = {"frame_width": 640, "frame_height": 480}
    assert contextual_recheck_box(seed, (0, 0, 100, 100), []) == (0, 0, 180, 180)
    assert contextual_recheck_box(seed, (100, 100, 200, 200), [(102, 102, 202, 202)]) == (20, 20, 280, 280)
    assert contextual_recheck_box(seed, (100, 100, 200, 200), [(220, 120, 260, 180)]) is None
    assert contextual_recheck_box(seed, (100, 100, 200, 200), [(0, 0, 640, 480)]) is None
    assert contextual_recheck_box(seed, (600, 100, 700, 200), []) is None


@pytest.mark.asyncio
async def test_context_is_not_scored_when_another_recovered_bird_is_inside_margin(monkeypatch):
    service = hq.HighQualitySnapshotService()
    rows = bundle()
    rows.append({**rows[3], "candidate_id": "neighbor", "detector_box": (1400, 1300, 1450, 1380)})
    monkeypatch.setattr(
        hq.bird_crop_service,
        "refine_observation_box",
        Mock(return_value={"detector_box": (1239, 1261, 1370, 1431), "confidence": 0.75}),
    )
    scorer = AsyncMock()
    monkeypatch.setattr(service, "_score_snapshot_candidate", scorer)
    recovered = await service._recheck_weak_count_candidates(rows)
    scorer.assert_not_awaited()
    assert recovered[0]["classifier_score"] == 0.155


def test_count_context_cannot_replace_the_main_species_or_be_applied_as_a_photo():
    from app.services.hq_classification_refinement import choose_hq_classification_refinement
    from app.routers.proxy import _pick_snapshot_candidate, SnapshotApplyRequest
    from tests.test_hq_classification_refinement import _candidate, _detection

    rows = [_candidate(frame, "Cardinalis cardinalis", 0.99, source_mode="model_observation") for frame in (30, 60)]
    assert choose_hq_classification_refinement(detection=_detection(), candidates=rows, minimum_score=0.65) is None
    assert _pick_snapshot_candidate(rows, SnapshotApplyRequest(mode="auto_best")) is None
    assert (
        _pick_snapshot_candidate(rows, SnapshotApplyRequest(mode="candidate", candidate_id=rows[0]["candidate_id"]))
        is None
    )
