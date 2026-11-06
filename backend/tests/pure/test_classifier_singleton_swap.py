"""Regression tests for GitHub issue #50 — stale classifier refs after reload."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import classifier_service as classifier_service_module
from app.services.classifier_service import (
    ClassifierService,
    resolve_live_classifier,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Clear the global classifier singleton around each test."""
    original = classifier_service_module._classifier_instance
    classifier_service_module._classifier_instance = None
    try:
        yield
    finally:
        classifier_service_module._classifier_instance = original


def test_resolve_live_classifier_returns_mocks_unchanged():
    """Tests inject MagicMock / SimpleNamespace; resolver must not swap them."""
    mock = MagicMock()
    assert resolve_live_classifier(mock) is mock


def test_resolve_live_classifier_swaps_stale_real_classifier():
    """After shutdown_classifier the singleton is replaced; cached real refs must update."""
    stale = ClassifierService.__new__(ClassifierService)
    fresh = ClassifierService.__new__(ClassifierService)
    classifier_service_module._classifier_instance = fresh
    assert resolve_live_classifier(stale) is fresh


def test_resolve_live_classifier_returns_current_when_unchanged():
    current = ClassifierService.__new__(ClassifierService)
    classifier_service_module._classifier_instance = current
    assert resolve_live_classifier(current) is current


def test_resolve_live_classifier_returns_singleton_when_stored_is_none():
    fresh = ClassifierService.__new__(ClassifierService)
    classifier_service_module._classifier_instance = fresh
    assert resolve_live_classifier(None) is fresh


def test_event_processor_classifier_property_self_heals_after_singleton_swap():
    from app.services.event_processor import EventProcessor

    stale = ClassifierService.__new__(ClassifierService)
    fresh = ClassifierService.__new__(ClassifierService)
    classifier_service_module._classifier_instance = stale

    processor = EventProcessor()
    assert processor.classifier is stale

    # Simulate the settings-driven reload: shutdown_classifier nulls the global,
    # then the next get_classifier() creates a new singleton.
    classifier_service_module._classifier_instance = fresh

    assert processor.classifier is fresh, "EventProcessor still points at stale classifier"


def test_event_processor_keeps_injected_mock_across_singleton_changes():
    """Tests inject mocks; the property must never replace them with a real classifier."""
    from app.services.event_processor import EventProcessor

    mock = MagicMock()
    processor = EventProcessor(mock)
    assert processor.classifier is mock

    # Simulate global singleton churn that would otherwise tempt the resolver
    # to swap. Mock is not a ClassifierService → stays pinned.
    classifier_service_module._classifier_instance = ClassifierService.__new__(ClassifierService)
    assert processor.classifier is mock


def test_backfill_service_classifier_property_self_heals_after_singleton_swap():
    from app.services.backfill_service import BackfillService

    stale = ClassifierService.__new__(ClassifierService)
    fresh = ClassifierService.__new__(ClassifierService)
    classifier_service_module._classifier_instance = stale

    service = BackfillService()
    assert service.classifier is stale

    classifier_service_module._classifier_instance = fresh
    assert service.classifier is fresh


def test_backfill_service_keeps_injected_mock():
    from app.services.backfill_service import BackfillService

    mock = MagicMock()
    service = BackfillService(mock)
    classifier_service_module._classifier_instance = ClassifierService.__new__(ClassifierService)
    assert service.classifier is mock
