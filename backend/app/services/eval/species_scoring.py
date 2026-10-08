"""Score a model by species identity, and separately on the birds it can name.

A prediction's species comes from the species catalogue, keyed on the model's
output index, the same identity live detections use. Comparing labels instead
marks a regional model wrong for naming a bird its own way ("Common starling"
for "European Starling"). A model is also never built to name every test bird:
a European model has no output for a Blue Jay, so those images say nothing
about how well it identifies the birds it was made for. Both figures are kept;
the in-vocabulary one is the fair comparison between models.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.model_taxon_map import scientific_name_from_label
from app.utils.canonical_species import is_unknown_species_label
from app.utils.classifier_labels import collapse_classifier_label

_BINOMIAL = re.compile(r"^[A-Z][a-z]+ [a-z][a-z-]+$")
_WORDS = re.compile(r"[a-z]+")


def _genus(scientific_name: Optional[str]) -> Optional[str]:
    words = str(scientific_name or "").split()
    return words[0].casefold() if words else None


def _head_noun(common_name: Optional[str]) -> Optional[str]:
    """The last word of a common name: "Rock Pigeon" and "Feral pigeon" are both pigeons."""
    words = _WORDS.findall(str(common_name or "").casefold())
    return words[-1] if words else None


def _label_identity(label: str) -> tuple[Optional[str], Optional[str]]:
    """(genus, head noun) an unresolved output label could stand for.

    A hierarchy or paired label is certainly scientific. A bare two-word label is
    ambiguous: "Columba livia" and the sentence-case common name "Feral pigeon"
    have the same shape, so it counts both ways.
    """
    scientific = scientific_name_from_label(label.strip())
    if scientific:
        return _genus(scientific), None
    # Labels can carry a trailing qualifier ("Western Scrub-Jay (ID: 952)").
    text = collapse_classifier_label(label, strategy="strip_trailing_parenthetical").strip()
    if _BINOMIAL.match(text):
        return _genus(text), _head_noun(text)
    return None, _head_noun(text)


@dataclass(frozen=True)
class ModelVocabulary:
    """The species a model can name, as `{output_index: species_id}` from the catalogue."""

    species_by_output: Mapping[int, int]
    # The model's own labels for outputs the catalogue cannot identify.
    unresolved_labels: Sequence[str] = ()
    species_ids: frozenset[int] = field(init=False)
    _unresolved_genera: frozenset[str] = field(init=False)
    _unresolved_head_nouns: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "species_ids", frozenset(self.species_by_output.values()))
        identities = [_label_identity(label) for label in self.unresolved_labels if not is_unknown_species_label(label)]
        object.__setattr__(self, "_unresolved_genera", frozenset(genus for genus, _ in identities if genus))
        object.__setattr__(self, "_unresolved_head_nouns", frozenset(noun for _, noun in identities if noun))

    def species_for(self, prediction: Mapping[str, Any]) -> Optional[int]:
        index = prediction.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            return None
        return self.species_by_output.get(index)

    def same_species(self, prediction: Mapping[str, Any], expected_species_id: Optional[int]) -> Optional[bool]:
        """True or False when both identities are known, None when identity cannot decide."""
        predicted = self.species_for(prediction)
        if predicted is None or expected_species_id is None:
            return None
        return predicted == expected_species_id

    def can_name(
        self,
        expected_species_id: Optional[int],
        *,
        scientific_name: Optional[str] = None,
        common_name: Optional[str] = None,
    ) -> Optional[bool]:
        """True or False when known; None when the catalogue cannot settle it.

        A species missing from the resolved outputs is proven unnameable only if no
        unresolved output could be it: none shares its genus or the last word of its
        common name. Erring this way can understate a model, never hide its misses.
        """
        if expected_species_id is None:
            return None
        if expected_species_id in self.species_ids:
            return True
        if _genus(scientific_name) in self._unresolved_genera or _head_noun(common_name) in self._unresolved_head_nouns:
            return None
        return False


def _rate(hits: int, total: int) -> float:
    if not total:
        return 0.0
    return round(hits / total, 4)


def _rate_or_none(hits: int, total: int) -> Optional[float]:
    return round(hits / total, 4) if total else None


@dataclass
class _Counts:
    images: int = 0
    top1: int = 0
    top3: int = 0
    top5: int = 0
    shared_core_images: int = 0
    shared_core_top1: int = 0
    regional_images: int = 0
    regional_top1: int = 0

    def add(self, match_flags: Sequence[bool], panel: str) -> None:
        hit = bool(match_flags and match_flags[0])
        self.images += 1
        self.top1 += hit
        self.top3 += any(match_flags[:3])
        self.top5 += any(match_flags[:5])
        if panel == "shared_core":
            self.shared_core_images += 1
            self.shared_core_top1 += hit
        else:
            self.regional_images += 1
            self.regional_top1 += hit


@dataclass
class AccuracyTally:
    """Accuracy over every test image, and over the images the model can name."""

    _all: _Counts = field(default_factory=_Counts)
    _known: _Counts = field(default_factory=_Counts)

    def add(self, match_flags: Sequence[bool], *, panel: str, can_name: Optional[bool]) -> None:
        self._all.add(match_flags, panel)
        # Only a bird proven to be outside the vocabulary is set aside; an
        # unknown membership still counts, so a miss is never hidden on a guess.
        if can_name is not False:
            self._known.add(match_flags, panel)

    def summary(self, *, vocabulary_known: bool) -> dict[str, Any]:
        everything, known = self._all, self._known
        figures: dict[str, Any] = {
            "top1_accuracy": _rate(everything.top1, everything.images),
            "top3_accuracy": _rate(everything.top3, everything.images),
            "top5_accuracy": _rate(everything.top5, everything.images),
            "shared_core_top1": _rate(everything.shared_core_top1, everything.shared_core_images),
            "regional_top1": _rate(everything.regional_top1, everything.regional_images),
            "images_in_vocabulary": None,
            "top1_accuracy_in_vocabulary": None,
            "top3_accuracy_in_vocabulary": None,
            "top5_accuracy_in_vocabulary": None,
            "shared_core_top1_in_vocabulary": None,
            "regional_top1_in_vocabulary": None,
        }
        if vocabulary_known:
            figures.update(
                {
                    "images_in_vocabulary": known.images,
                    "top1_accuracy_in_vocabulary": _rate_or_none(known.top1, known.images),
                    "top3_accuracy_in_vocabulary": _rate_or_none(known.top3, known.images),
                    "top5_accuracy_in_vocabulary": _rate_or_none(known.top5, known.images),
                    "shared_core_top1_in_vocabulary": _rate_or_none(known.shared_core_top1, known.shared_core_images),
                    "regional_top1_in_vocabulary": _rate_or_none(known.regional_top1, known.regional_images),
                }
            )
        return figures
