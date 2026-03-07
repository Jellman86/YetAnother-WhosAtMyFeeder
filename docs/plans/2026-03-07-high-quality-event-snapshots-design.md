# High-Quality Event Snapshots Design

**Date:** 2026-03-07

**Goal**
Add an optional YA-WAMF feature that replaces the default Frigate snapshot with a higher-quality image derived asynchronously from the Frigate event clip recorded on the main stream.

**Why**
Frigate currently generates snapshots from the detect stream, which limits snapshot quality when detection is intentionally run on a lower-resolution substream. YA-WAMF can sidestep this limitation by deriving a better still image from the clip produced by the record stream.

## Summary
- Feature is backend-controlled and default `off`.
- YA-WAMF continues to fetch and cache the normal Frigate snapshot immediately.
- If enabled, YA-WAMF schedules a background job after event save to fetch the Frigate clip, extract a representative still frame, and overwrite the cached snapshot.
- If replacement fails, the original Frigate snapshot remains.
- Existing UI/API consumers continue using the same snapshot endpoints and cache paths.

## Architecture
### Core approach
1. Event ingestion remains unchanged.
2. YA-WAMF caches the Frigate snapshot as it does today.
3. A new background replacement task is scheduled only when the feature flag is enabled.
4. The replacement task waits for clip availability, extracts one still image from the clip, and atomically replaces the cached snapshot.
5. Clients continue to read the same snapshot endpoint/path regardless of source.

### Why asynchronous replacement
- Keeps event processing and notifications fast.
- Reuses the existing clip polling and retry behavior already present in the auto video classification path.
- Avoids coupling event completion to clip-finalization timing.

### Why CPU-first extraction
- Single-frame extraction from a short MP4 is likely fast enough off the main event path.
- Hardware acceleration adds device-specific complexity and failure modes.
- Optimization should follow measurement, not lead design.

## Configuration
Add a new backend setting, default `off`, under media or classification settings. Suggested shape:

```yaml
media_cache:
  high_quality_event_snapshots:
    enabled: false
    timeout_seconds: 20
```

V1 should keep the setting surface minimal. Optional frame-selection tuning can wait.

## Components
### Frigate client
Reuse existing clip access in `backend/app/services/frigate_client.py`.

### Snapshot replacement service
Create a new backend service responsible for:
- deduplicating one job per event
- waiting for clip availability using bounded retries
- extracting a representative frame from clip bytes
- atomically overwriting the cached snapshot
- logging success/failure with explicit reasons

### Media cache integration
Reuse existing snapshot cache paths in `backend/app/services/media_cache.py`.
The replacement should update the same cached snapshot file so existing consumers automatically benefit.

### Background scheduling
Schedule replacement after the event is saved and the original snapshot is cached.
This should not block event completion.

### Client/UI/API
No new API surface is required for v1 if the existing YA-WAMF snapshot-serving endpoints already prefer the local cache.
An optional later improvement could broadcast an update event so open clients refresh immediately.

## Data Flow
1. Frigate event arrives.
2. YA-WAMF processes the event normally.
3. YA-WAMF fetches and caches the default Frigate snapshot.
4. YA-WAMF saves the detection record.
5. If the feature is enabled, YA-WAMF schedules a background snapshot replacement job.
6. The background job:
   - waits for the Frigate clip to become available
   - extracts one representative still frame from the clip
   - overwrites the cached snapshot for that event
7. If the job fails, the original Frigate snapshot remains in place.

## Error Handling
### Failure policy
- If the toggle is off, do nothing.
- If clip fetch or extraction fails, keep the Frigate snapshot.
- Never delete the original snapshot unless the replacement write succeeds.

### Failure cases
- clip not found
- clip timeout
- invalid or undecodable MP4
- no valid frame extracted
- cache write failure
- duplicate job scheduling

### Guardrails
- bounded retries and total timeout
- single in-flight replacement per event
- atomic write/replace into the snapshot cache path
- structured logs with explicit reason codes

## Frame Selection
V1 should keep this simple.
Use a representative frame from the clip rather than attempting to infer the absolute “best bird frame.”
Likely candidates:
- middle-of-clip frame
- first valid frame after a short offset

The exact heuristic should be chosen for reliability and simplicity, not sophistication.

## Testing
### Unit tests
- feature flag off: no replacement scheduled
- feature flag on + clip available: replacement succeeds and cached snapshot changes
- clip timeout/unavailable: original snapshot remains
- extraction failure: original snapshot remains
- duplicate scheduling ignored
- atomic write behavior and temp-file cleanup

### Integration tests
- mocked event flow with cached Frigate snapshot and mocked clip bytes
- verify served snapshot updates after background replacement completes

### Manual verification
- enable the feature
- trigger a real bird event
- confirm normal snapshot appears quickly
- confirm later replacement from the clip-derived image
- confirm existing event detail / notification image paths benefit without API changes

### Performance validation
Measure extraction time on actual hardware before considering hwaccel.
Only add hardware acceleration if CPU extraction is materially too slow.

## Non-Goals for V1
- hardware-accelerated extraction
- dual-image storage
- smart frame ranking / best-bird selection
- new public API surface specifically for alternate snapshot sources
- changing Frigate itself
