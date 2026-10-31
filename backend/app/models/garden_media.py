"""The record of a confirmed Garden capture's photograph and clip kept by YA-WAMF."""

from dataclasses import dataclass
from typing import Literal

PhotoState = Literal["kept", "retry", "missing", "changed", "evicted"]
ClipState = Literal["kept", "retry", "missing", "evicted"]
PhotoSource = Literal["frigate_snapshot", "motion_photo"]


@dataclass(frozen=True)
class KeptMediaRecord:
    """What was kept, or why not. Checksums bind each kept file to the evidence it copies."""

    photo_state: PhotoState
    photo_source: PhotoSource | None = None
    photo_sha256: str | None = None
    photo_bytes: int | None = None
    clip_state: ClipState | None = None
    clip_sha256: str | None = None
    clip_bytes: int | None = None
    source_start: float | None = None
    source_end: float | None = None
    retry_after: str | None = None


@dataclass(frozen=True)
class KeptMediaEntry:
    """One capture's kept bytes, as the shared media budget weighs them."""

    capture_id: str
    observed_at: str
    bytes_on_disk: int
