# Personalized Per-Camera Re-Ranking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a safe, toggle-gated, per-camera and per-model personalization layer that learns from manual tags and re-ranks classifier output after at least 20 tags.

**Architecture:** Capture manual feedback into a dedicated table, compute decayed correction statistics per camera+model, and apply bounded score adjustments during inference. Keep personalization optional and fail-open so base classification behavior and provider fallback are unaffected.

**Tech Stack:** FastAPI, SQLite/Alembic, Python services (`classifier_service`, repository layer), Svelte settings UI, pytest, svelte-check.

---

### Task 1: Add Feedback Persistence Schema

**Files:**
- Create: `backend/migrations/versions/<new_revision>_add_classification_feedback_table.py`
- Modify: `backend/app/db_schema.py`
- Test: `backend/tests/test_sqlite_schema_sanity.py`

**Step 1: Write failing schema test**

```python
def test_classification_feedback_table_exists(...):
    # assert table + required columns/indexes exist
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_sqlite_schema_sanity.py -q`  
Expected: FAIL because table does not exist.

**Step 3: Add migration + db schema table**

```python
sa.Column("camera_name", sa.String(), nullable=False)
sa.Column("model_id", sa.String(), nullable=False)
...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_sqlite_schema_sanity.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/migrations/versions/... backend/app/db_schema.py backend/tests/test_sqlite_schema_sanity.py
git commit -m "feat(db): add classification feedback table for personalization"
```

### Task 2: Add Settings Toggle Plumbing

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `apps/ui/src/lib/api.ts`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`

**Step 1: Write failing backend test for settings round-trip**

```python
def test_settings_roundtrip_personalized_rerank_enabled(...):
    # POST settings true then GET settings returns true
```

**Step 2: Run failing test**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_api.py -q`  
Expected: FAIL for missing field handling.

**Step 3: Implement minimal toggle support**

```python
personalized_rerank_enabled: bool = Field(default=False, ...)
```

**Step 4: Add UI toggle in Detection settings**

```svelte
<button role="switch" ...>Personalized re-ranking</button>
```

**Step 5: Verify**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_api.py -q`  
Run: `cd apps/ui && npm run check`  
Expected: both PASS.

**Step 6: Commit**

```bash
git add backend/app/config.py backend/app/routers/settings.py apps/ui/src/lib/api.ts apps/ui/src/lib/pages/Settings.svelte apps/ui/src/lib/components/settings/DetectionSettings.svelte
git commit -m "feat(settings): add personalized rerank toggle"
```

### Task 3: Capture Manual Feedback on Species Corrections

**Files:**
- Modify: `backend/app/routers/events.py`
- Modify: `backend/app/repositories/detection_repository.py`
- Create: `backend/tests/test_event_manual_update_api.py` (extend existing tests)

**Step 1: Write failing test for feedback capture**

```python
async def test_manual_update_writes_feedback_row(...):
    # patch event species and assert feedback row inserted
```

**Step 2: Run failing test**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_event_manual_update_api.py -q`  
Expected: FAIL (no feedback row).

**Step 3: Implement repository method + router call**

```python
await repo.insert_classification_feedback(...)
```

Capture:
- old species (`predicted_label`)
- new species (`corrected_label`)
- camera name
- active model id
- original score

**Step 4: Re-run test**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_event_manual_update_api.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/routers/events.py backend/app/repositories/detection_repository.py backend/tests/test_event_manual_update_api.py
git commit -m "feat(events): capture manual correction feedback for personalization"
```

### Task 4: Implement Personalization Engine

**Files:**
- Create: `backend/app/services/personalization_service.py`
- Create: `backend/tests/test_personalization_service.py`

**Step 1: Write failing unit tests**

```python
def test_rerank_inactive_below_min_tags(): ...
def test_rerank_active_at_20_tags(): ...
def test_time_decay_prefers_recent_feedback(): ...
def test_score_shift_capped(): ...
```

**Step 2: Run failing tests**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_personalization_service.py -q`  
Expected: FAIL (service missing).

**Step 3: Implement minimal service**

```python
class PersonalizationService:
    def rerank(self, *, model_id, camera_name, results): ...
```

Rules:
- min raw tags = 20
- exponential time decay
- bounded adjustments
- fail-open fallback to original results

**Step 4: Re-run tests**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_personalization_service.py -q`  
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/personalization_service.py backend/tests/test_personalization_service.py
git commit -m "feat(classifier): add per-camera per-model personalization reranker"
```

### Task 5: Integrate Re-Ranking into Inference Path

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/services/event_processor.py`
- Modify: `backend/app/routers/events.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write failing integration-style tests**

```python
def test_classify_applies_personalization_when_enabled(...): ...
def test_classify_skips_personalization_when_disabled(...): ...
```

**Step 2: Run failing tests**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_classifier_service.py -q`  
Expected: FAIL.

**Step 3: Implement context-aware classify hooks**

```python
def classify(self, image, camera_name: str | None = None): ...
```

Apply re-rank only when:
- toggle enabled
- camera_name present
- model_id resolved

**Step 4: Update callers to pass camera context**
- `EventProcessor._classify_snapshot`
- reclassify flow in `events.py` snapshot/video entry points where camera is known.

**Step 5: Re-run tests**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_classifier_service.py -q`  
Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/services/classifier_service.py backend/app/services/event_processor.py backend/app/routers/events.py backend/tests/test_classifier_service.py
git commit -m "feat(classifier): apply personalized reranking in camera-aware inference"
```

### Task 6: Add Status Visibility (Recommended Safety UX)

**Files:**
- Modify: `backend/app/routers/classifier.py`
- Modify: `apps/ui/src/lib/api.ts`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Test: `backend/tests/test_classifier_service.py` (or router test)

**Step 1: Write failing test**
- Assert status payload includes personalization state summary.

**Step 2: Implement**
- Add fields like:
  - `personalized_rerank_enabled`
  - `personalization_active_camera_models`
  - optional per-camera counts.

**Step 3: UI rendering**
- Show concise status line in Detection diagnostics.

**Step 4: Verify**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_classifier_service.py -q`  
Run: `cd apps/ui && npm run check`

**Step 5: Commit**

```bash
git add backend/app/routers/classifier.py apps/ui/src/lib/api.ts apps/ui/src/lib/components/settings/DetectionSettings.svelte backend/tests/test_classifier_service.py
git commit -m "feat(ui): surface personalization readiness and active state"
```

### Task 7: Regression + Safety Verification

**Files:**
- Verify touched backend/frontend files

**Step 1: Run focused backend suite**

Run:

```bash
cd backend
./venv/bin/python -m pytest tests/test_personalization_service.py tests/test_event_manual_update_api.py tests/test_classifier_service.py -q
```

Expected: PASS.

**Step 2: Lint backend touched files**

Run:

```bash
cd backend
./venv/bin/python -m ruff check app/services/personalization_service.py app/services/classifier_service.py app/routers/events.py app/routers/settings.py app/config.py tests/test_personalization_service.py
```

Expected: PASS.

**Step 3: Check frontend**

Run:

```bash
cd apps/ui
npm run check
```

Expected: PASS.

### Task 8: Documentation and Rollout Notes

**Files:**
- Modify: `docs/setup/configuration.md`
- Modify: `CHANGELOG.md`

**Step 1: Update docs**
- Add personalization toggle behavior.
- Document min 20 tags, per-camera/per-model isolation, and time-decay.

**Step 2: Add changelog entry**
- Include safety/fallback behavior note.

**Step 3: Commit**

```bash
git add docs/setup/configuration.md CHANGELOG.md
git commit -m "docs: add personalized reranking configuration and behavior notes"
```
