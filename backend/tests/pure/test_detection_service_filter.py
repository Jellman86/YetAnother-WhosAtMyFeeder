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


def test_filter_and_label_blocks_species_scoring_inside_the_unknown_catchall_band():
    """A blocked species must not be saved, including under the Unknown Bird catch-all.

    Scores between min_confidence and threshold are saved as an Unknown Bird
    catch-all rather than dropped. The blocked-species check therefore has to run
    before that gate, otherwise a blocked species re-enters history under a
    different name.
    """
    service = DetectionService(MagicMock())
    saved = _with_classification_settings(
        blocked_labels=["Grey Squirrel"],
        blocked_species=[],
        min_confidence=0.5,
        threshold=0.7,
    )
    try:
        # Control: an unblocked label in the same band is saved as Unknown Bird,
        # so the catch-all really is reachable at this score.
        allowed, allowed_reason = service.filter_and_label(
            classification={"label": "Some Bird", "score": 0.6, "index": 1},
            frigate_event="evt-catchall-allowed",
        )
        assert allowed is not None
        assert allowed["label"] == "Unknown Bird"
        assert allowed_reason == "unknown_catchall"

        blocked, blocked_reason = service.filter_and_label(
            classification={"label": "Grey Squirrel", "score": 0.6, "index": 1},
            frigate_event="evt-catchall-blocked",
        )
        assert blocked is None
        assert blocked_reason == "blocked_label"
    finally:
        _restore_classification_settings(saved)
