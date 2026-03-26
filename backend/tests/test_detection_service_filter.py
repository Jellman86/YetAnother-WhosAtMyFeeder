from unittest.mock import MagicMock

from app.config import settings
from app.services.detection_service import DetectionService


def _with_classification_settings(**overrides):
    original = {}
    for key, value in overrides.items():
        original[key] = getattr(settings.classification, key)
        setattr(settings.classification, key, value)
    return original


def _restore_classification_settings(original):
    for key, value in original.items():
        setattr(settings.classification, key, value)


def test_filter_and_label_demotes_disagreeing_sublabel_to_unknown_when_not_confident():
    service = DetectionService(MagicMock())
    saved = _with_classification_settings(
        threshold=0.7,
        min_confidence=0.4,
        trust_frigate_sublabel=False,
    )
    try:
        result, reason = service.filter_and_label(
            classification={"label": "Long-tailed Tit", "score": 0.82, "index": 7},
            frigate_event="evt-1",
            frigate_sub_label="Eurasian Blackbird",
            frigate_score=0.89,
        )
        assert result is not None
        assert result["label"] == "Unknown Bird"
        assert reason == "unknown_catchall"
    finally:
        _restore_classification_settings(saved)


def test_filter_and_label_keeps_disagreeing_sublabel_when_score_clears_guard():
    service = DetectionService(MagicMock())
    saved = _with_classification_settings(
        threshold=0.7,
        min_confidence=0.4,
        trust_frigate_sublabel=False,
    )
    try:
        result, reason = service.filter_and_label(
            classification={"label": "Long-tailed Tit", "score": 0.99, "index": 7},
            frigate_event="evt-2",
            frigate_sub_label="Eurasian Blackbird",
            frigate_score=0.89,
        )
        assert result is not None
        assert result["label"] == "Long-tailed Tit"
        assert reason == "threshold_passed_with_sublabel_disagreement_guard"
    finally:
        _restore_classification_settings(saved)


def test_filter_and_label_rejects_structured_blocked_species_by_common_name():
    service = DetectionService(MagicMock())
    saved = _with_classification_settings(
        blocked_labels=[],
        blocked_species=[
            {
                "scientific_name": "Haemorhous cassinii",
                "common_name": "Cassin's Finch",
                "taxa_id": 4567,
            }
        ],
    )
    try:
        result, reason = service.filter_and_label(
            classification={"label": "Cassin's Finch (Adult Male)", "score": 0.92, "index": 7},
            frigate_event="evt-blocked-structured",
        )
        assert result is None
        assert reason == "blocked_label"
    finally:
        _restore_classification_settings(saved)
