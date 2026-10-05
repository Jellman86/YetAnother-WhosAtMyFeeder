# Frigate NVR Integration

YA-WAMF is designed to be the perfect companion to [Frigate NVR](https://frigate.video/).

## Prerequisites

Before connecting YA-WAMF to Frigate you need:

- A running Frigate instance accessible from the YA-WAMF container
- An MQTT broker (Mosquitto) that both Frigate and YA-WAMF can reach — see the [MQTT Broker Setup](../setup/mqtt-broker.md) guide if you don't have one yet
- All three containers (Frigate, Mosquitto, YA-WAMF) on the same Docker network

## MQTT Configuration

YA-WAMF listens for events published by Frigate on the `frigate/events` topic. Ensure your Frigate `config.yml` has MQTT enabled with `topic_prefix: frigate`:

```yaml
mqtt:
  enabled: true
  host: mosquitto        # service name in your docker-compose
  port: 1883
  topic_prefix: frigate  # YA-WAMF expects frigate/events
  # Only needed if your broker requires authentication:
  user: YOUR_USERNAME
  password: YOUR_PASSWORD
```

> The `topic_prefix` must be `frigate` (the default). YA-WAMF subscribes to `{topic_prefix}/events`.

See the full [Recommended Frigate Config](../setup/frigate-config.md) for optimized snapshot, recording, and detection settings.

## API Connection

In YA-WAMF, set **Settings → Connection → Frigate URL** to the internal URL of your Frigate instance (e.g., `http://frigate:5000`). The backend uses the Frigate HTTP API to fetch:

- **Snapshots** — Frigate's final clean best frame plus its tracked-object coordinates
- **Video clips** — used for Deep Video Analysis and Full-visit clips
- **Config** — to auto-discover your configured camera names

**Test connection** probes the Frigate URL currently visible in the form, before you save it. When
that URL differs from the saved Frigate origin, YA-WAMF deliberately does not forward the stored
Frigate bearer token to the new host. The companion MQTT stage opens a separate, time-bounded
client with the current host, port, username, and entered-or-saved password, so testing cannot
interrupt the live event connection.

For best-available snapshots, Frigate's `end` event is important: YA-WAMF uses it to refresh any
live intermediate result from the completed track. The clean final still is the protected baseline.
Recorded frames can replace it only when the active classifier predicts a compatible identity and
improves confidence by the production margin; a failed clean-copy fetch falls back without applying
normalized box coordinates to a possibly pre-cropped regular snapshot. The completed still remains
a usable HQ source even when neither an event clip nor a cached recording clip is available.

### Initial classification image

In **Settings → Connection → Identify new detections from**, choose **Detection snapshot**
(the default) or **Recording frame**. The recording option
requests one full-resolution still through Frigate's [recording snapshot API](https://docs.frigate.video/integrations/api/get-snapshot-from-recording-camera-name-recordings-frame-time-snapshot-format-get/),
using the best snapshot's timestamp and its matching tracked-bird box. A full clean snapshot copy
establishes the native detection dimensions: completed event JPEGs can ignore crop and height
queries and may be saved cropped or resized. Frigate's current WebP and older PNG clean-copy
endpoints are supported; enable `snapshots.clean_copy` in Frigate. If no valid clean copy is
available, the original detection snapshot is kept. The lossless PNG recording response
is saved as JPEG at quality 95, avoiding Frigate's default recording JPEG compression. Pixel coordinates from
MQTT are scaled from the full detection frame; historical normalized coordinates scale directly.
The full recording frame is retained, and its crop alignment is saved with that photograph for
later reclassification. Other birds can still be localized by the configured crop model; this
setting does not change the separate high-quality photo or counted-bird pipeline.

The detect and recording streams must show the same view. A different aspect ratio, or a recording
frame smaller than the detection frame, keeps the detection snapshot. A recording frame the same
size is used: a sub stream scaled up to the detect size is a blurrier copy of the same view. This
cannot correct different lenses, digital zoom or PTZ views. Frigate needs retained recordings and
best-snapshot timestamp metadata; older events without that metadata use the snapshot.

Frigate can serve a recording frame only once that stretch of recording is written, 10 to 15
seconds after the moment (11 to 13 seconds measured on a live install). So a live detection waits:
YA-WAMF identifies it 12 seconds after Frigate's best snapshot, then retries every three seconds
until 30 seconds after it, and only then uses the detection snapshot. Each read keeps its
five-second bound. Updates for the event wait with it, and an end that arrives meanwhile is
handled once the detection exists. A camera whose recording frames did not arrive by the deadline
is identified at once for the next ten minutes, so a camera without retained recordings is not
delayed for nothing. Every fallback is logged at info with its reason. Backfill and missed past
events read once, since their recordings already exist. Existing end-of-event photo refinement
remains responsible for later photo improvements.

New detections, and their notifications, therefore arrive about 12 seconds later with **Recording
frame** than with **Detection snapshot**. Recording stills add decoding work on **Frigate**,
bandwidth and image decoding work on YA-WAMF.
They can reveal more detail but do not guarantee a more accurate model prediction. This choice
applies to new detections and backfill; reclassification prefers retained photos, including owner
selections. Saving the setting does not start a backfill or replace past photographs.
Configuration uses `frigate.classification_image_source` with `frigate_snapshot` or
`recording_snapshot`; environment configuration uses `FRIGATE__CLASSIFICATION_IMAGE_SOURCE`.

### Import retained event history

During first-run setup, **Import existing detections** can start a one-day, seven-day, or 30-day
background import. You can run a custom range later under **Settings → Data → Missed Detections**.
Custom dates use your browser timezone and include the whole final day.

YA-WAMF imports only bird events Frigate still returns with a snapshot. Reprocessing the same event
does not create a duplicate. A better image classification may update the species result, while
existing audio confirmation, weather, same-species taxonomy, the strongest Frigate score, and
sublabel evidence is preserved. Taxonomy from a replaced species is cleared rather than attached
to the new identity. If Frigate returns an error, invalid response, or incomplete pagination, the job fails visibly
instead of treating partial history as a successful empty result. The import can restore visual
detections and missing cached snapshots, but it cannot recreate BirdNET-Go audio that YA-WAMF never
stored.

## Full-visit reconciliation

Automatic full-visit reconciliation searches the last 24 hours in bounded batches. Completed
or cached visits are remembered across restarts so they cannot keep older uncached visits off
the next page. Failed visits wait 30 minutes, then one hour, then two hours between retries;
after the final failed attempt automatic retries stop. Cancelling unfinished work leaves it
retryable. Manual uploads are not sent to Frigate for full-visit processing.

Cache-budget eviction records a durable decision for both photo and full-visit work.
An admitted budget eviction finishes its file deletion and durable database decision before
shutdown cancellation returns. Favourite protection is rechecked before deletion.
If a generated variant filename also matches another saved visit's literal ID, the
whole ambiguous file group is retained under both per-species and size limits.
Every possible parent is rechecked before deletion, and active alias writers are
protected. Eviction can resume after the conflicting parent is removed. These
conservative groups can leave the cache above its configured budget.
Automatic reconciliation cannot refill that media after a restart or overwrite the
decision with a late success or failure. Admitted jobs are protected while their
fetch runs; the admission lock is released during network work. An owner can still
explicitly request the clip through the media proxy. The automatic recovery window
remains the last 24 hours.

## Update recovery

Normal updates can recover a missed start or an initial snapshot/inference failure. Once a visit
is saved, further updates do not classify it again. Missing visits retry at most once every five
seconds through updates, with one final recovery attempt after an update retry. A better later
frame can still pass the configured filters. Standard notifications send once when an update
first saves the visit; Final waits for completion and Silent sends none. Completed events keep
their final enrichment even when an older update arrives late.

## False-positive updates

Frigate false-positive updates hide untagged visits rather than deleting their history. Visits
tagged by the owner remain visible. Cached photos and owner photo choices are retained for
recovery and follow the configured cache retention and budget rules, including favourite
protection.

## Sublabel Proxy

When YA-WAMF identifies a species with high confidence, it pushes the label back to Frigate as a **sublabel**. This lets you see the species name directly in the Frigate UI and use it in Frigate's own notification rules and filters.

This can be disabled in **Settings → Detection** if you do not want YA-WAMF writing back to Frigate events.

## Camera Selection

After connecting, go to **Settings → Connection** and select which Frigate cameras YA-WAMF should monitor. Only events from selected cameras are processed.

## Live Camera Status

The camera button in each page header checks Frigate's lightweight `GET /api/stats` response every
15 seconds while the tab is visible. Frigate does not provide a separate per-camera REST health
route; its documented offline signal is a camera's `camera_fps` falling to `0`. YA-WAMF normalizes
that signal through the owner-only `GET /api/frigate/cameras/status` route and never uses preview
image loading as a health test.

- **Green** — every selected camera is producing frames.
- **Amber** — some cameras are online and some are offline or unknown.
- **Red** — every selected camera has a known result and is offline.
- **Grey** — the first check is running, status could not be retrieved, or Frigate did not report a
  usable frame rate. This avoids presenting an untested camera as failed.

Opening the viewer fetches only the selected camera's latest frame. Use the left/right buttons or
arrow keys to move through cameras; navigation wraps from the last camera back to the first. Closing
the viewer stops frame requests, and hidden browser tabs suspend both status and frame refreshes.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| No detections appearing | MQTT not connected | Check `docker compose logs yawamf \| grep -i mqtt` — you should see `Connected to MQTT topic=frigate/events` |
| Events received but no clips | Frigate recording or stream role not enabled | Add `record` to the camera's FFmpeg input roles, enable `record`, and set `record.continuous.days: 1` in Frigate config |
| Full-visit clips are unavailable or truncated | Only alert/detection event segments are retained | Set `record.continuous.days` to at least `1` for every YA-WAMF camera; the inline Settings status names any camera without full coverage |
| Detections missing for brief visits | `detect.fps` too low | Set `detect.fps` to match your sub-stream's native frame rate (10–15 FPS) so brief events are confirmed across multiple frames |
| `404` when fetching clips | Frigate URL wrong or not on same network | Confirm `FRIGATE_URL` and that all containers share a Docker network |
