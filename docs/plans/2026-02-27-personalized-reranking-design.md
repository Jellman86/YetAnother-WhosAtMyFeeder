# Personalized Per-Camera Re-Ranking Design

Date: 2026-02-27  
Repo: YA-WAMF

## 1. Goal

Improve bird ID accuracy for each user deployment by learning from manual species corrections and applying a safe, per-camera, per-model personalization layer at inference time.

This is not base-model retraining. It is an online correction layer that adjusts and re-ranks model outputs using locally collected supervision.

## 2. Approved Scope

Decisions confirmed:

- Per-camera personalization (not global).
- Explicit settings toggle to enable/disable.
- Allow re-ranking (not confidence-only).
- Require minimum `20` manual tags per camera+model before activation.
- Use time-decay so recent feedback has more weight.
- Keep calibrators separate per model ID.

## 3. Non-Goals (V1)

- No heavy retraining/fine-tuning job.
- No cloud training pipeline.
- No cross-user/shared learning.
- No changes to classifier model weights.

## 4. High-Level Architecture

V1 adds a lightweight personalization subsystem:

1. **Feedback Capture**
- Source: existing manual tag flow (`PATCH /api/events/{event_id}`).
- Persist records that include:
  - camera name
  - active model id
  - predicted species (before manual correction)
  - corrected species (user input normalized)
  - original score (optional)
  - timestamp

2. **Personalization Engine**
- Build decayed per-camera/per-model statistics from feedback.
- Compute score adjustments and perform bounded re-ranking of candidate classes.

3. **Inference Hook**
- Apply personalization after base model inference and before downstream filtering.
- If personalization is disabled, insufficient, or fails: return base predictions unchanged.

## 5. Data Model

Add a new table (name tentative: `classification_feedback`):

- `id` (pk)
- `created_at` (UTC timestamp)
- `frigate_event` (nullable, for traceability)
- `camera_name` (text, indexed)
- `model_id` (text, indexed)
- `predicted_label` (text)
- `corrected_label` (text)
- `predicted_score` (float nullable)
- `source` (text, default `manual_tag`)

Recommended indexes:

- `(camera_name, model_id, created_at)`
- `(camera_name, model_id, predicted_label, created_at)`

Rationale: efficient rolling aggregation by camera+model and predicted label.

## 6. Re-Ranking Algorithm (V1)

Given base top-K predictions for a camera/model:

1. Load feedback for that `camera + model`.
2. Apply decay weight for each feedback item:
- `w = exp(-ln(2) * age_days / half_life_days)`
3. Build:
- confusion map: `predicted -> corrected` weighted counts
- corrected prior: weighted frequency of corrected labels
4. Compute bounded adjustments for candidate labels.
5. Re-rank and renormalize scores.

Safety constraints:

- Activate only if weighted sample count >= minimum effective threshold (backed by hard floor at 20 raw manual tags).
- Max per-label score shift cap.
- Preserve monotonic sanity (no extreme jumps from near-zero to top unless supported strongly by feedback).
- If any error: fallback to original ranking and log warning.

## 7. Settings and UX

Add one explicit setting:

- `classification.personalized_rerank_enabled: bool` (default `false`)

UI:

- Add switch in Detection settings with safety-focused helper text:
  - Disabled by default.
  - Requires manual tags per camera/model before it has effect.
  - Base model remains fallback if unavailable.

Optional status readout (recommended for usability):

- Active/inactive per camera+model and current manual tag count.

## 8. Integration Points

Primary backend touchpoints:

- `backend/app/routers/events.py`
  - Capture manual tag feedback when species actually changes.
- `backend/app/services/classifier_service.py`
  - Apply personalization during classify/classify_video output assembly.
- `backend/app/services/event_processor.py`
  - Ensure camera context is passed into classification flow.
- `backend/app/config.py` and `backend/app/routers/settings.py`
  - Add toggle field and persistence.

Frontend touchpoints:

- `apps/ui/src/lib/api.ts`
  - add toggle field in settings types.
- `apps/ui/src/lib/pages/Settings.svelte`
  - load/save toggle.
- `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
  - render control and explanatory text.

## 9. Fallback and Failure Behavior

Requirements:

- CPU/ONNX/OpenVINO fallback behavior stays unchanged.
- Personalization never blocks detection processing.
- If personalization subsystem fails:
  - log warning
  - continue with base classifier output.

## 10. Testing Strategy

Backend tests:

- Feedback ingestion correctness (manual update writes expected row).
- Threshold gate: inactive below 20, active at/above 20.
- Decay behavior: newer feedback outweighs stale records.
- Re-rank bounds: score shift caps enforced.
- Failure isolation: personalization error returns base predictions.

Integration tests:

- End-to-end manual correction then later detection on same camera+model shows expected rank/score shift.
- Different cameras stay isolated.
- Different model IDs stay isolated.

Frontend tests/checks:

- Settings toggle renders, saves, reloads.
- No regressions in existing settings save flow.

## 11. Rollout Plan

1. Ship backend + toggle off by default.
2. Enable manually per instance.
3. Observe logs + behavior once each camera reaches 20 tags.
4. Iterate on adjustment weights if needed.

This yields measurable accuracy gains without model retraining risk.
