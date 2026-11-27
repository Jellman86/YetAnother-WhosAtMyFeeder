"""Which of the Explorer's filters each facet count follows (#1097)."""

from datetime import datetime

from app.services.explorer_facets import Facet, FacetScope, facet_scope, viewer_scope

CHOSEN = FacetScope(
    start=datetime(2033, 10, 3),
    end=datetime(2033, 10, 4),
    camera="patio",
    hidden_only=True,
    species="Blackbird",
    species_any=("Unknown Bird",),
    taxa_id=12716,
    species_ids=frozenset({7}),
    favorites=True,
    audio_only=True,
    multiple_species_only=True,
    owner_confirmed_only=True,
)


def test_the_species_list_is_never_narrowed_by_a_species_or_group_choice():
    scope = facet_scope(CHOSEN, Facet.SPECIES)

    assert (scope.species, scope.species_any, scope.taxa_id, scope.species_ids) == (None, None, None, None)
    assert (scope.start, scope.end, scope.camera, scope.hidden_only) == (CHOSEN.start, CHOSEN.end, "patio", True)
    assert scope.favorites and scope.audio_only and scope.multiple_species_only and scope.owner_confirmed_only


def test_the_camera_list_follows_every_filter_but_the_camera():
    scope = facet_scope(CHOSEN, Facet.CAMERA)

    assert scope.camera is None
    assert scope.species == "Blackbird" and scope.species_ids == frozenset({7})
    assert scope.favorites and scope.audio_only


def test_a_flag_counts_what_turning_it_on_would_show():
    plain = FacetScope(start=CHOSEN.start, camera="patio")

    assert facet_scope(plain, Facet.FAVOURITES).favorites is True
    assert facet_scope(plain, Facet.AUDIO).audio_only is True
    assert facet_scope(plain, Facet.VIDEO).video_analysed is True
    assert facet_scope(plain, Facet.HIDDEN).hidden_only is True
    assert facet_scope(plain, Facet.TOTAL) == plain
    assert facet_scope(plain, Facet.FAVOURITES).camera == "patio"


def test_an_owner_keeps_every_choice():
    assert viewer_scope(CHOSEN, owner=True, show_audio=False, show_camera_names=False) == CHOSEN


def test_a_visitor_never_counts_hidden_records_or_owner_only_choices():
    scope = viewer_scope(CHOSEN, owner=False, show_audio=True, show_camera_names=True)

    assert scope.hidden_only is False
    assert scope.multiple_species_only is False and scope.owner_confirmed_only is False
    assert scope.public_audio is True and scope.audio_only is True
    assert scope.camera == "patio"


def test_a_visitor_without_audio_or_camera_names_cannot_narrow_by_them():
    scope = viewer_scope(CHOSEN, owner=False, show_audio=False, show_camera_names=False)

    assert scope.audio_only is False
    assert scope.camera is None
