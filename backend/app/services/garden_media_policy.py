"""What YA-WAMF keeps of a Garden capture, decided without storage, network or settings.

Only a confirmed capture's media is kept. Its photograph is the full frame the
decision was made on; the clip is Frigate's event clip, kept only while clips
caching is on. A domestic bird's photograph may instead be YA-WAMF's own copy of
the whole frame its bird model classified, because Frigate discards a stationary
bird's event, snapshot and all, within minutes. Motion captures keep their
photograph only: their recording was never shown to the owner and was
person-checked at three sampled frames, so keeping it would publish footage
nobody reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any, Literal, Sequence

from app.models.garden_media import KeptMediaRecord

CAPTURE_ID = re.compile(r"[a-f0-9]{32}")
JPEG_MAGIC = b"\xff\xd8\xff"
PHOTO_BYTES_LIMIT = 16 * 1024 * 1024
MIN_CLIP_BYTES = 512
RETRY_AFTER = timedelta(hours=1)

# A whole frame the bird model read straight from Frigate. A crop, a frame chosen later from video
# and a copy whose cropping was never recorded are not the evidence the record's decision read.
CLASSIFIED_FRAME_SOURCES = frozenset(
    {"frigate_snapshot", "frigate_snapshot_uncropped", "frigate_recording_frame", "frigate_recording_snapshot"}
)


@dataclass(frozen=True)
class ClassifiedFrame:
    """Which of YA-WAMF's own photos is the classified frame, and the checksum it was stored with."""

    reference: str
    sha256: str | None


@dataclass(frozen=True)
class KeepPlan:
    photo: bool
    clip: bool

    @property
    def anything(self) -> bool:
        return self.photo or self.clip


def valid_capture_id(value: object) -> bool:
    return isinstance(value, str) and CAPTURE_ID.fullmatch(value) is not None


def kept_media_retention_days(media_retention_days: int, history_retention_days: int) -> int:
    """The bird media rule: the media setting, or detection retention when it is 0. 0 keeps media."""
    return media_retention_days if media_retention_days > 0 else max(0, history_retention_days)


def within_retention(observed_at: datetime, now: datetime, retention_days: int) -> bool:
    return retention_days <= 0 or observed_at >= now - timedelta(days=retention_days)


def classified_frame_kept(source: str | None) -> bool:
    """Whether a photo the bird model classified is a whole frame Garden may keep as its photograph."""
    return source in CLASSIFIED_FRAME_SOURCES


def classified_frame_reference(
    event_id: str, record_photo_source: str | None, photo_choices: Sequence[dict[str, Any]]
) -> ClassifiedFrame | None:
    """The whole frame a bird record was first classified from, among the photos YA-WAMF holds.

    A later high-quality pass may replace the record's photo with a crop; it retains the photo it
    replaced among the record's photo choices, so the earliest retained original is the classified
    frame. The record's photo stands in only while it is still that frame. A photo the owner hid is
    never used.
    """
    originals = [
        choice
        for choice in photo_choices
        if choice.get("source_mode") == "retained_photo"
        and classified_frame_kept(choice.get("snapshot_source"))
        and choice.get("image_ref")
        and not choice.get("photo_hidden")
    ]
    if originals:
        first = min(originals, key=lambda choice: str(choice.get("created_at") or ""))
        return ClassifiedFrame(reference=str(first["image_ref"]), sha256=first.get("content_sha256"))
    if classified_frame_kept(record_photo_source):
        return ClassifiedFrame(reference=event_id, sha256=None)
    return None


def own_copy_due(state: KeptMediaRecord | None, *, from_bird_record: bool) -> bool:
    """A moved bird record's photo was recorded missing before YA-WAMF looked for its own copy.

    Older versions asked only Frigate. Looking once records the result under the classified frame,
    found or not, so the same capture is never looked at again.
    """
    return (
        from_bird_record
        and state is not None
        and state.photo_state == "missing"
        and state.photo_source == "frigate_snapshot"
    )


def keep_plan(
    *,
    status: str,
    motion: bool,
    camera_enabled: bool,
    within_window: bool,
    clips_wanted: bool,
    state: KeptMediaRecord | None,
    now_iso: str,
    from_bird_record: bool = False,
) -> KeepPlan:
    """Which parts to fetch now. Settled outcomes (missing, changed, evicted) are never retried."""
    if status != "confirmed" or not camera_enabled or not within_window:
        return KeepPlan(photo=False, clip=False)
    retry_due = state is None or state.retry_after is None or state.retry_after <= now_iso
    photo = (
        state is None
        or (state.photo_state == "retry" and retry_due)
        or own_copy_due(state, from_bird_record=from_bird_record)
    )
    clip_possible = clips_wanted and not motion
    clip = clip_possible and (state is None or state.clip_state is None or (state.clip_state == "retry" and retry_due))
    return KeepPlan(photo=photo, clip=clip)


def decision_image_sha256(automatic_sha256: str | None, identification_sha256: str | None) -> str | None:
    """The photograph a recorded decision was made on, when one was recorded."""
    return automatic_sha256 or identification_sha256


def photo_outcome(
    image: bytes | None, *, expected_sha256: str | None, sha256: str | None
) -> Literal["kept", "missing", "changed"]:
    """Keep only a plausible JPEG that is the same evidence any recorded decision used."""
    if not image:
        return "missing"
    if len(image) > PHOTO_BYTES_LIMIT or not image.startswith(JPEG_MAGIC):
        return "changed"
    if expected_sha256 is not None and sha256 != expected_sha256:
        return "changed"
    return "kept"


def frigate_photo_error_state(error: str | None) -> Literal["missing", "retry"]:
    """A 404 is Frigate saying the snapshot is gone; anything else may be a passing failure."""
    return "missing" if error == "snapshot_not_found" else "retry"


def frigate_clip_error_state(error: str | None) -> Literal["missing", "retry"]:
    return "missing" if error in {"clip_not_found", "clip_not_retained"} else "retry"


def eviction_key(capture_id: str) -> str:
    """A Garden entry's key in the shared media budget, which never collides with a Frigate event ID."""
    return f"garden:{capture_id}"


def capture_id_from_eviction_key(key: str) -> str | None:
    prefix, _, capture_id = key.partition(":")
    return capture_id if prefix == "garden" and valid_capture_id(capture_id) else None
