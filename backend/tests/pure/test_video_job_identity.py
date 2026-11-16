"""The video queue names its jobs one way, in the jobs snapshot and in the stream's start event alike."""

from app.services.video_job_identity import reclassification_started_message, video_job_id


def test_a_manual_reclassification_and_queued_analysis_have_their_snapshot_ids():
    assert video_job_id("evt-1", "manual") == "reclassify:evt-1"
    assert video_job_id("evt-1", "live") == "video:evt-1"
    assert video_job_id("evt-1", "maintenance") == "video:evt-1"


def test_the_start_event_carries_the_server_job_it_belongs_to():
    manual = reclassification_started_message("evt-2", manual=True, source="maintenance")
    automatic = reclassification_started_message("evt-3", manual=False, source="live")

    assert manual == {
        "type": "reclassification_started",
        "data": {"event_id": "evt-2", "strategy": "video", "job_id": "reclassify:evt-2"},
    }
    assert automatic["data"] == {"event_id": "evt-3", "strategy": "auto_video", "job_id": "video:evt-3"}
