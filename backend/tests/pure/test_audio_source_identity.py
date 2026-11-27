"""One BirdNET-Go source stays one source across a rename, and two microphones never become one (#1111)."""

import pytest

from app.utils.audio_source_identity import (
    MAX_SOURCE_TEXT_LENGTH,
    AudioSourceDirectory,
    SourceObservation,
    StoredSource,
    clean_source_identifier,
    clean_source_label,
    explicit_source_name,
    extract_birdnet_source_id,
    extract_birdnet_source_node,
    read_stored_source,
    source_of_payload,
)

CARD = "audio_card_22a9b331"


def _observe(node, source_id, name, last_seen, count=1, shown=True):
    return SourceObservation(node=node, source_id=source_id, name=name, last_seen=last_seen, count=count, shown=shown)


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"sourceId": " rtsp_3af0d74c ", "sourceName": "birdcam"}, "rtsp_3af0d74c"),
        ({"sourceId": CARD, "sourceName": "Default Audio Device"}, CARD),
        ({"Source": {"id": "rtsp_old", "displayName": "Garden"}}, "rtsp_old"),
        ({"src": "rtsp_short"}, "rtsp_short"),
        ({"sourceId": "", "Source": {"id": "rtsp_nested"}}, "rtsp_nested"),
        ({"sourceName": "birdcam"}, None),
        ({"Source": "rtsp://camera/stream"}, None),
        ({"sourceId": 42}, None),
        (None, None),
        # An unsafe id is refused, never swapped for another field or cut short.
        ({"sourceId": "rtsp_\x00a", "src": "rtsp_b"}, None),
        ({"sourceId": "rtsp_" + "a" * MAX_SOURCE_TEXT_LENGTH}, None),
        ({"sourceId": "rtsp_\ud800"}, None),
        ({"sourceId": "rtsp_a, *, y"}, None),
        ({"sourceId": "rtsp a"}, None),
    ],
)
def test_the_source_id_comes_from_any_published_shape(payload, expected):
    assert extract_birdnet_source_id(payload) == expected


def test_the_source_node_is_birdnet_gos_node_name_when_it_is_safe():
    assert extract_birdnet_source_node({"SourceNode": " BirdNET-Go Quark "}) == "BirdNET-Go Quark"
    assert extract_birdnet_source_node({"SourceNode": ""}) is None
    assert extract_birdnet_source_node({"SourceNode": ["House"]}) is None
    assert extract_birdnet_source_node({"SourceNode": "House\nShed"}) is None
    assert extract_birdnet_source_node({"SourceNode": "pi@shed, west"}) == "pi@shed, west"


def test_identifiers_are_refused_not_shortened_and_names_lose_control_characters():
    assert clean_source_identifier("x" * MAX_SOURCE_TEXT_LENGTH) == "x" * MAX_SOURCE_TEXT_LENGTH
    assert clean_source_identifier("x" * (MAX_SOURCE_TEXT_LENGTH + 1)) is None
    assert clean_source_identifier("a\x07b") is None
    assert clean_source_label(" Garden\x00 \tMic\n ") == "Garden Mic"
    assert clean_source_label("Patio\ud800") == "Patio"
    assert clean_source_label("n" * (MAX_SOURCE_TEXT_LENGTH + 1)) is None
    assert clean_source_label(7) is None


@pytest.mark.parametrize(
    "sensor,payload,expected",
    [
        # A name BirdNET-Go sent counts, even when it is the id.
        ("rtsp_a", {"sourceId": "rtsp_a", "sourceName": "rtsp_a"}, "rtsp_a"),
        ("Feeder", {"sourceId": "rtsp_a", "sourceName": "Feeder"}, "Feeder"),
        ("Backyard", {"nm": "Backyard", "sourceName": "Feeder", "sourceId": "rtsp_b"}, "Backyard"),
        # No name was sent: the id stored as the sensor is no name at all.
        ("rtsp_a", {"sourceId": "rtsp_a"}, None),
        ("rtsp_a", {"Source": {"id": "rtsp_a"}}, None),
        # A sensor stored without an id stands in, as history has always shown it.
        ("mic1", {"sensor_id": "mic1"}, "mic1"),
        ("sensor_A", {"comName": "Blue Jay", "id": "sensor_A"}, "sensor_A"),
        ("mic", None, "mic"),
    ],
)
def test_a_name_is_one_birdnet_go_sent_never_one_made_from_the_id(sensor, payload, expected):
    assert explicit_source_name(sensor, payload) == expected


