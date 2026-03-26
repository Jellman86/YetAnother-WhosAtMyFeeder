# Full-Visit Recording Clip Design

## Goal

Add a first-class "full visit" video variant that serves a configurable recording window around a Frigate event, with support across playback, downloads, share links, and public-access paths.

## Decision

The feature will be gated in **Settings > Connection > Frigate** behind a config-backed capability check. Users can only enable full-visit clips when YA-WAMF can confirm that the current Frigate configuration appears compatible with camera-level recording clip access.

This is intentionally stricter than a warning-only UX. The feature depends on Frigate recording configuration, not just YA-WAMF playback code, so the settings surface should prevent users from entering a misleading "enabled but impossible" state.

## Product Shape

### User-visible settings

Add the following settings under the Frigate/connection area:

- `recording_clip_enabled: bool`
- `recording_clip_before_seconds: int`
- `recording_clip_after_seconds: int`

The UI should show:

- a `Full-visit clips` toggle
- a capability status panel
- numeric controls for the before/after window, only enabled when the feature is enabled

The capability panel should report:

- whether Frigate recording clips appear supported
- why the feature is disabled when support is not detected
- which selected cameras are eligible
- the detected retention window when it can be derived

### User-visible media behavior

When enabled and available for an event, the app should treat the recording clip as a second clip variant:

- `Event clip`
- `Full visit`

This should work consistently in:

- the video player modal
- clip downloads
- owner share links
- public-access playback, subject to existing clip-download/public-access rules

The default remains `Event clip` so existing behavior does not change unless the user explicitly switches variants.

## Capability Model

### Backend capability probe

The backend should expose a single Frigate capability endpoint that evaluates whether full-visit clips are likely to work.

Suggested payload:

```json
{
  "supported": true,
  "reason": null,
  "recordings_enabled": true,
  "retention_days": 7,
  "eligible_cameras": ["front_feeder"],
  "ineligible_cameras": {
    "garage": "recordings disabled"
  }
}
```

### Capability rules

Support should be `true` only when all of these are true:

1. Frigate is reachable.
2. `api/config` can be read.
3. At least one relevant camera has recording enabled.
4. Retention/config implies recordings can exist for the requested window.

Best-effort parsing is acceptable. If Frigate config is reachable but ambiguous, YA-WAMF should return `supported=false` with a clear reason instead of guessing.

### Runtime truth still wins

Even after the settings gate passes, per-event requests may still fail:

- recordings expired
- continuous recording disabled later
- event outside retention window
- Frigate returns no recordings for that time range

So the runtime path must still fail soft with a clean `404`, and the UI must hide or disable the variant for that event.

## Backend Design

### Route model

Add a new proxy route pair:

- `HEAD /api/frigate/{event_id}/recording-clip.mp4`
- `GET /api/frigate/{event_id}/recording-clip.mp4`

These should mirror the auth, guest-rate-limit, and public-access behavior of the existing event clip endpoints.

### Frigate source

The route should:

1. Resolve `camera_name` and `detection_time` from the YA-WAMF database.
2. Build a time window from:
   - `detection_time - recording_clip_before_seconds`
   - `detection_time + recording_clip_after_seconds`
3. Proxy Frigate's camera-level clip endpoint:

```text
/api/{camera}/clip.mp4?after={unix_start}&before={unix_end}
```

### Media cache

Use a separate cache key from the event clip, for example:

- event clip: `{event_id}.mp4`
- recording clip: `{event_id}_recording.mp4`

The cache layer should avoid collisions between the two variants and preserve existing cleanup behavior.

### Error semantics

If Frigate reports no recordings for the requested time range, YA-WAMF should normalize that to a `404` with a clear API error.

Suggested normalized condition bucket:

- `recording_clip_not_available`

This should be distinct from:

- event clip missing
- event not found
- generic Frigate timeout / auth failure

## Frontend Design

### Video player

`VideoPlayer.svelte` already has clip probing, preview probing, downloads, and share-link management. It should be extended to manage a clip variant state:

- `event`
- `recording`

Behavior:

- probe event clip as today
- probe recording clip only when the feature is enabled
- show a two-state toggle when both are available
- reset playback position when switching variants
- switch the download/share URL source with the selected variant

### Share links and public access

Full-visit clips should be first-class, not modal-only.

That means the share model needs to preserve variant intent. The cleanest v1 is:

- keep the existing share link bound to the event
- allow the clip variant to be requested in the media URL

For example, the player/share UI can request the recording clip endpoint directly for the same event and share token. No separate share-link entity is needed just for clip type.

### Settings UI

The Frigate settings area should surface:

- capability status
- enable toggle
- before/after numeric inputs

The toggle should be disabled when capability is false. The status text should explain why.

## Testing

### Backend

Add targeted tests for:

- capability endpoint: supported / unsupported / ambiguous config
- recording clip proxy happy path
- recording clip `404` when Frigate says no recordings found
- auth and public-access parity with event clips
- separate cache keys for event vs recording clips

### Frontend

Add tests for:

- settings gate behavior
- video-player variant toggle visibility rules
- download/share URL switching by variant
- no-toggle fallback when recording clip probe returns `404`

## Non-goals for v1

- generating a second preview thumbnail track for the recording clip
- camera-specific custom windows
- auto-switching to full visit by default
- a second share-link object model dedicated to recording clips

If recording preview thumbnails matter later, they can be added as a follow-up once the variant model is stable.
