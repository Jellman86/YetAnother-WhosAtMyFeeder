# AI Analysis Canonical Media Design

## Goal

Make detection AI analysis use the same media truth as the rest of the product: prefer a persisted full-visit recording clip when available, otherwise use the short event clip, and finally fall back to a snapshot.

## Current Problem

`/api/events/{event_id}/analyze` currently bypasses the canonical media contract. It fetches the raw Frigate event clip directly and samples frames from the middle 40% of that clip. If the useful bird moment is outside that narrow window, or if a better persisted full-visit clip already exists, the LLM never sees it.

## Design

### Media priority

For owner-triggered AI analysis:

1. Use a validated cached recording/full-visit clip when present.
2. Otherwise use the Frigate event clip.
3. Otherwise use the snapshot fallback.

This is explicit analysis work, not passive browsing, so the route should resolve the best existing media source. It should not invent a separate “AI only” clip-selection model.

### Frame selection

AI analysis should stay center-biased for both clip sources because the likely bird action is usually around the middle of the clip.

- `event` clip: sample around the middle using a tighter central window.
- `recording` clip: sample around the middle using a wider central window.
- `snapshot`: single-image analysis only.

### Observability

The analysis prompt metadata should include which source was used, so future debugging can distinguish:

- `recording`
- `event`
- `snapshot`

## Files

- `backend/app/routers/ai.py`
- `backend/app/services/ai_service.py`
- `backend/tests/test_ai_service.py`
- `backend/tests/test_ai_analysis_media_api.py`
- `CHANGELOG.md`
