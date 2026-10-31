"""Pure decisions for one automatic Garden check: what it found and where the capture goes.

The service supplies the model's coarse presence outcome, the camera's bird watch and
the owner's settings, then the naming result; nothing here reads settings, storage or
the network.
"""

from dataclasses import dataclass
from typing import Literal

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
    plan: AutomaticPlan, naming: NamingResult, bird_route: GardenBirdRoute
) -> tuple[Outcome, DecisionReason | None]:
    """Combine the plan with the naming result from the same crop."""
    if naming == "person":
        return "human_rejected", None
    if naming == "named":
        return "animal", None
    if naming == "low_confidence":
        return plan.outcome, "below_threshold"
    if plan.outcome == "uncertain":
        # The top species is a bird the owner does not keep, so the photo goes with birds.
        return "uncertain", bird_route if naming == "bird" and bird_route != "domestic_bird" else plan.decision_reason
    return plan.outcome, "identity_unavailable"


def automatic_check_dismisses(outcome: str, decision_reason: str | None) -> bool:
    """Whether a completed check moves a pending capture to Dismissed.

    An animal the check is confident is there stays in Needs review when its species
    score is below the naming threshold: a low species score is not evidence of absence.
    Only uncertain photos are dismissed for a low score.
    """
    if outcome in {"bird", "non_animal"}:
        return True
    return outcome == "uncertain" and decision_reason in {"below_threshold", "bird_camera", "wild_bird"}
