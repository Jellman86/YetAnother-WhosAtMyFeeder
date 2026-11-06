"""Plan a snapshot-candidate commit before writing anything.

Choosing which candidates survive (owner choices, the displayed photo, retained and
reviewed frames) happens first, in the high-quality snapshot service. This module
turns that final list into the exact writes: media files in order, the rows that
replace the event's candidates, and legacy dismissals that still match their content.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# Payloads that are written as media files or used only while choosing, never stored in rows.
_TRANSIENT_FIELDS = ("image_bytes", "thumbnail_bytes", "observation_boxes")


@dataclass(frozen=True)
class CandidateMediaWrite:
    kind: Literal["image", "thumbnail"]
    ref: str
    content: bytes
    film_alignment: Optional[dict[str, Any]] = field(default=None)


@dataclass(frozen=True)
class SnapshotEvidenceCommitPlan:
    event_id: str
    media_writes: tuple[CandidateMediaWrite, ...]
    rows: tuple[dict[str, Any], ...]
    # (candidate_id, content digest) pairs whose hidden legacy photo is unchanged.
    legacy_dismissals: tuple[tuple[str, str], ...]
    # The candidates being replaced, so files nothing references any more can be pruned.
    previous_rows: tuple[dict[str, Any], ...]


def build_snapshot_evidence_commit_plan(
    event_id: str,
    candidates: list[dict[str, Any]],
    *,
    previous_rows: list[dict[str, Any]],
    legacy_removed_hashes: dict[str, str],
) -> SnapshotEvidenceCommitPlan:
    media_writes: list[CandidateMediaWrite] = []
    for candidate in candidates:
        image_ref = str(candidate.get("image_ref") or "")
        thumbnail_ref = str(candidate.get("thumbnail_ref") or "")
        image_bytes = candidate.get("image_bytes")
        thumbnail_bytes = candidate.get("thumbnail_bytes")
        if image_ref and isinstance(image_bytes, (bytes, bytearray)):
            media_writes.append(
                CandidateMediaWrite("image", image_ref, bytes(image_bytes), candidate.get("film_alignment") or None)
            )
        if thumbnail_ref and isinstance(thumbnail_bytes, (bytes, bytearray)):
            media_writes.append(CandidateMediaWrite("thumbnail", thumbnail_ref, bytes(thumbnail_bytes)))

    rows = tuple(
        {key: value for key, value in candidate.items() if key not in _TRANSIENT_FIELDS} for candidate in candidates
    )
    legacy_dismissals = tuple(
        (row["candidate_id"], legacy_removed_hashes[row["candidate_id"]])
        for row in rows
        if legacy_removed_hashes.get(row["candidate_id"])
        and legacy_removed_hashes[row["candidate_id"]] == row.get("content_sha256")
    )
    return SnapshotEvidenceCommitPlan(
        event_id=event_id,
        media_writes=tuple(media_writes),
        rows=rows,
        legacy_dismissals=legacy_dismissals,
        previous_rows=tuple(previous_rows),
    )
