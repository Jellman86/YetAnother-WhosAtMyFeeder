"""Which BirdNET-Go source a stored call came from, kept whole across a rename (#1111).

BirdNET-Go names each audio source, and the owner can rename it at any time. It also gives each
source an id hashed from its connection string: the stream address for a network stream
(``rtsp_3af0d74c``), the device name for a sound card (``audio_card_22a9b331``). A rename leaves
the id alone, so YA-WAMF identifies a source by that id on the BirdNET-Go install that sent it,
named by the node name BirdNET-Go publishes as ``SourceNode``. Both are compared exactly as sent,
case included, once whitespace at either end is trimmed: ``Shed`` and ``shed``, or ``rtsp_A`` and
``rtsp_a``, are different installs and different ids.

- The hash covers only the connection string, so two installs can send the same id for two
  microphones: each reading its own ``rtsp://localhost:8554/audio``, or its own ``default`` sound
  card. An id is therefore one source per install, never shared across installs.
- A call that names no install is unattributed: it never joins an install's source, and it is kept
  apart by its name as well as its id, because two unknown installs can send the same id.

Changing a source's address changes its id, so BirdNET-Go and YA-WAMF both treat it as a new source.

A call's name is the one BirdNET-Go sent (``nm``, ``sourceName`` or ``Source.displayName``, or the
name an older version stored). A label made up from the id because no name was sent is no name at
all, so a source is never named, or given an older call, on the strength of its own id.

Calls recorded before BirdNET-Go sent ids carry only a name. Such a call joins the one source with
an id that carried the same name (on the call's install, when it names one), judged from every call
the owner keeps, hidden or not, so hiding a call never moves an older call to another microphone.
A name two sources have carried stays an entry of its own: two different sources are never merged.

Every source field arrives in an untrusted MQTT message, so it is cleaned before it is stored:
identifiers with control characters, broken Unicode, whitespace, mapping separators, ``*`` or more
than ``MAX_SOURCE_TEXT_LENGTH`` characters are refused rather than shortened, so two distinct ids can
never be cut into one; names lose their control characters and are refused when too long. A call
whose id is refused is not one from before ids, so it keeps its install but no name: it is an
unknown source on its install and never joins a source by name. Calls with neither an id nor a name
are one unknown source per install.

Only Audio history's sources, and its source filter, read this identity. Camera mappings still
match the names and ids each call was stored with, literally, as they always have.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_SOURCE_TEXT_LENGTH = 200

# Never part of a BirdNET-Go id, and each would let an id change how a mapping is read.
_UNSAFE_IN_IDENTIFIER = re.compile(r"[,;|*\s]")

# Control characters and lone surrogates: never part of a name a person gave a source.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cs"})


def _has_unsafe_characters(value: str) -> bool:
    return any(unicodedata.category(character) in _UNSAFE_CATEGORIES for character in value)


def clean_source_identifier(value: object) -> str | None:
    """A source id fit to store and compare, or None when it is missing or unsafe."""
    cleaned = clean_node_name(value)
    if cleaned is None or _UNSAFE_IN_IDENTIFIER.search(cleaned):
        return None
    return cleaned


def clean_node_name(value: object) -> str | None:
    """A BirdNET-Go node name fit to store and compare, or None when it is missing or unsafe."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_SOURCE_TEXT_LENGTH or _has_unsafe_characters(cleaned):
        return None
    return cleaned


def clean_source_label(value: object) -> str | None:
    """A source's name fit to store and show: control characters dropped, None when missing or too long."""
    if not isinstance(value, str) or len(value) > MAX_SOURCE_TEXT_LENGTH * 4:
        return None
    visible = "".join(
        " " if unicodedata.category(character) == "Cc" else character
        for character in value
        if unicodedata.category(character) != "Cs"
    )
    cleaned = " ".join(visible.split())
    if not cleaned or len(cleaned) > MAX_SOURCE_TEXT_LENGTH:
        return None
    return cleaned


def _fold(value: str | None) -> str:
    """How a name is compared when an older call is matched to a source, and in text searches."""
    return " ".join((value or "").split()).casefold()


def extract_birdnet_source_id(payload: object) -> str | None:
    """BirdNET-Go's id for the source of a detection, from any payload shape it has published."""
    if not isinstance(payload, dict):
        return None
    nested = payload.get("Source")
    nested = nested if isinstance(nested, dict) else {}
    for candidate in (payload.get("sourceId"), nested.get("id"), payload.get("src")):
        if isinstance(candidate, str) and candidate.strip():
            return clean_source_identifier(candidate)
    return None


def extract_birdnet_source_node(payload: object) -> str | None:
    """The BirdNET-Go install that reported a detection, as its node name."""
    if not isinstance(payload, dict):
        return None
    return clean_node_name(payload.get("SourceNode"))


