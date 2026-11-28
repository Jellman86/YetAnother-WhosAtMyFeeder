"""The BirdNET-Go sources a camera can be linked to, one entry per stream (#1111).

A camera's audio link matches the names and ids stored on each call, literally
(``app.utils.birdnet_payload.extract_audio_mapping_keys``). BirdNET-Go keeps a stream's id when the
stream is renamed, so a link by id survives a rename where a link by name does not. Each entry
therefore offers the stream's id as the value to save, and the names it has carried, newest first.

A link by id matches that id from any BirdNET-Go install, so streams are grouped by id alone: the
list offers each value a camera can be linked by once. A source from a BirdNET-Go version that sent
no id can only be linked by its name. Calls stored under a name before BirdNET-Go sent ids join the
one stream that carried the same name; a name two streams carried stays an entry of its own.

``has_calls_without_id`` tells Settings whether replacing a name link with the id would unlink
stored calls: those without an id match by name only.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


def fold_source_name(name: str | None) -> str:
    """How a camera link compares a name: case and surrounding or repeated whitespace ignored."""
    return " ".join((name or "").split()).casefold()


@dataclass(frozen=True)
class SourceNameUse:
    """The visible calls stored under one (install, stream id, name): the newest one's time and how many."""

    node: str | None
    source_id: str | None
    name: str | None
    last_seen: str
    count: int


@dataclass(frozen=True)
class EarlierSourceName:
    name: str
    last_seen: str
    has_calls_without_id: bool


@dataclass(frozen=True)
class AudioSourceLink:
    mapping_value: str
    source_name: str
    source_id: str | None
    earlier_names: list[EarlierSourceName]
    last_seen: str
    seen_count: int


@dataclass
class _Entry:
    source_id: str | None
    # Folded name -> (newest stored time, the name as last sent).
    names: dict[str, tuple[str, str]] = field(default_factory=dict)
    last_seen: str = ""
    count: int = 0

    def add(self, name: str | None, last_seen: str, count: int, *, names_it: bool = True) -> None:
        self.count += count
        self.last_seen = max(self.last_seen, last_seen)
        if name and names_it:
            folded = fold_source_name(name)
            current = self.names.get(folded)
            if current is None or last_seen >= current[0]:
                self.names[folded] = (last_seen, name)


def audio_source_links(uses: Iterable[SourceNameUse], names_without_id: set[str]) -> list[AudioSourceLink]:
    """Each linkable source, newest first.

    ``names_without_id`` holds the folded names any stored call without an id carries, hidden ones
    included, since a hidden call still matches the camera it is linked to.
    """
    streams: dict[str, _Entry] = {}
    unidentified: dict[str, list[SourceNameUse]] = {}
    for use in uses:
        if use.source_id:
            streams.setdefault(use.source_id, _Entry(source_id=use.source_id)).add(use.name, use.last_seen, use.count)
        elif use.name:
            unidentified.setdefault(fold_source_name(use.name), []).append(use)

    named: dict[str, _Entry] = {}
    for folded, name_uses in unidentified.items():
        carriers = [entry for entry in streams.values() if folded in entry.names]
        if len(carriers) == 1:
            # The stream's own calls name it: an older call without an id is never its newest name.
            for use in name_uses:
                carriers[0].add(use.name, use.last_seen, use.count, names_it=False)
            continue
        target = named.setdefault(folded, _Entry(source_id=None))
        for use in name_uses:
            target.add(use.name, use.last_seen, use.count)

    links = [_link(entry, names_without_id) for entry in [*streams.values(), *named.values()]]
    return sorted(links, key=lambda link: (link.last_seen, link.mapping_value), reverse=True)


def _link(entry: _Entry, names_without_id: set[str]) -> AudioSourceLink:
    by_age = sorted(entry.names.items(), key=lambda item: item[1][0], reverse=True)
    current = by_age[0][1][1] if by_age else None
    display = current or entry.source_id or ""
    return AudioSourceLink(
        mapping_value=entry.source_id or display,
        source_name=display,
        source_id=entry.source_id,
        earlier_names=[
            EarlierSourceName(name=name, last_seen=last_seen, has_calls_without_id=folded in names_without_id)
            for folded, (last_seen, name) in by_age[1:]
        ]
        if entry.source_id
        else [],
        last_seen=entry.last_seen,
        seen_count=entry.count,
    )
