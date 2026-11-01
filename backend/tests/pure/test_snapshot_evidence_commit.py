"""A snapshot-candidate commit is decided in full before its first write.

The plan says which media files are written, in what order, which rows replace the
event's candidates, and which legacy dismissals bind to unchanged content. Building it
touches no files or database, so these cases are the decisions alone.
"""

import dataclasses

import pytest

from app.services.snapshot_evidence_commit import (
    CandidateMediaWrite,
    SnapshotEvidenceCommitPlan,
    build_snapshot_evidence_commit_plan,
)


def _candidate(candidate_id: str, **fields):
    return {"candidate_id": candidate_id, "selected": False, **fields}


def test_media_is_written_in_candidate_order_with_each_image_before_its_thumbnail():
    plan = build_snapshot_evidence_commit_plan(
        "evt",
        [
            _candidate(
                "a",
                image_ref="evt__a__image",
                image_bytes=bytearray(b"image-a"),
                thumbnail_ref="evt__a__thumb",
                thumbnail_bytes=b"thumb-a",
                film_alignment={"offset": 1.5},
            ),
            _candidate("b", image_ref="evt__b__image", image_bytes=b"image-b"),
        ],
        previous_rows=[],
        legacy_removed_hashes={},
    )

    assert plan.media_writes == (
        CandidateMediaWrite("image", "evt__a__image", b"image-a", {"offset": 1.5}),
        CandidateMediaWrite("thumbnail", "evt__a__thumb", b"thumb-a"),
        CandidateMediaWrite("image", "evt__b__image", b"image-b"),
    )
    assert isinstance(plan.media_writes[0].content, bytes)


def test_rows_without_a_ref_or_without_bytes_write_no_media():
    plan = build_snapshot_evidence_commit_plan(
        "evt",
        [
            _candidate("kept", image_ref="evt__kept__image"),
            _candidate("unreferenced", image_bytes=b"orphan", thumbnail_bytes=b"orphan-thumb"),
            _candidate("not-bytes", image_ref="evt__x__image", image_bytes="text"),
        ],
        previous_rows=[],
        legacy_removed_hashes={},
    )

    assert plan.media_writes == ()


def test_persisted_rows_carry_no_payload_bytes_or_observation_boxes():
    candidate = _candidate(
        "a",
        image_ref="evt__a__image",
        image_bytes=b"image",
        thumbnail_bytes=b"thumb",
        observation_boxes=[[0, 0, 1, 1]],
        content_sha256="digest",
        selected=True,
    )

    plan = build_snapshot_evidence_commit_plan("evt", [candidate], previous_rows=[], legacy_removed_hashes={})

    assert plan.rows == (
        {"candidate_id": "a", "selected": True, "image_ref": "evt__a__image", "content_sha256": "digest"},
    )
    assert "image_bytes" in candidate


def test_a_legacy_dismissal_binds_only_to_unchanged_content():
    plan = build_snapshot_evidence_commit_plan(
        "evt",
        [
            _candidate("same", content_sha256="old-same"),
            _candidate("changed", content_sha256="new"),
            _candidate("never-hidden", content_sha256="whatever"),
        ],
        previous_rows=[],
        legacy_removed_hashes={"same": "old-same", "changed": "old-changed"},
    )

    assert plan.legacy_dismissals == (("same", "old-same"),)


def test_the_plan_keeps_the_previous_rows_for_pruning_and_is_frozen():
    previous = [_candidate("old", image_ref="evt__old__image")]

    plan = build_snapshot_evidence_commit_plan("evt", [], previous_rows=previous, legacy_removed_hashes={})

    assert plan == SnapshotEvidenceCommitPlan(
        event_id="evt", media_writes=(), rows=(), legacy_dismissals=(), previous_rows=tuple(previous)
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.event_id = "other"  # type: ignore[misc]
