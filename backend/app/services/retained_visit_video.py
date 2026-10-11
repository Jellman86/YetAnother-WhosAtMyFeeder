"""A visit's own video that YA-WAMF keeps outside Frigate and the media cache.

The player plays a favourite's archived clip and an uploaded video after Frigate and the cache have let
go of them, so anything that needs the visit's video must be able to find them too (#481).
"""

from pathlib import Path
from typing import Optional

from app.services.archive_service import archive_service
from app.services.manual_observation_service import manual_observation_service


async def retained_event_clip(event_id: str) -> Optional[Path]:
    """The archived event clip of a favourite, or the uploaded video of a manual observation."""
    if event_id.startswith("manual_"):
        return await manual_observation_service.video_path_for_event(event_id)
    return await archive_service.clip_path(event_id)


async def retained_recording_clip(event_id: str) -> Optional[Path]:
    """The archived full-visit recording of a favourite."""
    if event_id.startswith("manual_"):
        return None
    return await archive_service.recording_path(event_id)


async def has_retained_video(event_id: str) -> bool:
    return await retained_recording_clip(event_id) is not None or await retained_event_clip(event_id) is not None
