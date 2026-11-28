"""Which candidate rows one displayed photo choice stands for.

The strip folds the framings of one frame (the detector's crop, the camera's crop, the whole
scene) into one thumbnail. Removing that thumbnail has to remove every framing behind it, or the
next framing takes its place and the photo seems to survive the click (#1107). The rows of one
removal therefore have to be photographs of one frame of this capture.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from app.repositories.detection_repository import AS_RECORDED_CANDIDATE_ID

PREVIOUS_PHOTO_MODE = "retained_photo"
EVIDENCE_ONLY_MODE = "model_observation"


class PhotoChoiceRequestError(ValueError):
    """The named candidates are not one photo choice."""


class PhotoChoiceNotFound(LookupError):
    """A named candidate is not a photo choice of this capture."""


def resolve_photo_choice(
    candidates: Sequence[Mapping[str, Any]],
    candidate_id: str,
    companion_candidate_ids: Sequence[str] | None,
) -> list[Mapping[str, Any]]:
    """Return the candidate rows of one choice, the shown one first; none for the camera's own snapshot."""
    companions = list(companion_candidate_ids or [])
    named = [candidate_id, *companions]
    if any(not identifier.strip() for identifier in named):
        raise PhotoChoiceRequestError("A photo choice needs a candidate ID")
    if len(set(named)) != len(named):
        raise PhotoChoiceRequestError("Name each photo choice once")
    if AS_RECORDED_CANDIDATE_ID in companions or (candidate_id == AS_RECORDED_CANDIDATE_ID and companions):
        raise PhotoChoiceRequestError("The camera's own snapshot is removed on its own")
    if candidate_id == AS_RECORDED_CANDIDATE_ID:
        return []

    by_id = {str(candidate.get("candidate_id") or ""): candidate for candidate in candidates}
    members = [by_id.get(identifier) for identifier in named]
    if any(member is None for member in members):
        raise PhotoChoiceNotFound("Photo choice unavailable")
    found = [member for member in members if member is not None]
    if any(member.get("source_mode") == EVIDENCE_ONLY_MODE for member in found):
        raise PhotoChoiceRequestError("Evidence the model used is not a photo choice")
    if companions and any(member.get("source_mode") == PREVIOUS_PHOTO_MODE for member in found):
        raise PhotoChoiceRequestError("An earlier photograph is removed on its own")
    if len({(member.get("clip_variant"), member.get("frame_index")) for member in found}) > 1:
        raise PhotoChoiceRequestError("A photo choice holds photographs of one frame")
    return found
