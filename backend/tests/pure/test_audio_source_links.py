"""Settings lists each BirdNET-Go stream once, by the value a camera should be linked by (#1111).

A stream renamed in BirdNET-Go keeps its id on its install, so it is one entry under its newest
name with the names it carried before; a source from a BirdNET-Go version that sent no id is linked
by its name, exactly as the matcher reads it.
"""

from app.utils.audio_source_identity import SourceObservation
from app.utils.audio_source_links import audio_source_links, literal_source_name

STREAM = "rtsp_52d54d7d"


def _seen(source_id, name, last_seen, node="Quark", shown=True):
    return SourceObservation(node=node, source_id=source_id, name=name, last_seen=last_seen, shown=shown)


def _names(entry):
    return [(name.name, name.last_seen, name.current, name.offer_link_by_id) for name in entry.names]


def test_a_renamed_stream_is_one_entry_under_its_newest_name_linked_by_its_id():
    [entry] = audio_source_links(
        [
            _seen(STREAM, "ESP32 v3.0", "2026-11-27 10:00:00"),
            _seen(STREAM, "ESP32 v3.0 X", "2026-11-28 09:00:00"),
        ]
    )
    assert (entry.mapping_value, entry.source_id, entry.source_node) == (STREAM, STREAM, "Quark")
    assert entry.source_name == "ESP32 v3.0 X"
    assert entry.last_seen == "2026-11-28 09:00:00"
    assert _names(entry) == [
        ("ESP32 v3.0 X", "2026-11-28 09:00:00", True, False),
        ("ESP32 v3.0", "2026-11-27 10:00:00", False, True),
    ]


def test_a_source_without_an_id_is_linked_by_the_name_the_matcher_reads():
    [entry] = audio_source_links(
        [_seen(None, "Garden Mic", "2026-11-28 09:00:00")],
        literal_names={("Quark", "Garden Mic"): "Garden  Mic"},
    )
    assert (entry.mapping_value, entry.source_id, entry.source_name) == ("Garden  Mic", None, "Garden Mic")
    assert _names(entry) == [("Garden Mic", "2026-11-28 09:00:00", True, False)]


def test_the_literal_name_is_the_first_name_field_trimmed_but_otherwise_as_sent():
    assert literal_source_name("garden-mic", '{"sourceName": "  Garden  Mic "}') == "Garden  Mic"
    assert literal_source_name("Shed  Mic", '{"detectionId": 4}') == "Shed  Mic"
    assert literal_source_name(" Shed ", "not json") == "Shed"
    assert literal_source_name(None, '{"nm": 4}') is None


def test_a_stream_that_sent_no_name_is_named_by_its_id():
    [entry] = audio_source_links([_seen(STREAM, None, "2026-11-28 09:00:00")])
    assert (entry.mapping_value, entry.source_name, entry.names) == (STREAM, STREAM, [])


def test_calls_from_before_ids_join_the_stream_that_carried_their_name_on_their_install():
    """They match the name, so its time moves; they do not carry the id, so the id's time does not."""
    [entry] = audio_source_links(
        [
            _seen(STREAM, "ESP32 v3.0", "2026-11-27 10:00:00"),
            _seen(STREAM, "ESP32 v3.0 X", "2026-11-28 08:00:00"),
            _seen(None, "ESP32 v3.0", "2026-11-28 09:00:00"),
        ]
    )
    assert (entry.source_name, entry.last_seen) == ("ESP32 v3.0 X", "2026-11-28 08:00:00")
    assert _names(entry)[1] == ("ESP32 v3.0", "2026-11-28 09:00:00", False, True)


def test_a_call_without_an_id_from_another_install_keeps_its_own_entry():
    entries = audio_source_links(
        [
            _seen(STREAM, "Feeder", "2026-11-27 10:00:00", node="Quark"),
            _seen(None, "Feeder", "2026-11-28 09:00:00", node="Shed"),
        ]
    )
    assert [(entry.mapping_value, entry.source_node) for entry in entries] == [("Feeder", "Shed"), (STREAM, "Quark")]


