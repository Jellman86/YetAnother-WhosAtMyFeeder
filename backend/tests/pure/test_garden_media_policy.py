"""What a Garden capture keeps is decided without storage, network or settings."""

from datetime import datetime, timedelta
import hashlib

import pytest

from app.models.garden_media import KeptMediaRecord
from app.services.garden_media_cache import kept_path
from app.services.garden_media_policy import (
    capture_id_from_eviction_key,
    classified_frame_kept,
    classified_frame_reference,
    own_copy_due,
    settled_missing_source,
    decision_image_sha256,
    eviction_key,
    frigate_clip_error_state,
    frigate_photo_error_state,
    keep_plan,
    kept_media_retention_days,
    photo_outcome,
    valid_capture_id,
    within_retention,
)

NOW = "2026-10-31T12:00:00"
JPEG = b"\xff\xd8\xff\xe0" + b"photo"


def plan(**overrides):
    values = {
        "status": "confirmed",
        "motion": False,
        "camera_enabled": True,
        "within_window": True,
        "clips_wanted": True,
        "state": None,
        "now_iso": NOW,
    }
    return keep_plan(**{**values, **overrides})


@pytest.mark.parametrize("status", ["pending", "dismissed", "blocked"])
def test_unconfirmed_captures_never_keep_anything(status):
    assert not plan(status=status).anything


def test_a_confirmed_frigate_capture_keeps_its_photo_and_clip_while_clips_are_cached():
    assert plan().photo and plan().clip
    assert plan(clips_wanted=False).photo and not plan(clips_wanted=False).clip


def test_a_confirmed_motion_capture_keeps_its_photo_but_never_a_clip():
    kept = plan(motion=True)
    assert kept.photo and not kept.clip


def test_a_switched_off_camera_or_expired_capture_keeps_nothing():
    assert not plan(camera_enabled=False).anything
    assert not plan(within_window=False).anything


@pytest.mark.parametrize("settled", ["kept", "missing", "changed", "evicted"])
def test_settled_photos_are_never_fetched_again(settled):
    state = KeptMediaRecord(photo_state=settled, clip_state="missing")
    assert not plan(state=state).anything


def test_a_retry_waits_for_its_time():
    early = KeptMediaRecord(photo_state="retry", clip_state="retry", retry_after="2026-10-31T13:00:00")
    due = KeptMediaRecord(photo_state="retry", clip_state="retry", retry_after="2026-10-31T11:00:00")
    assert not plan(state=early).anything
    assert plan(state=due).photo and plan(state=due).clip


def test_turning_clip_caching_on_later_fetches_only_the_missing_clip():
    state = KeptMediaRecord(photo_state="kept", clip_state=None)
    later = plan(state=state)
    assert later.clip and not later.photo


def test_media_retention_follows_the_bird_media_rule():
    assert kept_media_retention_days(0, 30) == 30
    assert kept_media_retention_days(14, 30) == 14
    assert kept_media_retention_days(0, 0) == 0
    now = datetime(2026, 10, 31)
    assert within_retention(now - timedelta(days=400), now, 0)
    assert within_retention(now - timedelta(days=6), now, 7)
    assert not within_retention(now - timedelta(days=8), now, 7)


def test_a_photo_is_kept_only_when_it_is_the_evidence_the_decision_used():
    sha = hashlib.sha256(JPEG).hexdigest()
    assert photo_outcome(JPEG, expected_sha256=None, sha256=sha) == "kept"
    assert photo_outcome(JPEG, expected_sha256=sha, sha256=sha) == "kept"
    assert photo_outcome(JPEG, expected_sha256="a" * 64, sha256=sha) == "changed"
    assert photo_outcome(b"<html>not a photo</html>", expected_sha256=None, sha256="b" * 64) == "changed"
    assert photo_outcome(None, expected_sha256=sha, sha256=None) == "missing"


def test_the_automatic_check_photo_is_the_decision_evidence_before_a_later_suggestion():
    assert decision_image_sha256("a" * 64, "b" * 64) == "a" * 64
    assert decision_image_sha256(None, "b" * 64) == "b" * 64
    assert decision_image_sha256(None, None) is None


def test_only_frigate_saying_gone_settles_a_missing_source():
    assert frigate_photo_error_state("snapshot_not_found") == "missing"
    assert frigate_photo_error_state("snapshot_timeout") == "retry"
    assert frigate_clip_error_state("clip_not_retained") == "missing"
    assert frigate_clip_error_state("clip_request_error") == "retry"


@pytest.mark.parametrize(
    "unsafe", ["../" + "a" * 29, "A" * 32, "a" * 31, "a" * 33, "1700000000.1-cat", "", "a" * 31 + "/"]
)
def test_kept_paths_come_only_from_validated_capture_ids(unsafe):
    assert not valid_capture_id(unsafe)
    with pytest.raises(ValueError):
        kept_path(unsafe, "photo")


