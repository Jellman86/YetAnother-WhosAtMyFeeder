"""#481: a Frigate track can move on to a neighbouring bird after the photographed one leaves.

The fixture is the reporter's real event: Frigate photographed a chickadee at the
left of the tray, the chickadee flew off, and the same track id then sat on a
Northern Cardinal for the rest of the event. Crops taken after that jump must
not count as evidence for the event's own bird.
"""

import math

import pytest

from app.services.auto_video_classifier_service import AutoVideoClassifierService
from app.services.classifier_service import ClassifierService, _normalize_classification_input_context

SNAPSHOT_BOX = [0.22135416666666666, 0.5740740740740741, 0.04635416666666667, 0.09259259259259259]
SNAPSHOT_TIME = 1790958435.67411
# The recording clip starts 15 s before the event (recording_clip_before_seconds).
CLIP_START = 1790958433.739871 - 15.0
REPORTER_PATH = [
    [[0.2135, 0.6519], 1790958434.302312],
    [[0.2146, 0.6556], 1790958434.521277],
    [[0.351, 0.6981], 1790958436.904277],
    [[0.3521, 0.6389], 1790958438.330044],
]
UHD = (3840, 2160)


def _event(*, path=REPORTER_PATH, snapshot_time=SNAPSHOT_TIME):
    data = {
        "box": SNAPSHOT_BOX,
        "region": [0.15104166666666666, 0.47685185185185186, 0.16666666666666666, 0.2962962962962963],
        "path_data": path,
    }
    if snapshot_time is not None:
        data["snapshot_frame_time"] = snapshot_time
    return {"id": "1790958433.739871-6eaxsc", "data": data}


def _frame(event, frigate_timestamp, image_size=UHD):
    context = AutoVideoClassifierService()._build_classification_input_context(
        event_id=event["id"],
        event_data=event,
        is_cropped=False,
        clip_variant="recording",
        clip_start_timestamp=CLIP_START,
    )
    service = ClassifierService.__new__(ClassifierService)
    return service._video_frame_input_context(
        _normalize_classification_input_context(context),
        frame_offset_seconds=frigate_timestamp - CLIP_START,
        image_size=image_size,
    ).model_dump()


def test_hint_stays_on_the_photographed_bird_after_the_track_jumps_to_another():
    event = _event()

    at_snapshot = _frame(event, SNAPSHOT_TIME)
    before_snapshot = _frame(event, 1790958434.302312)
    after_jump = _frame(event, 1790958436.904277)
    later = _frame(event, 1790958438.330044)

    assert at_snapshot["frigate_box"] == pytest.approx(SNAPSHOT_BOX)
    assert before_snapshot["frigate_box"] == pytest.approx(
        [0.2135 - SNAPSHOT_BOX[2] / 2, 0.6519 - SNAPSHOT_BOX[3], *SNAPSHOT_BOX[2:]]
    )
    assert "frigate_box" not in after_jump
    assert "frigate_box" not in later


def test_subject_region_does_not_stretch_to_the_bird_the_track_jumped_to():
    region = _frame(_event(), SNAPSHOT_TIME)["event_subject_region"]

    right_edge = region[0] + region[2]
    # Event region ends at 0.318; the jumped-to cardinal's path starts at 0.351.
    assert right_edge == pytest.approx(0.15104166666666666 + 0.16666666666666666)


def test_a_bird_walking_steadily_keeps_its_whole_track():
    # Steps just over Frigate's 5.7% sampling distance: one recorded point per stride.
    walk = [[[0.21 + 0.06 * step, 0.66], SNAPSHOT_TIME - 1.0 + 0.4 * step] for step in range(6)]
    event = _event(path=walk)

    last_x, last_time = walk[-1][0][0], walk[-1][1]
    assert _frame(event, last_time)["frigate_box"][0] == pytest.approx(last_x - SNAPSHOT_BOX[2] / 2)
    assert _frame(event, walk[0][1])["frigate_box"] is not None


def test_a_snapshot_taken_after_the_jump_follows_the_bird_it_shows():
    # Frigate's best photograph can come from the second bird; the event then is that bird.
    event = _event(snapshot_time=1790958438.0)
    event["data"]["box"] = [0.3521 - SNAPSHOT_BOX[2] / 2, 0.6389 - SNAPSHOT_BOX[3], *SNAPSHOT_BOX[2:]]

    assert "frigate_box" not in _frame(event, 1790958434.302312)
    assert _frame(event, 1790958438.330044)["frigate_box"] is not None


def test_without_a_snapshot_time_the_whole_track_is_used_as_before():
    event = _event(snapshot_time=None)

    assert _frame(event, 1790958436.904277)["frigate_box"] is not None


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -1.0, "soon", True, None])
def test_video_context_keeps_only_a_usable_snapshot_time(invalid):
    event = _event()
    event["data"]["snapshot_frame_time"] = invalid

    context = AutoVideoClassifierService()._build_classification_input_context(
        event_id=event["id"], event_data=event, is_cropped=False
    )

    assert "frigate_snapshot_frame_time" not in context


def test_video_context_carries_the_snapshot_time():
    context = AutoVideoClassifierService()._build_classification_input_context(
        event_id="evt", event_data=_event(), is_cropped=False
    )

    assert context["frigate_snapshot_frame_time"] == SNAPSHOT_TIME
