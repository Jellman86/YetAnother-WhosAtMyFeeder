"""The BirdNET-Go sources a camera can be linked to, one entry per stream (#1111).

A camera's audio link matches the names and ids stored on each call, literally
(``app.utils.birdnet_payload.extract_audio_mapping_keys``): each token is trimmed and case-folded,
nothing more. BirdNET-Go keeps a stream's id when the stream is renamed, so a link by id survives a
rename where a link by name does not. Each entry therefore offers the stream's id as the value to
save, and the names it has carried.

Streams are told apart exactly as Audio history tells them apart
(``app.utils.audio_source_identity``): by id on the install that sent it, with calls from before
BirdNET-Go sent ids joining the one stream that carried their name. Two installs that send the same
id are two entries with the same value to save, since a link by id hears both. A source that never
sent an id is linked by its name, as the matcher reads it from the stored call.

Each name says whether Settings should offer to link by the stream's id instead: only when the name
is one this stream alone has carried and no source carries now. That is decided from every call the
owner keeps, hidden ones included, so hiding a call never invents or hides a rename. Hidden calls
never name a stream and never give a time.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.utils.audio_source_identity import AudioSourceDirectory, SourceKey, SourceObservation
from app.utils.birdnet_payload import normalize_mapping_key

_IDENTIFIED = frozenset({"node", "unattributed"})


def literal_source_name(sensor_id: str | None, raw_data: str | None) -> str | None:
    """The name a call without an id is matched by: its first name field, trimmed, as sent."""
    try:
        payload = json.loads(raw_data) if raw_data else None
    except (TypeError, ValueError):
        payload = None
    candidates: list[object] = []
    if isinstance(payload, dict):
        nested = payload.get("Source")
        nested = nested if isinstance(nested, dict) else {}
        candidates = [payload.get("nm"), payload.get("sourceName"), nested.get("displayName")]
    for candidate in [*candidates, sensor_id]:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


@dataclass(frozen=True)
class SourceLinkName:
    name: str
    # The newest visible call under this name, from any call the name matches; None when only hidden calls carry it.
    last_seen: str | None
    current: bool
    offer_link_by_id: bool


@dataclass(frozen=True)
class AudioSourceLink:
    mapping_value: str
    source_name: str
    source_id: str | None
    source_node: str | None
    # The newest visible call carrying the value to save: the id, or the name of a source without one.
    last_seen: str
    names: list[SourceLinkName]


@dataclass
class _Name:
    # (stored time, spelling) of the newest call under this name, and of the newest visible one.
    newest: tuple[str, str]
    newest_shown: tuple[str, str] | None = None

    @property
    def spelling(self) -> str:
        return (self.newest_shown or self.newest)[1]


@dataclass
class _Stream:
    last_seen: str = ""
    names: dict[str, _Name] = field(default_factory=dict)

    def record(self, observation: SourceObservation, carries_value: bool) -> None:
        if observation.shown and carries_value:
            self.last_seen = max(self.last_seen, observation.last_seen)
        if not observation.name:
            return
        stamp = (observation.last_seen, observation.name)
        name = self.names.setdefault(normalize_mapping_key(observation.name), _Name(newest=stamp))
        name.newest = max(name.newest, stamp)
        if observation.shown:
            name.newest_shown = max(name.newest_shown or stamp, stamp)


def audio_source_links(
    observations: Iterable[SourceObservation],
    literal_names: Mapping[tuple[str | None, str], str] | None = None,
) -> list[AudioSourceLink]:
    """Each linkable source with a visible call, newest first.

    ``observations`` are the owner's, hidden calls included as evidence (``shown=False``).
    ``literal_names`` maps a stored (node, name) without an id to the name the matcher reads.
    """
    seen = list(observations)
    directory = AudioSourceDirectory(seen)
    streams: dict[SourceKey, _Stream] = {}
    for observation in seen:
        key = directory.key_for(observation.node, observation.source_id, observation.name)
        if key[0] == "unknown":
            continue
        carries_value = bool(observation.source_id) or key[0] == "name"
        streams.setdefault(key, _Stream()).record(observation, carries_value)

    current = {key: directory.display_name(key) for key in streams}
    current_names = {normalize_mapping_key(name) for name in current.values() if name}
    carriers: dict[str, int] = {}
    for key, stream in streams.items():
        if key[0] in _IDENTIFIED:
            for name in stream.names:
                carriers[name] = carriers.get(name, 0) + 1

    links = []
    for key, stream in streams.items():
        if not stream.last_seen:
            continue
        name_now = current[key]
        now_key = normalize_mapping_key(name_now)
        source_id = directory.source_id(key) if key[0] in _IDENTIFIED else None
        if source_id:
            mapping_value = source_id
        else:
            mapping_value = (literal_names or {}).get((key[1] or None, key[2])) or name_now or key[2]
        names = [
            SourceLinkName(
                name=name.spelling,
                last_seen=name.newest_shown[0] if name.newest_shown else None,
                current=folded == now_key,
                offer_link_by_id=bool(source_id)
                and folded != now_key
                and folded not in current_names
                and carriers.get(folded) == 1,
            )
            for folded, name in stream.names.items()
        ]
        # The current name first, then the others, the most recently heard first.
        names.sort(key=lambda name: (name.current, name.last_seen or ""), reverse=True)
        links.append(
            AudioSourceLink(
                mapping_value=mapping_value,
                source_name=name_now or mapping_value,
                source_id=source_id,
                source_node=directory.source_node(key),
                last_seen=stream.last_seen,
                names=names,
            )
        )
    return sorted(links, key=lambda link: (link.last_seen, link.mapping_value, link.source_node or ""), reverse=True)