def _id_fields(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    nested = payload.get("Source")
    nested = nested if isinstance(nested, dict) else {}
    # Not "id": that is the detection number now, and was a sensor's name in the oldest messages.
    values = (payload.get("sourceId"), payload.get("src"), nested.get("id"))
    return {value.strip() for value in values if isinstance(value, str) and value.strip()}


def explicit_source_name(sensor_id: str | None, payload: object) -> str | None:
    """The name a call's source was given, or None when its only label would be made from its id.

    A name field BirdNET-Go sent counts even when it equals the id. Without one, the stored sensor
    stands in, as history has always shown it, unless it is one of the call's own ids: that is what
    is stored when a call carries no name.
    """
    nested = payload.get("Source") if isinstance(payload, dict) else None
    nested = nested if isinstance(nested, dict) else {}
    if isinstance(payload, dict):
        for candidate in (payload.get("nm"), payload.get("sourceName"), nested.get("displayName")):
            if isinstance(candidate, str) and candidate.strip():
                return clean_source_label(candidate)
    if isinstance(sensor_id, str) and sensor_id.strip() and sensor_id.strip() not in _id_fields(payload):
        return clean_source_label(sensor_id)
    return None


@dataclass(frozen=True)
class StoredSource:
    """Who reported a call (node), BirdNET-Go's id for the source, and the name it was given."""

    node: str | None
    source_id: str | None
    name: str | None


def _sent_a_source_id(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    nested = payload.get("Source")
    nested = nested if isinstance(nested, dict) else {}
    values = (payload.get("sourceId"), nested.get("id"), payload.get("src"))
    return any(value is not None and not (isinstance(value, str) and not value.strip()) for value in values)


def source_of_payload(sensor_id: str | None, payload: object) -> StoredSource:
    """A call's source as ingest records it, from the payload BirdNET-Go published.

    A call that sent an id YA-WAMF refused keeps its install but no name: it is not a call from
    before BirdNET-Go sent ids, so its name must not join it to a source that carried the name.
    """
    source_id = extract_birdnet_source_id(payload)
    refused = source_id is None and _sent_a_source_id(payload)
    return StoredSource(
        node=extract_birdnet_source_node(payload),
        source_id=source_id,
        name=None if refused else explicit_source_name(sensor_id, payload),
    )


def read_stored_source(source_node: str | None, source_id: str | None, source_name: str | None) -> StoredSource:
    """A stored call's source, from the columns ingest and the upgrade fill.

    The upgrade reads every stored payload by the same rule ingest uses, so a call whose columns
    are all empty is one whose payload names no source: it is an unknown source, and its payload is
    never read again.
    """
    return StoredSource(
        clean_node_name(source_node), clean_source_identifier(source_id), clean_source_label(source_name)
    )


@dataclass(frozen=True)
class SourceObservation:
    """Calls from one source under one name: the newest one's stored time and how many there were.

    ``shown`` is False for calls kept only as evidence of who carried which name: the owner's hidden
    calls in the visible view, and visible calls in the hidden view.
    """

    node: str | None
    source_id: str | None
    name: str | None
    last_seen: str
    count: int = 1
    shown: bool = True


# ("node", node, id) for a source on a named install, ("unattributed", id, name) for one whose
# install is unknown, ("name", node, name) for a call without an id that joins no source, and
# ("unknown", node) for a call with neither, on its install when it names one. Node, id and name
# are exact, as sent.
SourceKey = tuple[str, ...]
_IDENTIFIED = frozenset({"node", "unattributed"})


def identity_key(node: str | None, source_id: str | None, name: str | None) -> SourceKey | None:
    """The source a call with an id belongs to, by the rule in this module's docstring."""
    if not source_id:
        return None
    if node:
        return ("node", node, source_id)
    return ("unattributed", source_id, name or "")


@dataclass
class _Source:
    source_id: str | None
    node: str | None = None
    # Folded names the source has carried on any call the owner keeps: who may own an older call.
    evidence_names: set[str] = field(default_factory=set)
    # What the view shows: the newest name, and how many calls.
    latest_name: tuple[str, str] | None = None
    last_seen: str = ""
    count: int = 0

    def record(self, name: str | None, last_seen: str, count: int, shown: bool) -> None:
        if name:
            self.evidence_names.add(_fold(name))
        if not shown:
            return
        self.count += count
        self.last_seen = max(self.last_seen, last_seen)
        if name and (self.latest_name is None or last_seen >= self.latest_name[0]):
            self.latest_name = (last_seen, name)

    @property
    def display_name(self) -> str | None:
        return self.latest_name[1] if self.latest_name else self.source_id


def _clean_key_part(node: str | None, source_id: str | None, name: str | None) -> tuple[str, str, str]:
    return (
        clean_node_name(node) or "",
        clean_source_identifier(source_id) or "",
        clean_source_label(name) or "",
    )


class AudioSourceDirectory:
    """Every source the stored history has heard, the names each has carried, and its latest name.

    Built from one grouped read of the history, so the Sources list and the source filter resolve
    a row to the same source.
    """

    def __init__(self, observations: Iterable[SourceObservation] = ()) -> None:
        self._sources: dict[SourceKey, _Source] = {}
        # Calls with no id, by exact (node, name).
        self._unidentified: dict[tuple[str, str], _Source] = {}
        # Calls with neither, by exact node.
        self._unknown: dict[str, _Source] = {}
        self._resolved_rows: dict[tuple[str, str, str], SourceKey] = {}
        # Every (node, id, name) exactly as stored, so a filter can name the calls of a source in SQL.
        self._stored: set[tuple[str | None, str | None, str | None]] = set()
        self._shown_names: dict[SourceKey, tuple[str, str] | None] | None = None
        for observation in observations:
            self.observe(observation)

    def observe(self, observation: SourceObservation) -> None:
        self._stored.add((observation.node, observation.source_id, observation.name))
        node, source_id, name = _clean_key_part(observation.node, observation.source_id, observation.name)
        key = identity_key(node, source_id, name)
        if key is not None:
            source = self._sources.setdefault(key, _Source(source_id=source_id, node=node or None))
        elif name:
            source = self._unidentified.setdefault((node, name), _Source(source_id=None, node=node or None))
        else:
            source = self._unknown.setdefault(node, _Source(source_id=None, node=node or None))
        source.record(name or None, observation.last_seen, observation.count, observation.shown)
        self._resolved_rows.clear()
        self._shown_names = None

    def _owner_of_name(self, node: str, name: str) -> SourceKey | None:
        # Every kept call counts, shown or not: hiding a call must not hand an older one to another source.
        folded = _fold(name)
        candidates = [
            key
            for key, source in self._sources.items()
            if folded in source.evidence_names and (not node or (key[0] == "node" and key[1] == node))
        ]
        return candidates[0] if len(candidates) == 1 else None

    def key_for(self, node: str | None, source_id: str | None, name: str | None) -> SourceKey:
        """The one source a stored call belongs to."""
        row = _clean_key_part(node, source_id, name)
        cached = self._resolved_rows.get(row)
        if cached is not None:
            return cached
        clean_node, clean_id, clean_name = row
        resolved = identity_key(clean_node, clean_id, clean_name)
        if resolved is None:
            if not clean_name:
                resolved = ("unknown", clean_node)
            else:
                resolved = self._owner_of_name(clean_node, clean_name) or ("name", clean_node, clean_name)
        self._resolved_rows[row] = resolved
        return resolved

    def _source(self, key: SourceKey) -> _Source | None:
        if key[0] in _IDENTIFIED:
            return self._sources.get(key)
        if key[0] == "name":
            return self._unidentified.get((key[1], key[2]))
        return self._unknown.get(key[1])

    def _latest_shown_names(self) -> dict[SourceKey, tuple[str, str] | None]:
        """Each identified source's newest shown name, taken from the older calls that joined it
        when none of its own calls with an id is shown, as when they are all hidden."""
        if self._shown_names is not None:
            return self._shown_names
        latest = {key: source.latest_name for key, source in self._sources.items()}
        for (node, name), source in self._unidentified.items():
            if not source.count or not source.latest_name:
                continue
            key = self.key_for(node or None, None, name)
            if key in latest and self._sources[key].latest_name is None:
                current = latest[key]
                if current is None or source.latest_name[0] > current[0]:
                    latest[key] = source.latest_name
        self._shown_names = latest
        return latest

    def display_name(self, key: SourceKey) -> str | None:
        """The name the source carries now: the one on its newest shown call, or None for a source not read."""
        source = self._source(key)
        if source is None:
            return None
        if key[0] in _IDENTIFIED:
            latest = self._latest_shown_names().get(key)
            if latest is not None:
                return latest[1]
        return source.display_name if source.count else None

    def source_id(self, key: SourceKey) -> str | None:
        source = self._source(key)
        return source.source_id if source is not None else None

    def source_node(self, key: SourceKey) -> str | None:
        """The install the source belongs to; None when its calls name none."""
        source = self._source(key)
        return source.node if source is not None and key[0] in {"node", "name", "unknown"} else None

    def stored_identities_of(self, keys: set[SourceKey]) -> list[tuple[str | None, str | None, str | None]]:
        """Each (node, id, name) stored on a call of one of these sources, exactly as stored."""
        return sorted(
            (identity for identity in self._stored if self.key_for(*identity) in keys),
            key=lambda identity: tuple("" if part is None else part for part in identity),
        )

    def keys_matching_text(self, text: str | None) -> set[SourceKey]:
        """Sources whose id or any name they have carried contains ``text``, as a source filter reads it."""
        needle = _fold(text)
        if not needle:
            return set()
        matched = {
            key
            for key, source in self._sources.items()
            if needle in _fold(source.source_id) or any(needle in name for name in source.evidence_names)
        }
        for (node, name), _source in self._unidentified.items():
            if needle in _fold(name):
                matched.add(self.key_for(node or None, None, name))
        return matched
