# Recording-frame classification fallback

**Roadmap source:** [Telemetry health findings 2026-07-09](../reviews/2026-07-09-telemetry-health-findings.md),
recommendation 1 (highest-leverage pre-3.0 item).

## Problem

The single biggest real failure across the fleet is Frigate media unavailability:
`event_processor / drop_classify_snapshot_unavailable` (error, **8 of 13 installs**,
still active). It fires when a bird is tracked so briefly that Frigate never persists
a snapshot/thumbnail for the event, so every source in the classification fallback
chain is empty and the detection is **dropped outright** — silent loss of a real
sighting.

The current chain in `EventProcessor._load_snapshot_classification_fallback` is:

```
cropped snapshot (caller) → uncropped snapshot → thumbnail → cached snapshot → DROP
```

Frigate's **continuous recording** usually still covers the moment even when the
event snapshot/thumbnail is gone. Nothing in the chain consults it.

## Solution

Add a **recording-frame** source as the last step before dropping: fetch a short
recording-clip window around the event start from Frigate's continuous recordings,
extract one representative frame, and classify that.

```
… → cached snapshot → recording frame → DROP
```

### Components

1. **`frigate_client.get_recording_clip_with_error(camera, after, before, timeout)`** —
   GET `api/{camera}/start/{after}/end/{before}/clip.mp4` (the continuous-recording
   clip URL already built by `get_camera_recording_clip_url`). Returns `(bytes, None)`
   on 200; `(None, reason)` for 404 / 400-not-retained / timeout — same shape as
   `get_clip_with_error`.

2. **`EventProcessor._load_recording_frame_fallback(event_id, camera, start_time_ts)`** —
   guarded by config + presence of `camera`/`start_time_ts`. Builds a short window
   (`start_time_ts − BEFORE` … `start_time_ts + AFTER`), fetches the recording clip,
   and extracts a representative JPEG via the existing
   `high_quality_snapshot_service._extract_snapshot_from_clip` (run in a thread, since
   OpenCV is blocking). Returns `(frame_bytes, "frigate_recording_frame")` or `(None, …)`.

3. **Wiring** — `_load_snapshot_classification_fallback` gains `camera`/`start_time_ts`
   params and calls the recording-frame fallback after the cached-snapshot step; the
   `_classify_snapshot` call site passes `event.camera` / `event.start_time_ts`.

4. **Config** — `frigate.recording_frame_classification_fallback: bool = True`. On by
   default because it recovers otherwise-dropped detections; when Frigate isn't
   retaining recordings the fetch fails gracefully and the event still drops as before.

### Window

Short and centred on the event start (default 2 s before, 8 s after — one ~10 s clip),
independent of the full-visit `recording_clip_*` feature. This keeps the download small
while still capturing a briefly-present bird. The representative-frame extractor picks
the best frame within it.

## Safety

- Runs only as the **last resort** (all cheaper sources already failed), so it adds no
  cost to the common path.
- Never weakens ingest: on any failure it returns `None` and the event drops exactly as
  it does today (§1 conservative-default).
- Blocking OpenCV work is off-loaded to a thread.

## Tests (TDD)

- `frigate_client`: recording clip 200 → bytes; 404 → `clip_not_found`; 400 not-retained
  → `clip_not_retained`; timeout → `clip_timeout`.
- `event_processor`: when snapshot/thumbnail/cache all empty but a recording frame is
  available → returns the frame with source `frigate_recording_frame`; when the recording
  is unavailable → `unavailable` (drops); when the config flag is off → recording source
  is never consulted.
