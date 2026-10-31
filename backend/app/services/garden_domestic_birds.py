"""Domestic birds the owner keeps: pure identity and routing decisions.

A declared domestic bird is a Garden animal on every camera and never enters bird
history. Nothing is domestic unless the owner declares it, because most kept birds
share an identity with a wild bird (Mallard, Greylag Goose, Wild Turkey, Rock Dove).

Identity is exact: catalogue scientific names, resolved to catalogue species ids for
the bird model, and SpeciesNet 4.0.3 output ids for Garden checks. Names are never
matched loosely.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

DomesticBirdKey = Literal[
    "chicken", "domestic_duck", "domestic_goose", "turkey", "guinea_fowl", "peafowl", "domestic_pigeon", "quail"
]


@dataclass(frozen=True)
class DomesticBird:
    key: DomesticBirdKey
    name: str
    # The catalogue identity a routed record is named and placed in the family tree by.
    record_scientific_name: str
    # Every catalogue scientific name that can stand for this bird, domestic and wild form.
    scientific_names: tuple[str, ...]
    # SpeciesNet 4.0.3 output ids (checksum-pinned package) that can stand for this bird.
    speciesnet_taxa: frozenset[str]


DOMESTIC_BIRDS: dict[str, DomesticBird] = {
    bird.key: bird
    for bird in (
        DomesticBird(
            "chicken",
            "Chicken",
            "Gallus gallus domesticus",
            ("Gallus gallus domesticus", "Gallus gallus"),
            frozenset(
                {
                    "cae9534f-f302-4229-9e11-b91138333d92",  # domestic chicken
                    "89851bea-765b-431a-bb03-6f821931ebdc",  # red junglefowl
                    "e94dc728-b517-4cb5-8b73-e4ae6128434c",  # gallus species
                }
            ),
        ),
        DomesticBird(
            "domestic_duck",
            "Domestic duck",
            "Anas platyrhynchos",
            ("Anas platyrhynchos", "Cairina moschata"),
            frozenset(
                {
                    "3eb4472d-b8da-4bd8-9533-7b9b4e844f6a",  # mallard
                    "2a54b5b4-1d76-4e1d-97ad-d5cf459d53b3",  # muscovy duck
                }
            ),
        ),
        DomesticBird(
            "domestic_goose",
            "Domestic goose",
            "Anser anser domesticus",
            ("Anser anser domesticus", "Anser anser", "Anser cygnoides"),
            frozenset({"4173d2d9-1d0e-42cd-bf66-f295e62a7c08"}),  # domestic goose
        ),
        DomesticBird(
            "turkey",
            "Turkey",
            "Meleagris gallopavo",
            ("Meleagris gallopavo",),
            frozenset(
                {
                    "94d8284e-6193-43b5-b80c-9029cf951675",  # wild turkey
                    "c5de71c5-1b03-409f-a79e-aba281310236",  # meleagris species
                }
            ),
        ),
        DomesticBird(
            "guinea_fowl",
            "Guineafowl",
            "Numida meleagris",
            ("Numida meleagris",),
            frozenset({"83133617-8358-4910-82ee-4c23e40ba3dc"}),  # helmeted guineafowl
        ),
        DomesticBird(
            "peafowl",
            "Peafowl",
            "Pavo cristatus",
            ("Pavo cristatus",),
            frozenset({"f90f90b5-b363-489d-ac71-feea6c780f56"}),  # indian peafowl
        ),
        DomesticBird(
            "domestic_pigeon",
            "Domestic pigeon or dove",
            "Columba livia",
            ("Columba livia", "Streptopelia roseogrisea"),
            frozenset({"4b7d3cff-8c0a-49b3-a8c0-a2e28f156818"}),  # rock dove
        ),
        DomesticBird(
            "quail",
            "Quail",
            "Coturnix japonica",
            ("Coturnix japonica", "Coturnix coturnix"),
            frozenset({"deaf5677-d5ef-4647-9800-1a2b0c010499"}),  # quail species (Coturnix)
        ),
    )
}


def normalize_domestic_birds(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > len(DOMESTIC_BIRDS):
        raise ValueError("Domestic birds must be a list of supported domestic birds")
    keys = list(dict.fromkeys(str(item).strip().lower() for item in value))
    if any(key not in DOMESTIC_BIRDS for key in keys):
        raise ValueError("Choose supported domestic birds: " + ", ".join(DOMESTIC_BIRDS))
    return keys


def _scientific_key(name: str | None) -> str:
    return " ".join(str(name or "").split()).casefold()


def domestic_bird_for_speciesnet(taxon_id: str | None) -> str | None:
    """The domestic bird a SpeciesNet output stands for, declared or not."""
    return next((bird.key for bird in DOMESTIC_BIRDS.values() if taxon_id in bird.speciesnet_taxa), None)


def domestic_bird_for_bird_label(
    *,
    species_id: int | None,
    scientific_names: Iterable[str | None],
    species_ids_by_bird: Mapping[str, frozenset[int]],
) -> str | None:
    """The domestic bird a bird-model result stands for, declared or not.

    ``species_ids_by_bird`` holds each bird's scientific names resolved to catalogue
    ids. A model output the catalogue identifies is compared by id; a label without
    a catalogue identity (for example a Frigate sub-label) only by its exact name.
    """
    if species_id is not None:
        match = next((key for key, ids in species_ids_by_bird.items() if species_id in ids), None)
        if match:
            return match
    names = {_scientific_key(name) for name in scientific_names if name}
    return next(
        (
            bird.key
            for bird in DOMESTIC_BIRDS.values()
            if names & {_scientific_key(name) for name in bird.scientific_names}
        ),
        None,
    )


BirdEventRoute = Literal["garden", "bird_history"]


def bird_event_route(
    top: str | None,
    top_score: float | None,
    accepted: str | None,
    declared: Iterable[str],
    *,
    threshold: float,
    garden_enabled: bool,
) -> BirdEventRoute:
    """Where a classified Frigate bird event belongs.

    ``top`` is the domestic bird the model's top result stands for, before any
    admission filter (such as a range filter) can reject it; it counts only at the
    bird naming threshold, as a bird detection would. ``accepted`` is the one the
    admitted result stands for after any fallback. Either, when declared, makes the
    event a Garden animal. With Garden off the declaration has no effect.
    """
    if not garden_enabled:
        return "bird_history"
    keep = set(declared)
    confident_top = top in keep and top_score is not None and top_score >= threshold
    return "garden" if confident_top or accepted in keep else "bird_history"


GardenBirdRoute = Literal["domestic_bird", "bird_camera", "wild_bird"]


def garden_bird_route(domestic: str | None, declared: Iterable[str], *, camera_watches_birds: bool) -> GardenBirdRoute:
    """What a Garden check does with a bird.

    A declared domestic bird is named as an animal on any Garden camera. Any other
    bird belongs to bird detection where the camera is watched for birds; on a
    Garden-only camera nothing else would record it, which the reason says.
    """
    if domestic is not None and domestic in set(declared):
        return "domestic_bird"
    return "bird_camera" if camera_watches_birds else "wild_bird"


def camera_watches_birds(camera: str, bird_cameras: Iterable[str]) -> bool:
    """An empty bird camera list watches every camera, as bird ingest does."""
    cameras = list(bird_cameras)
    return not cameras or camera in cameras