def test_a_kept_path_stays_inside_the_garden_folder():
    path = kept_path("a" * 32, "clip")
    assert path.name == "a" * 32 + ".mp4"
    assert path.parent.name == "garden"


def test_budget_keys_round_trip_only_for_garden_captures():
    key = eviction_key("c" * 32)
    assert capture_id_from_eviction_key(key) == "c" * 32
    assert capture_id_from_eviction_key("1700000000.1-bird") is None
    assert capture_id_from_eviction_key("garden:../etc") is None


# The bird model's first read of a visit, and the copies YA-WAMF made of the record's photos.
EVENT = "1795166156.230183-07thuv"


def retained(source, digest, created_at, *, mode="retained_photo", hidden=False):
    return {
        "source_mode": mode,
        "snapshot_source": source,
        "image_ref": f"{EVENT}__retained_snapshot__{digest[:12]}__image",
        "content_sha256": digest,
        "created_at": created_at,
        "photo_hidden": hidden,
    }


@pytest.mark.parametrize(
    "source",
    ["frigate_snapshot", "frigate_snapshot_uncropped", "frigate_recording_frame", "frigate_recording_snapshot"],
)
def test_a_whole_frame_the_bird_model_read_from_frigate_is_kept(source):
    assert classified_frame_kept(source)


@pytest.mark.parametrize(
    "source",
    [
        None,
        "",
        "frigate_snapshot_cropped",
        "frigate_snapshot_unverified",
        "hq_candidate_model_crop",
        "hq_candidate_full_frame",
        "video_evidence_full_frame",
        "cached_snapshot_unknown",
    ],
)
def test_a_crop_a_later_video_frame_or_an_unverified_copy_is_not_the_classified_frame(source):
    assert not classified_frame_kept(source)


def test_the_earliest_retained_original_is_the_classified_frame_even_after_a_crop_replaced_the_record_photo():
    rows = [
        retained("hq_candidate_model_crop", "b" * 64, "2026-11-20 09:17:42"),
        retained("frigate_recording_frame", "a" * 64, "2026-11-20 09:17:43"),
        retained("frigate_snapshot", "c" * 64, "2026-11-20 09:18:00"),
        retained("frigate_recording_frame", "e" * 64, "2026-11-20 09:16:00", mode="full_frame"),
    ]
    frame = classified_frame_reference(EVENT, {"source": "hq_candidate_model_crop"}, rows)
    assert frame is not None
    assert frame.reference == f"{EVENT}__retained_snapshot__{'a' * 12}__image"
    assert frame.sha256 == "a" * 64


def test_the_record_photo_stands_in_only_while_it_is_still_the_classified_frame():
    record_photo = {"source": "frigate_recording_frame", "image_sha256": "d" * 64}
    frame = classified_frame_reference(EVENT, record_photo, [])
    assert frame is not None and (frame.reference, frame.sha256) == (EVENT, "d" * 64)
    assert classified_frame_reference(EVENT, {"source": "hq_candidate_model_crop", "image_sha256": "d" * 64}, []) is None
    assert classified_frame_reference(EVENT, {}, []) is None


def test_the_record_photo_needs_its_recorded_checksum_to_stand_in():
    # Without the digest the bytes read later could be a crop written in between.
    assert classified_frame_reference(EVENT, {"source": "frigate_recording_frame"}, []) is None


def test_an_owners_chosen_photo_is_never_the_classified_frame():
    chosen = {"source": "frigate_snapshot", "image_sha256": "d" * 64, "manual_selection": True}
    assert classified_frame_reference(EVENT, chosen, []) is None


def test_a_photo_the_owner_hid_is_never_used():
    rows = [retained("frigate_recording_frame", "a" * 64, "2026-11-20 09:17:43", hidden=True)]
    assert classified_frame_reference(EVENT, {"source": "hq_candidate_model_crop"}, rows) is None


def test_a_photo_frigate_lost_before_yawamf_looked_for_its_own_copy_is_looked_for_once():
    untried = KeptMediaRecord(photo_state="missing", photo_source="frigate_snapshot", clip_state="missing")
    looked = KeptMediaRecord(photo_state="missing", photo_source="classified_frame", clip_state="missing")
    assert own_copy_due(untried, from_bird_record=True)
    assert not own_copy_due(untried, from_bird_record=False)
    assert not own_copy_due(looked, from_bird_record=True)
    assert not own_copy_due(None, from_bird_record=True)
    assert plan(state=untried, from_bird_record=True).photo
    assert not plan(state=untried, from_bird_record=True).clip
    assert not plan(state=untried).anything
    assert not plan(state=looked, from_bird_record=True).anything


def test_a_moved_capture_whose_photo_cannot_be_looked_for_settles_at_once():
    for from_bird_record in (True, False):
        settled = KeptMediaRecord(photo_state="missing", photo_source=settled_missing_source(from_bird_record=from_bird_record))
        assert not own_copy_due(settled, from_bird_record=from_bird_record)
    assert settled_missing_source(from_bird_record=False) == "frigate_snapshot"