def test_ingest_records_the_node_the_id_and_the_given_name():
    payload = {"SourceNode": "Quark", "sourceId": "rtsp_a", "sourceName": "birdcam", "nm": "Birdcam West"}
    assert source_of_payload("birdcam", payload) == StoredSource("Quark", "rtsp_a", "Birdcam West")
    assert source_of_payload("mic", {"sourceId": "rtsp_a", "sourceName": "x\x00y"}) == StoredSource(
        None, "rtsp_a", "x y"
    )
    # An id that is refused leaves the call no name to join a source by.
    hostile = {"SourceNode": "\ud800", "sourceId": "rtsp_" + "z" * 5000, "sourceName": "x\x00y"}
    assert source_of_payload("mic", hostile) == StoredSource(None, None, None)
    assert source_of_payload("Feeder", {"SourceNode": "House", "sourceId": 42, "sourceName": "Feeder"}) == (
        StoredSource("House", None, None)
    )
    # An empty id field is no id: such a call is one from before ids, and keeps its name.
    assert source_of_payload("Feeder", {"sourceId": " ", "sourceName": "Feeder"}) == StoredSource(None, None, "Feeder")


def test_a_stored_row_is_read_from_its_columns_alone():
    assert read_stored_source(" Quark ", "rtsp_a", "birdcam") == StoredSource("Quark", "rtsp_a", "birdcam")
    assert read_stored_source("Quark", "rtsp_a", None).name is None
    # Columns the upgrade left empty mean the payload named no source: it is never read again.
    assert read_stored_source(None, None, None) == StoredSource(None, None, None)


def test_a_call_with_a_refused_id_never_joins_another_installs_source():
    stored = source_of_payload("rtsp shed", {"SourceNode": "House", "sourceId": "rtsp shed"})
    assert stored == StoredSource("House", None, None)
    directory = AudioSourceDirectory(
        [
            _observe("Shed", "rtsp_a", "rtsp shed", "2026-11-01 08:00:00", count=5),
            _observe("Shed", "rtsp_a", "Feeder", "2026-11-02 08:00:00", count=5),
            _observe("House", None, None, "2026-11-03 08:00:00"),
            _observe("Shed", None, None, "2026-11-03 08:00:00"),
            _observe("House", None, "Feeder", "2026-11-03 08:00:00"),
        ]
    )
    shed = directory.key_for("Shed", "rtsp_a", "Feeder")
    house_unknown = directory.key_for(stored.node, stored.source_id, stored.name)
    assert house_unknown != shed
    # One unknown source per install, each on its own.
    assert house_unknown != directory.key_for("Shed", None, None)
    assert directory.source_node(house_unknown) == "House"
    # Named, it still stays on its own install.
    assert directory.key_for("House", None, "Feeder") != shed
    assert directory.source_node(directory.key_for("House", None, "Feeder")) == "House"


def test_a_renamed_source_is_one_source_named_by_its_latest_name():
    directory = AudioSourceDirectory(
        [
            _observe("Node", "rtsp_a", "birdcam", "2026-11-01 08:00:00", count=40),
            _observe("Node", "rtsp_a", "Feeder", "2026-11-20 08:00:00", count=2),
        ]
    )
    key = directory.key_for("Node", "rtsp_a", "birdcam")
    assert key == directory.key_for("Node", "rtsp_a", "Feeder")
    assert directory.display_name(key) == "Feeder"
    assert directory.source_id(key) == "rtsp_a"


def test_a_source_renamed_to_its_own_id_is_named_by_it():
    directory = AudioSourceDirectory(
        [
            _observe("Node", "rtsp_a", "Feeder", "2026-11-01 08:00:00"),
            _observe("Node", "rtsp_a", "rtsp_a", "2026-11-02 08:00:00"),
        ]
    )
    assert directory.display_name(directory.key_for("Node", "rtsp_a", "Feeder")) == "rtsp_a"


def test_a_source_that_never_sent_a_name_is_named_by_its_id():
    directory = AudioSourceDirectory([_observe("Node", "rtsp_a", None, "2026-10-01 08:00:00")])
    assert directory.display_name(directory.key_for("Node", "rtsp_a", None)) == "rtsp_a"
    directory.observe(_observe("Node", "rtsp_a", "birdcam", "2026-09-01 08:00:00"))
    assert directory.display_name(directory.key_for("Node", "rtsp_a", None)) == "birdcam"


