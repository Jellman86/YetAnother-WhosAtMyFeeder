"""Pure decisions for one automatic Garden check: what it found and where the capture goes.

The service supplies the model's coarse presence outcome, the camera's bird watch and
the owner's settings, then the naming result; nothing here reads settings, storage or
the network.
"""

from dataclasses import dataclass
from typing import Literal

from app.models.garden import GardenAutomaticCheck
from app.services.garden_domestic_birds import GardenBirdRoute

Outcome = Literal["animal", "bird", "non_animal", "uncertain", "human_rejected"]
DecisionReason = Literal[
    "below_threshold", "naming_disabled", "location_required", "identity_unavailable", "bird_camera", "wild_bird"
]
NamingResult = Literal["person", "named", "low_confidence", "bird", "unresolved"]


@dataclass(frozen=True)
class AutomaticPlan:
    outcome: Outcome
    decision_reason: DecisionReason | None
    run_naming: bool


def _naming_plan(outcome: Outcome, *, automatic_naming: bool, country_known: bool) -> AutomaticPlan:
    if not automatic_naming:
        return AutomaticPlan(outcome, "naming_disabled" if outcome == "animal" else None, False)
    if not country_known:
        return AutomaticPlan(outcome, "location_required", False)
    # Until a name is saved, an uncertain photo counts as below the naming threshold.
    return AutomaticPlan(outcome, "below_threshold" if outcome == "uncertain" else None, True)


def plan_automatic_check(
    presence: Outcome, bird_route: GardenBirdRoute, *, automatic_naming: bool, country_known: bool
) -> AutomaticPlan:
    """What to do before naming, from the coarse presence outcome.

    ``bird_route`` says what the top species result means if it is a bird. A declared
    domestic bird is an animal like a dog; any other bird is handed to bird detection
    on a camera watched for birds, or dismissed as a wild bird on a Garden-only one.
    """
    if presence in {"human_rejected", "non_animal"}:
        return AutomaticPlan(presence, None, False)
    if presence == "bird":
        if bird_route == "domestic_bird":
            return _naming_plan("animal", automatic_naming=automatic_naming, country_known=country_known)
        return AutomaticPlan("bird", bird_route, False)
    return _naming_plan(presence, automatic_naming=automatic_naming, country_known=country_known)


def finish_automatic_check(
    plan: AutomaticPlan, naming: NamingResult, bird_route: GardenBirdRoute, *, score_below_threshold: bool = False
) -> tuple[Outcome, DecisionReason | None]:
    """Combine the plan with the naming result from the same crop.

    ``score_below_threshold`` says whether the top species score missed the naming
    threshold; a name the catalogue cannot bind waits for a person only when it did not.
    """
    if naming == "person":
        return "human_rejected", None
    if naming == "named":
        return "animal", None
    if naming == "low_confidence":
        return plan.outcome, "below_threshold"
    if plan.outcome == "uncertain":
        # The top species is a bird the owner does not keep, so the photo goes with birds.
        return "uncertain", bird_route if naming == "bird" and bird_route != "domestic_bird" else plan.decision_reason
    return plan.outcome, "below_threshold" if score_below_threshold else "identity_unavailable"


def automatic_check_dismisses(outcome: str, decision_reason: str | None) -> bool:
    """Whether a completed check moves a pending capture to Dismissed.

    The naming threshold is the owner's floor for what Garden shows: an animal or an
    uncertain photo whose species score misses it is dismissed, and stays restorable.
    """
    if outcome in {"bird", "non_animal"}:
        return True
    if decision_reason == "below_threshold":
        return outcome in {"animal", "uncertain"}
    return outcome == "uncertain" and decision_reason in {"bird_camera", "wild_bird"}


def saved_check_dismisses(check: GardenAutomaticCheck) -> bool:
    """Whether a saved check dismisses its capture under the current policy.

    Checks saved before an unbound low score counted as below the threshold carry
    ``identity_unavailable`` with the score that missed it.
    """
    if automatic_check_dismisses(check.outcome, check.decision_reason):
        return True
    return (
        check.decision_reason == "identity_unavailable"
        and check.naming_score is not None
        and check.naming_threshold is not None
        and check.naming_score < check.naming_threshold
    )
