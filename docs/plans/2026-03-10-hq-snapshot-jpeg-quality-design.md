# HQ Snapshot JPEG Quality Design

**Date:** 2026-03-10

**Goal**
Make the derived high-quality event snapshot JPEG quality configurable without changing snapshot file format, cache paths, or API surface.

## Context

High-quality event snapshots are currently encoded as JPEG with a hard-coded quality value of `95` in the background clip-frame extraction path.

The rest of the YA-WAMF snapshot pipeline is strongly JPEG-oriented:
- cached snapshots use `*.jpg`,
- snapshot-serving routes are `.jpg`,
- multiple downstream integrations assume `image/jpeg`.

Because of that, a configurable JPEG quality setting is a safer short-term optimization than switching to WebP.

## Requirements

- Add a user-configurable derived-snapshot JPEG quality setting.
- Default to `95`.
- Keep output format as JPEG.
- Bound the setting to a safe range suitable for UI slider input.
- Expose the setting through backend settings APIs and the frontend Data Settings UI.

## Approaches Considered

### 1. Configurable JPEG quality only
- Add a bounded media-cache setting and wire it into the encoder.

**Pros**
- Minimal-risk change.
- No compatibility break with cache paths, routes, or external integrations.
- Gives immediate control over file size.

**Cons**
- Less compression potential than WebP.

### 2. WebP switch
- Replace derived snapshot encoding with WebP.

**Pros**
- Better compression efficiency.

**Cons**
- Requires broader cache/route/MIME/integration changes.

### 3. Dual-format support
- Internal WebP plus JPEG compatibility outputs.

**Pros**
- Best long-term flexibility.

**Cons**
- Larger change than needed now.

## Recommended Design

Add `media_cache.high_quality_event_snapshot_jpeg_quality` to backend media-cache settings with:
- default `95`
- range `70-100`

Wire the setting into `HighQualitySnapshotService._extract_snapshot_from_clip(...)` so OpenCV encodes the derived frame with the configured JPEG quality instead of the current hard-coded `95`.

Expose the setting in:
- backend settings read/update schemas
- frontend Data Settings UI as a slider shown with the HQ event snapshots controls

## Testing Strategy

- Backend unit test for settings exposure/update if needed.
- Focused high-quality snapshot service test verifying the configured JPEG quality is passed to `cv2.imencode`.
- Frontend/UI test coverage if there is an existing settings test seam; otherwise keep UI change minimal and rely on type/check verification.
