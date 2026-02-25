# BirdNET Source Name Mapping (nm) Design

**Date:** 2026-02-25  
**Status:** Approved design (hard switch)  
**Related Issue:** `#16` ("No audio detection mapped")

## Summary

Switch BirdNET-Go audio stream mapping from dynamic ID-based keys (`src` / `Source.id`) to stable source-name keys (`nm` / `Source.displayName`) and add a helper in the UI/backend to surface recently observed BirdNET source names so users can map cameras without guessing.

This is a **hard switch**:
- ID-based mapping is deprecated and no longer supported as a mapping target.
- Users must map Frigate cameras to BirdNET source names (for example `BirdCam`).

## Evidence (from live test in this environment)

Direct MQTT observation before/after a real `birdnet-go` restart showed:
- `src` / `Source.id` changed from `rtsp_46d334cf` to `rtsp_3b6c6363`
- `nm` / `Source.displayName` remained `BirdCam`

YA-WAMF currently ingests the dynamic ID into `sensor_id`, which explains the reporter's remapping breakage after restarts.

## Goals

- Make audio correlation resilient across BirdNET-Go restarts.
- Reduce user confusion in BirdNET settings (remove “Sensor ID” terminology).
- Help users map cameras correctly by exposing recently seen BirdNET source names.

## Non-Goals

- Backward compatibility for ID-based mappings
- Schema rename (`sensor_id` column can remain for now, semantics change)
- Multi-stream disambiguation beyond current single-string mapping (follow-up if needed)

## Design Decisions

### 1) Canonical mapping key is BirdNET source name

YA-WAMF will treat BirdNET source name as the canonical mapping key:
- Prefer `nm`
- Fallback to `Source.displayName`
- Final fallback for malformed payloads: existing ID-style field to avoid dropping events, but this value is not promoted in UI mapping guidance

Stored field:
- Keep using `AudioDetection.sensor_id` and `audio_detections.sensor_id` for now to avoid a migration.
- Semantics become “canonical BirdNET source key (normally source name)”.

### 2) Hard switch for settings/UI

The settings UI will:
- rename labels/help from “Sensor ID” to “BirdNET Source Name”
- remove guidance encouraging `*` for dynamic IDs
- keep manual text input
- add helper suggestions populated from recently observed BirdNET source names

### 3) Helper endpoint for discovered source names

Add a backend endpoint under `/api/audio` that returns recently observed BirdNET sources.

Proposed response fields (minimal but useful):
- `source_name` (canonical, what user should map to)
- `last_seen`
- `sample_source_id` (debugging only; current `src`/`Source.id` if available)
- `seen_count` (optional)

Data source:
- Prefer DB (`audio_detections.raw_data` + `sensor_id`) for persistence across backend restarts
- Optionally combine with in-memory buffer for very recent observations

### 4) Correlation behavior

No change to correlation algorithm shape (time window + camera mapping + species confidence).
Only the mapping key changes:
- camera maps to source name
- detections are stored/matched by source name

### 5) Existing configs after deploy

Because this is a hard switch:
- users with ID-based mappings must re-enter values as source names
- helper list reduces friction by showing names observed from live BirdNET traffic

## Risks and Mitigations

### Risk: `nm` collisions (multiple streams same name)

Mitigation:
- helper endpoint returns `sample_source_id` and last-seen metadata to aid debugging
- document limitation
- if collisions are observed, follow up with explicit mapping mode or composite key support

### Risk: Payloads missing `nm`

Mitigation:
- ingest fallback to `Source.displayName`
- final fallback to ID-style field prevents silent ingest failure
- helper endpoint should omit blank names or mark unknowns clearly

### Risk: Terminology drift (`sensor_id` field actually stores source name)

Mitigation:
- accept temporary semantic mismatch
- add follow-up tech-debt item to rename to `audio_source_key` / `source_name`

## Testing Strategy (high level)

- Unit tests for ingest extraction precedence (`nm`/`Source.displayName`)
- Unit tests for camera mapping match using source names
- Router tests for helper endpoint output
- Manual live test:
  - map camera to `BirdCam`
  - restart `birdnet-go`
  - confirm raw audio still ingests and correlation/dashboard audio confirmations continue working

## Rollout Notes

- Add release note / changelog entry: BirdNET camera mapping now uses source names, not dynamic IDs.
- Mention how to remap using helper list in Settings.