@pytest.mark.parametrize(
    "first,second",
    [
        (("Node", "rtsp_old_url", "birdcam"), ("Node", "rtsp_new_url", "birdcam")),
        # Two installs reading their own rtsp://localhost:8554/audio send one id.
        (("House", "rtsp_a", "birdcam"), ("Shed", "rtsp_a", "shedcam")),
        (("Shed", CARD, "Default Audio Device"), ("House", CARD, "Default Audio Device")),
        # A call that names no install never joins one that does.
        ((None, "rtsp_a", "birdcam"), ("House", "rtsp_a", "birdcam")),
        ((None, CARD, "Shed mic"), (None, CARD, "Porch mic")),
        # Installs and ids are compared exactly as sent.
        (("Shed", "rtsp_a", "Feeder"), ("shed", "rtsp_a", "Perch")),
        (("Shed", "rtsp_A", "Feeder"), ("Shed", "rtsp_a", "Perch")),
    ],
)
def test_two_microphones_are_never_one_source(first, second):
    directory = AudioSourceDirectory(
        [_observe(*first, "2026-11-01 08:00:00"), _observe(*second, "2026-11-02 08:00:00")]
    )
    assert directory.key_for(*first) != directory.key_for(*second)


def test_rows_without_an_id_join_the_one_source_that_carried_their_name():
    directory = AudioSourceDirectory(
        [
            _observe(None, None, "birdcam", "2026-08-01 08:00:00", count=10),
            _observe("Node", "rtsp_a", "birdcam", "2026-10-01 08:00:00", count=5),
            _observe("Node", "rtsp_a", "Feeder", "2026-11-01 08:00:00"),
        ]
    )
    assert directory.key_for(None, None, "BirdCam") == directory.key_for("Node", "rtsp_a", "Feeder")


@pytest.mark.parametrize(
    "others",
    [
        # Two sources carried the name.
        [("Node", "rtsp_old_url", "birdcam"), ("Node", "rtsp_new_url", "birdcam")],
        # One of them carried it as its own id, sent as its name.
        [("Shed", "rtsp_a", "rtsp_a"), ("Shed", "rtsp_b", "rtsp_a")],
    ],
)
def test_rows_without_an_id_stay_apart_when_their_name_belonged_to_two_sources(others):
    name = others[0][2]
    directory = AudioSourceDirectory(
        [_observe(None, None, name, "2026-08-01 08:00:00")]
        + [_observe(*other, f"2026-1{index}-01 08:00:00") for index, other in enumerate(others)]
    )
    legacy = directory.key_for(None, None, name)
    assert legacy[0] == "name"
    assert directory.display_name(legacy) == name


def test_rows_without_an_id_on_another_install_do_not_join():
    directory = AudioSourceDirectory(
        [
            _observe("Shed", None, "birdcam", "2026-08-01 08:00:00"),
            _observe("House", "rtsp_a", "birdcam", "2026-10-01 08:00:00"),
        ]
    )
    assert directory.key_for("Shed", None, "birdcam")[0] == "name"
    assert directory.source_node(directory.key_for("Shed", None, "birdcam")) == "Shed"


def test_hiding_a_call_never_hands_an_older_call_to_another_microphone():
    directory = AudioSourceDirectory(
        [
            _observe(None, None, "Reused", "2026-08-01 08:00:00"),
            _observe("Node", "rtsp_a", "Reused", "2026-10-01 08:00:00"),
            _observe("Node", "rtsp_b", "Reused", "2026-11-01 08:00:00", shown=False),
        ]
    )
    assert directory.key_for(None, None, "Reused")[0] == "name"


@pytest.mark.parametrize("hidden_view", [False, True])
def test_a_source_whose_only_identified_call_is_hidden_is_named_by_its_shown_older_calls(hidden_view):
    directory = AudioSourceDirectory(
        [
            _observe(None, None, "Feed Here", "2026-08-01 08:00:00", shown=not hidden_view),
            _observe("Node", "rtsp_a", "Feed Here", "2026-11-01 08:00:00", shown=hidden_view),
        ]
    )
    assert directory.display_name(directory.key_for("Node", "rtsp_a", "Feed Here")) == "Feed Here"


def test_a_filter_finds_a_source_by_any_name_it_has_carried_or_its_id():
    directory = AudioSourceDirectory(
        [
            _observe(None, None, "birdcam", "2026-08-01 08:00:00"),
            _observe("Node", "rtsp_a", "birdcam", "2026-10-01 08:00:00"),
            _observe("Node", "rtsp_a", "Feeder", "2026-11-01 08:00:00"),
            _observe("Node", "rtsp_b", "nestcam", "2026-11-01 08:00:00"),
        ]
    )
    source_a = directory.key_for("Node", "rtsp_a", "Feeder")
    assert directory.keys_matching_text("feed") == {source_a}
    assert directory.keys_matching_text("BIRD") == {source_a}
    assert directory.keys_matching_text("RTSP_A") == {source_a}
    assert directory.keys_matching_text("  ") == set()
