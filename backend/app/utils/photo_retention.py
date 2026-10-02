"""Bound older generated photo choices while protecting human review evidence."""

from typing import Any

MAX_EARLIER_PHOTO_CHOICES = 8


def _age_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("created_at") or ""), str(row.get("candidate_id") or "")


def merge_photo_choices(
    existing: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
    *,
    reviewed_frames: set[tuple[str, int]],
    manual_candidate_id: str | None,
    displayed_photo_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """Keep the new scan, eight earlier choices, the original and reviewed scenes."""
    fresh_by_id = {row["candidate_id"]: row for row in fresh}
    combined = {row["candidate_id"]: {**row, "selected": False} for row in existing}
    combined.update(fresh_by_id)
    protected = {manual_candidate_id} if manual_candidate_id in combined else set()
    old_selected_ids = {row["candidate_id"] for row in existing if row.get("selected")}
    protected |= old_selected_ids
    displayed = [
        row
        for row in combined.values()
        if displayed_photo_sha256 and row.get("content_sha256") == displayed_photo_sha256
    ]
    if displayed:
        protected.add(max(displayed, key=_age_key)["candidate_id"])
    scenes = [row for row in combined.values() if row.get("source_mode") == "full_frame"]
    for frame in reviewed_frames:
        # Keep the existing counted scene while a new scan is being saved. A
        # repeated version of the same moment must not preserve every JPEG.
        matching = [
            row
            for row in existing
            if row.get("source_mode") == "full_frame" and (row.get("clip_variant"), row.get("frame_index")) == frame
        ]
        if matching:
            protected.add(max(matching, key=_age_key)["candidate_id"])
    photos = [
        row
        for key, row in combined.items()
        if row.get("source_mode") != "full_frame" or row.get("classifier_label") or key in old_selected_ids
    ]
    if photos:
        originals = [row for row in photos if str(row.get("snapshot_source") or "").startswith("frigate_")]
        original = min(
            originals or photos,
            key=lambda row: (_age_key(row)[0], row.get("source_mode") != "retained_photo", _age_key(row)[1]),
        )
        protected.add(original["candidate_id"])
    keep = {key for key, row in fresh_by_id.items() if row.get("source_mode") != "retained_photo"} | protected
    older_choices = [
        row
        for key, row in combined.items()
        if key not in keep
        and (row.get("source_mode") != "full_frame" or row.get("classifier_label") or key in old_selected_ids)
    ]
    older_choices.sort(key=_age_key, reverse=True)
    keep.update(row["candidate_id"] for row in older_choices[:MAX_EARLIER_PHOTO_CHOICES])
    # A retained crop's comparison must still use its own whole frame.
    for key in list(keep):
        row = combined[key]
        if row.get("source_mode") in {"retained_photo", "full_frame"}:
            continue
        frame = (row.get("clip_variant"), row.get("frame_index"))
        matching = [scene for scene in scenes if (scene.get("clip_variant"), scene.get("frame_index")) == frame]
        if matching:
            earlier = [scene for scene in matching if _age_key(scene)[0] <= _age_key(row)[0]]
            counterpart = max(earlier or matching, key=_age_key)
            keep.add(counterpart["candidate_id"])
    return [row for key, row in combined.items() if key in keep]


def photo_content_key(event_id: str, candidate: dict[str, Any], digest: str) -> str:
    """Make candidate media immutable while keeping its visit ownership shape."""
    if candidate.get("source_mode") == "retained_photo":
        return f"{event_id}__retained_snapshot__{digest[:12]}"
    candidate_id = str(candidate.get("candidate_id") or "")
    prefix, _, old_digest = candidate_id.rpartition("__")
    if candidate_id.startswith(f"{event_id}__") and len(old_digest) == 10:
        return f"{prefix}__{digest[:10]}"
    mode = candidate.get("source_mode")
    if mode not in {"model_crop", "frigate_hint_crop", "frigate_region_crop", "full_frame"}:
        mode = "full_frame"
    frame = (
        "final" if candidate.get("clip_variant") == "frigate_snapshot" else f"f{int(candidate.get('frame_index') or 0)}"
    )
    return f"{event_id}__{mode}__{frame}__{digest[:10]}"
