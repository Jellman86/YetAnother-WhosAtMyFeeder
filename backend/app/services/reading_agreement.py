"""Whether two readings of one capture name the same bird (#804).

A capture is read once from its snapshot when it arrives and again later from its
video. When the two name different species, a person should look before trusting
the name. Readings are compared by catalogue species, never by label text: two
models spell one species in different label grammars, and one label string can
come from an output the catalogue cannot identify.

The policy abstains rather than guess. A reading that names no catalogued bird,
a second reading too weak to be named on its own, or a species one of the models
could not have named all give ``cannot_compare``: a model cannot disagree about a
bird it does not know.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

ReadingAgreement = Literal["agree", "disagree", "cannot_compare"]
#: Every value the ``detections.reading_agreement`` column accepts.
READING_AGREEMENTS: tuple[ReadingAgreement, ...] = ("agree", "disagree", "cannot_compare")


@dataclass(frozen=True)
class Reading:
    """One model's answer for a capture, in catalogue terms."""

    species_id: int | None
    score: float
    #: Every species the producing model can name; None when the catalogue does not know the model.
    vocabulary: frozenset[int] | None


class SpeciesCatalogue(Protocol):
    def cached_output_species_id(self, model_sha256: str | None, output_index: int, label: str) -> int | None: ...

    def species_outputs(self, model_sha256: str | None) -> dict[int, int] | None: ...


def reading_from_model_output(
    catalogue: SpeciesCatalogue,
    *,
    model_sha256: str | None,
    output_index: int | None,
    label: str | None,
    score: float,
) -> Reading:
    """The catalogue species a model output names, bound to the label the catalogue recorded for it."""
    if not model_sha256:
        return Reading(species_id=None, score=score, vocabulary=None)
    outputs = catalogue.species_outputs(model_sha256)
    vocabulary = frozenset(outputs.values()) if outputs is not None else None
    species_id = None
    if isinstance(output_index, int) and output_index >= 0 and label:
        species_id = catalogue.cached_output_species_id(model_sha256, output_index, label)
    return Reading(species_id=species_id, score=score, vocabulary=vocabulary)


def compare_readings(first: Reading, second: Reading, *, floor: float) -> ReadingAgreement:
    """Compare a capture's first reading with a later one.

    ``floor`` is the lowest score the app names a bird at: a weaker second reading
    is not evidence against the first.
    """
    if first.species_id is None or second.species_id is None:
        return "cannot_compare"
    if first.species_id == second.species_id:
        return "agree"
    if not math.isfinite(second.score) or not 0.0 <= second.score <= 1.0 or second.score < floor:
        return "cannot_compare"
    if first.vocabulary is None or second.vocabulary is None:
        return "cannot_compare"
    if first.species_id not in second.vocabulary or second.species_id not in first.vocabulary:
        return "cannot_compare"
    return "disagree"
