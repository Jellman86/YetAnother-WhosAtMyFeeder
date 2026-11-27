"""A window's visits and species rows, built from one reading of its captures (#1096).

The Dashboard's Visits, the Unknown birds among them and the species list are all drawn from the
same captures here, so they describe one moment and can never disagree: every visit is counted
once, under its species or as an Unknown bird.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.utils.canonical_species import UNKNOWN_BIRD_DISPLAY_LABEL, user_facing_species_label


@dataclass(frozen=True, slots=True)
class VisitMember:
    """One visible capture in the window, with the visit the shared visit rule put it in.

    ``at`` is naive UTC, whatever format the row was stored in. ``visit_key`` is the rule's
    (identity, camera, visit number), and ``species_key`` the capture's own catalogue key.
    """

    id: int
    at: datetime
    camera: str | None
    frigate_event: str
    display_name: str | None
    category_name: str | None
    scientific_name: str | None
    common_name: str | None
    taxa_id: int | None
    visit_key: tuple
    visit_position: int
    species_key: str | None


@dataclass(frozen=True, slots=True)
class WindowVisit:
    """One visit, by its first capture in the window."""

    camera: str | None
    opened_at: datetime
    unknown: bool


@dataclass(frozen=True, slots=True)
class WindowVisits:
    """Every visit in opening order, the named species rows, and the Unknown birds' row if any."""

    visits: list[WindowVisit]
    species: list[dict]
    unknown: dict | None

    @property
    def rows(self) -> list[dict]:
        """The species rows as the species list shows them, the Unknown birds' row included."""
        return [*self.species, *([self.unknown] if self.unknown else [])]


def _latest(members: Iterable[VisitMember]) -> VisitMember:
    return max(members, key=lambda member: (member.at, member.id, member.frigate_event))


def is_shown_unknown(member: VisitMember, extra_unknown_labels: Iterable[str] | None = None) -> bool:
    """Whether a capture is shown as "Unknown bird", by the rule every screen uses.

    That is an Unknown, abstention or configured unknown label, a legacy group label ("Great tit
    and allies"), an Unknown category behind a kept species name, or no name at all.
    """
    shown = user_facing_species_label(
        member.display_name, raw_label=member.category_name, extra_unknown_labels=extra_unknown_labels
    )
    return shown == UNKNOWN_BIRD_DISPLAY_LABEL


def _bucket_key(member: VisitMember) -> str:
    return member.species_key or f"event:{member.frigate_event}"


def _agreed(members: list[VisitMember], field: str) -> object:
    """The one value the bucket's captures give for a field, or None when they give none or disagree."""
    values = {getattr(member, field) for member in members} - {None, ""}
    return values.pop() if len(values) == 1 else None


def summarize_window_visits(
    members: Iterable[VisitMember], *, extra_unknown_labels: Iterable[str] | None = None
) -> WindowVisits:
    """Group the window's captures into its visits and species rows.

    The resolved visit identity decides only attribution: a visit is judged at its first capture,
    and the captures of an Unknown visit go to the Unknown birds' row only, never into a species
    row, even when they kept that species' catalogue id or scientific name. So every visit is
    counted once.

    The captures of named visits keep the species buckets they always had, one per catalogue key,
    in descending capture count with ties by key, so the alias merge that follows keeps the same
    names, taxonomy and order as before. A capture shown as Unknown bird inside a named visit (a
    legacy group label, an Unknown category) never makes a bucket of its own: it joins its key's
    bucket only when named captures already fill it, and otherwise the bucket of its visit's first
    capture. Names and taxonomy come only from named captures, the newest of them first, with a
    field it lacks taken from the bucket's other named captures when they agree; the newest capture
    of any kind gives the photo.
    """
    by_visit: dict[tuple, list[VisitMember]] = {}
    for member in members:
        by_visit.setdefault(member.visit_key, []).append(member)

    visits: list[tuple[VisitMember, WindowVisit]] = []
    named: dict[str, list[VisitMember]] = {}
    shown_unknown: list[tuple[VisitMember, str]] = []
    unknown_members: list[VisitMember] = []
    unknown_visits = 0
    for visit_members in by_visit.values():
        opening = min(visit_members, key=lambda member: (member.visit_position, member.at, member.id))
        unknown = is_shown_unknown(opening, extra_unknown_labels)
        visits.append((opening, WindowVisit(camera=opening.camera, opened_at=opening.at, unknown=unknown)))
        if unknown:
            unknown_visits += 1
            unknown_members.extend(visit_members)
        else:
            opening_key = _bucket_key(opening)
            for member in visit_members:
                if is_shown_unknown(member, extra_unknown_labels):
                    shown_unknown.append((member, opening_key))
                else:
                    named.setdefault(_bucket_key(member), []).append(member)
    # Once every named capture has its bucket, each shown-Unknown one joins a bucket that has names.
    naming = {key: list(bucket) for key, bucket in named.items()}
    for member, opening_key in shown_unknown:
        key = _bucket_key(member)
        named[key if key in naming else opening_key].append(member)

    species = []
    for key in sorted(named, key=lambda key: (-len(named[key]), key)):
        bucket = named[key]
        latest = _latest(bucket)
        shown_named = naming[key]
        named_by = _latest(shown_named)
        species.append(
            {
                "species": named_by.display_name,
                "count": len(bucket),
                "visit_count": sum(1 for member in bucket if member.visit_position == 1),
                "latest_event": latest.frigate_event,
                "latest_detection_time": latest.at,
                **{
                    field: getattr(named_by, field) or _agreed(shown_named, field)
                    for field in ("scientific_name", "common_name", "taxa_id")
                },
            }
        )

    unknown_row = None
    if unknown_members:
        latest = _latest(unknown_members)
        unknown_row = {
            "species": UNKNOWN_BIRD_DISPLAY_LABEL,
            "count": len(unknown_members),
            "visit_count": unknown_visits,
            "latest_event": latest.frigate_event,
            "latest_detection_time": latest.at,
            "scientific_name": None,
            "common_name": None,
            "taxa_id": None,
        }

    visits.sort(key=lambda item: (item[0].at, item[0].id))
    return WindowVisits(visits=[visit for _opening, visit in visits], species=species, unknown=unknown_row)
