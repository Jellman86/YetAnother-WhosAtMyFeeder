"""The video analysis queue as the owner sees it: what is waiting, running, and why it is held."""

from app.models.analysis_status import AnalysisStatusResponse
from app.services.auto_video_classifier_service import auto_video_classifier

BATCH_ANALYSIS_MAX_QUEUE_PER_RUN = 50
BATCH_ANALYSIS_MAX_SCAN_PER_RUN = 200

__all__ = ["AnalysisStatusResponse", "build_analysis_status"]


def build_analysis_status() -> AnalysisStatusResponse:
    return AnalysisStatusResponse.model_validate(
        {
            **auto_video_classifier.get_status(),
            "queue_limit": BATCH_ANALYSIS_MAX_QUEUE_PER_RUN,
            "scan_limit": BATCH_ANALYSIS_MAX_SCAN_PER_RUN,
        }
    )
