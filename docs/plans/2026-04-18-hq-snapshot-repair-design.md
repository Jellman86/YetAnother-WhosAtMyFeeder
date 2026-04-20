# HQ Snapshot Repair Design

## Goal

Make high-quality event snapshots more reliable automatically, while giving owners a concrete recovery flow when the stored snapshot is wrong.

## Problem

Today YA-WAMF picks a single derived HQ frame and optionally crops it. When that chosen frame or crop is wrong:

- the cached snapshot can miss the bird entirely
- there is no durable explanation of why that frame was chosen
- the owner-facing recovery path is limited to a single "HQ bird crop" action

That is weak for both correctness and supportability.

## Recommended Approach

Persist a bounded set of HQ snapshot candidates per detection, then use that same candidate set for:

1. automatic best-frame selection
2. owner manual repair / override
3. later debugging and support

We will not persist full-resolution candidate images in the database. We will persist compact candidate metadata plus small cached candidate thumbnails on disk.

## Architecture

### Backend candidate generation

Extend `HighQualitySnapshotService` so the clip-derived HQ flow evaluates a bounded shortlist of candidates instead of committing the first acceptable frame.

Each candidate is a combination of:

- frame offset / frame index
- source image mode:
  - `full_frame`
  - `frigate_hint_crop`
  - `model_crop`
- crop metadata when relevant
- ranking telemetry:
  - classifier label / score
  - crop score / confidence
  - ranking score
  - `selected` flag

The automatic path stores the top N candidates, selects the best one, and then replaces the cached snapshot from that chosen candidate.

### Persistence

Add a dedicated candidate table keyed by `frigate_event` plus `candidate_id`.

Store:

- event id
- frame index / timestamp offset
- source type
- clip variant
- crop box
- crop confidence
- classifier label / score
- ranking score
- selected flag
- thumbnail cache ref / snapshot provenance
- created / updated timestamps

Thumbnail bytes stay in the media cache filesystem, not SQLite.

### Manual repair flow

Add owner-only snapshot-management endpoints that let the UI:

- inspect current snapshot provenance and candidate set
- regenerate / refresh candidates
- apply a candidate as the active snapshot
- apply direct source modes without picker:
  - full frame
  - Frigate hint crop
  - model crop
  - auto best
- revert to the original Frigate snapshot

### UI

Add a `Change snapshot` control to detection details.

The modal workflow should provide:

- quick source actions
- a candidate thumbnail picker
- explicit display of current snapshot provenance
- graceful fallback messaging if regeneration fails or the clip is gone

## Ranking Policy

Use a recall-first candidate ranking:

- prioritize visible-bird candidates over visually empty crops
- prefer stronger classifier confidence
- reward crop validity and sane crop size
- prefer Frigate or model crops over full frame when they are valid
- fall back to full frame when no crop candidate clears the quality bar

Initial implementation should stay heuristic and bounded. It should not become a second full video-classification pipeline.

## Defensive Behavior

- If candidate generation fails, keep the existing snapshot untouched.
- If cached clips disappear later, keep persisted thumbnails visible in the picker even if apply/regenerate actions fail.
- If a selected candidate cannot be re-materialized, fail softly and preserve the current snapshot.
- Keep candidate generation bounded in frame count and candidate count.

## Testing

Backend:

- candidate generation and ranking
- persistence / retrieval
- fallback to full frame
- manual apply / revert
- missing or corrupt clip handling

UI:

- detection modal snapshot-management state
- provenance display
- candidate picker actions

Integration:

- wrong auto crop can be repaired manually
- revert back to full frame / original snapshot works
- reopening the modal shows the same persisted candidates
