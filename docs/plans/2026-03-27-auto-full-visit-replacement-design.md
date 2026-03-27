# Automatic Full-Visit Replacement Design

## Goal

Automatically generate and persist a full-visit clip for every eligible detection after the Frigate event finishes, then make YA-WAMF treat that persisted file as the canonical clip for the event.

## Decision

When `recording_clip_enabled` is enabled, YA-WAMF should automatically attempt full-visit generation for every eligible bird detection after Frigate reports the event as `end`.

This replacement happens inside YA-WAMF only. Frigate's own event clip is not modified or deleted. Instead, YA-WAMF's existing `/api/frigate/{event_id}/clip.mp4` route should prefer the persisted full-visit file when one exists, and fall back to the normal Frigate event clip otherwise.

No new user-facing setting is needed for v1. Automatic generation is part of enabling recording clips.

## Product Shape

### User-visible behavior

Once a full-visit clip has been generated successfully for an event:

- the normal clip player should open the persisted full-visit clip through the existing `/clip.mp4` route
- downloads using the normal clip route should download the persisted full-visit clip
- share links and public-access playback that already target `/clip.mp4` should receive the persisted full-visit clip automatically
- the existing `Full visit` badge can remain as a useful indicator that the replacement clip is the persisted long-form variant

Before the full-visit file exists, the app should continue to serve the normal short Frigate event clip exactly as it does today.

### Eligibility

Automatic generation should run only when all of these are true:

- `clips_enabled` is `true`
- `recording_clip_enabled` is `true`
- the MQTT payload is for a `bird`
- the event is a normal Frigate `end` event, not a false positive cleanup
- the event has a valid `frigate_event` and camera context
- a persisted full-visit clip for that event does not already exist

## Trigger Model

### Primary trigger: Frigate `end`

YA-WAMF currently processes `new` bird events and explicitly discards routine `update` and `end` chatter in `backend/app/services/event_processor.py`.

This design changes that behavior narrowly:

- keep the existing `new` path unchanged for snapshot classification, detection save, notifications, and video analysis
- add a second lightweight `end` path for eligible bird events
- the `end` path should not reclassify the snapshot, rewrite the detection, or rerun the main ingest flow
- the `end` path should only enqueue a background full-visit generation attempt

This keeps the main ingest pipeline stable while still honoring the user's expectation that the full visit is created after the event has actually finished.

### Background generation job

The automatic generation job should:

1. confirm the feature is enabled and the event is still valid
2. no-op if the persisted recording clip already exists
3. resolve the recording context using the same detection-based time window logic as the current `/recording-clip.mp4` route
4. fetch the recording clip from Frigate
5. persist the result to the media cache as `{event_id}_recording.mp4`

The existing recording-clip cache path in `backend/app/services/media_cache.py` should remain the source of truth for whether the full-visit replacement is ready.

## Replacement Model

### Canonical YA-WAMF clip route

The normal clip route in `backend/app/routers/proxy.py`:

- `GET /api/frigate/{event_id}/clip.mp4`

should change its cache preference order:

1. if a valid persisted recording clip exists, serve `{event_id}_recording.mp4`
2. otherwise, if a normal cached event clip exists, serve `{event_id}.mp4`
3. otherwise, proxy the normal Frigate event clip and optionally cache it as today

This gives YA-WAMF-wide replacement behavior with minimal frontend churn because most app surfaces already depend on `/clip.mp4`.

### Dedicated recording route remains

The existing dedicated recording route:

- `HEAD /api/frigate/{event_id}/recording-clip.mp4`
- `GET /api/frigate/{event_id}/recording-clip.mp4`
- `POST /api/frigate/{event_id}/recording-clip/fetch`

should remain for compatibility, diagnostics, and explicit manual recovery. It should continue to operate on the same persisted `{event_id}_recording.mp4` file.

## Failure Handling

### Retry semantics

Automatic full-visit generation should be best-effort and resilient to Frigate timing races.

If the automatic fetch sees temporary recording unavailability immediately after `end`, it should retry a small number of times with short delays before giving up. This mirrors the existing retry pattern YA-WAMF already uses for Frigate event availability in auto video classification.

### Missed `end` recovery

YA-WAMF should not assume it will receive every `end` event.

To prevent permanent misses caused by:

- MQTT disconnects
- service restarts
- delayed Frigate recording availability

add a bounded periodic reconciler that scans recent detections for events that:

- are old enough that their full-visit window should be complete
- do not already have a persisted recording clip
- still have recording clips enabled

The reconciler should enqueue the same background generation path used by `end` events rather than inventing a separate fetch implementation.

### Fallback behavior

If automatic full-visit generation fails after retries:

- do not surface noisy user-facing errors
- keep the event on the normal short clip path
- allow the explicit manual fetch path to remain available as a recovery affordance

Failure must never break `/clip.mp4`.

## Concurrency And Idempotency

- Use per-event locking so duplicate `end` messages and reconciler passes cannot fetch the same recording clip concurrently.
- Treat an existing valid `{event_id}_recording.mp4` file as success and no-op.
- Reuse the existing media-cache minimum-size validation so stub or empty Frigate responses are never treated as valid persisted clips.

## Frontend Impact

Frontend changes should be intentionally small for v1.

Because the canonical replacement happens in `/clip.mp4`, existing playback surfaces should benefit automatically without widespread UI rewiring.

The frontend should still keep:

- the `Full visit` badge
- the existing preferred-variant/full-visit store behavior
- the explicit `Fetch full clip` action

Those become secondary affordances rather than the primary path. A follow-up cleanup can simplify the dual-variant UX once the automatic replacement behavior has proven stable.

## Testing

### Backend

Add targeted coverage for:

- `end` event handling now triggering automatic full-visit generation
- non-`end` bird events preserving the current ingest behavior
- false positives and unrelated events not scheduling full-visit generation
- `/clip.mp4` preferring the persisted recording clip when present
- `/clip.mp4` falling back cleanly to the normal event clip when the recording clip is absent
- automatic generation retries on initial recording unavailability
- reconciler recovery for recently-finished detections missing a persisted recording clip

### Frontend

Add targeted coverage for:

- existing clip URLs still going through `/clip.mp4`
- persisted full-visit state still displaying the `Full visit` badge
- manual fetch/store behavior remaining intact after the backend replacement change

## Non-goals For v1

- modifying or replacing Frigate's own stored event clip
- adding a second settings toggle for automatic generation
- removing the manual `Fetch full clip` path
- removing the dedicated `/recording-clip.mp4` route
- redesigning the player UI around a single clip type
