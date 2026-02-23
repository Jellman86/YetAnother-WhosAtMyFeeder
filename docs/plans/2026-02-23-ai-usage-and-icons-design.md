# AI Usage Tracking & UI Refresh Design

**Status:** Approved
**Date:** 2026-02-23

## Problem Statement
Users need visibility into AI API consumption and costs to manage their budgets. Additionally, the application requires a branding update with a new icon set.

## Proposed Solution
1. Implement a database-backed usage logging system for cloud LLM providers (Gemini, OpenAI, Claude).
2. Create a dedicated "AI" settings tab to centralize configuration and usage metrics.
3. Replace the existing application icon set with assets generated from a new source image.

## Technical Approach

### Backend
- **Schema:** New `ai_usage_log` table (id, timestamp, provider, model, feature, input_tokens, output_tokens).
- **Service:** `AIService` updated to capture usage metadata from response payloads.
- **API:** New `GET /api/stats/ai/usage` for aggregated reporting.
- **Config:** Add `ai_pricing_json` to `ClassificationSettings` for dynamic cost calculation.

### Frontend
- **Dedicated Tab:** New "AI" tab in `Settings.svelte`.
- **Usage Dashboard:** Real-time metrics for calls, tokens, and estimated cost.
- **Localization:** Full translation keys for all 9 supported languages.
- **Branding:** Scripted icon generation via `Pillow` to replace `favicon.ico`, `apple-touch-icon.png`, and manifest icons.

### Migration Excellence
- Idempotent schema changes with existence guards.
- Best-effort data backfills if applicable.
- Final PRAGMA integrity and FK checks.

## Success Metrics
- AI usage logs appear in the database after analysis requests.
- Users can view estimated USD costs in the UI.
- New icons appear in browser tabs and PWA installs.
