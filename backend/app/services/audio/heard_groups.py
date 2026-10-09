"""Fold BirdNET-Go calls into heard groups for the Explorer.

BirdNET-Go reports one detection per few seconds of song, so a sparrow chattering for half an hour
is dozens of rows. The Explorer lists visits, not frames (layout-patterns 1.2), and heard calls
follow the same rule: calls of one species with no more than ``gap_seconds`` of silence between
them are one group. The rule is pure so the Explorer, its tests and any later surface agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

HEARD_GROUP_GAP_SECONDS = 600


@dataclass(frozen=True)
class HeardCall:
    timestamp: datetime
    species: str
    scientific_name: str | None
    confidence: float
    birdnet_id: int | None
    source_name: str | None


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


def _identity(call: HeardCall) -> str:
    name = call.scientific_name or call.species
    return name.strip().casefold()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


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
