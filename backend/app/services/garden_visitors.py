"""Pure, opt-in garden decisions for the isolated prototype in #641.

Garden output cannot call bird
repositories, notifications, external submissions or personalization.
"""

from dataclasses import dataclass, field
import math
import re
from typing import Literal, Mapping, Sequence


@dataclass(frozen=True)
class Taxon:
    id: str
    name: str
    ranks: tuple[str, str, str, str, str]

    @property
    def key(self) -> str:
        return ";".join(self.ranks)

    @property
    def human(self) -> bool:
        return self.ranks[3:] == ("homo", "sapiens") or self.name == "human"

    @property
    def bird(self) -> bool:
        return self.ranks[0] == "aves"

    @property
    def animal(self) -> bool:
        return bool(self.ranks[0] and self.ranks[0] != "no cv result") or self.name == "animal"


@dataclass(frozen=True)
class GardenPolicy:
    enabled: bool = False
    cameras: frozenset[str] = field(default_factory=frozenset)
    labels: frozenset[str] = field(default_factory=frozenset)
    min_confidence: float = 0.7
    human_threshold: float = 0.1

    def __post_init__(self) -> None:
        if not 0 < self.min_confidence <= 1 or not 0 < self.human_threshold <= 1:
            raise ValueError("Garden thresholds must be finite probabilities in (0, 1]")


Route = Literal["bird", "garden", "disabled", "camera_excluded", "label_excluded", "human_rejected"]


def route_event(
    camera: str, label: str, policy: GardenPolicy, *, bird_labels: frozenset[str] = frozenset({"bird"})
) -> Route:
    label = label.strip().lower()
    if label in {"person", "human"}:
        return "human_rejected"
    if label in bird_labels:
        return "bird"
    if not policy.enabled:
        return "disabled"
    if camera not in policy.cameras:
        return "camera_excluded"
    if label not in policy.labels:
        return "label_excluded"
    return "garden"


@dataclass(frozen=True)
class GardenDecision:
    reason: str
    taxon: Taxon | None = None
    score: float | None = None
    geofenced: bool = False
    needs_review: bool = False


@dataclass(frozen=True)
class GardenCoarsePrediction:
    suggestion: Literal["bird", "mammal", "uncertain", "human_rejected"]
    mass: dict[str, float]
    human_winner: bool = False


def coarse_prediction_mass(
    probabilities: Sequence[float], outputs: Sequence[Taxon], *, expected_width: int = 2498
) -> GardenCoarsePrediction:
    """Preserve complete model uncertainty for an advisory check, never a review."""
    if (
        type(expected_width) is not int
        or expected_width <= 0
        or len(outputs) != expected_width
        or len(probabilities) != expected_width
        or any(
            not isinstance(taxon, Taxon)
            or not isinstance(taxon.id, str)
            or not taxon.id
            or not isinstance(taxon.name, str)
            or not isinstance(taxon.ranks, tuple)
            or len(taxon.ranks) != 5
            or any(not isinstance(rank, str) for rank in taxon.ranks)
            for taxon in outputs
        )
        or len({taxon.id for taxon in outputs}) != expected_width
    ):
        raise ValueError("Coarse assessment requires the complete unique output mapping")
    if any(
        type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1 for score in probabilities
    ):
        raise ValueError("Coarse assessment requires finite probabilities")
    if not math.isclose(math.fsum(probabilities), 1.0, rel_tol=0, abs_tol=0.000001):
        raise ValueError("Coarse assessment requires complete probability mass")
    groups: dict[str, list[float]] = {key: [] for key in ("bird", "mammal", "human", "blank", "other")}
    for taxon, score in zip(outputs, probabilities):
        if taxon.human:
            group = "human"
        elif taxon.bird:
            group = "bird"
        elif taxon.ranks[0] == "mammalia":
            group = "mammal"
        elif taxon.name == "blank":
            group = "blank"
        else:
            group = "other"
        groups[group].append(score)
    mass = {key: math.fsum(values) for key, values in groups.items()}
    maximum = max(probabilities)
    human_winner = any(taxon.human and score == maximum for taxon, score in zip(outputs, probabilities))
    if human_winner or mass["human"] >= GardenPolicy().human_threshold:
        return GardenCoarsePrediction("human_rejected", mass, human_winner)
    # An advisory gate does not establish presence, absence or calibrated accuracy.
    if mass["bird"] >= 0.8:
        return GardenCoarsePrediction("bird", mass)
    if mass["mammal"] >= 0.8:
        return GardenCoarsePrediction("mammal", mass)
    return GardenCoarsePrediction("uncertain", mass)


def _blocked(taxon: Taxon, country: str, geofence: Mapping[str, dict]) -> bool:
    rule = geofence.get(taxon.key, {})
    allowed = rule.get("allow")
    blocked = rule.get("block", {})
    # Region-only block rules cannot exclude a whole country. The prototype
    # intentionally accepts country only, and never transmits coordinates.
    return bool((allowed and country not in allowed) or (country in blocked and not blocked[country]))


def decide_prediction(
    predictions: Sequence[tuple[Taxon, float]],
    policy: GardenPolicy,
    *,
    country: str,
    taxonomy: Sequence[Taxon],
    geofence: Mapping[str, dict],
) -> GardenDecision:
    if not re.fullmatch(r"[A-Z]{3}", country):
        raise ValueError("Garden replay requires an uppercase ISO-3 country code")
    if not predictions or any(not math.isfinite(score) or not 0 <= score <= 1 for _, score in predictions):
        raise ValueError("Predictions must contain finite probabilities")
    if any(left[1] < right[1] for left, right in zip(predictions, predictions[1:])):
        raise ValueError("Predictions must be ordered by decreasing probability")
    if sum(score for _, score in predictions) > 1.00001:
        raise ValueError("Prediction probabilities exceed one")
    if predictions[0][0].human or any(taxon.human and score >= policy.human_threshold for taxon, score in predictions):
        return GardenDecision("human_rejected")
    taxon, score = predictions[0]
    if taxon.bird:
        return GardenDecision("bird_excluded")
    if not taxon.animal:
        return GardenDecision("non_animal")
    if score < policy.min_confidence:
        return GardenDecision("low_confidence")
    geofenced = _blocked(taxon, country, geofence)
    if geofenced:
        by_key = {item.key: item for item in taxonomy if item.animal}
        # Retain only the winner's ancestry. A geographically plausible
        # runner-up must never replace the observed classification.
        for depth in (3, 2, 1, 0):
            ancestor = by_key.get(";".join(taxon.ranks[:depth] + ("",) * (5 - depth)))
            if ancestor and ancestor.animal and not ancestor.human and not _blocked(ancestor, country, geofence):
                taxon = ancestor
                break
        else:
            return GardenDecision("geofence_unresolved")
    return GardenDecision("garden", taxon, score, geofenced, not bool(taxon.ranks[4]))
