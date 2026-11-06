"""BirdNET-Go payload parsing shared by audio ingest and audio history."""

import json

import pytest

from app.utils.birdnet_payload import (
    extract_audio_mapping_keys,
    extract_birdnet_id,
    extract_birdnet_source_name,
    parse_mapping_filter_values,
)


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"detectionId": 7}, 7),
        ({"detection_id": " 8 "}, 8),
        ({"id": "9"}, 9),
        ({"detectionId": True, "id": 10}, 10),
        ({"detectionId": 0, "id": "x"}, None),
        ("not a dict", None),
    ],
)
def test_the_detection_id_comes_from_any_published_key_and_never_from_a_bool(payload, expected):
    assert extract_birdnet_id(payload) == expected


def test_a_mapping_lists_source_keys_or_matches_everything():
    assert parse_mapping_filter_values(" Garden Mic ;shed|") == (False, {"garden mic", "shed"})
    assert parse_mapping_filter_values("garden, *") == (True, set())
    assert parse_mapping_filter_values(None) == (False, set())


def test_a_stored_detection_is_mapped_by_its_sensor_and_every_source_name_or_id():
    raw = json.dumps({"nm": "Garden Mic", "Source": {"id": "Dev-1"}, "id": 5})
    assert extract_audio_mapping_keys("garden-mic", raw) == {"garden-mic", "garden mic", "dev-1", "5"}
    assert extract_audio_mapping_keys(None, "not json") == set()


def test_the_source_name_prefers_a_human_label_over_the_sensor_id():
    assert extract_birdnet_source_name("mic-1", json.dumps({"Source": {"displayName": " Patio "}})) == "Patio"
    assert extract_birdnet_source_name(" mic-1 ", "not json") == "mic-1"
    assert extract_birdnet_source_name(None, None) is None
