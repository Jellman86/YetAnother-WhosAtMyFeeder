"""Whether a detection's media counts as missing upstream.

Pure decision logic, extracted from the maintenance endpoints so it can be
tested without Frigate, a database or a scheduler (§2). Getting this wrong is
how a working detection gets marked missing — or deleted, on `delete`.
"""

import pytest

from app.services.media_integrity_scan import evaluate_media_presence


def test_an_event_frigate_no_longer_has_is_missing():
    missing, reason = evaluate_media_presence(None, "event_not_found", media="any", clips_enabled=True)
    assert missing is True
    assert reason == "event_not_found"


def test_a_lookup_failure_with_no_reason_still_names_one():
    """A reason of `None` would reach the policy and be recorded as an empty
    error, leaving an owner with a row marked missing and nothing saying why."""
    missing, reason = evaluate_media_presence(None, None, media="any", clips_enabled=True)
    assert missing is True
    assert reason == "event_not_found"


def test_an_event_with_all_its_media_is_present():
    event = {"has_clip": True, "has_snapshot": True}
    assert evaluate_media_presence(event, None, media="any", clips_enabled=True) == (False, None)


@pytest.mark.parametrize(
    ("event", "media", "clips_enabled", "expected_missing", "expected_reason"),
    [
        ({"has_clip": False, "has_snapshot": True}, "clip", True, True, "clip_unavailable"),
        ({"has_clip": False, "has_snapshot": True}, "snapshot", True, False, None),
        ({"has_clip": True, "has_snapshot": False}, "snapshot", True, True, "snapshot_unavailable"),
        ({"has_clip": True, "has_snapshot": False}, "clip", True, False, None),
        ({"has_clip": False, "has_snapshot": True}, "any", True, True, "clip_unavailable"),
        ({"has_clip": True, "has_snapshot": False}, "any", True, True, "snapshot_unavailable"),
    ],
)
def test_the_media_selector_decides_what_counts(event, media, clips_enabled, expected_missing, expected_reason):
    """Someone who scanned only clips must keep scanning only clips. Widening it
    silently would mark rows missing that their setting never covered."""
    assert evaluate_media_presence(event, None, media=media, clips_enabled=clips_enabled) == (
        expected_missing,
        expected_reason,
    )


def test_a_clip_is_not_expected_when_clips_are_turned_off():
    """With Frigate clips disabled there is no clip to be missing, so its
    absence must not condemn the detection."""
    event = {"has_clip": False, "has_snapshot": True}
    assert evaluate_media_presence(event, None, media="any", clips_enabled=False) == (False, None)
    assert evaluate_media_presence(event, None, media="clip", clips_enabled=False) == (False, None)


def test_a_snapshot_is_assumed_present_when_frigate_does_not_say():
    """Frigate omits `has_snapshot` on some event shapes. Absence of the field
    is not evidence of absence of the snapshot."""
    assert evaluate_media_presence({"has_clip": True}, None, media="any", clips_enabled=True) == (False, None)


def test_both_media_missing_reports_both_reasons():
    missing, reason = evaluate_media_presence(
        {"has_clip": False, "has_snapshot": False}, None, media="any", clips_enabled=True
    )
    assert missing is True
    assert reason == "clip_unavailable,snapshot_unavailable"
