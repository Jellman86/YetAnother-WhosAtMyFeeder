"""The rules that turn a request to record a feeder refill into one stored refill, or a refusal (#946)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.feeder_refill import StoredRefill
from app.services.feeder_refills import REFILL_COOLDOWN, RefillRefused, RefillRequest, decide_refill, prepare_refill

NOW = datetime(2026, 11, 28, 9, 30, 15, 640000)
CAMERAS = ("birdcam", "greenhousecam")


def stored(refill_id: int, at: datetime, camera: str | None = "birdcam", event: str | None = None) -> StoredRefill:
    return StoredRefill(
        id=refill_id,
        refilled_at=at,
        camera_name=camera,
        source="api",
        note=None,
        source_event_id=event,
        created_at=at,
    )


def test_a_refill_without_a_time_is_recorded_now_to_the_second():
    refill = prepare_refill(RefillRequest(source="manual"), now=NOW, configured_cameras=CAMERAS)
    assert refill.refilled_at == datetime(2026, 11, 28, 9, 30, 15)
    assert refill.camera_name is None
    assert refill.source == "manual"


def test_a_refill_time_with_an_offset_is_stored_in_utc():
    at = datetime(2026, 11, 28, 3, 0, 0, 321000, tzinfo=timezone(timedelta(hours=-5)))
    refill = prepare_refill(RefillRequest(source="api", refilled_at=at), now=NOW, configured_cameras=CAMERAS)
    assert refill.refilled_at == datetime(2026, 11, 28, 8, 0, 0, 321000)
    assert refill.refilled_at.tzinfo is None


@pytest.mark.parametrize("ahead", [timedelta(microseconds=1), timedelta(seconds=40), timedelta(hours=1)])
def test_a_refill_in_the_future_is_refused(ahead):
    with pytest.raises(RefillRefused) as refused:
        prepare_refill(RefillRequest(source="manual", refilled_at=NOW + ahead), now=NOW, configured_cameras=CAMERAS)
    assert refused.value.code == "future_time"


def test_a_camera_yawamf_does_not_watch_is_refused():
    with pytest.raises(RefillRefused) as refused:
        prepare_refill(RefillRequest(source="api", camera_name="frontdoor"), now=NOW, configured_cameras=CAMERAS)
    assert refused.value.code == "unknown_camera"


def test_a_configured_camera_is_kept_and_a_blank_one_means_no_camera():
    named = prepare_refill(RefillRequest(source="api", camera_name=" birdcam "), now=NOW, configured_cameras=CAMERAS)
    blank = prepare_refill(RefillRequest(source="api", camera_name="  "), now=NOW, configured_cameras=CAMERAS)
    assert named.camera_name == "birdcam"
    assert blank.camera_name is None


def test_a_note_is_kept_as_one_line_of_plain_text():
    refill = prepare_refill(
        RefillRequest(source="manual", note="  Sunflower\nhearts\t<b>and</b>\x00 suet  "),
        now=NOW,
        configured_cameras=CAMERAS,
    )
    assert refill.note == "Sunflower hearts <b>and</b> suet"


def test_an_empty_note_is_no_note():
    refill = prepare_refill(RefillRequest(source="manual", note=" \n "), now=NOW, configured_cameras=CAMERAS)
    assert refill.note is None


@pytest.mark.parametrize("note", ["x" * 281, "x" + " " * 280])
def test_a_note_over_the_limit_is_refused_rather_than_cut_short(note):
    with pytest.raises(RefillRefused) as refused:
        prepare_refill(RefillRequest(source="manual", note=note), now=NOW, configured_cameras=CAMERAS)
    assert refused.value.code == "note_too_long"


@pytest.mark.parametrize(
    "event_id", ["", "a" * 129, "door\nopened", "door\x00", "door\u2028opened", "door\u2029opened"]
)
def test_an_unusable_automation_event_id_is_refused(event_id):
    with pytest.raises(RefillRefused) as refused:
        prepare_refill(RefillRequest(source="api", source_event_id=event_id), now=NOW, configured_cameras=CAMERAS)
    assert refused.value.code == "invalid_source_event_id"


def test_the_same_automation_event_twice_is_one_refill():
    refill = prepare_refill(RefillRequest(source="api", source_event_id="ha-42"), now=NOW, configured_cameras=CAMERAS)
    earlier = stored(7, NOW - timedelta(days=2), event="ha-42")
    decision = decide_refill(refill, same_event=earlier, nearby=[])
    assert decision.outcome == "same_event"
    assert decision.refill == earlier


def test_two_refills_of_one_camera_inside_the_cooldown_fold_into_the_nearest():
    refill = prepare_refill(RefillRequest(source="manual", camera_name="birdcam"), now=NOW, configured_cameras=CAMERAS)
    far = stored(1, refill.refilled_at - REFILL_COOLDOWN + timedelta(minutes=1))
    near = stored(2, refill.refilled_at - timedelta(minutes=3))
    decision = decide_refill(refill, same_event=None, nearby=[far, near])
    assert decision.outcome == "within_cooldown"
    assert decision.refill == near


def test_refills_of_other_cameras_or_outside_the_cooldown_do_not_fold():
    refill = prepare_refill(RefillRequest(source="manual", camera_name="birdcam"), now=NOW, configured_cameras=CAMERAS)
    other_camera = stored(1, refill.refilled_at, camera="greenhousecam")
    no_camera = stored(2, refill.refilled_at, camera=None)
    too_early = stored(3, refill.refilled_at - REFILL_COOLDOWN - timedelta(seconds=1))
    decision = decide_refill(refill, same_event=None, nearby=[other_camera, no_camera, too_early])
    assert decision.outcome == "recorded"
    assert decision.refill is None


def test_two_refills_with_no_camera_inside_the_cooldown_fold():
    refill = prepare_refill(RefillRequest(source="manual"), now=NOW, configured_cameras=CAMERAS)
    earlier = stored(4, refill.refilled_at - timedelta(minutes=10), camera=None)
    assert decide_refill(refill, same_event=None, nearby=[earlier]).outcome == "within_cooldown"


def test_a_backdated_refill_folds_into_a_later_one_inside_the_cooldown():
    at = NOW - timedelta(days=1)
    refill = prepare_refill(
        RefillRequest(source="manual", camera_name="birdcam", refilled_at=at.replace(tzinfo=timezone.utc)),
        now=NOW,
        configured_cameras=CAMERAS,
    )
    later = stored(5, refill.refilled_at + timedelta(minutes=5))
    assert decide_refill(refill, same_event=None, nearby=[later]).refill == later
