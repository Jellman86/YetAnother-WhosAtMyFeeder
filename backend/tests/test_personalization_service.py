from datetime import datetime, timedelta, timezone

from app.services.personalization_service import PersonalizationService


def _result(label: str, score: float, index: int = 0) -> dict:
    return {"label": label, "score": score, "index": index}


def _feedback(predicted: str, corrected: str, created_at: datetime) -> dict:
    return {
        "predicted_label": predicted,
        "corrected_label": corrected,
        "created_at": created_at,
    }


def _score_for(results: list[dict], label: str) -> float:
    for row in results:
        if row["label"] == label:
            return float(row["score"])
    raise AssertionError(f"Label {label!r} not found in reranked results")


def test_rerank_inactive_below_min_tags():
    now = datetime(2026, 2, 27, tzinfo=timezone.utc)
    service = PersonalizationService(min_feedback_tags=20)
    results = [_result("A", 0.6), _result("B", 0.3), _result("C", 0.1)]
    feedback_rows = [_feedback("A", "B", now - timedelta(days=1)) for _ in range(19)]

    reranked = service.rerank_with_feedback(
        results=results,
        feedback_rows=feedback_rows,
        raw_feedback_count=19,
        now=now,
    )

    assert reranked == results


def test_rerank_active_at_20_tags():
    now = datetime(2026, 2, 27, tzinfo=timezone.utc)
    service = PersonalizationService(min_feedback_tags=20)
    results = [_result("A", 0.55), _result("B", 0.35), _result("C", 0.10)]
    feedback_rows = [_feedback("A", "B", now - timedelta(days=1)) for _ in range(20)]

    reranked = service.rerank_with_feedback(
        results=results,
        feedback_rows=feedback_rows,
        raw_feedback_count=20,
        now=now,
    )

    assert reranked[0]["label"] == "B"
    assert _score_for(reranked, "B") > _score_for(reranked, "A")


def test_time_decay_prefers_recent_feedback():
    now = datetime(2026, 2, 27, tzinfo=timezone.utc)
    service = PersonalizationService(min_feedback_tags=20, half_life_days=30)
    results = [_result("A", 0.6), _result("B", 0.25), _result("C", 0.15)]

    feedback_rows = []
    feedback_rows.extend(_feedback("A", "B", now - timedelta(days=180)) for _ in range(20))
    feedback_rows.extend(_feedback("A", "C", now - timedelta(days=1)) for _ in range(20))

    reranked = service.rerank_with_feedback(
        results=results,
        feedback_rows=feedback_rows,
        raw_feedback_count=40,
        now=now,
    )

    assert _score_for(reranked, "C") > _score_for(reranked, "B")


def test_score_shift_capped():
    now = datetime(2026, 2, 27, tzinfo=timezone.utc)
    service = PersonalizationService(
        min_feedback_tags=20,
        half_life_days=30,
        max_relative_shift=0.35,
        max_absolute_shift=0.2,
    )
    results = [_result("A", 0.95), _result("B", 0.03), _result("C", 0.02)]
    feedback_rows = [_feedback("A", "B", now - timedelta(hours=1)) for _ in range(200)]

    reranked = service.rerank_with_feedback(
        results=results,
        feedback_rows=feedback_rows,
        raw_feedback_count=200,
        now=now,
    )

    original_a = _score_for(results, "A")
    reranked_a = _score_for(reranked, "A")

    assert (original_a - reranked_a) <= 0.2 + 1e-9
