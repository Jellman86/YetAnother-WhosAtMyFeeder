"""Settings lists each BirdNET-Go stream once, by the value a camera should be linked by (#1111).

A stream renamed in BirdNET-Go keeps its id, so it is one entry under its newest name with the
names it carried before; a source from a BirdNET-Go version that sent no id is linked by its name.
"""

from app.utils.audio_source_links import SourceNameUse, audio_source_links

STREAM = "rtsp_52d54d7d"


def _use(source_id, name, last_seen, count=1, node="Quark"):
    return SourceNameUse(node=node, source_id=source_id, name=name, last_seen=last_seen, count=count)


def test_a_renamed_stream_is_one_entry_under_its_newest_name_linked_by_its_id():
    [entry] = audio_source_links(
        [
            _use(STREAM, "ESP32 v3.0", "2026-11-27 10:00:00", count=40),
            _use(STREAM, "ESP32 v3.0 X", "2026-11-28 09:00:00", count=3),
        ],
        names_without_id=set(),
    )
    assert entry.mapping_value == STREAM
    assert entry.source_id == STREAM
    assert entry.source_name == "ESP32 v3.0 X"
    assert [(name.name, name.last_seen) for name in entry.earlier_names] == [("ESP32 v3.0", "2026-11-27 10:00:00")]
    assert entry.last_seen == "2026-11-28 09:00:00"
    assert entry.seen_count == 43


def test_a_source_without_an_id_is_linked_by_its_name():
    [entry] = audio_source_links(
        [_use(None, "Patio Mic", "2026-11-28 09:00:00", count=5)], names_without_id={"patio mic"}
    )
    assert (entry.mapping_value, entry.source_id, entry.source_name, entry.seen_count) == (
        "Patio Mic",
        None,
        "Patio Mic",
        5,
    )
    assert entry.earlier_names == []


def test_a_stream_that_sent_no_name_is_named_by_its_id():
    [entry] = audio_source_links([_use(STREAM, None, "2026-11-28 09:00:00")], names_without_id=set())
    assert (entry.mapping_value, entry.source_name) == (STREAM, STREAM)


def test_calls_from_before_ids_join_the_stream_that_carried_their_name():
    """An older call under "ESP32 v3.0" with no id is the same microphone, not a second entry."""
    [entry] = audio_source_links(
        [
            _use(None, "ESP32 v3.0", "2026-10-01 08:00:00", count=7),
            _use(STREAM, "ESP32 v3.0", "2026-11-27 10:00:00", count=40),
            _use(STREAM, "ESP32 v3.0 X", "2026-11-28 09:00:00", count=3),
        ],
        names_without_id={"esp32 v3.0"},
    )
    assert entry.mapping_value == STREAM
    assert entry.seen_count == 50
    [earlier] = entry.earlier_names
    assert (earlier.name, earlier.has_calls_without_id) == ("ESP32 v3.0", True)


def test_an_earlier_name_says_whether_calls_without_an_id_still_match_it_alone():
    """Hidden calls count too: a link by name is only dropped when nothing stored needs the name."""
    [entry] = audio_source_links(
        [
            _use(STREAM, "Reolink", "2026-11-27 10:00:00"),
            _use(STREAM, "Reolink TEST", "2026-11-28 09:00:00"),
        ],
        names_without_id={"reolink"},
    )
    assert [(name.name, name.has_calls_without_id) for name in entry.earlier_names] == [("Reolink", True)]
    [entry] = audio_source_links(
        [
            _use(STREAM, "Reolink", "2026-11-27 10:00:00"),
            _use(STREAM, "Reolink TEST", "2026-11-28 09:00:00"),
        ],
        names_without_id=set(),
    )
    assert [(name.name, name.has_calls_without_id) for name in entry.earlier_names] == [("Reolink", False)]


def test_a_name_two_streams_carried_stays_its_own_entry():
    """Older calls under a shared name cannot be given to either stream, so they keep their name link."""
    entries = audio_source_links(
        [
            _use("rtsp_a", "Garden", "2026-11-27 10:00:00"),
            _use("rtsp_b", "Garden", "2026-11-27 11:00:00"),
            _use(None, "Garden", "2026-10-01 08:00:00"),
        ],
        names_without_id={"garden"},
    )
    assert [entry.mapping_value for entry in entries] == ["rtsp_b", "rtsp_a", "Garden"]


def test_entries_are_newest_first_and_a_stream_on_two_installs_is_one_link():
    """A link by id matches that id from any install, so the list offers it once."""
    entries = audio_source_links(
        [
            _use("rtsp_quiet", "Pond", "2026-08-01 06:00:00"),
            _use(STREAM, "Feeder", "2026-11-28 09:00:00", node="Shed"),
            _use(STREAM, "Feeder", "2026-11-28 08:00:00", node="Quark"),
        ],
        names_without_id=set(),
    )
    assert [(entry.mapping_value, entry.seen_count) for entry in entries] == [(STREAM, 2), ("rtsp_quiet", 1)]


def test_calls_with_neither_an_id_nor_a_name_cannot_be_linked_and_are_not_listed():
    assert audio_source_links([_use(None, None, "2026-11-28 09:00:00")], names_without_id=set()) == []


def test_a_call_without_an_id_never_renames_the_stream_it_joins():
    """A late call under the old name and no id is the same microphone, but the stream's own calls name it."""
    [entry] = audio_source_links(
        [
            _use(STREAM, "Feeder", "2026-11-27 10:00:00"),
            _use(STREAM, "Private Door", "2026-11-27 11:00:00"),
            _use(None, "Feeder", "2026-11-28 09:00:00", node=None),
        ],
        names_without_id={"feeder"},
    )
    assert (entry.source_name, entry.last_seen, entry.seen_count) == ("Private Door", "2026-11-28 09:00:00", 3)
    assert [(name.name, name.last_seen) for name in entry.earlier_names] == [("Feeder", "2026-11-27 10:00:00")]
