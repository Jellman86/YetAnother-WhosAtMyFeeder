# Video Analysis Snapshot Upgrade Design

**Date:** 2026-03-07

**Goal**
Extend the high-quality event snapshot feature so manual video reclassification and batch/auto video analysis can also refresh the cached event snapshot when a valid clip is already available.

**Why**
The current high-quality snapshot feature improves images only for newly ingested detections. Manual video reclassification and queued video analysis already fetch and validate clip data, so they are a natural place to reuse that clip for snapshot replacement. This allows users to test and benefit from the feature on existing detections without waiting for a new event.

## Summary
- Keep the existing feature flag as the single gate.
- When the flag is enabled, any clip-backed analysis path that already has valid clip bytes may upgrade the cached snapshot.
- This applies even if the classification result does not change the label.
- If a requested video analysis falls back to snapshot because the clip is unavailable or invalid, do not start a second delayed retry path from that action.
- Snapshot upgrade remains best-effort and must never make reclassification or batch analysis fail.

## Architecture
### Core approach
1. Keep the existing event-ingest snapshot upgrade behavior unchanged.
2. Extend the high-quality snapshot service with a direct clip-bytes entry point, for example `replace_from_clip_bytes(event_id, clip_bytes)`.
3. Reuse that shared method from manual video reclassification after clip validation succeeds.
4. Reuse the same shared method from auto/batch video analysis after `_wait_for_clip(...)` succeeds.
5. Do not duplicate frame extraction or cache replacement logic in individual analysis paths.

### Why a shared clip-bytes entry point
- Manual and batch/auto analysis already hold validated clip bytes in memory.
- Re-fetching the clip would add cost and complexity for no value.
- A shared service keeps logging, outcome accounting, and cache-write behavior consistent.

## Data Flow
### Manual video reclassify
1. User requests `strategy=video`.
2. YA-WAMF fetches and validates clip data.
3. If the clip is valid and the high-quality snapshot feature is enabled, call the shared clip-bytes replacement method.
4. Continue the normal video classification flow.
5. If snapshot replacement fails, keep the current cached snapshot and continue.

### Batch/auto video analysis
1. Worker waits for clip availability.
2. When valid clip bytes are retrieved, and the feature is enabled, call the shared clip-bytes replacement method.
3. Continue normal classification and DB update flow.
4. If snapshot replacement fails, classification still completes.

### Snapshot fallback cases
- If manual video reclassify falls back to snapshot because the clip was unavailable or invalid, do not schedule a second delayed snapshot-upgrade attempt from that action.
- The explicit user action should either use the clip it already had or not attempt upgrade at all.

## Error Handling
- Snapshot replacement is operationally separate from classification success.
- Reclassification API success/failure must reflect classification behavior, not snapshot-upgrade behavior.
- Batch/auto worker success/failure must reflect classification behavior, not snapshot-upgrade behavior.
- Allowed outcome examples:
  - `replaced`
  - `clip_invalid`
  - `frame_extract_failed`
  - `snapshot_replace_failed`
  - `disabled`
- If a path already had valid clip bytes, use them once; do not create a hidden second retry path.

## Testing
### Backend tests
- Manual video reclassify with valid clip bytes triggers shared snapshot replacement when enabled.
- Manual video reclassify fallback-to-snapshot does not trigger replacement.
- Auto/batch analysis with valid clip bytes triggers shared snapshot replacement when enabled.
- Feature flag off makes the new calls no-op.
- Snapshot replacement failure does not fail classification.

### Manual verification
- Enable the feature.
- Re-run video analysis on an existing detection with a valid clip.
- Confirm the event image is upgraded after analysis without waiting for a new detection.
- Confirm a manual video request that falls back to snapshot does not later mutate the image from a hidden retry.

## Non-Goals
- No new setting.
- No second retry system for manual fallback paths.
- No change to label semantics or batch-analysis queue semantics.
- No UI redesign beyond benefiting from the replaced cached snapshot automatically.
