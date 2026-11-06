"""Select completed evidence for the currently selected model, never a recommendation."""

from collections.abc import Iterable
from pydantic import ValidationError
from app.models.inference_execution import InferenceExecution


def latest_model_execution(model_id: str | None, observations: Iterable[object]) -> InferenceExecution | None:
    valid: list[InferenceExecution] = []
    for observation in observations:
        try:
            execution = InferenceExecution.model_validate(observation)
        except ValidationError:
            continue
        if execution.model_id == model_id:
            valid.append(execution)
    return max(valid, key=lambda item: item.checked_at) if valid else None
