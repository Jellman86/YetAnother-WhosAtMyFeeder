"""Which of the Explorer's filters each facet count follows.

A count beside a filter states how many results choosing it would give, so it is taken under every
other filter the rail holds. A facet never narrows itself: the species list is counted as if no
species or group of species were chosen, and the camera list as if no camera were.
"""

from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum


class Facet(Enum):
    SPECIES = "species"
    CAMERA = "camera"
    TOTAL = "total"
    FAVOURITES = "favorites"
    AUDIO = "audio_matched"
    VIDEO = "video_analysed"
    HIDDEN = "hidden"


@dataclass(frozen=True)
class FacetScope:
    """The results the rail describes: one window and the filters chosen in it."""

    start: datetime | None = None
    end: datetime | None = None
    camera: str | None = None
    hidden_only: bool = False
    species: str | None = None
    species_any: tuple[str, ...] | None = None
    taxa_id: int | None = None
    species_ids: Collection[int] | None = None
    favorites: bool = False
    audio_only: bool = False
    public_audio: bool = False
    multiple_species_only: bool = False
    owner_confirmed_only: bool = False
    video_analysed: bool = False


def viewer_scope(scope: FacetScope, *, owner: bool, show_audio: bool, show_camera_names: bool) -> FacetScope:
    """A visitor's counts keep the clamps their results have: no hidden records, no owner-only filters."""
    if owner:
        return scope
    return replace(
        scope,
        hidden_only=False,
        multiple_species_only=False,
        owner_confirmed_only=False,
        public_audio=True,
        audio_only=scope.audio_only and show_audio,
        camera=scope.camera if show_camera_names else None,
    )


def facet_scope(scope: FacetScope, facet: Facet) -> FacetScope:
    """The scope one facet's count is taken under."""
    if facet is Facet.SPECIES:
        return replace(scope, species=None, species_any=None, taxa_id=None, species_ids=None)
    if facet is Facet.CAMERA:
        return replace(scope, camera=None)
    if facet is Facet.FAVOURITES:
        return replace(scope, favorites=True)
    if facet is Facet.AUDIO:
        return replace(scope, audio_only=True)
    if facet is Facet.VIDEO:
        return replace(scope, video_analysed=True)
    if facet is Facet.HIDDEN:
        return replace(scope, hidden_only=True)
    return scope
