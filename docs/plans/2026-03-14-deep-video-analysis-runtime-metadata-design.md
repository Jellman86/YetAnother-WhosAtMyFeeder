# Deep Video Analysis Runtime Metadata Design

**Date:** 2026-03-14

**Goal**
Surface the inference provider and model used for completed deep video analysis results in the detection details modal, while keeping the displayed metadata historically accurate for each detection.

## Problem

The event modal already contains a "Deep Video Analysis" result card, but it does not currently show enough runtime context to answer two operator questions:

- was this result produced on CPU or GPU?
- which classification model produced it?

The existing UI only partially supports provider display:

- the in-progress media-slot header can show a provider badge,
- the completed-result card can only show a provider badge if `video_classification_provider` is already present on the detection payload,
- and there is no persisted or exposed video-classification model field at all.

Showing the current classifier status as a fallback for completed detections would be misleading, because the active provider/model may have changed since the historical result was generated.

## Approved Direction

**Approach:** Persist video-classification runtime metadata with the completed detection result and render it only from detection-specific stored data.

This means:

- `video_classification_provider` remains the source of truth for CPU/GPU display.
- A new nullable `video_classification_model_id` field is stored on `detections`.
- The backend derives a friendly `video_classification_model_name` from the model registry and exposes it to the UI.
- The completed Deep Video Analysis card in the detection modal renders compact metadata chips for provider and model when those fields are present.

## Why This Direction

### Historical Accuracy

Completed detections must show what actually produced that result, not what the classifier happens to be using now.

### Safe UI Logic

The UI should not own a second copy of the model-name mapping. Friendly model names should come from backend-derived metadata tied to the stored model id.

### Backward Compatibility

Older detections will not have a stored model id. In those cases, the card should simply omit the model chip rather than guess.

## Database Design

Add a nullable `video_classification_model_id` column to `detections`.

Constraints:

- no backfill migration for legacy rows
- nullable to preserve compatibility
- idempotent Alembic migration with existence guards
- `backend/app/db_schema.py` updated to match
- `backend/tests/test_sqlite_schema_sanity.py` extended to verify the upgraded schema

This follows the repo’s current migration pattern used for runtime metadata columns.

## Backend Changes

### Persistence

When video classification results are written to a detection row, also persist the effective model id used for that inference run.

Expected write path behavior:

- resolve effective model id once during video classification
- pass it through to repository update logic
- store it in `video_classification_model_id` alongside:
  - `video_classification_label`
  - `video_classification_score`
  - `video_classification_provider`
  - `video_classification_backend`

### API Shape

Extend detection/event payloads and per-event classification-status payloads with:

- `video_classification_model_id`
- `video_classification_model_name`

`video_classification_model_name` should be derived server-side from `REMOTE_REGISTRY` when the stored id is known. If the id is unknown or legacy, return `null` for the friendly name and leave the raw id available.

## Frontend Changes

Target surface:

- the completed-result "Deep Video Analysis" card in the event detection modal

Do not change:

- the events list cards
- dashboard list cards
- unrelated in-progress status surfaces in this iteration

### Card Presentation

Render two compact chips under the video-classification label when metadata is available:

- provider chip:
  - GPU icon + `GPU` label for GPU providers such as `intel_gpu` or `cuda`
  - CPU icon + `CPU` label for CPU providers
- model chip:
  - neutral chip styling
  - friendly model name such as `ConvNeXt Large (High Accuracy)`

If only one field is present, render only that chip.

If neither field is present, preserve the current card layout.

## Data Flow

1. Video classifier completes a result.
2. Backend persists provider/backend/model id to `detections`.
3. Events API returns the stored metadata plus backend-derived friendly model name.
4. Detection modal reads the event payload and renders chips in the completed Deep Video Analysis card.

## Error Handling And Edge Cases

### Legacy Rows

Rows without `video_classification_model_id` should not trigger any fallback lookup from current classifier state.

### Unknown Model Ids

If a stored model id is not found in `REMOTE_REGISTRY`:

- keep `video_classification_model_id`
- return `video_classification_model_name = null`
- optionally render the raw id only if explicitly chosen later

For this iteration, the UI should prefer the friendly name and otherwise omit the model chip.

### Provider Normalization

Provider rendering should remain simple and deterministic:

- known GPU providers map to a GPU chip
- everything else maps to CPU unless there is a later need for a third device class

## Second- And Third-Order Effects Considered

### Avoiding Historical Drift

Using stored metadata prevents completed detections from changing appearance after a model switch or provider fallback.

### Avoiding UI/Backend Mapping Drift

Deriving friendly model names in the backend avoids duplicate model registries and inconsistent naming across surfaces.

### Migration Safety

Adding one nullable column avoids risky rewrites of existing rows and keeps upgrade behavior simple for historical databases.

## Testing Strategy

### Backend

- schema sanity test verifies the new column exists after migrations
- repository test verifies video-classification updates persist `video_classification_model_id`
- API test verifies event/classification-status responses include model id and friendly model name

### Frontend

- component-level or targeted UI test for the detection modal result card rendering:
  - provider chip only
  - provider + model chip
  - legacy row with neither chip

### Verification

- backend targeted pytest for migration/schema/repository/API coverage
- UI typecheck/build
- manual verification in Events -> open detection -> completed Deep Video Analysis card

## Out Of Scope

- showing runtime metadata in list cards or dashboards
- using current classifier status as fallback for historical completed rows
- introducing a richer device taxonomy beyond the current CPU/GPU distinction
- retroactive backfill of model ids for older detections
