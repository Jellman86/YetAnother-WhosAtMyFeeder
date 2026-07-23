from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.classification_input_provenance import (
    build_snapshot_classification_input_context,
    cached_snapshot_input_provenance,
    frigate_snapshot_input_provenance,
    load_snapshot_classification_input,
)


def test_cached_hq_crop_provenance_preserves_actual_input_source():
    provenance = cached_snapshot_input_provenance({"source": "hq_candidate_frigate_hint_crop"})

    assert provenance.input_source == "hq_candidate_frigate_hint_crop"
    assert provenance.is_cropped is True


def test_regular_frigate_snapshot_fallback_fails_safe_to_cropped():
    provenance = cached_snapshot_input_provenance({"source": "hq_candidate_frigate_snapshot_fallback"})

    assert provenance.input_source == "hq_candidate_frigate_snapshot_fallback"
    assert provenance.is_cropped is True


def test_cached_full_frame_provenance_is_not_marked_as_cropped():
    provenance = cached_snapshot_input_provenance({"source": "hq_candidate_full_frame"})

    assert provenance.input_source == "hq_candidate_full_frame"
    assert provenance.is_cropped is False


def test_unknown_cached_snapshot_provenance_fails_safe_to_uncropped():
    provenance = cached_snapshot_input_provenance({"source": "unexpected_external_value"})

    assert provenance.input_source == "cached_snapshot_unknown"
    assert provenance.is_cropped is False


def test_frigate_snapshot_is_only_marked_cropped_while_event_is_live():
    live = frigate_snapshot_input_provenance({"end_time": None})
    ended = frigate_snapshot_input_provenance({"end_time": 1234.5})
    unknown = frigate_snapshot_input_provenance(None)

    assert live.input_source == "frigate_snapshot_cropped"
    assert live.is_cropped is True
    assert ended.input_source == "frigate_snapshot"
    assert ended.is_cropped is False
    assert unknown.input_source == "frigate_snapshot"
    assert unknown.is_cropped is False


def test_completed_full_frame_context_includes_valid_frigate_localisation_hints():
    provenance = frigate_snapshot_input_provenance({"end_time": 1234.5})

    context = build_snapshot_classification_input_context(
        event_id="event-1",
        event_data={
            "end_time": 1234.5,
            "data": {
                "box": [0.2, 0.3, 0.4, 0.5],
                "region": (0.1, 0.2, 0.8, 0.9),
            },
        },
        provenance=provenance,
    )

    assert context == {
        "is_cropped": False,
        "event_id": "event-1",
        "input_source": "frigate_snapshot",
        "frigate_box": [0.2, 0.3, 0.4, 0.5],
        "frigate_region": [0.1, 0.2, 0.8, 0.9],
        "restore_frigate_snapshot_crop": True,
    }


def test_cropped_snapshot_context_does_not_add_hints_or_double_crop():
    provenance = frigate_snapshot_input_provenance({"end_time": None})

    context = build_snapshot_classification_input_context(
        event_id="event-live",
        event_data={
            "end_time": None,
            "data": {
                "box": [0.2, 0.3, 0.4, 0.5],
                "region": [0.1, 0.2, 0.8, 0.9],
            },
        },
        provenance=provenance,
    )

    assert context == {
        "is_cropped": True,
        "event_id": "event-live",
        "input_source": "frigate_snapshot_cropped",
    }


def test_temporally_unaligned_cached_full_frame_does_not_use_final_event_hints():
    provenance = cached_snapshot_input_provenance({"source": "hq_candidate_full_frame"})

    context = build_snapshot_classification_input_context(
        event_id="event-hq-frame",
        event_data={
            "data": {
                "box": [0.2, 0.3, 0.4, 0.5],
                "region": [0.1, 0.2, 0.8, 0.9],
            }
        },
        provenance=provenance,
    )

    assert context == {
        "is_cropped": False,
        "event_id": "event-hq-frame",
        "input_source": "hq_candidate_full_frame",
    }


def test_full_frame_context_ignores_malformed_localisation_hints():
    provenance = frigate_snapshot_input_provenance({"end_time": 1234.5})

    context = build_snapshot_classification_input_context(
        event_id="event-invalid-hints",
        event_data={"data": {"box": [0.2, 0.3, 0.4], "region": "not-a-region"}},
        provenance=provenance,
    )

    assert context == {
        "is_cropped": False,
        "event_id": "event-invalid-hints",
        "input_source": "frigate_snapshot",
    }


def test_completed_full_frame_context_accepts_current_frigate_top_level_box():
    provenance = frigate_snapshot_input_provenance({"end_time": 1234.5})

    context = build_snapshot_classification_input_context(
        event_id="event-top-level-box",
        event_data={"end_time": 1234.5, "box": [0.2, 0.3, 0.4, 0.5]},
        provenance=provenance,
    )

    assert context == {
        "is_cropped": False,
        "event_id": "event-top-level-box",
        "input_source": "frigate_snapshot",
        "frigate_box": [0.2, 0.3, 0.4, 0.5],
        "restore_frigate_snapshot_crop": True,
    }


@pytest.mark.asyncio
async def test_load_snapshot_falls_back_to_frigate_when_cache_read_fails():
    cache = SimpleNamespace(
        get_snapshot=AsyncMock(side_effect=OSError("cache unavailable")),
        get_snapshot_metadata=AsyncMock(),
    )
    client = SimpleNamespace(get_snapshot=AsyncMock(return_value=b"frigate"))

    image, provenance = await load_snapshot_classification_input(
        "event-2",
        event_data={"end_time": 123.0},
        media_cache_service=cache,
        frigate_client_service=client,
    )

    assert image == b"frigate"
    assert provenance.input_source == "frigate_snapshot"
    assert provenance.is_cropped is False
    client.get_snapshot.assert_awaited_once_with("event-2", crop=False, quality=95)


@pytest.mark.asyncio
async def test_load_live_snapshot_requests_frigate_crop():
    cache = SimpleNamespace(get_snapshot=AsyncMock(return_value=None))
    client = SimpleNamespace(get_snapshot=AsyncMock(return_value=b"frigate-crop"))

    image, provenance = await load_snapshot_classification_input(
        "event-live",
        event_data={"end_time": None},
        media_cache_service=cache,
        frigate_client_service=client,
    )

    assert image == b"frigate-crop"
    assert provenance.input_source == "frigate_snapshot_cropped"
    assert provenance.is_cropped is True
    client.get_snapshot.assert_awaited_once_with("event-live", crop=True, quality=95)


@pytest.mark.asyncio
async def test_load_snapshot_keeps_cached_image_when_metadata_read_fails():
    cache = SimpleNamespace(
        get_snapshot=AsyncMock(return_value=b"cached"),
        get_snapshot_metadata=AsyncMock(side_effect=ValueError("broken metadata")),
    )
    client = SimpleNamespace(get_snapshot=AsyncMock())

    image, provenance = await load_snapshot_classification_input(
        "event-3",
        media_cache_service=cache,
        frigate_client_service=client,
    )

    assert image == b"cached"
    assert provenance.input_source == "cached_snapshot_unknown"
    assert provenance.is_cropped is False
    client.get_snapshot.assert_not_awaited()
