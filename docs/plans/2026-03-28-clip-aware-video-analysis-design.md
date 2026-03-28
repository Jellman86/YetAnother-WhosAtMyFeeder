# Clip-Aware Video Analysis Design

## Goal

Improve manual video reclassification accuracy by preferring the persisted full-visit clip when available and by using temporal frame sampling that adapts to the clip type.

## Approach

Manual video reclassification should remain event-based, but when YA-WAMF already has a persisted `{event_id}_recording.mp4` full-visit clip it should analyze that file instead of the short event clip. This keeps the longer context available without re-downloading or renaming anything.

Frame sampling should become clip-aware:
- `event` clips: center-weighted with explicit edge coverage, because the target bird is usually near the middle of the event timeline
- `recording` clips: hybrid broad coverage with mild center emphasis, because the bird may appear anywhere in the larger visit window

The scorer stays unchanged. This is only a clip-source and temporal-sampling improvement.

## Scope

- Manual video reclassification backend path
- Classifier video frame-index selection
- Targeted backend tests

## Non-Goals

- Replacing auto-video classification with full-visit analysis
- Changing score aggregation
- Renaming cached recording clip files
