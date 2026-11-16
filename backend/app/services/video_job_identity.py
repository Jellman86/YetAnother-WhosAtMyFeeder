"""How the video queue names a job, so the jobs snapshot and the live stream name it alike.

A page that follows a reclassification over the stream learns the server job it belongs to from
the start event, and counts it once: as the server's work, whether or not the server's capped
jobs list happens to include it. Work that runs outside the queue (a snapshot reclassification
inside the request) has no server job and no `job_id`.
"""


def video_job_id(event_id: str, source: str) -> str:
    return f"reclassify:{event_id}" if source == "manual" else f"video:{event_id}"


def reclassification_started_message(event_id: str, *, manual: bool, source: str) -> dict[str, object]:
    return {
        "type": "reclassification_started",
        "data": {
            "event_id": event_id,
            "strategy": "video" if manual else "auto_video",
            "job_id": video_job_id(event_id, "manual" if manual else source),
        },
    }