def test_two_installs_sharing_an_id_are_two_entries_and_never_each_others_rename():
    card = "audio_card_22a9b331"
    entries = audio_source_links(
        [
            _seen(card, "Shed Mic", "2026-11-28 08:00:00", node="Shed"),
            _seen(card, "House Mic", "2026-11-28 09:00:00", node="House"),
        ]
    )
    assert [(entry.source_name, entry.mapping_value, entry.source_node) for entry in entries] == [
        ("House Mic", card, "House"),
        ("Shed Mic", card, "Shed"),
    ]
    assert [_names(entry) for entry in entries] == [
        [("House Mic", "2026-11-28 09:00:00", True, False)],
        [("Shed Mic", "2026-11-28 08:00:00", True, False)],
    ]


def test_a_hidden_old_name_still_offers_the_stream_id_but_never_names_or_times_it():
    [entry] = audio_source_links(
        [
            _seen(STREAM, "ESP32 v3.0", "2026-11-28 10:00:00", shown=False),
            _seen(STREAM, "ESP32 v3.0 X", "2026-11-28 09:00:00"),
        ]
    )
    assert (entry.source_name, entry.last_seen) == ("ESP32 v3.0 X", "2026-11-28 09:00:00")
    assert _names(entry) == [
        ("ESP32 v3.0 X", "2026-11-28 09:00:00", True, False),
        ("ESP32 v3.0", None, False, True),
    ]


def test_an_old_name_that_is_another_streams_current_name_offers_nothing():
    """On any install: a link by that name still hears the other stream, so it is not a rename to fix."""
    entries = audio_source_links(
        [
            _seen(STREAM, "Garden", "2026-11-27 10:00:00", node="Quark"),
            _seen(STREAM, "Feeder", "2026-11-28 09:00:00", node="Quark"),
            _seen("rtsp_other", "Garden", "2026-11-20 09:00:00", node="Shed"),
        ]
    )
    feeder = next(entry for entry in entries if entry.source_name == "Feeder")
    assert ("Garden", "2026-11-27 10:00:00", False, False) in _names(feeder)


def test_an_old_name_two_streams_carried_offers_nothing_even_when_one_carried_it_in_hidden_calls():
    entries = audio_source_links(
        [
            _seen("rtsp_a", "Garden", "2026-11-20 10:00:00", shown=False),
            _seen("rtsp_a", "Pond", "2026-11-28 08:00:00"),
            _seen("rtsp_b", "Garden", "2026-11-21 10:00:00"),
            _seen("rtsp_b", "Hedge", "2026-11-28 09:00:00"),
        ]
    )
    for entry in entries:
        assert not any(name.offer_link_by_id for name in entry.names), entry


def test_hiding_a_streams_calls_never_hands_its_older_calls_to_another_stream():
    entries = audio_source_links(
        [
            _seen("rtsp_a", "Feeder", "2026-11-20 10:00:00", shown=False),
            _seen("rtsp_b", "Feeder", "2026-11-21 10:00:00"),
            _seen(None, "Feeder", "2026-10-01 08:00:00"),
        ]
    )
    assert [entry.mapping_value for entry in entries] == ["rtsp_b", "Feeder"]


def test_names_compare_as_the_matcher_does():
    """Case folds fully, so Straße and STRASSE are one name; a stored name keeps its newest spelling."""
    [entry] = audio_source_links(
        [
            _seen(STREAM, "STRASSE", "2026-11-27 10:00:00"),
            _seen(STREAM, "Straße", "2026-11-27 11:00:00"),
            _seen(STREAM, "Hof", "2026-11-28 09:00:00"),
        ]
    )
    assert _names(entry) == [
        ("Hof", "2026-11-28 09:00:00", True, False),
        ("Straße", "2026-11-27 11:00:00", False, True),
    ]


def test_calls_with_neither_an_id_nor_a_name_cannot_be_linked_and_are_not_listed():
    assert audio_source_links([_seen(None, None, "2026-11-28 09:00:00")]) == []
