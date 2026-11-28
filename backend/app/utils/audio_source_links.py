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
    # Every install with a listed stream sending this id, when more than one does; otherwise empty.
    installs_sharing_id: list[str]
    # The newest visible call carrying the value to save: the id, or the name of a source without one.
    last_seen: str
    names: list[SourceLinkName]


# (node, id, name, shown) as stored -> the names the matcher reads from the oldest and the newest such call.
LiteralNames = Mapping[tuple[str | None, str | None, str, bool], tuple[str, str]]


@dataclass
class _Label:
    """One cleaned stored name on a stream: the spellings seen behind it, and its newest call of any visibility."""

    spellings: set[str] = field(default_factory=set)
    newest: str = ""


@dataclass
class _Name:
    # (stored time, spelling) of the newest call under this name, and of the newest visible one.
    newest: tuple[str, str]
    newest_shown: tuple[str, str] | None = None
    # Matcher keys of the cleaned stored names this spelling was read from.
    labels: set[str] = field(default_factory=set)

    @property
    def spelling(self) -> str:
        return (self.newest_shown or self.newest)[1]


@dataclass
class _Stream:
    last_seen: str = ""
    # Matcher key of the spelling the calls carried -> that name.
    names: dict[str, _Name] = field(default_factory=dict)
    # Cleaned stored name -> (newest visible time, matcher key of its spelling).
    shown_spellings: dict[str, tuple[str, str]] = field(default_factory=dict)
    # Matcher key of a cleaned stored name -> what the indexed reads saw behind it.
    labels: dict[str, _Label] = field(default_factory=dict)

    def record(self, observation: SourceObservation, spellings: tuple[str, str] | None, carries_value: bool) -> None:
        if observation.shown and carries_value:
            self.last_seen = max(self.last_seen, observation.last_seen)
        if not observation.name or not spellings:
            return
        label_key = normalize_mapping_key(observation.name)
        label = self.labels.setdefault(label_key, _Label())
        label.spellings.update(normalize_mapping_key(spelling) for spelling in spellings)
        label.newest = max(label.newest, observation.last_seen)
        spelling = spellings[1]
        key = normalize_mapping_key(spelling)
        stamp = (observation.last_seen, spelling)
        name = self.names.setdefault(key, _Name(newest=stamp))
        name.newest = max(name.newest, stamp)
        name.labels.add(label_key)
        if observation.shown:
            name.newest_shown = max(name.newest_shown or stamp, stamp)
            known = self.shown_spellings.get(observation.name)
            if known is None or observation.last_seen >= known[0]:
                self.shown_spellings[observation.name] = (observation.last_seen, key)

    def key_of(self, display_name: str | None) -> str:
        """The matcher key of the spelling behind a cleaned display name."""
        shown = self.shown_spellings.get(display_name or "")
        return shown[1] if shown else normalize_mapping_key(display_name)


def audio_source_links(
    observations: Iterable[SourceObservation],
    literal_names: LiteralNames | None = None,
) -> list[AudioSourceLink]:
    """Each linkable source with a visible call, newest first.

    ``observations`` are the owner's, hidden calls included as evidence (``shown=False``).
    ``literal_names`` gives, for each stored (node, id, name, shown), the name the matcher reads
    from its oldest and its newest call; names are offered, compared and shown in the newest
    spelling. Stored names are cleaned, so two spellings that differ only in inner spaces share one
    stored name: when the reads see both behind it, no camera's link can be told to be the old name,
    and neither is offered. A name's "last heard" stays that of its stored name.
    """
    seen = list(observations)
    literals = literal_names or {}
    directory = AudioSourceDirectory(seen)
    streams: dict[SourceKey, _Stream] = {}
    for observation in seen:
        key = directory.key_for(observation.node, observation.source_id, observation.name)
        if key[0] == "unknown":
            continue
        spellings = None
        if observation.name:
            identity = (observation.node, observation.source_id, observation.name, observation.shown)
            spellings = literals.get(identity) or (observation.name, observation.name)
        carries_value = bool(observation.source_id) or key[0] == "name"
        streams.setdefault(key, _Stream()).record(observation, spellings, carries_value)

    current = {key: directory.display_name(key) for key in streams}
    now_keys = {key: stream.key_of(current[key]) for key, stream in streams.items()}
    current_names = {now_keys[key] for key in streams if current[key]}
    carriers: dict[str, int] = {}
    label_carriers: dict[str, int] = {}
    for key, stream in streams.items():
        if key[0] in _IDENTIFIED:
            for name in stream.names:
                carriers[name] = carriers.get(name, 0) + 1
            for label in stream.labels:
                label_carriers[label] = label_carriers.get(label, 0) + 1
    ambiguous = {
        label for stream in streams.values() for label, seen in stream.labels.items() if len(seen.spellings) > 1
    }
    listed = [key for key, stream in streams.items() if stream.last_seen]
    sharing: dict[str, list[SourceKey]] = {}
    for key in listed:
        if key[0] in _IDENTIFIED and (source_id := directory.source_id(key)):
            sharing.setdefault(source_id, []).append(key)

    links = []
    for key in listed:
        stream = streams[key]
        now_key = now_keys[key]
        name_now = stream.names[now_key] if now_key in stream.names else None
        heard_now = name_now.newest_shown[0] if name_now and name_now.newest_shown else None
        source_id = directory.source_id(key) if key[0] in _IDENTIFIED else None
        display = name_now.spelling if name_now else current[key]
        names = [
            SourceLinkName(
                name=name.spelling,
                last_seen=name.newest_shown[0] if name.newest_shown else None,
                current=folded == now_key,
                # An earlier name only this stream carried, in one spelling, that no source carries
                # now, and that it last carried, in visible or hidden calls, before its current name.
                offer_link_by_id=bool(source_id)
                and folded != now_key
                and folded not in current_names
                and carriers.get(folded) == 1
                and heard_now is not None
                and all(
                    label not in ambiguous
                    and label_carriers.get(label) == 1
                    and stream.labels[label].newest < heard_now
                    for label in name.labels
                ),
            )
            for folded, name in stream.names.items()
        ]
        # The current name first, then the others, the most recently heard first.
        names.sort(key=lambda name: (name.current, name.last_seen or "", name.name), reverse=True)
        mapping_value = source_id or display or key[2]
        shared = sharing.get(source_id, []) if source_id else []
        links.append(
            AudioSourceLink(
                mapping_value=mapping_value,
                source_name=display or mapping_value,
                source_id=source_id,
                source_node=directory.source_node(key),
                installs_sharing_id=sorted({node for other in shared if (node := directory.source_node(other))})
                if len(shared) > 1
                else [],
                last_seen=stream.last_seen,
                names=names,
            )
        )
    return sorted(links, key=lambda link: (link.last_seen, link.mapping_value, link.source_node or ""), reverse=True)
