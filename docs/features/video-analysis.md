# Deep Video Analysis

While real-time detection uses a single snapshot, YA-WAMF provides a **Deep Video Analysis** mode for the most accurate identification possible. By sampling many frames from the full clip and combining their predictions, it significantly reduces errors from motion blur, partial occlusion, or a bad angle in a single frame.

## How It Works

1. The backend resolves the best local video first: a complete cached full-visit recording, a
   decodable partial recording, then the cached event clip. It asks Frigate for the event clip only
   when no usable local copy exists. Each candidate is decoded before inference; an invalid cached
   file is removed and resolution continues instead of falling straight back to a snapshot.
2. It uses deterministic, centre-weighted stratified sampling. Event clips retain their first/last
   boundaries and place the remaining samples through the central half, where the tracked subject is
   most likely to be useful. Longer recording clips keep roughly 70% uniform coverage and spend the
   remaining samples in that central region. The default is **15 frames**, configurable in
   **Settings > Detection**.
3. Each frame is evaluated as a full frame and, when valid, with independent Frigate-hint and
   detector-crop representations that match the active model's input contract.
4. Each representation must form its own temporal consensus across multiple frames. Conflicting
   representations cause an abstention rather than adding misleading extra votes.
5. A confident result updates the detection. If neither video nor the snapshot fallback has usable
   evidence, YA-WAMF returns **No confident result**, preserves the existing identification, and
   records no manual override.

## Running an Analysis

Click **Reclassify** on any detection card. When an event clip or fetched full-visit clip is
available, YA-WAMF performs temporal video analysis; it does not replace that explicit video run
with a faster snapshot-only result. If no video can be decoded, it explains the downgrade and uses
the best cached or Frigate snapshot as a fallback.

The action is admitted to the same bounded queue as live and maintenance video work, returns
immediately, and deduplicates by event. The Jobs view is authoritative for queued/running progress.
Temporal inference always runs in a supervised subprocess; cancellation or a hard timeout
terminates that worker, so native OpenVINO/ONNX work cannot continue invisibly after the request
ends.

A shorter-than-requested full-visit clip remains valid evidence when it is a real, decodable MP4.
YA-WAMF analyzes the frames it contains instead of discarding the clip merely because Frigate could
not provide the ideal window.

This source selection is independent of stale Frigate metadata. If the detection says its event
clip is gone but YA-WAMF can still play a cached full-visit recording, the Reclassify action uses
that recording. Completing a cached-video run also replaces any obsolete `event_not_found` status
with the result of the new attempt.

## Visual Feedback

During analysis, a real-time **progress overlay** appears on the detection card. It shows:

- How many frames have been processed so far
- The current leading species based on frames analyzed so far
- A progress bar counting toward the total frame count

Once complete, the detection card updates with the new result. A valid abstention closes the job
normally and explains that the existing identification was kept. Missing or unreadable video first
causes a visible downgrade to the best snapshot; exhaustion of both media routes or an unrecovered
runtime fault remains an explicit failure.

The owner **Jobs** view also shows automatic and maintenance video work from the backend. A queued
item remains labelled **Queued** until a worker starts it, and pending/processing automatic jobs are
reclaimed from the detections database after a container restart. Frame progress sent by a
subprocess retains the sampled frame number and exact clip offset, so saved top-frame evidence can
be traced back to the media position that produced it.

## Settings

| Setting | Location | Description |
|---------|----------|-------------|
| **Frame count** | Settings > Detection | Number of frames sampled per clip (default: 15). Higher values improve accuracy on long clips but take longer. |
| **Max concurrent jobs** | Settings > Detection | How many video analysis jobs can run in parallel (default: 1). Raise this if you have spare CPU/GPU headroom. |

## Requirements

- `record: enabled: True` must be set in your Frigate config, every analyzed camera needs an FFmpeg input with the `record` role, and `continuous.days` must be at least `1` so the recording exists when analysis runs. Alert/detection retention alone only preserves matching event segments and cannot guarantee the complete analysis window.
- The active model must be downloaded. Deep Video Analysis uses the same model as real-time detection.

See the [Recommended Frigate Config](../setup/frigate-config.md) for the exact recording settings needed.
