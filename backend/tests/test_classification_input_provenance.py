from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.classification_input_provenance import (
    cached_snapshot_input_provenance,
    frigate_snapshot_input_provenance,
    load_snapshot_classification_input,
)


def test_cached_hq_crop_provenance_preserves_actual_input_source():
    provenance = cached_snapshot_input_provenance({"source": "hq_candidate_frigate_hint_crop"})

    assert provenance.input_source == "hq_candidate_frigate_hint_crop"
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
