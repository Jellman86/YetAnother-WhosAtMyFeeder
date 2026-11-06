"""Conservative physical-bird evidence, independent of species identity.

These development thresholds require scene and provider qualification before
the confirmation policy is enabled in counting. No inference or I/O runs here.
Proposal presence does not establish individuality: selection must still apply
duplicate and cluster ambiguity gates before publishing a capture count.
"""

from dataclasses import dataclass
import math
import re
from typing import Literal


MIN_DETECTOR_CONFIDENCE = 0.08
STRONG_DETECTOR_CONFIDENCE = 0.60
MIN_BIRD_MASS = 0.50
MIN_NONBIRD_MASS = 0.85

PhysicalVerdict = Literal["counted", "excluded", "unconfirmed"]


@dataclass(frozen=True)
class PhysicalGroupEvidence:
    model_sha256: str
    mapping_sha256: str
    crop_sha256: str
    output_width: int
    bird_outputs: int
    nonbird_outputs: int
    bird_mass: float
    nonbird_mass: float
    unknown_mass: float
    top_group: Literal["bird", "nonbird", "unknown"]


@dataclass(frozen=True)
class PhysicalBirdDecision:
    verdict: PhysicalVerdict
    reason: str


def _probability(value: object) -> bool:
    return type(value) in {int, float} and 0.0 <= value <= 1.0 and math.isfinite(value)


def _digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _bound_evidence(
    evidence: PhysicalGroupEvidence,
    *,
    model_sha256: str | None,
    mapping_sha256: str | None,
    crop_sha256: str | None,
) -> bool:
    bindings = (
        (evidence.model_sha256, model_sha256),
        (evidence.mapping_sha256, mapping_sha256),
        (evidence.crop_sha256, crop_sha256),
    )
    if any(not _digest(actual) or actual != expected for actual, expected in bindings):
        return False
    counts = (evidence.output_width, evidence.bird_outputs, evidence.nonbird_outputs)
    if any(type(count) is not int or count <= 0 for count in counts):
        return False
    known_outputs = evidence.bird_outputs + evidence.nonbird_outputs
    if known_outputs > evidence.output_width:
        return False
    masses = (evidence.bird_mass, evidence.nonbird_mass, evidence.unknown_mass)
    if not all(_probability(mass) for mass in masses) or not math.isclose(sum(masses), 1.0, abs_tol=1e-5):
        return False
    if known_outputs == evidence.output_width and evidence.unknown_mass > 1e-5:
        return False
    if not isinstance(evidence.top_group, str) or evidence.top_group not in {"bird", "nonbird", "unknown"}:
        return False
    group_mass = {"bird": masses[0], "nonbird": masses[1], "unknown": masses[2]}
    return group_mass[evidence.top_group] > 0.0


def decide_physical_bird(
    detector_confidence: float | None,
    *,
    finder_qualified: bool,
    evidence: PhysicalGroupEvidence | None,
    expected_model_sha256: str | None,
    expected_mapping_sha256: str | None,
    expected_crop_sha256: str | None,
) -> PhysicalBirdDecision:
    """Use only qualified detector evidence and verified, own-pixel group mass.

    A bird-only classifier cannot prove presence by summing its outputs. Unknown
    taxonomic mass stays unknown; it is never redistributed over known groups.
    """
    if finder_qualified is not True:
        return PhysicalBirdDecision("unconfirmed", "finder_not_qualified")
    if not _probability(detector_confidence) or detector_confidence < MIN_DETECTOR_CONFIDENCE:
        return PhysicalBirdDecision("unconfirmed", "invalid_detector_evidence")
    strong = detector_confidence >= STRONG_DETECTOR_CONFIDENCE
    if evidence is None:
        return (
            PhysicalBirdDecision("counted", "strong_detector")
            if strong
            else PhysicalBirdDecision("unconfirmed", "confirmation_unavailable")
        )
    if not isinstance(evidence, PhysicalGroupEvidence) or not _bound_evidence(
        evidence,
        model_sha256=expected_model_sha256,
        mapping_sha256=expected_mapping_sha256,
        crop_sha256=expected_crop_sha256,
    ):
        return PhysicalBirdDecision("unconfirmed", "unbound_confirmation")
    if evidence.nonbird_mass >= MIN_NONBIRD_MASS and evidence.top_group == "nonbird":
        return (
            PhysicalBirdDecision("unconfirmed", "conflicting_confirmation")
            if strong
            else PhysicalBirdDecision("excluded", "own_crop_nonbird")
        )
    if strong:
        return PhysicalBirdDecision("counted", "strong_detector")
    if evidence.bird_mass >= MIN_BIRD_MASS:
        return PhysicalBirdDecision("counted", "own_crop_bird")
    return PhysicalBirdDecision("unconfirmed", "insufficient_confirmation")
