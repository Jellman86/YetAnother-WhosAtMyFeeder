"""Attribute BirdNET-Go calls to visits and fold the rest into bouts for the Explorer.

BirdNET-Go reports one detection per few seconds of song, so a sparrow chattering for half an hour
is dozens of rows. The Explorer lists visits, not frames (layout-patterns 1.2), and heard calls
follow the same idea in two steps:

1. A call belongs to a visit when the pipeline already confirmed that visit with a call, the call
   is the same species, comes from a microphone mapped to the visit's camera, and falls inside the
   visit widened by the correlation window. Only those calls count on the visit; a bout that runs
   on past a visit is split at its edge rather than absorbed whole.
2. Every other call of one species, with no more than ``gap_seconds`` of silence between calls,
   is one bout. The default matches the default correlation window, so "the same bout" and
   "matches this visit" use the same span.

The rules are pure so the route, its tests and any later surface agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

HEARD_GROUP_GAP_SECONDS = 300


@dataclass(frozen=True)
class HeardCall:
    timestamp: datetime
    species: str
    scientific_name: str | None
    confidence: float
    birdnet_id: int | None
    source_name: str | None
    mapping_keys: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ConfirmedVisit:
    visit_id: str
    start: datetime
    end: datetime
    camera_name: str
    scientific_key: str
    names: frozenset[str]


@dataclass
class HeardGroup:
    species: str
    scientific_name: str | None
    first_heard: datetime
    last_heard: datetime
    call_count: int
    best_confidence: float
    best_heard: datetime
    best_birdnet_id: int | None
    source_name: str | None


def _key(value: str | None) -> str:
    return (value or "").strip().casefold()


def _identity(call: HeardCall) -> str:
    return _key(call.scientific_name or call.species)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _microphone_allowed(mapping_value: str | None, keys: frozenset[str]) -> bool:
    """A camera with no mapping accepts any microphone, as the live correlation does."""
    tokens = {_key(token) for token in re.split(r"[,\n;|]+", mapping_value or "")} - {""}
    return not tokens or "*" in tokens or bool(tokens & {_key(key) for key in keys})


def _same_species(call: HeardCall, visit: ConfirmedVisit) -> bool:
    if call.scientific_name and _key(call.scientific_name) == visit.scientific_key:
        return True
    return _key(call.species) in visit.names


def attribute_calls(
    calls: list[HeardCall],
    visits: list[ConfirmedVisit],
    *,
    window_seconds: int,
    camera_audio_mapping: dict[str, str],
) -> tuple[dict[str, int], list[HeardCall]]:
    """Count each call on the nearest confirmed visit it supports; return the rest unchanged."""
    matched: dict[str, int] = {}
    remaining: list[HeardCall] = []
    window = max(0, window_seconds)
    for call in calls:
        heard_at = _utc(call.timestamp)
        best: tuple[float, str] | None = None
        for visit in visits:
            start, end = _utc(visit.start), _utc(visit.end)
            if heard_at < start:
                distance = (start - heard_at).total_seconds()
            elif heard_at > end:
                distance = (heard_at - end).total_seconds()
            else:
                distance = 0.0
            if distance > window or not _same_species(call, visit):
                continue
            if not _microphone_allowed(camera_audio_mapping.get(visit.camera_name), call.mapping_keys):
                continue
            if best is None or distance < best[0]:
                best = (distance, visit.visit_id)
        if best is None:
            remaining.append(call)
        else:
            matched[best[1]] = matched.get(best[1], 0) + 1
    return matched, remaining


def fold_heard_calls(calls: list[HeardCall], gap_seconds: int = HEARD_GROUP_GAP_SECONDS) -> list[HeardGroup]:
    """Group calls per species across silences of at most ``gap_seconds``, newest group first.

    The picture of a group is its strongest call that BirdNET-Go can still serve, so a group whose
    loudest call has no BirdNET-Go id still shows a spectrogram from another of its calls.
    """
    open_groups: dict[str, HeardGroup] = {}
    best_with_media: dict[int, float] = {}
    groups: list[HeardGroup] = []
    for call in sorted(calls, key=lambda item: _utc(item.timestamp)):
        heard_at = _utc(call.timestamp)
        key = _identity(call)
        group = open_groups.get(key)
        if group is None or (heard_at - group.last_heard).total_seconds() > gap_seconds:
            group = HeardGroup(
                species=call.species,
                scientific_name=call.scientific_name,
                first_heard=heard_at,
                last_heard=heard_at,
                call_count=0,
                best_confidence=call.confidence,
                best_heard=heard_at,
                best_birdnet_id=None,
                source_name=call.source_name,
            )
            open_groups[key] = group
            groups.append(group)
        group.call_count += 1
        group.last_heard = heard_at
        if call.confidence > group.best_confidence:
            group.best_confidence = call.confidence
            group.best_heard = heard_at
            group.source_name = call.source_name or group.source_name
        if call.birdnet_id is not None and call.confidence > best_with_media.get(id(group), -1.0):
            best_with_media[id(group)] = call.confidence
            group.best_birdnet_id = call.birdnet_id
    return sorted(groups, key=lambda item: item.last_heard, reverse=True)
