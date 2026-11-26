"""Choose cache evictions without deleting observations, archived favourites, or kept owner photos."""

from dataclasses import dataclass
from collections import Counter


@dataclass(frozen=True)
class CachedVisit:
    event_id: str
    species_key: str
    detected_at: str
    bytes_on_disk: int
    is_favorite: bool = False
    keep_photo: bool = False
    photo_bytes: int = 0

    @property
    def evictable_bytes(self) -> int:
        if self.is_favorite:
            return 0
        if self.keep_photo:
            return max(0, self.bytes_on_disk - max(0, self.photo_bytes))
        return max(0, self.bytes_on_disk)


def select_media_evictions(
    visits: list[CachedVisit],
    *,
    per_species_maximum: int,
    max_bytes: int,
    protected_event_ids: set[str] | None = None,
) -> list[str]:
    protected = protected_event_ids or set()
    newest = sorted(visits, key=lambda visit: (visit.detected_at, visit.event_id), reverse=True)
    counts: Counter[str] = Counter()
    evictions: set[str] = set()
    for visit in newest:
        if visit.is_favorite or visit.event_id in protected:
            continue
        if visit.keep_photo and visit.evictable_bytes <= 0:
            continue
        counts[visit.species_key] += 1
        if per_species_maximum > 0 and counts[visit.species_key] > per_species_maximum:
            evictions.add(visit.event_id)
    remaining = sum(
        visit.bytes_on_disk - (visit.evictable_bytes if visit.event_id in evictions else 0) for visit in visits
    )
    if max_bytes > 0:
        for visit in reversed(newest):
            if remaining <= max_bytes:
                break
            if (
                visit.is_favorite
                or visit.event_id in protected
                or visit.event_id in evictions
                or visit.evictable_bytes <= 0
            ):
                continue
            evictions.add(visit.event_id)
            remaining -= visit.evictable_bytes
    return [visit.event_id for visit in reversed(newest) if visit.event_id in evictions]
