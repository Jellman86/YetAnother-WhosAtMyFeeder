# AI Usage Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement AI token usage tracking, cost estimation, and a dedicated AI settings tab.

**Architecture:**
- **Database:** New `ai_usage_log` table via Alembic migration (following Excellence Standard).
- **Backend:** Update `AIService` to parse and log usage metadata; add `GET /api/stats/ai/usage` endpoint.
- **Frontend:** Relocate AI settings to a new "AI" tab in `Settings.svelte`; add usage dashboard.
- **Pricing:** Dynamic cost calculation using a JSON-configurable pricing registry.

**Tech Stack:** Python (FastAPI, Alembic, aiosqlite), Svelte 5

---

### Task 1: Documentation & Initial Assets

**Files:**
- Create: `docs/ai-pricing.json`

**Step 1: Copy reference pricing from HarborWatch**
Run: `cp /config/workspace/HarborWatch/ai-pricing.json /config/workspace/YA-WAMF/docs/ai-pricing.json`

**Step 2: Commit**
```bash
git add docs/ai-pricing.json
git commit -m "docs: add reference AI pricing registry"
```

---

### Task 2: Database Migration (AI Usage Log)

**Files:**
- Create: `backend/migrations/versions/XXXX_add_ai_usage_log_table.py`

**Step 1: Generate migration**
Run: `cd backend && export PYTHONPATH=. && venv/bin/alembic revision -m "add ai_usage_log table"`

**Step 2: Implement upgrade/downgrade with guards**
Follow `DB_MIGRATION_EXCELLENCE.md`. Include indexes on `timestamp` and `(provider, model)`.

**Step 3: Run migration**
Run: `export DB_PATH=/config/workspace/YA-WAMF/data/detections.db && cd backend && venv/bin/alembic upgrade head`

**Step 4: Verify schema**
Run: `sqlite3 /config/workspace/YA-WAMF/data/detections.db ".schema ai_usage_log"`

**Step 5: Commit**
```bash
git add backend/migrations/versions/*.py
git commit -m "db: add ai_usage_log table for tracking API consumption"
```

---

### Task 3: Backend Model & Repository Updates

**Files:**
- Modify: `backend/app/models/ai_models.py`
- Modify: `backend/app/repositories/ai_usage_repository.py` (New)
- Modify: `backend/app/config.py`

**Step 1: Add AIUsageLog model**
```python
class AIUsageLog(BaseModel):
    timestamp: datetime
    provider: str
    model: str
    feature: str
    input_tokens: int
    output_tokens: int
```

**Step 2: Create AIUsageRepository**
Implement `record_usage` and `get_summary(start_date, end_date)`.

**Step 3: Add `ai_pricing_json` to `ClassificationSettings`**
Initialize with a default empty list or basic registry.

---

### Task 4: AIService Usage Capture

**Files:**
- Modify: `backend/app/services/ai_service.py`

**Step 1: Update Gemini response parsing**
Capture `usageMetadata` (promptTokenCount, candidatesTokenCount).

**Step 2: Update OpenAI response parsing**
Capture `usage` (prompt_tokens, completion_tokens).

**Step 3: Update Claude response parsing**
Capture `usage` (input_tokens, output_tokens).

**Step 4: Log to database**
Call `AIUsageRepository.record_usage` after every successful request.

---

### Task 5: AI Stats API

**Files:**
- Create: `backend/app/routers/stats_ai.py`
- Modify: `backend/app/main.py`

**Step 1: Implement summary endpoint**
`GET /api/stats/ai/usage?span=30d`.
Calculate costs dynamically using `settings.classification.ai_pricing_json`.

**Step 2: Register router**
Include in `app/main.py`.

---

### Task 6: Frontend UI - AI Tab & Usage Dashboard

**Files:**
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Create: `apps/ui/src/lib/components/settings/AISettings.svelte`

**Step 1: Relocate settings**
Move Provider, API Key, Model, and Prompts to the new component.

**Step 2: Implement Usage Dashboard**
Add cards for Total Tokens and Estimated Cost.
Include a breakdown table.

**Step 3: Add Pricing Editor**
JSON textarea for `ai_pricing_json` with a link to `docs/ai-pricing.json`.

---

### Task 7: Localization

**Files:**
- Modify: `apps/ui/src/lib/i18n/locales/*.json` (all 9)

**Step 1: Add new keys**
`settings.tabs.ai`, `settings.ai.*`, `stats.ai.*`.

---

### Task 8: Icon Refresh

**Files:**
- Modify: `apps/ui/public/*`
- Create: `scripts/generate_icons.py`

**Step 1: Create generation script**
Use `Pillow` to crop/resize the source PNG into all required sizes.

**Step 2: Run and verify**
Execute script and check browser tab / PWA install.
